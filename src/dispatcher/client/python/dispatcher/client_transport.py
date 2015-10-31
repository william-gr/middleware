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
from dispatcher.spawn_thread import spawn_thread
from dispatcher.spawn_thread import ClientType
from abc import ABCMeta, abstractmethod

_debug_log_file = None

if os.getenv("DISPATCHERCLIENT_TYPE") == "GEVENT":
    from ws4py.client.geventclient import WebSocketClient
    from gevent.lock import RLock
    from gevent.event import Event
    from gevent.greenlet import Greenlet
    _thread_type = ClientType.GEVENT
else:
    from ws4py.client.threadedclient import WebSocketClient
    from threading import Thread
    from threading import Event
    from threading import RLock
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
        else:
            raise ValueError('Unsupported type of connection scheme.')

class ClientTransportBase(object):

    __metaclass__ = ABCMeta

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
    def recv(self):
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

        def received_message(self, message):
            self.parent.current_message = message
            self.parent.recv()

    def __init__(self):
        self.parent = None
        self.scheme_default_port = None
        self.ws = None
        self.hostname = None
        self.username = None
        self.port = None
        self.current_message = None
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
                self.username = kwargs.get('username',None)
        else:
            if 'username' in kwargs:
                raise ValueError('Username cannot be delared in both url and arguments.')
        if self.username:
            raise ValueError('Username cannot be delared at this state for ws transport type.')

        if not self.hostname:
            self.hostname = kwargs.get('hostname',"127.0.0.1")
        else:
            if 'hostname' in kwargs:
                raise ValueError('Host name cannot be delared in both url and arguments.')

        if not self.port:
            self.port = kwargs.get('port',self.scheme_default_port)
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
        except OSError, err:
            if err.errno == errno.EPIPE:
                debug_log('Socket is closed. Closing connection')
                self.close()
 
    def recv(self):
        self.parent.recv(self.current_message)

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
                
        self.password = kwargs.get('password',None)
        self.pkey = kwargs.get('pkey',None)
        self.key_filename = kwargs.get('key_filename',None)
        if not self.pkey and not self.password and not self.key_filename:
            raise ValueError('No password, key_filename nor pkey for authentication declared.')

        debug_log('Trying to connect to {0}', self.hostname)

        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(self.hostname,
                            port = self.port,
                            username = self.username,
                            password = self.password,
                            pkey = self.pkey,
                            key_filename = self.key_filename)
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

        self.stdin, self.stdout, self.stderr = self.ssh.exec_command("python /usr/local/libexec/dispatcher/ssh_transport_catcher", bufsize = 0)
        self.channel = self.ssh.get_transport().open_session()

        recv_t = spawn_thread(target = self.recv)
        recv_t.setDaemon(True)
        recv_t.start()
        closed_t = spawn_thread(target = self.closed)
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
                self.parent.recv(data_received)

    def closed(self):
        exit_status = self.channel.recv_exit_status()
        debug_log("Transport connection has closed with exit status {0}", exit_status)
        self.terminated = True
        self.ssh.close()

    def close(self):
        debug_log("Transport connection closed by client.")
        self.terminated = True
        self.ssh.close()
    
    @property
    def address(self):
        return self.hostname
