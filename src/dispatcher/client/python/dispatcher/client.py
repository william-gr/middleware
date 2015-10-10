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
import enum
import uuid
import errno
import socket
from jsonenc import dumps, loads
from dispatcher import rpc
from dispatcher.client_transport import ClientTransportBuilder
from fnutils.query import matches
from ws4py.compat import urlsplit


class ClientError(enum.Enum):
    INVALID_JSON_RESPONSE = 1
    CONNECTION_TIMEOUT = 2
    CONNECTION_CLOSED = 3
    RPC_CALL_TIMEOUT = 4
    RPC_CALL_ERROR = 5
    SPURIOUS_RPC_RESPONSE = 6
    LOGOUT = 7
    OTHER = 8


class ClientType(enum.Enum):
    THREADED = 1
    GEVENT = 2


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


_debug_log_file = None


def debug_log(message, *args):
    global _debug_log_file

    if os.getenv('DISPATCHER_CLIENT_DEBUG'):
        if not _debug_log_file:
            try:
                _debug_log_file = open('/var/tmp/dispatcherclient.{0}.log'.format(os.getpid()), 'w')
            except OSError:
                pass

        print(message.format(*args), file=_debug_log_file)
        _debug_log_file.flush()


def spawn_thread(*args, **kwargs):
    if _thread_type == ClientType.THREADED:
        return Thread(*args, **kwargs)

    if _thread_type == ClientType.GEVENT:
        run = kwargs.pop('target')
        args = kwargs.pop('args')
        return Greenlet(run, *args)


