#+
# Copyright 2015 iXsystems, Inc.
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


import os
import sys
import errno
import imp
import setproctitle
import socket
import traceback
import logging
import queue
from threading import Event
from dispatcher.client import Client, ClientType
from dispatcher.rpc import RpcService, RpcException
from datastore import get_default_datastore
from datastore.config import ConfigStore
from task import TaskException


def serialize_error(err):
    ret = {
        'type': type(err).__name__,
        'message': str(err),
        'stacktrace': traceback.format_exc()
    }

    if isinstance(err, RpcException):
        ret['code'] = err.code
        ret['message'] = err.message
        if err.extra:
            ret['extra'] = err.extra
    else:
        ret['code'] = errno.EFAULT

    return ret


class DispatcherWrapper(object):
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    def __run_hook(self, name, args):
        return self.dispatcher.call_sync('task.run_hook', name, args, timeout=300)

    def __verify_subtask(self, task, name, args):
        return self.dispatcher.call_sync('task.verify_subtask', name, args)

    def __run_subtask(self, task, name, args):
        return self.dispatcher.call_sync('task.run_subtask', name, args, timeout=60)

    def __join_subtasks(self, *tasks):
        return self.dispatcher.call_sync('task.join_subtasks', tasks, timeout=None)

    def __getattr__(self, item):
        if item == 'dispatch_event':
            return self.dispatcher.emit_event

        if item == 'run_hook':
            return self.__run_hook

        if item == 'verify_subtask':
            return self.__verify_subtask

        if item == 'run_subtask':
            return self.__run_subtask

        if item == 'join_subtasks':
            return self.__join_subtasks

        return getattr(self.dispatcher, item)


class TaskProxyService(RpcService):
    def __init__(self, context):
        self.context = context

    def get_status(self):
        self.context.running.wait()
        return self.context.instance.get_status()

    def abort(self):
        if not hasattr(self.context.instance, 'abort'):
            raise RpcException(errno.ENOTSUP, 'Abort not supported')

        try:
            self.context.instance.abort()
        except BaseException as err:
            raise RpcException(errno.EFAULT, 'Cannot abort: {0}'.format(str(err)))

    def run(self, task):
        self.context.task.put(task)


class Context(object):
    def __init__(self):
        self.service = TaskProxyService(self)
        self.task = queue.Queue(1)
        self.datastore = None
        self.configstore = None
        self.conn = None
        self.instance = None
        self.running = Event()

    def put_status(self, state, result=None, exception=None):
        obj = {
            'status': state,
            'result': None
        }

        if result:
            obj['result'] = result

        if exception:
            obj['error'] = serialize_error(exception)

        self.conn.call_sync('task.put_status', obj)

    def main(self):
        if len(sys.argv) != 2:
            print("Invalid number of arguments", file=sys.stderr)
            sys.exit(errno.EINVAL)

        key = sys.argv[1]
        logging.basicConfig(level=logging.DEBUG)

        self.datastore = get_default_datastore()
        self.configstore = ConfigStore(self.datastore)
        self.conn = Client()
        self.conn.connect('unix:')
        self.conn.login_service('task.{0}'.format(os.getpid()))
        self.conn.enable_server()
        self.conn.rpc.register_service_instance('taskproxy', self.service)
        self.conn.call_sync('task.checkin', key)
        setproctitle.setproctitle('task executor (idle)')

        while True:
            try:
                task = self.task.get()
                setproctitle.setproctitle('task executor (tid {0})'.format(task['id']))

                if task['debugger']:
                    sys.path.append('/usr/local/lib/dispatcher/pydev')

                    import pydevd
                    host, port = task['debugger']
                    pydevd.settrace(host, port=port, stdoutToServer=True, stderrToServer=True)

                module = imp.load_source('plugin', task['filename'])
                setproctitle.setproctitle('task executor (tid {0})'.format(task['id']))

                try:
                    self.instance = getattr(module, task['class'])(DispatcherWrapper(self.conn), self.datastore)
                    self.instance.configstore = self.configstore
                    self.running.set()
                    result = self.instance.run(*task['args'])
                except BaseException as err:
                    print("Task exception: {0}".format(str(err)), file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    self.put_status('FAILED', exception=err)
                else:
                    self.put_status('FINISHED', result=result)

            except RpcException as err:
                print("RPC failed: {0}".format(str(err)), file=sys.stderr)
                sys.exit(errno.EBADMSG)
            except socket.error as err:
                print("Cannot connect to dispatcher: {0}".format(str(err)), file=sys.stderr)
                sys.exit(errno.ETIMEDOUT)

            if task['debugger']:
                import pydevd
                pydevd.stoptrace()

            setproctitle.setproctitle('task executor (idle)')


if __name__ == '__main__':
    ctx = Context()
    ctx.main()
