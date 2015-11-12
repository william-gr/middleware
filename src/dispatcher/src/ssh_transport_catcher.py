#+
# Copyright 2014 iXsystems, Inc.
# All rights reserved
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted providing that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
# IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
#####################################################################

from __future__ import print_function
import io
import sys
import os
import uuid
import struct
import socket
import select
from dispatcher.jsonenc import dumps
from dispatcher.spawn_thread import ClientType

_thread_type = ClientType.THREADED
_debug_log_file = None


def debug_log(message, *args):
    global _debug_log_file

    if os.getenv('DISPATCHER_TRANSPORT_CATCHER_DEBUG'):
        if not _debug_log_file:
            try:
                _debug_log_file = open('/var/tmp/dispatchercatcher.{0}.log'.format(os.getpid()), 'w')
            except OSError:
                pass

        print(message.format(*args), file=_debug_log_file)
        _debug_log_file.flush()


class TransportCatcherSSH(object):

    def __init__(self):
        self.ended = False
        self.sock_fd = None
        self.stdin_fd = None
        self.stdout_fd = None
        self.sock = None
        self.terminated = False

    def start(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect('/var/run/dispatcher.sock')
        self.sock_fd = self.sock.makefile('rwb')

        ssh_client_data = os.getenv("SSH_CLIENT")
        addr, outport, inport = ssh_client_data.split(' ', 3)
        outport = int(outport)
        client_address = [addr, outport]

        message = self.pack('transport', 'setup', client_address)

        header = struct.pack('II', 0xdeadbeef, len(message))
        message = header + message.encode('utf-8')
        sent = self.sock_fd.write(message)
        self.sock_fd.flush()
        if sent == 0:
            debug_log("Can't send transport setup message: {0} - connection closed", message)
            return
        else:
            debug_log("Sent data: {0}", message)

        debug_log('Connection opened.')

        self.stdin_fd = io.open(sys.stdin.fileno(), 'rb')
        self.stdout_fd = io.open(sys.stdout.fileno(), 'wb')

        inputs = [sys.stdin.fileno(), self.sock.fileno()]
        while self.terminated is False:
            inputready, outputready, exceptready = select.select(inputs, [], [])

            for fd in inputready:

                if fd == sys.stdin.fileno():
                    debug_log('New message: Client -> Server')
                    data = self.stdin_fd.read1(4096)
                    if data == b'':
                        self.closed()
                        break
                    sent = self.sock_fd.write(data)
                    if sent == 0:
                        self.closed()
                    self.sock_fd.flush()
                elif fd == self.sock.fileno():
                    debug_log('New message: Server -> Client')
                    data = self.sock_fd.read1(4096)
                    if data == b'':
                        self.closed()
                        break
                    sent = self.stdout_fd.write(data)
                    if sent == 0:
                        self.closed()
                    self.stdout_fd.flush()
                else:
                    debug_log('Bad fd ready received {0}', fd)
                    self.closed()
                    break

    @staticmethod
    def pack(namespace, name, args):
        return dumps({
            'namespace': namespace,
            'name': name,
            'args': args,
            'id': str(uuid.uuid4())
        })

    def closed(self):
        self.sock.close()
        self.sock_fd.close()
        self.terminated = True
        debug_log('Connection closed.')

catcher = TransportCatcherSSH()
catcher.start()