class Client(object):
    class WebSocketHandler(WebSocketClient):
        def __init__(self, url, parent):
            super(Client.WebSocketHandler, self).__init__(url)
            self.parent = parent

        def opened(self):
            debug_log('Connection opened, local address {0}', self.local_address)
            self.parent.opened.set()

        def closed(self, code, reason=None):
            debug_log('Connection closed, code {0}', code)
            self.parent.opened.clear()
            if self.parent.error_callback is not None:
                self.parent.error_callback(ClientError.CONNECTION_CLOSED)

        def received_message(self, message):
            debug_log('-> {0}', unicode(message))
            try:
                msg = loads(unicode(message))
            except ValueError, err:
                if self.parent.error_callback is not None:
                    self.parent.error_callback(ClientError.INVALID_JSON_RESPONSE, err)

                return

            self.parent.decode(msg)

    class PendingCall(object):
        def __init__(self, id, method, args=None):
            self.id = id
            self.method = method
            self.args = args
            self.result = None
            self.error = None
            self.completed = Event()
            self.callback = None

    class SubscribedEvent(object):
        def __init__(self, name, *filters):
            self.name = name
            self.refcount = 0
            self.filters = filters

        def match(self, name, args):
            if self.name != name:
                return False

            if self.filters:
                return match(args, *self.filters)

    def __init__(self):
        self.pending_calls = {}
        self.event_handlers = {}
        self.rpc = None
        self.ws = None
        self.opened = Event()
        self.event_callback = None
        self.error_callback = None
        self.rpc_callback = None
        self.receive_thread = None
        self.token = None
        self.event_distribution_lock = RLock()
        self.default_timeout = 10
        self.username = None
        self.hostname = None
        self.port = None
        self.scheme = None
        self.scheme_default_port = None
        self.transport = None
        self.parsed_url = None
        self.buffer_size = None

    def __pack(self, namespace, name, args, id=None):
        return dumps({
            'namespace': namespace,
            'name': name,
            'args': args,
            'id': str(id if id is not None else uuid.uuid4())
        })

    def __call_timeout(self, call):
        pass

    def __call(self, pending_call, call_type='call', custom_payload=None):
        if custom_payload is None:
            payload = {
                'method': pending_call.method,
                'args': pending_call.args,
            }
        else:
            payload = custom_payload

        self.__send(self.__pack(
            'rpc',
            call_type,
            payload,
            pending_call.id
        ))

    def __send_event(self, name, params):
        self.__send(self.__pack(
            'events',
            'event',
            {'name': name, 'args': params}
        ))

    def __send_error(self, id, errno, msg, extra=None):
        payload = {
            'code': errno,
            'message': msg
        }

        if extra is not None:
            payload.update(extra)

        self.__send(self.__pack('rpc', 'error', id=id, args=payload))

    def __send_response(self, id, resp):
        self.__send(self.__pack('rpc', 'response', id=id, args=resp))

    def __send(self, data):
        debug_log('<- {0}', data)
        try:
            self.ws.send(data)
        except OSError, err:
            if err.errno == errno.EPIPE:
                self.error_callback(ClientError.CONNECTION_CLOSED)

    def __process_event(self, name, args):
        self.event_distribution_lock.acquire()
        if name in self.event_handlers:
            for h in self.event_handlers[name]:
                h(args)

        if self.event_callback:
            self.event_callback(name, args)

        self.event_distribution_lock.release()

    def decode(self, msg):
        if self.client_transport is not None:
            wait_forever()
        
        if 'namespace' not in msg:
            self.error_callback(ClientError.INVALID_JSON_RESPONSE)
            return

        if 'name' not in msg:
            self.error_callback(ClientError.INVALID_JSON_RESPONSE)
            return

        if msg['namespace'] == 'events' and msg['name'] == 'event':
            args = msg['args']
            t = spawn_thread(target=self.__process_event, args=(args['name'], args['args']))
            t.start()
            return

        if msg['namespace'] == 'events' and msg['name'] == 'logout':
            self.error_callback(ClientError.LOGOUT)
            return

        if msg['namespace'] == 'rpc':
            if msg['name'] == 'call':
                if self.rpc is None:
                    self.__send_error(msg['id'], errno.EINVAL, 'Server functionality is not supported')
                    return

                if 'args' not in msg:
                    self.__send_error(msg['id'], errno.EINVAL, 'Malformed request')
                    return

                args = msg['args']
                if 'method' not in args or 'args' not in args:
                    self.__send_error(msg['id'], errno.EINVAL, 'Malformed request')
                    return

                def run_async(msg, args):
                    try:
                        result = self.rpc.dispatch_call(args['method'], args['args'], sender=self)
                    except rpc.RpcException, err:
                        self.__send_error(msg['id'], err.code, err.message)
                    else:
                        self.__send_response(msg['id'], result)

                t = spawn_thread(target=run_async, args=(msg, args))
                t.start()
                return

            if msg['name'] == 'response':
                if msg['id'] in self.pending_calls.keys():
                    call = self.pending_calls[msg['id']]
                    call.result = msg['args']
                    call.completed.set()
                    if call.callback is not None:
                        call.callback(msg['args'])

                    del self.pending_calls[str(call.id)]
                else:
                    if self.error_callback is not None:
                        self.error_callback(ClientError.SPURIOUS_RPC_RESPONSE, msg['id'])

            if msg['name'] == 'error':
                if msg['id'] in self.pending_calls.keys():
                    call = self.pending_calls[msg['id']]
                    call.result = None
                    call.error = msg['args']
                    call.completed.set()
                    del self.pending_calls[str(call.id)]
                if self.error_callback is not None:
                    self.error_callback(ClientError.RPC_CALL_ERROR)

    def parse_url(self, url):
        self.parsed_url = urlsplit(url, scheme="http")
        self.scheme = self.parsed_url.scheme
        self.hostname = self.parsed_url.hostname
        self.username = self.parsed_url.username
        self.port = self.parsed_url.port

    def connect(self, url, **kwargs):
        self.parse_url(url)
        if self.scheme is None:
            self.scheme = kwargs.get('scheme',"ws")
        else:
            if 'scheme' in kwargs:
                raise ValueError('Connection scheme cannot be delared in both url and arguments.')
        if self.scheme is "http":
            self.scheme = "ws"
        if self.scheme is "ws":
            self.scheme_default_port = 5000

        if self.username is None:
                self.username = kwargs.get('username',None)
        else:
            if 'username' in kwargs:
                raise ValueError('Username cannot be delared in both url and arguments.')
        if self.username is not None and self.scheme is "ws":
            raise ValueError('Username cannot be delared at this state for ws transport type.')

        if self.hostname is None:
            self.hostname = kwargs.get('hostname',"127.0.0.1")
        else:
            if 'hostname' in kwargs:
                raise ValueError('Host name cannot be delared in both url and arguments.')

        if self.port is None:
            self.port = kwargs.get('port',self.scheme_default_port)
        else:
            if 'port' in kwargs:
                raise ValueError('Port cannot be delared in both url and arguments.')
                
        self.buffer_size = kwargs.get('buffer_size', 65536)

        if self.scheme is "ws":
            ws_url = 'ws://{0}:{1}/socket'.format(self.hostname, self.port)
            self.ws = self.WebSocketHandler(ws_url, self)
            self.ws.connect()
        else:
            builder = ClientTransportBuilder()
            self.transport = builder.create(self.scheme)
            self.ws = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.transport.connect(self.parsed_url, self.ws, **kwargs)
            self.wait_forever()
        self.opened.wait()

    def login_user(self, username, password, timeout=None):
        call = self.PendingCall(uuid.uuid4(), 'auth')
        self.pending_calls[str(call.id)] = call
        self.__call(call, call_type='auth', custom_payload={'username': username, 'password': password})
        call.completed.wait(timeout)
        if call.error:
            raise rpc.RpcException(
                call.error['code'],
                call.error['message'],
                call.error['extra'] if 'extra' in call.error else None)

        self.token = call.result[0]

    def login_service(self, name, timeout=None):
        call = self.PendingCall(uuid.uuid4(), 'auth')
        self.pending_calls[str(call.id)] = call
        self.__call(call, call_type='auth_service', custom_payload={'name': name})
        if call.error:
            raise rpc.RpcException(
                call.error['code'],
                call.error['message'],
                call.error['extra'] if 'extra' in call.error else None)

        call.completed.wait(timeout)

    def login_token(self, token, timeout=None):
        call = self.PendingCall(uuid.uuid4(), 'auth')
        self.pending_calls[str(call.id)] = call
        self.__call(call, call_type='auth_token', custom_payload={'token': token})
        call.completed.wait(timeout)
        if call.error:
            raise rpc.RpcException(
                call.error['code'],
                call.error['message'],
                call.error['extra'] if 'extra' in call.error else None)

        self.token = call.result[0]

    def disconnect(self):
        self.ws.close()

    def enable_server(self):
        self.rpc = rpc.RpcContext()

    def on_event(self, callback):
        self.event_callback = callback

    def on_call(self, callback):
        self.rpc_callback = callback

    def on_error(self, callback):
        self.error_callback = callback

    def subscribe_events(self, *masks):
        self.__send(self.__pack('events', 'subscribe', masks))

    def unsubscribe_events(self, *masks):
        self.__send(self.__pack('events', 'unsubscribe', masks))

    def register_service(self, name, impl):
        if self.rpc is None:
            raise RuntimeError('Call enable_server() first')

        self.rpc.register_service_instance(name, impl)
        self.call_sync('plugin.register_service', name)

    def unregister_service(self, name):
        if self.rpc is None:
            raise RuntimeError('Call enable_server() first')

        self.rpc.unregister_service(name)
        self.call_sync('plugin.unregister_service', name)

    def resume_service(self, name):
        if self.rpc is None:
            raise RuntimeError('Call enable_server() first')

        self.call_sync('plugin.resume_service', name)

    def register_schema(self, name, schema):
        if self.rpc is None:
            raise RuntimeError('Call enable_server() first')

        self.call_sync('plugin.register_schema', name, schema)

    def unregister_schema(self, name):
        if self.rpc is None:
            raise RuntimeError('Call enable_server() first')

        self.call_sync('plugin.unregister_schema', name)

    def call_async(self, name, callback, *args):
        call = self.PendingCall(uuid.uuid4(), name, args)
        self.pending_calls[call.id] = call

    def call_sync(self, name, *args, **kwargs):
        timeout = kwargs.pop('timeout', self.default_timeout)
        call = self.PendingCall(uuid.uuid4(), name, args)
        self.pending_calls[str(call.id)] = call
        self.__call(call)

        if not call.completed.wait(timeout):
            if self.error_callback:
                self.error_callback(ClientError.RPC_CALL_TIMEOUT, method=call.method, args=call.args)

            raise rpc.RpcException(errno.ETIMEDOUT, 'Call timed out')

        if call.result is None and call.error is not None:
            raise rpc.RpcException(
                call.error['code'],
                call.error['message'],
                call.error['extra'] if 'extra' in call.error else None)

        return call.result

    def call_task_sync(self, name, *args):
        tid = self.call_sync('task.submit', name, args)
        self.call_sync('task.wait', tid, timeout=3600)
        return self.call_sync('task.status', tid)

    def submit_task(self, name, *args):
        return self.call_sync('task.submit', name, args)

    def emit_event(self, name, params):
        self.__send_event(name, params)
        
    def sock_recv(self):
        while recv_data is None:
            recv_data = ws.recv(self.buffer_size)
        self.decode(recv_data)

    def wait_forever(self):
        if self.client_transport is None:
            if os.getenv("DISPATCHERCLIENT_TYPE") == "GEVENT":
                import gevent
                while True:
                    gevent.sleep(60)
            else:
                self.ws.run_forever()
        else:
            t = spawn_thread(target = self.sock_recv)
            t.start()

    def register_event_handler(self, name, handler):
        if name not in self.event_handlers:
            self.event_handlers[name] = []

        self.event_handlers[name].append(handler)
        self.subscribe_events(name)
        return handler

    def unregister_event_handler(self, name, handler):
        self.event_handlers[name].remove(handler)

    def exec_and_wait_for_event(self, event, match_fn, fn, timeout=None):
        done = Event()
        self.subscribe_events(event)
        self.event_distribution_lock.acquire()

        try:
            fn()
        except:
            self.event_distribution_lock.release()
            raise

        def handler(args):
            if match_fn(args):
                done.set()

        self.register_event_handler(event, handler)
        self.event_distribution_lock.release()
        done.wait(timeout=timeout)
        self.unregister_event_handler(event, handler)

    def test_or_wait_for_event(self, event, match_fn, initial_condition_fn, timeout=None):
        done = Event()
        self.subscribe_events(event)
        self.event_distribution_lock.acquire()

        if initial_condition_fn():
            self.event_distribution_lock.release()
            return

        def handler(args):
            if match_fn(args):
                done.set()

        self.register_event_handler(event, handler)
        self.event_distribution_lock.release()
        done.wait(timeout=timeout)
        self.unregister_event_handler(event, handler)

    def get_lock(self, name):
        self.call_sync('lock.init', name)
        return rpc.ServerLockProxy(self, name)

    @property
    def connected(self):
        return self.opened.is_set()
