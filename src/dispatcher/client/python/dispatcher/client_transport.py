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
import os
import errno
import paramiko
import socket
from dispatcher.spawn_thread import spawn_thread
from dispatcher.spawn_thread import ClientType
from abc import ABCMeta, abstractmethod
from six import with_metaclass
import struct
from ws4py.messaging import BinaryMessage

_debug_log_file = None

if os.getenv("DISPATCHERCLIENT_TYPE") == "GEVENT":
    from ws4py.client.geventclient import WebSocketClient
    from gevent.event import Event
    _thread_type = ClientType.GEVENT
else:
    from ws4py.client.threadedclient import WebSocketClient
    from threading import Event
    _thread_type = ClientType.THREADED


def debug_log(message, *args):
    global _debug_log_file

    if os.getenv('DISPATCHER_TRANSPORT_DEBUG'):
        if not _debug_log_file:
            try:
                _debug_log_file = open('/var/tmp/dispatchertransport.{0}.log'.format(os.getpid()), 'w')
            except OSError:
                pass

        print(message.format(*args), file=_debug_log_file)
        _debug_log_file.flush()


class ClientTransportBuilder(object):
    def create(self, scheme):
        if 'ssh' in scheme:
            return ClientTransportSSH()
        elif 'ws' in scheme:
            return ClientTransportWS()
        elif 'unix' in scheme:
            return ClientTransportSock()
        else:
            raise ValueError('Unsupported type of connection scheme.')


class ClientTransportBase(with_metaclass(ABCMeta, object)):

    @abstractmethod
    def connect(self, url, parent, **kwargs):
        return

    @property
    @abstractmethod
    def address(self):
        return

    @abstractmethod
    def send(self, message):
        return

    @abstractmethod
    def close(self):
        return


class ClientTransportWS(ClientTransportBase):
    class WebSocketHandler(WebSocketClient):
        def __init__(self, url, parent):
            super(ClientTransportWS.WebSocketHandler, self).__init__(url)
            self.parent = parent

        def opened(self):
            debug_log('Connection opened, local address {0}', self.local_address)
            self.parent.opened.set()

        def closed(self, code, reason=None):
            debug_log('Connection closed, code {0}', code)
            self.parent.opened.clear()
            self.parent.parent.drop_pending_calls()
            if self.parent.parent.error_callback is not None:
                from dispatcher.client import ClientError
                self.parent.parent.error_callback(ClientError.CONNECTION_CLOSED)

        def received_message(self, message):
            self.parent.parent.recv(message)

    def __init__(self):
        self.parent = None
        self.scheme_default_port = None
        self.ws = None
        self.hostname = None
        self.username = None
        self.port = None
        self.opened = Event()

    def connect(self, url, parent, **kwargs):
        self.scheme_default_port = 5000
        self.parent = parent
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

        if not self.parent:
            raise RuntimeError('ClientTransportWS can be only created inside of a class')

        if not self.username:
                self.username = kwargs.get('username', None)
        else:
            if 'username' in kwargs:
                raise ValueError('Username cannot be delared in both url and arguments.')
        if self.username:
            raise ValueError('Username cannot be delared at this state for ws transport type.')

        if not self.hostname:
            self.hostname = kwargs.get('hostname', "127.0.0.1")
        else:
            if 'hostname' in kwargs:
                raise ValueError('Host name cannot be delared in both url and arguments.')

        if not self.port:
            self.port = kwargs.get('port', self.scheme_default_port)
        else:
            if 'port' in kwargs:
                raise ValueError('Port cannot be delared in both url and arguments.')

        ws_url = 'ws://{0}:{1}/socket'.format(self.hostname, self.port)
        self.ws = self.WebSocketHandler(ws_url, self)
        self.ws.connect()
        self.opened.wait()

    @property
    def address(self):
        return self.ws.local_address

    def send(self, message):
        try:
            self.ws.send(message)
        except OSError as err:
            if err.errno == errno.EPIPE:
                debug_log('Socket is closed. Closing connection')
                self.close()

    def close(self):
        self.ws.close()

    def wait_forever(self):
        if os.getenv("DISPATCHERCLIENT_TYPE") == "GEVENT":
            import gevent
            while True:
                gevent.sleep(60)
        else:
            self.ws.run_forever()

    @property
    def connected(self):
        return self.opened.is_set()


