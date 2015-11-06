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

from ws4py.client.threadedclient import WebSocketClient
from ws4py.exc import HandshakeError
from dispatcher.spawn_thread import spawn_thread
from dispatcher.spawn_thread import ClientType
from threading import Event

_thread_type = ClientType.THREADED


class TransportWSHandler(object):
    class WebSocketHandler(WebSocketClient):
        def __init__(self, url, parent):
            super(TransportWSHandler.WebSocketHandler, self).__init__(url)
            self.parent = parent

        def opened(self):
            self.parent.opened.set()

        def closed(self, code, reason=None):
            self.parent.opened.clear()
            self.parent.connection_ended()

        def received_message(self, message):
            if message:
                self.parent.recv(message)

    def __init__(self, parent):
        self.hostname = '127.0.0.1'
        self.port = 5000
        self.ws = None
        self.opened = Event()
        self.parent = parent

    def wait_forever(self):
        self.ws.run_forever()

    def start(self):
        if self.parent is None:
            raise RuntimeError('TransportWSHandler can be only created inside of a class')

        ws_url = 'ws://{0}:{1}/socket'.format(self.hostname, self.port)
        self.ws = self.WebSocketHandler(ws_url, self)
        try:
            self.ws.connect()
        except HandshakeError:
            raise
        self.opened.wait()
        t = spawn_thread(target=self.wait_forever)
        t.setDaemon(True)
        t.start()

    def send(self, message):
        try:
            self.ws.send(message)
        except ValueError:
            raise

    def connection_ended(self):
        self.parent.connection_ended()

    def recv(self, message):
        self.parent.recv(message)

    def close(self):
        self.ws.close()
