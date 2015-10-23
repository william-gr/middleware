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
import gc
import traceback
import errno
import subprocess
from gevent.event import Event
from gevent.lock import Semaphore
from dispatcher.rpc import RpcService, RpcException, pass_sender, private
from auth import ShellToken
from task import TaskState
from utils import first_or_default


class ManagementService(RpcService):
    def initialize(self, context):
        self.context = context
        self.dispatcher = context.dispatcher

    def status(self):
        return {
            'started-at': self.dispatcher.started_at,
            'connected-clients': sum([len(s.connections) for s in self.dispatcher.ws_servers])
        }

    def ping(self):
        return 'pong'

    def reload_plugins(self):
        self.dispatcher.reload_plugins()

    def restart(self):
        pass

    def get_event_sources(self):
        return self.dispatcher.event_sources.keys()

    def get_connected_clients(self):
        return [
            inner
            for outter in [s.clients.keys() for s in self.dispatcher.ws_servers]
            for inner in outter
        ]

    def wait_ready(self):
        return self.dispatcher.ready.wait()

    @pass_sender
    def kick_session(self, session_id, sender):
        session = first_or_default(
            lambda s: s.session_id == session_id,
            self.dispatcher.ws_server.connections)

        if not session:
            raise RpcException(errno.ENOENT, 'Session {0} not found'.format(session_id))

        session.logout('Kicked out by {0}'.format(sender.user.name))

    def die_you_gravy_sucking_pig_dog(self):
        self.dispatcher.die()


class DebugService(RpcService):
    def initialize(self, context):
        self.dispatcher = context.dispatcher

    @private
    def dump_stacks(self):
        from greenlet import greenlet

        # If greenlet is present, let's dump each greenlet stack
        dump = []
        for ob in gc.get_objects():
            if not isinstance(ob, greenlet):
                continue
            if not ob:
                continue   # not running anymore or not started

            dump.append(''.join(traceback.format_stack(ob.gr_frame)))

        return dump

    @private
    def attach(self, host, port):
        sys.path.append('/usr/local/lib/dispatcher/pydev')

        import pydevd
        pydevd.settrace(host, port=port, stdoutToServer=True, stderrToServer=True)

    @private
    def detach(self):
        import pydevd
        pydevd.stoptrace()

    @private
    def set_tasks_debug(self, host, port, tasks=None):
        self.dispatcher.balancer.debugger = (host, port)
        self.dispatcher.balancer.debugged_tasks = tasks or ['*']

    @private
    def cancel_tasks_debug(self):
        self.dispatcher.balancer.debugger = None
        self.dispatcher.balancer.debugged_tasks = None


class EventService(RpcService):
    def initialize(self, context):
        self.__datastore = context.dispatcher.datastore
        self.__dispatcher = context.dispatcher

    def query(self, filter=None, params=None):
        filter = filter if filter else []
        params = params if params else {}
        return list(self.__datastore.query('events', *filter, **params))

    @pass_sender
    def get_my_subscriptions(self, sender):
        return list(sender.event_masks)

    @private
    def suspend(self):
        self.__dispatcher.event_delivery_lock.acquire()

    @private
    def resume(self):
        self.__dispatcher.event_delivery_lock.release()


