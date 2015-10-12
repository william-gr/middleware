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
import socket
import os
import time
import paramiko
import socket
from abc import ABCMeta, abstractmethod

_debug_log_file = None

def debug_log(message, *args):
    global _debug_log_file

    if os.getenv('DISPATCHER_TRANSPORT_DEBUG'):
        if not _debug_log_file:
            try:
                _debug_log_file = open('/var/tmp/dispatchertransport.{0}.log'.format(os.getpid()), 'w')
            except OSError:
                pass

        debug_log(message.format(*args), file=_debug_log_file)
        _debug_log_file.flush()

class ClientTransportBuilder(object):

    def create(self, scheme):
        if 'ssh' in scheme:
            return ClientTransportSSH()
        else:
            raise ValueError('Unsupported type of connection scheme.')

class ClientTransportBase(object):

    __metaclass__ = ABCMeta

    @abstractmethod
    def connect(self, url, sock, **kwargs):
        return

    @abstractmethod
    def send(self):
        return

    @abstractmethod
    def recv(self):
        return

class ClientTransportSSH(ClientTransportBase):

    def __init__(self):
        self.ssh = None
        self.channel = None
        self.url = None
        self.sock = None
        self.hostname = None
        self.username = None
        self.password = None
        self.port = None
        self.pkey = None
        self.key_filename = None
        self.buffer_size = None
        self.terminated = False
        self.stdin = None
        self.stdout = None
        self.stderr = None

    def connect(self, url, sock, **kwargs):
        self.url = url
        self.sock = sock
        self.username = url.username
        self.port = url.port

        if url.hostname:
            self.hostname = url.hostname
        elif url.netloc:
            self.hostname = url.netloc
            if '@' in self.hostname:
                temp, self.hostname = self.hostname.split('@')
        elif url.path:
            self.hostname = url.path

        if not self.username:
                self.username = kwargs.get('username',None)
        else:
            if 'username' in kwargs:
                raise ValueError('Username cannot be delared in both url and arguments.')
        if not self.username:
            raise ValueError('Username is not declared.')

        if not self.hostname:
                self.hostname = kwargs.get('hostname',None)
        else:
            if 'hostname' in kwargs:
                raise ValueError('Hostname cannot be delared in both url and arguments.')
        if not self.hostname:
            raise ValueError('Hostname is not declared.')

        if not self.port:
                self.port = kwargs.get('port',22)
        else:
            if 'port' in kwargs:
                raise ValueError('Port cannot be delared in both url and arguments.')

        self.buffer_size = kwargs.get('buffer_size',65536)

        self.password = kwargs.get('password',None)
        self.pkey = kwargs.get('pkey',None)
        self.key_filename = kwargs.get('key_filename',None)
        if not self.pkey and not self.password and not self.key_filename:
            raise ValueError('No password, key_filename nor pkey for authentication declared.')

        debug_log('Trying to connect to %s' % self.hostname)

        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(self.hostname,
                            port = self.port,
                            username = self.username,
                            password = self.password,
                            pkey = self.pkey,
                            key_filename = self.key_filename)
            debug_log('Connected to %s' % self.hostname)

        except paramiko.AuthenticationException as err:
            debug_log('Authentication exception: %s' % err)
            raise

        except paramiko.BadAuthenticationType as err:
            ddebug_log('Bad authentication type exception: %s' % err)
            raise

        except paramiko.BadHostKeyException as err:
            debug_log('Bad host key exception: %s' % err)
            raise

        except paramiko.ChannelException as err:
            debug_log('Channel exception: %s' % err)
            raise

        except paramiko.PartialAuthentication as err:
            debug_log('Partial authentication exception: %s' % err)
            raise

        except paramiko.SSHException as err:
            debug_log('SSH exception: %s' % err)
            raise

        self.stdin, self.stdout, self.stderr = self.ssh.exec_command("python /usr/local/libexec/dispatcher/ssh_transport_catcher", bufsize = 0)
        self.channel = self.ssh.get_transport().open_session()

        from dispatcher.client import spawn_thread
        t = spawn_thread(target = self.send)
        t.setDaemon(True)
        t.start()
        t1 = spawn_thread(target = self.recv)
        t1.setDaemon(True)
        t1.start()
        t2 = spawn_thread(target = self.closed)
        t2.setDaemon(True)
        t2.start()

    def send(self):
        while self.terminated is False:
            data_to_send = self.sock.recv(self.buffer_size)
            if self.terminated is False:
                self.stdin.write(str(data_to_send) + '\n')
                self.stdin.flush()
                debug_log("Sent data: %s" % data_to_send)

    def recv(self):
        while self.terminated is False:
            data_received = self.stdout.readline()
            data_received = data_received[:-1]
            debug_log("Received data: %s" % data_received)
            if self.terminated is False:
                self.sock.send(data_received)

    def closed(self):
        exit_status = self.channel.recv_exit_status()
        debug_log("Transport connection has closed.")
        self.terminated = True
        self.ssh.close()
        self.sock.close()

    def close(self):
        debug_log("Transport connection closed by client.")
        self.terminated = True
        self.ssh.close()
        self.sock.close()