class ClientTransportSSH(ClientTransportBase):
    def __init__(self):
        self.ssh = None
        self.channel = None
        self.url = None
        self.parent = None
        self.hostname = None
        self.username = None
        self.password = None
        self.port = None
        self.pkey = None
        self.key_filename = None
        self.terminated = False
        self.stdin = None
        self.stdout = None
        self.stderr = None
        self.host_key_file = None
        self.host_key = None
        self.look_for_keys = True

    def connect(self, url, parent, **kwargs):
        self.url = url
        self.parent = parent
        self.username = url.username
        self.port = url.port

        if not self.parent:
            raise RuntimeError('ClientTransportSSH can be only created inside of a class')

        if url.hostname:
            self.hostname = url.hostname
        elif url.netloc:
            self.hostname = url.netloc
            if '@' in self.hostname:
                temp, self.hostname = self.hostname.split('@')
        elif url.path:
            self.hostname = url.path

        if not self.username:
                self.username = kwargs.get('username', None)
        else:
            if 'username' in kwargs:
                raise ValueError('Username cannot be delared in both url and arguments.')
        if not self.username:
            raise ValueError('Username is not declared.')

        if not self.hostname:
                self.hostname = kwargs.get('hostname', None)
        else:
            if 'hostname' in kwargs:
                raise ValueError('Hostname cannot be delared in both url and arguments.')
        if not self.hostname:
            raise ValueError('Hostname is not declared.')

        if not self.port:
                self.port = kwargs.get('port', 22)
        else:
            if 'port' in kwargs:
                raise ValueError('Port cannot be delared in both url and arguments.')

        self.password = kwargs.get('password', None)
        self.pkey = kwargs.get('pkey', None)
        self.key_filename = kwargs.get('key_filename', None)
        if not self.pkey and not self.password and not self.key_filename:
            raise ValueError('No password, key_filename nor pkey for authentication declared.')

        self.host_key = kwargs.get('host_key', None)
        self.host_key_file = kwargs.get('host_key_file', None)
        if self.host_key and self.host_key_file:
            raise ValueError('Both host_key and host_key_file parameters cannot be specified simultaneously.')

        debug_log('Trying to connect to {0}', self.hostname)

        try:
            self.ssh = paramiko.SSHClient()
            if self.host_key_file:
                try:
                    self.ssh.load_host_keys(self.host_key_file)
                    self.look_for_keys = False
                except IOError:
                    debug_log('Cannot read host key file: {0}. SSH transport is closing.', self.host_key_file)
                    self.close()
                    raise
            elif self.host_key:
                key_hostname, key_type, key = self.host_key.split(' ')
                if not key_hostname:
                    raise ValueError('Hostname field of host key is not specified.')
                if not key:
                    raise ValueError('Key field of host key is not specified.')
                if key_type is not "ssh-rsa" or key_type is not "ssh-dss":
                    raise ValueError('Key_type field of host key must be either ssh-rsa or ssh-dss.')
                self.ssh._host_keys.add(key_hostname, key_type, key)
            else:
                self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self.ssh.connect(
                self.hostname,
                port=self.port,
                username=self.username,
                password=self.password,
                pkey=self.pkey,
                look_for_keys=self.look_for_keys,
                key_filename=self.key_filename
            )

            debug_log('Connected to {0}', self.hostname)

        except paramiko.AuthenticationException as err:
            debug_log('Authentication exception: {0}', err)
            raise

        except paramiko.BadHostKeyException as err:
            debug_log('Bad host key exception: {0}', err)
            raise

        except paramiko.SSHException as err:
            debug_log('SSH exception: {0}', err)
            raise

        except socket.error as err:
            debug_log('Socket exception: {0}', err)
            raise

        self.stdin, self.stdout, self.stderr = self.ssh.exec_command(
            "sh /usr/local/libexec/dispatcher/ssh_transport_catcher",
            bufsize=0
        )

        self.channel = self.ssh.get_transport().open_session()

        recv_t = spawn_thread(target=self.recv)
        recv_t.setDaemon(True)
        recv_t.start()
        closed_t = spawn_thread(target=self.closed)
        closed_t.setDaemon(True)
        closed_t.start()

    def send(self, message):
        if self.terminated is False:
            self.stdin.write(str(message) + '\n')
            self.stdin.flush()
            debug_log("Sent data: {0}", message)

    def recv(self):
        while self.terminated is False:
            data_received = self.stdout.readline()
            if self.terminated is False:
                debug_log("Received data: {0}", data_received)
                self.parent.recv(BinaryMessage(data_received.encode('utf8')))

    def closed(self):
        exit_status = self.channel.recv_exit_status()
        debug_log("Transport connection has closed with exit status {0}", exit_status)
        self.terminated = True
        self.ssh.close()
        self.parent.drop_pending_calls()
        if self.parent.error_callback is not None:
            from dispatcher.client import ClientError
            self.parent.error_callback(ClientError.CONNECTION_CLOSED)

    def close(self):
        debug_log("Transport connection closed by client.")
        self.terminated = True
        self.ssh.close()

    @property
    def address(self):
        return self.hostname

    @property
    def host_keys(self):
        return self.ssh.get_host_keys()


class ClientTransportSock(ClientTransportBase):

    def __init__(self):
        self.path = '/var/run/dispatcher.sock'
        self.sock = None
        self.parent = None
        self.terminated = False
        self.fd = None

    def connect(self, url, parent, **kwargs):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.fd = self.sock.makefile('rwb')
        self.parent = parent
        if not self.parent:
            raise RuntimeError('ClientTransportSock can be only created inside of a class')

        if url.path:
            self.path = url.path

        try:
            self.sock.connect(self.path)

            debug_log('Connected to {0}', self.path)

            recv_t = spawn_thread(target=self.recv)
            recv_t.setDaemon(True)
            recv_t.start()
        except socket.error as err:
            self.terminated = True
            debug_log('Socket connection exception: {0}', err)
            raise

    @property
    def address(self):
        return self.path

    def send(self, message):
        if self.terminated is False:
            header = struct.pack('II', 0xdeadbeef, len(message))
            message = header + message.encode('utf-8')
            sent = self.fd.write(message)
            if sent == 0:
                self.closed()
            else:
                debug_log("Sent data: {0}", message)

    def recv(self):
        while self.terminated is False:
            header = self.fd.read(8)
            if header == b'':
                self.closed()

            magic, length = struct.unpack('II', header)
            if magic != 0xdeadbeef:
                debug_log('Message with wrong magic dropped')
                continue

            message = self.fd.read(length)
            if message == b'':
                self.closed()
            else:
                debug_log("Received data: {0}", message)
                self.parent.recv(message)

    def close(self):
        debug_log("Transport connection closed by client.")
        self.terminated = True
        self.sock.close()
        self.fd.close()

    def closed(self):
        debug_log("Transport socket connection terminated abnormally.")
        self.terminated = True
        self.parent.drop_pending_calls()
        self.sock.close()
        self.fd.close()
        if self.parent.error_callback is not None:
            from dispatcher.client import ClientError
            self.parent.error_callback(ClientError.CONNECTION_CLOSED)