class PluginService(RpcService):
    class RemoteServiceWrapper(RpcService):
        def __init__(self, connection, name):
            self.connection = connection
            self.service_name = name
            self.resumed = Event()

        def get_metadata(self):
            return self.connection.call_client_sync(self.service_name + '.get_metadata')

        def enumerate_methods(self):
            return list(self.connection.call_client_sync(self.service_name + '.enumerate_methods'))

        def __getattr__(self, name):
            def call_wrapped(*args):
                self.resumed.wait()
                return self.connection.call_client_sync(
                    '.'.join([self.service_name, name]),
                    *args)

            return call_wrapped

    def __client_disconnected(self, args):
        for name, svc in self.services.items():
            if args['address'] == svc.connection.ws.handler.client_address:
                self.unregister_service(name, svc.connection)

        for name, conn in self.schemas.items():
            if args['address'] == conn.ws.handler.client_address:
                self.unregister_schema(name, conn)

        for name, conn in self.event_types.items():
            if args['address'] == conn.ws.handler.client_address:
                self.unregister_event_type(name)

    def initialize(self, context):
        self.services = {}
        self.schemas = {}
        self.events = {}
        self.event_types = {}
        self.__dispatcher = context.dispatcher
        self.__dispatcher.register_event_handler(
            'server.client_disconnected',
            self.__client_disconnected)

    @pass_sender
    def register_service(self, name, sender):
        wrapper = self.RemoteServiceWrapper(sender, name)
        self.services[name] = wrapper
        self.__dispatcher.rpc.register_service_instance(name, wrapper)
        self.__dispatcher.dispatch_event('plugin.service_registered', {
            'address': sender.ws.handler.client_address,
            'service-name': name,
            'description': "Service {0} registered".format(name)
        })

        if name in self.events.keys():
            self.events[name].set()

    @pass_sender
    def unregister_service(self, name, sender):
        if name not in self.services.keys():
            raise RpcException(errno.ENOENT, 'Service not found')

        svc = self.services[name]
        if svc.connection != sender:
            raise RpcException(errno.EPERM, 'Permission denied')

        self.__dispatcher.rpc.unregister_service(name)
        self.__dispatcher.dispatch_event('plugin.service_unregistered', {
            'address': sender.ws.handler.client_address,
            'service-name': name,
            'description': "Service {0} unregistered".format(name)
        })

        del self.services[name]

    @pass_sender
    def resume_service(self, name, sender):
        if name not in self.services.keys():
            raise RpcException(errno.ENOENT, 'Service not found')

        svc = self.services[name]
        if svc.connection != sender:
            raise RpcException(errno.EPERM, 'Permission denied')

        svc.resumed.set()

    @pass_sender
    def register_schema(self, name, schema, sender):
        self.schemas[name] = sender
        self.__dispatcher.register_schema_definition(name, schema)

    @pass_sender
    def unregister_schema(self, name, sender):
        if name not in self.schemas.keys():
            raise RpcException(errno.ENOENT, 'Schema not found')

        conn = self.schemas[name]
        if conn != sender:
            raise RpcException(errno.EPERM, 'Permission denied')

        self.__dispatcher.unregister_schema_definition(name)
        del self.schemas[name]

    @pass_sender
    def register_event_type(self, service, event, sender):
        wrapper = self.services[service]
        self.event_types[event] = sender
        self.__dispatcher.register_event_type(event, wrapper)

    @pass_sender
    def unregister_event_type(self, event):
        self.__dispatcher.unregister_event_type(event)
        del self.event_types[event]

    def wait_for_service(self, name, timeout=None):
        if name in self.services.keys():
            return

        self.events[name] = Event()
        self.events[name].wait(timeout)
        del self.events[name]


