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
import logging
import re

from datastore import DatastoreException
from datastore.config import ConfigNode
from dispatcher.rpc import RpcException, SchemaHelper as h, description, accepts, returns
from task import Task, Provider, TaskException, ValidationException, VerifyException, query

logger = logging.getLogger('RsyncdPlugin')


@description('Provides info about Rsyncd service configuration')
class RsyncdProvider(Provider):
    @accepts()
    @returns(h.ref('service-rsyncd'))
    def get_config(self):
        return ConfigNode('service.rsyncd', self.configstore)


@description("Provides access to rsyncd modules database")
class RsyncdModuleProvider(Provider):
    @description("Lists rsyncd modules present in the system")
    @query('rsyncd-module')
    def query(self, filter=None, params=None):
        return self.datastore.query('rsyncd-module', *(filter or []), **(params or {}))


@description('Configure Rsyncd service')
@accepts(h.ref('service-rsyncd'))
class RsyncdConfigureTask(Task):
    def describe(self, share):
        return 'Configuring Rsyncd service'

    def verify(self, rsyncd):
        errors = []

        node = ConfigNode('service.rsyncd', self.configstore).__getstate__()
        node.update(rsyncd)

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, rsyncd):
        try:
            node = ConfigNode('service.rsyncd', self.configstore)
            node.update(rsyncd)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'services')
            self.dispatcher.call_sync('services.restart', 'rsyncd')
            self.dispatcher.dispatch_event('service.rsyncd.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException, e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure Rsyncd: {0}'.format(str(e))
            )


@description("Create a rsync module in the system")
@accepts(h.all_of(
    h.ref('rsyncd-module'),
    h.required('name', 'path'),
))
class RsyncdModuleCreateTask(Task):
    def describe(self, rsyncmod):
        return 'Adding rsync module'

    def verify(self, rsyncmod):
        errors = []

        if re.search(r'[/\]]', rsyncmod['name']):
            errors.append('name', errno.EINVAL, 'The name cannot contain slash or a closing square backet.')

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, rsyncmod):

        try:
            uuid = self.datastore.insert('rsyncd-module', rsyncmod)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'rsyncd')
            self.dispatcher.call_sync('services.restart', 'rsyncd')
        except DatastoreException as e:
            raise TaskException(errno.EBADMSG, 'Cannot add rsync module: {0}'.format(str(e)))
        except RpcException as e:
            raise TaskException(errno.ENXIO, 'Cannot regenerate rsyncd {0}'.format(str(e)))
        self.dispatcher.dispatch_event('service.rsyncd.module.changed', {
            'operation': 'create',
            'ids': [uuid]
        })
        return uuid


@description("Update a rsync module in the system")
@accepts(str, h.all_of(
    h.ref('rsyncd-module'),
))
class RsyncdModuleUpdateTask(Task):
    def describe(self, uuid, updated_fields):
        return 'Updating rsync module'

    def verify(self, uuid, updated_fields):

        rsyncmod = self.datastore.get_by_id('rsyncd-module', uuid)
        if rsyncmod is None:
            raise VerifyException(errno.ENOENT, 'Rsync module {0} does not exists'.format(uuid))
        rsyncmod.update(updated_fields)

        errors = []

        if re.search(r'[/\]]', rsyncmod['name']):
            errors.append('name', errno.EINVAL, 'The name cannot contain slash or a closing square backet.')

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, uuid, updated_fields):

        rsyncmod = self.datastore.get_by_id('rsyncd-module', uuid)
        try:
            rsyncmod.update(updated_fields)
            self.datastore.update('rsyncd-module', uuid, rsyncmod)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'rsyncd')
            self.dispatcher.call_sync('services.restart', 'rsyncd')
        except DatastoreException as e:
            raise TaskException(errno.EBADMSG, 'Cannot update rsync module: {0}'.format(str(e)))
        except RpcException as e:
            raise TaskException(errno.ENXIO, 'Cannot regenerate rsyncd {0}'.format(str(e)))

        self.dispatcher.dispatch_event('service.rsyncd.module.changed', {
            'operation': 'update',
            'ids': [uuid]
        })


@description("Delete a rsync module in the system")
@accepts(str)
class RsyncdModuleDeleteTask(Task):
    def describe(self, uuid, updated_fields):
        return 'Deleting rsync module'

    def verify(self, uuid):

        rsyncmod = self.datastore.get_by_id('rsyncd-module', uuid)
        if rsyncmod is None:
            raise VerifyException(errno.ENOENT, 'Rsync module {0} does not exists'.format(uuid))

        return ['system']

    def run(self, uuid):

        try:
            self.datastore.delete('rsyncd-module', uuid)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'rsyncd')
            self.dispatcher.call_sync('services.restart', 'rsyncd')
        except DatastoreException as e:
            raise TaskException(errno.EBADMSG, 'Cannot delete rsync module: {0}'.format(str(e)))
        except RpcException as e:
            raise TaskException(errno.ENXIO, 'Cannot regenerate rsyncd {0}'.format(str(e)))

        self.dispatcher.dispatch_event('service.rsyncd.module.changed', {
            'operation': 'delete',
            'ids': [uuid]
        })


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):

    # Make sure collections are present
    dispatcher.require_collection('rsyncd-module')

    # Register schemas
    plugin.register_schema_definition('service-rsyncd', {
        'type': 'object',
        'properties': {
            'port': {'type': 'integer'},
            'auxiliary': {'type': 'string'},
        },
        'additionalProperties': False,
    })
    plugin.register_schema_definition('rsyncd-module', {
        'type': 'object',
        'properties': {
            'name': {'type': 'string'},
            'description': {'type': ['string', 'null']},
            'path': {'type': 'string'},
            'mode': {'type': 'string', 'enum': [
                'READONLY',
                'WRITEONLY',
                'READWRITE',
            ]},
            'max_connections': {'type': ['integer', 'null']},
            'user': {'type': 'string'},
            'group': {'type': 'string'},
            'hosts_allow': {'type': ['string', 'null']},
            'hosts_deny': {'type': ['string', 'null']},
            'auxiliary': {'type': ['string', 'null']},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.rsyncd", RsyncdProvider)
    plugin.register_provider("service.rsyncd.module", RsyncdModuleProvider)

    # Register tasks
    plugin.register_task_handler("service.rsyncd.configure", RsyncdConfigureTask)
    plugin.register_task_handler("service.rsyncd.module.create", RsyncdModuleCreateTask)
    plugin.register_task_handler("service.rsyncd.module.update", RsyncdModuleUpdateTask)
    plugin.register_task_handler("service.rsyncd.module.delete", RsyncdModuleDeleteTask)
