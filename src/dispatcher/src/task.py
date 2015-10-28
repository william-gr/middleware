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

import errno
import logging
from dispatcher.rpc import RpcService, RpcException
from datastore.config import ConfigStore
import collections


class TaskState(object):
    CREATED = 'CREATED'
    WAITING = 'WAITING'
    EXECUTING = 'EXECUTING'
    FINISHED = 'FINISHED'
    FAILED = 'FAILED'
    ABORTED = 'ABORTED'


class Task(object):
    SUCCESS = (0, "Success")

    def __init__(self, dispatcher, datastore):
        self.dispatcher = dispatcher
        self.datastore = datastore
        self.configstore = ConfigStore(datastore)
        self.logger = logging.getLogger(self.__class__.__name__)

    @classmethod
    def _get_metadata(cls):
        return {
            'description': cls.description if hasattr(cls, 'description') else None,
            'schema': cls.params_schema if hasattr(cls, 'params_schema') else None,
            'abortable': True if (hasattr(cls, 'abort') and isinstance(cls.abort, collections.Callable)) else False
        }

    def get_status(self):
        return TaskStatus(50, 'Executing...')

    def verify_subtask(self, classname, *args):
        return self.dispatcher.verify_subtask(self, classname, args)

    def run_subtask(self, classname, *args):
        return self.dispatcher.run_subtask(self, classname, args)

    def join_subtasks(self, *tasks):
        return self.dispatcher.join_subtasks(*tasks)

    def chain(self, task, *args):
        self.dispatcher.balancer.submit(task, *args)


class ProgressTask(Task):
    def __init__(self, dispatcher, datastore):
        super(ProgressTask, self).__init__(dispatcher, datastore)
        self.progress = 0
        self.message = 'Executing...'

    def get_status(self):
        return TaskStatus(self.progress, self.message)

    def set_progress(self, percentage, message=None):
        self.progress = percentage
        if message:
            self.message = message


class TaskException(RpcException):
    pass


class TaskAbortException(TaskException):
    pass


class ValidationException(TaskException):
    def __init__(self, errors):
        extra = {'fields': {}}
        for name, code, message in errors:
            if name not in extra['fields']:
                extra['fields'][name] = []
            extra['fields'][name].append((code, message))
        super(ValidationException, self).__init__(errno.EBADMSG, 'Validation Exception Errors', extra=extra)


class VerifyException(TaskException):
    pass


class TaskStatus(object):
    def __init__(self, percentage, message=None, extra=None):
        self.percentage = percentage
        self.message = message
        self.extra = extra

    def __getstate__(self):
        return {
            'percentage': self.percentage,
            'message': self.message,
            'extra': self.extra
        }

    def __setstate__(self, obj):
        self.percentage = obj['percentage']
        self.message = obj['message']
        self.extra = obj['extra']


class Provider(RpcService):
    def initialize(self, context):
        self.dispatcher = context.dispatcher
        self.datastore = self.dispatcher.datastore
        self.configstore = self.dispatcher.configstore


def query(result_type):
    def wrapped(fn):
        fn.params_schema = [
            {
                'title': 'filter',
                'type': 'array',
                'items': {
                    'type': 'array',
                    'minItems': 2,
                    'maxItems': 4
                }
            },
            {
                'title': 'options',
                'type': 'object',
                'properties': {
                    'sort-field': {'type': 'string'},
                    'sort-order': {'type': 'string', 'enum': ['asc', 'desc']},
                    'limit': {'type': 'integer'},
                    'offset': {'type': 'integer'},
                    'single': {'type': 'boolean'},
                    'count': {'type': 'boolean'}
                }
            }
        ]

        fn.result_schema = {
            'anyOf': [
                {
                    'type': 'array',
                    'items': {'$ref': result_type}
                },
                {
                    'type': 'integer'
                },
                {
                    '$ref': result_type
                }
            ]
        }

        return fn

    return wrapped