class TaskService(RpcService):
    def initialize(self, context):
        self.__dispatcher = context.dispatcher
        self.__datastore = context.dispatcher.datastore
        self.__balancer = context.dispatcher.balancer

    @pass_sender
    def submit(self, name, args, sender):
        tid = self.__balancer.submit(name, args, sender)
        return tid

    def status(self, id):
        t = self.__datastore.get_by_id('tasks', id)
        task = self.__balancer.get_task(id)

        if task and task.progress:
            t['progress'] = task.progress.__getstate__()

        return t

    def wait(self, id):
        task = self.__balancer.get_task(id)
        if task:
            task.ended.wait()
            return

        raise RpcException(errno.ENOENT, 'No such task')

    def abort(self, id):
        self.__balancer.abort(id)

    def list_resources(self):
        result = []
        for res in self.__dispatcher.resource_graph.nodes:
            result.append({
                'name': res.name,
                'busy': res.busy,
            })

        return result

    def query(self, filter=None, params=None):
        def extend(t):
            task = self.__balancer.get_task(t['id'])
            if task and task.progress:
                t['progress'] = task.progress.__getstate__()

            return t

        return self.__datastore.query('tasks', *(filter or []), callback=extend, **(params or {}))

    @private
    @pass_sender
    def checkin(self, key, sender):
        task = self.__balancer.get_task_by_key(key)
        if not task:
            raise RpcException(errno.EPERM, 'Not authorized')

        return task.executor.checkin(sender)

    @private
    @pass_sender
    def put_status(self, status, sender):
        task = self.__balancer.get_task_by_sender(sender)
        if not task:
            raise RpcException(errno.EPERM, 'Not authorized')

        task.executor.put_status(status)

    @private
    @pass_sender
    def run_hook(self, hook, args, sender):
        task = self.__balancer.get_task_by_sender(sender)
        if not task:
            raise RpcException(errno.EPERM, 'Not authorized')

        return self.__dispatcher.run_hook(hook, args)

    @private
    @pass_sender
    def verify_subtask(self, name, args, sender):
        task = self.__balancer.get_task_by_sender(sender)
        if not task:
            raise RpcException(errno.EPERM, 'Not authorized')

        return self.__dispatcher.verify_subtask(task, name, args)

    @private
    @pass_sender
    def run_subtask(self, name, args, sender):
        task = self.__balancer.get_task_by_sender(sender)
        if not task:
            raise RpcException(errno.EPERM, 'Not authorized')

        ret = self.__dispatcher.balancer.run_subtask(task, name, args)
        return ret.id

    @private
    @pass_sender
    def join_subtasks(self, subtask_ids, sender):
        task = self.__balancer.get_task_by_sender(sender)
        if not task:
            raise RpcException(errno.EPERM, 'Not authorized')

        subtasks = map(self.__balancer.get_task, subtask_ids)
        self.__dispatcher.balancer.join_subtasks(*subtasks)

        for i in subtasks:
            if i.state != TaskState.FINISHED:
                raise RpcException(errno.EFAULT, 'Subtask failed: {0}'.format(i.error['message']))

        return map(lambda t: t.result, subtasks)


class LockService(RpcService):
    def initialize(self, context):
        self.locks = {}
        self.mutex = Semaphore()

    def init(self, lock):
        with self.mutex:
            if lock not in self.locks:
                self.locks[lock] = Semaphore()

    def acquire(self, lock, timo=None):
        with self.mutex:
            if lock not in self.locks:
                self.locks[lock] = Semaphore()

        return self.locks[lock].acquire(True, timo)

    def release(self, lock):
        with self.mutex:
            if lock not in self.locks:
                self.locks[lock] = Semaphore()
                return

        self.locks[lock].release()

    def is_locked(self, lock):
        with self.mutex:
            if lock not in self.locks:
                self.locks[lock] = Semaphore()
                return False

        return self.locks[lock].locked()

    def get_locks(self):
        return self.locks.keys()


class ShellService(RpcService):
    def initialize(self, context):
        self.dispatcher = context.dispatcher

    def get_shells(self):
        return self.dispatcher.configstore.get('system.shells')

    @pass_sender
    def execute(self, command, sender, input=None):
        proc = subprocess.Popen(
            ['/usr/bin/su', '-m', sender.user.name, '-c', command],
            stderr=subprocess.STDOUT,
            stdout=subprocess.PIPE,
            stdin=(subprocess.PIPE if input else None))

        out, _ = proc.communicate(input)
        proc.wait()
        return [proc.returncode, out]

    @pass_sender
    def spawn(self, shell, sender):
        return self.dispatcher.token_store.issue_token(ShellToken(user=sender.user, lifetime=60, shell=shell))
