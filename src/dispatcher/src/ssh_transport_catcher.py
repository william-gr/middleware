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

import sys
import os
import uuid
from threading import Thread
from threading import Event
from threading import RLock
from ws4py.exc import HandshakeError
from dispatcher.jsonenc import dumps
from dispatcher.spawn_thread import spawn_thread
from dispatcher.spawn_thread import ClientType
from transport_ws_handler import TransportWSHandler
from transport_catcher_base import TransportCatcherBase, debug_log

_thread_type = ClientType.THREADED

class TransportCatcherSSH(TransportCatcherBase):

    def __init__(self):
        self.ended = False
        self.transport_ws_handler = None

    def start(self):
        self.transport_ws_handler = TransportWSHandler(self)
        try:
            self.transport_ws_handler.start()
        except HandshakeError:
            debug_log('HandshakeError received. Closing')
            raise

        debug_log('Connection opened.')

        ssh_client_data = os.getenv("SSH_CLIENT")
        addr, outport, inport = ssh_client_data.split(' ', 3)
        outport = int(outport)
        client_address = [addr, outport]

        self.transport_ws_handler.send(self.pack('transport', 'setup', client_address))
        debug_log('Transport setup sent')
        t = spawn_thread(target=self.send)
        t.setDaemon(True)
        t.start()
        self.transport_ws_handler.wait_forever()

    def send(self):
        while self.ended is False:
            message = sys.stdin.readline()
            if message:
                message = message[:-1]
                try:
                    self.transport_ws_handler.send(message)
                    debug_log('Sent message: {0}', message)
                except ValueError:
                    debug_log('ValueError on sending message: {0}', message)
                    self.transport_ws_handler.close()
            else:
                self.transport_ws_handler.close()
                sys.exit(0)

    def recv(self, message):
        try:
            message = str(message) + '\n'
            sys.stdout.write(message)
            sys.stdout.flush()
            debug_log('Received message: {0}', message[:-1])
        except ValueError:
            debug_log('ValueError on receiving message: {0}', message)

    def connection_ended(self):
        debug_log('Connection closed.')
        self.ended = True
        sys.exit(0)

    def pack(self, namespace, name, args, id=None):
        return dumps({
            'namespace': namespace,
            'name': name,
            'args': args,
            'id': str(id if id is not None else uuid.uuid4())
        })

catcher = TransportCatcherSSH()
try:
    catcher.start()
except HandshakeError:
    sys.exit(1)
