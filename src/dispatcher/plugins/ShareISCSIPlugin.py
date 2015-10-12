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

import os
import errno
from gevent import Timeout
from task import Task, TaskStatus, Provider, TaskException
from dispatcher.rpc import RpcException, description, accepts, returns, private
from dispatcher.rpc import SchemaHelper as h
from resources import Resource


@description("Provides info about configured iSCSI shares")
class ISCSISharesProvider(Provider):
    @private
    @accepts(str)
    def get_connected_clients(self, share_name):
        pass


@description("Adds new iSCSI share")
@accepts(h.ref('iscsi-share'))
class CreateISCSIShareTask(Task):
    def describe(self, share):
        return "Creating iSCSI share {0}".format(share['id'])

    def verify(self, share):
        return ['service:iscsi']

    def run(self, share):
        self.datastore.insert('shares', share)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'iscsi')
        self.dispatcher.call_sync('services.ensure_started', 'iscsi')
        self.dispatcher.call_sync('services.reload', 'iscsi')

        self.dispatcher.dispatch_event('shares.iscsi.changed', {
            'operation': 'create',
            'ids': [share['id']]
        })


@description("Updates existing iSCSI share")
@accepts(str, h.ref('iscsi-share'))
class UpdateISCSIShareTask(Task):
    def describe(self, name, updated_fields):
        return "Updating iSCSI share {0}".format(name)

    def verify(self, name, updated_fields):
        return ['service:iscsi']

    def run(self, name, updated_fields):
        share = self.datastore.get_by_id('shares', name)
        share.update(updated_fields)
        self.datastore.update('shares', name, share)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'iscsi')

        pass

        self.dispatcher.dispatch_event('shares.iscsi.changed', {
            'operation': 'update',
            'ids': [name]
        })


@description("Removes iSCSI share")
@accepts(str)
class DeleteiSCSIShareTask(Task):
    def describe(self, name):
        return "Deleting iSCSI share {0}".format(name)

    def verify(self, name):
        return ['service:iscsi']

    def run(self, name):
        share = self.datastore.get_by_id('shares', name)
        self.datastore.delete('shares', name)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'iscsi')
        self.dispatcher.call_sync('services.reload', 'iscsi')

        pass

        self.dispatcher.dispatch_event('shares.iscsi.changed', {
            'operation': 'delete',
            'ids': [name]
        })


def _metadata():
    return {
        'type': 'sharing',
        'method': 'iscsi'
    }


def _init(dispatcher, plugin):
    plugin.register_schema_definition('iscsi-share-properties', {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'serial': {'type': 'string'},
            'size': {'type': 'integer'},
            'block_size': {
                'type': 'integer',
                'enum': [512, 1024, 2048, 4096]
            },
            'disable_physical_block_size': {'type': 'boolean'},
            'available_space_threshold': {'type': 'integer'},
            'tpc': {'type': 'boolean'},
            'xen_compat': {'type': 'boolean'},
            'rpm': {
                'type': 'string',
                'enum': ['UNKNOWN', 'SSD', '5400', '7200', '10000', '15000']
            }
        }
    })

    plugin.register_schema_definition('iscsi-target', {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'id': {'type': 'string'},
            'description': {'type': 'string'},
            'extents': {
                'type': 'array',
                'items': {'type': 'string'},
            }
        }
    })

    plugin.register_schema_definition('iscsi-portal', {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'id': {'type': 'integer'},
            'description': {'type': 'string'},
            'discovery_auth_metod': {
                'type': 'string',
                'enum': ['NONE', 'CHAP', 'MUTUAL_CHAP']
            },
            'discovery_auth_group': {'type': ['integer', 'null']},
            'listen': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {
                        'address': {'type': 'string'},
                        'port': {'type': 'integer'}
                    }
                }
            }
        }
    })

    plugin.register_schema_definition('iscsi-initiator-group', {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'id': {'type': 'integer'},
            'description': {'type': 'string'},
            'initiators': {
                'type': 'array',
                'items': {'type': 'string'}
            },
            'networks': {
                'type': 'array',
                'items': {'type': 'string'}
            },
        }
    })

    plugin.register_task_handler("share.iscsi.create", CreateISCSIShareTask)
    plugin.register_task_handler("share.iscsi.update", UpdateISCSIShareTask)
    plugin.register_task_handler("share.iscsi.delete", DeleteiSCSIShareTask)
    plugin.register_provider("shares.iscsi", ISCSISharesProvider)
    plugin.register_event_type('shares.iscsi.changed')
