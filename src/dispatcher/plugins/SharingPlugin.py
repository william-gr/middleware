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


import errno
from dispatcher.rpc import description, accepts, returns
from dispatcher.rpc import SchemaHelper as h
from task import Task, TaskException, VerifyException, Provider, RpcException, query


class SharesProvider(Provider):
    @query('share')
    def query(self, filter=None, params=None):
        return self.datastore.query('shares', *(filter or []), **(params or {}))

    @description("Returns list of supported sharing providers")
    @returns(h.array(str))
    def supported_types(self):
        result = []
        for p in self.dispatcher.plugins.values():
            if p.metadata and p.metadata.get('type') == 'sharing':
                result.append(p.metadata['method'])

        return result

    @description("Returns list of clients connected to particular share")
    @accepts(str)
    @returns(h.array(h.ref('share-client')))
    def get_connected_clients(self, share_name):
        share = self.datastore.get_by_id('shares', share_name)
        if not share:
            raise RpcException(errno.ENOENT, 'Share not found')

        return self.dispatcher.call_sync('shares.{0}.get_connected_clients'.format(share['type']), share_name)

    @description("Get shares dependent on provided filesystem path")
    @accepts(str)
    @returns(h.array('share'))
    def get_dependencies(self, path):
        result = []
        for i in self.datastore.query('shares', ('enabled', '=', True)):
            if i['target'][0] != '/':
                # non-filesystem share
                continue

            if i['target'].startswith(path):
                result.append(i)

        return result


@description("Creates new share")
@accepts(h.all_of(
    h.ref('share'),
    h.required('id', 'type', 'target', 'properties')
))
class CreateShareTask(Task):
    def verify(self, share):
        return ['system']

    def run(self, share):
        self.join_subtasks(self.run_subtask('share.{0}.create'.format(share['type']), share))
        self.dispatcher.dispatch_event('shares.changed', {
            'operation': 'create',
            'ids': [share['id']]
        })


@description("Updates existing share")
@accepts(str, h.ref('share'))
class UpdateShareTask(Task):
    def verify(self, name, updated_fields):
        share = self.datastore.get_by_id('shares', name)
        if not share:
            raise VerifyException(errno.ENOENT, 'Share not found')

        return ['system']

    def run(self, name, updated_fields):
        share = self.datastore.get_by_id('shares', name)
        self.join_subtasks(
            self.run_subtask('share.{0}.update'.format(share['type']), name, updated_fields)
        )
        self.dispatcher.dispatch_event('shares.changed', {
            'operation': 'update',
            'ids': [share['id']]
        })


@description("Deletes share")
@accepts(str)
class DeleteShareTask(Task):
    def verify(self, name):
        share = self.datastore.get_by_id('shares', name)
        if not share:
            raise VerifyException(errno.ENOENT, 'Share not found')

        return ['system']

    def run(self, name):
        share = self.datastore.get_by_id('shares', name)
        self.join_subtasks(self.run_subtask('share.{0}.delete'.format(share['type']), name))
        self.dispatcher.dispatch_event('shares.changed', {
            'operation': 'delete',
            'ids': [name]
        })


@description("Deletes all shares dependent on specified volume/dataset")
@accepts(str)
class DeleteDependentShares(Task):
    def verify(self, path):
        return ['system']

    def run(self, path):
        subtasks = []
        ids = []
        for i in self.dispatcher.call_sync('shares.get_dependencies', path):
            subtasks.append(self.run_subtask('share.delete', i['id']))
            ids.append(i['id'])

        self.join_subtasks(*subtasks)
        self.dispatcher.dispatch_event('shares.changed', {
            'operation': 'delete',
            'ids': ids
        })


def _init(dispatcher, plugin):
    plugin.register_schema_definition('share', {
        'type': 'object',
        'properties': {
            'id': {'type': 'string'},
            'description': {'type': 'string'},
            'enabled': {'type': 'boolean'},
            'type': {'type': 'string'},
            'target': {'type': 'string'},
            'homedirs': {'type': 'boolean'},
            'properties': {'type': 'object'}
        }
    })

    plugin.register_schema_definition('share-client', {
        'type': 'object',
        'properties': {
            'host': {'type': 'string'},
            'share': {'type': 'string'},
            'user': {'type': ['string', 'null']},
            'connected_at': {'type': ['string', 'null']},
            'extra': {
                'type': 'object'
            }
        }
    })

    dispatcher.require_collection('shares', 'string')
    plugin.register_provider('shares', SharesProvider)
    plugin.register_task_handler('share.create', CreateShareTask)
    plugin.register_task_handler('share.update', UpdateShareTask)
    plugin.register_task_handler('share.delete', DeleteShareTask)
    plugin.register_task_handler('share.delete_dependent', DeleteDependentShares)
    plugin.register_event_type('shares.changed')
