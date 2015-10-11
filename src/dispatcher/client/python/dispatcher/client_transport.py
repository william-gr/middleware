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
        self.timeout = None
        self.hostname = None
        self.username = None
        self.password = None
        self.port = None
        self.pkey = None
        self.key_filename = None
        self.buffer_size = None
        self.terminated = None
        self.stdin = None
        self.stdout = None
        self.stderr = None
        
    def connect(self, url, sock, **kwargs):
        self.url = url
        self.sock = sock
        self.timeout = kwargs.get('timeout',30)
        self.hostname = url.hostname
        self.username = url.username
        self.port = url.port
        
        if self.username is None:
                self.username = kwargs.get('username',None)
        else:
            if 'username' in kwargs:
                raise ValueError('Username cannot be delared in both url and arguments.')
        if self.username is None:
            raise ValueError('Username is not declared.')
            
        if self.hostname is None:
                self.hostname = kwargs.get('hostname',None)
        else:
            if 'hostname' in kwargs:
                raise ValueError('Hostname cannot be delared in both url and arguments.')
        if self.hostname is None:
            raise ValueError('Hostname is not declared.')
            
        if self.port is None:
                self.port = kwargs.get('port',22)
        else:
            if 'port' in kwargs:
                raise ValueError('Port cannot be delared in both url and arguments.')
                
        self.buffer_size = kwargs.get('buffer_size',65536)
                
        self.password = kwargs.get('password',None)
        self.pkey = kwargs.get('pkey',None)
        self.key_filename = kwargs.get('key_filename',None)
        if self.pkey is None and self.password is None and self.key_filename is None:
            raise ValueError('No password, key_filename nor pkey for authentication declared.')

        i = 1
        while True:
            print("Trying to connect to %s (%i/%i)" % (self.hostname, i, self.timeout))

            try:
                self.ssh = paramiko.SSHClient()
                self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.ssh.connect(self.hostname,
                                port = self.port, 
                                username = self.username, 
                                password = self.password, 
                                pkey = self.pkey,
                                key_filename = self.key_filename)
                print("Connected to %s" % self.hostname)
                break

            except paramiko.AuthenticationException:
                raise RuntimeError("Authentication failed when connecting to %s" % self.hostname)

            except:
                print("Could not connect via SSH to %s, waiting for it to start" % self.hostname)
                i += 1
                time.sleep(2)

            if i == self.timeout:
                raise RuntimeError("Could not connect to %s. Giving up" % hostname)
        
        
        self.stdin, self.stdout, self.stderr = self.ssh.exec_command("python /usr/local/libexec/dispatcher/ssh_transport_catcher", bufsize = 0)
        self.channel = self.ssh.get_transport().open_session()
        
        from dispatcher.client import spawn_thread
        t = spawn_thread(target = self.send)
        t.setDaemon(True)
        t.start()
        t1 = spawn_thread(target = self.recv)
        t1.setDaemon(True)
        t1.start()
        t2 = spawn_thread(target = self.close)
        t2.setDaemon(True)
        t2.start()
        t3 = spawn_thread(target = self.err)
        t3.setDaemon(True)
        t3.start()

    
    def send(self):
        while not self.terminated:
            data_to_send = self.sock.recv(self.buffer_size)
            print("Data to send")
            print("%s" % data_to_send)
            self.stdin.write(data_to_send + '\n')
            self.stdin.flush()
            print("Data sent")
    
    def recv(self):
        while not self.terminated:
            data_received = self.stdout.readline()
            data_received = data_received[:-1]
            #print("Data received")
            print("%s" % data_received)
            self.sock.send(data_received)
            
    def close(self):
        exit_status = self.channel.recv_exit_status()
        print("SSH tunel has closed")
        self.sock.close()
        exit()
        
    def err(self):
        while not self.terminated:
            err = self.stderr._read(self.buffer_size)
            if err is not None:
                print("Error received %s <----" % err)
                exit(1)