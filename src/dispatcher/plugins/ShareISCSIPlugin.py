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
import uuid
import hashlib
from task import Task, TaskStatus, Provider, TaskException, VerifyException
from dispatcher.rpc import RpcException, description, accepts, returns, private
from dispatcher.rpc import SchemaHelper as h
from fnutils import normalize
from fnutils.query import wrap


@description("Provides info about configured iSCSI shares")
class ISCSISharesProvider(Provider):
    @private
    @accepts(str)
    def get_connected_clients(self, share_name=None):
        pass

    @returns(str)
    def generate_serial(self):
        nic = wrap(self.dispatcher.call_sync('network.interfaces.query', [('type', '=', 'ETHER')], {'single': True}))
        laddr = nic['status.link_address'].replace(':', '')
        idx = 0

        while True:
            serial = '{0}{1:02}'.format(laddr, idx)
            if not self.datastore.exists('shares', ('properties.serial', '=', serial)):
                return serial

            idx += 1

        raise RpcException(errno.EBUSY, 'No free serial numbers found')


class ISCSITargetsProvider(Provider):
    def query(self, filter=None, params=None):
        return self.datastore.query('iscsi.targets', *(filter or []), **(params or {}))


class ISCSIAuthProvider(Provider):
    def query(self, filter=None, params=None):
        return self.datastore.query('iscsi.auth', *(filter or []), **(params or {}))


@description("Adds new iSCSI share")
@accepts(h.ref('iscsi-share'))
class CreateISCSIShareTask(Task):
    def describe(self, share):
        return "Creating iSCSI share {0}".format(share['id'])

    def verify(self, share):
        if share['target'][0] == '/':
            # File extent
            if not os.path.exists(share['target']):
                raise VerifyException(errno.ENOENT, "Extent file does not exist")
        else:
            if not os.path.exists(convert_share_target(share['target'])):
                raise VerifyException(errno.ENOENT, "Extent ZVol does not exist")

        return ['service:ctl']

    def run(self, share):
        props = share['properties']
        if not props.get('properties.serial'):
            props['serial'] = self.dispatcher.call_sync('shares.iscsi.generate_serial')

        normalize(props, {
            'block_size': 512,
            'physical_block_size': True,
            'tpc': False,
            'vendor_id': None,
            'device_id': None,
            'rpm': 'SSD'
        })

        share['target'] = convert_share_target(share['target'])
        props['naa'] = generate_naa()
        self.datastore.insert('shares', share)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'iscsi')
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
        return ['service:ctl']

    def run(self, name, updated_fields):
        if 'target' in updated_fields:
            updated_fields['target'] = convert_share_target(updated_fields['target'])

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
        return ['service:ctl']

    def run(self, name):
        share = self.datastore.get_by_id('shares', name)
        self.datastore.delete('shares', name)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'iscsi')
        self.dispatcher.call_sync('services.reload', 'iscsi')

        self.dispatcher.dispatch_event('shares.iscsi.changed', {
            'operation': 'delete',
            'ids': [name]
        })


@accepts(h.ref('iscsi-target'))
class CreateISCSITargetTask(Task):
    def verify(self, target):
        for i in target['extents']:
            if not self.datastore.exists('shares', ('type', '=', 'iscsi'), ('name', '=', i['name'])):
                raise VerifyException(errno.ENOENT, "Share {0} not found".format(i['name']))

        return ['service:ctl']

    def run(self, target):
        normalize(target, {
            'description': None,
            'auth_group': 'no-authentication',
            'extents': []
        })

        id = self.datastore.insert('iscsi.targets', target)
        self.dispatcher.dispatch_event('iscsi.target.changed', {
            'operation': 'create',
            'ids': [id]
        })

        return id


@accepts(str, h.ref('iscsi-target'))
class UpdateISCSITargetTask(Task):
    def verify(self, id, updated_params):
        if not self.datastore.exists('iscsi.targets', ('id', '=', id)):
            raise VerifyException(errno.ENOENT, 'Target {0} does not exist'.format(id))

        if 'extents' in updated_params:
            for i in updated_params['extents']:
                if not self.datastore.exists('shares', ('type', '=', 'iscsi'), ('name', '=', i['name'])):
                    raise VerifyException(errno.ENOENT, "Share {0} not found".format(i['name']))

        return ['service:ctl']

    def run(self, id, updated_params):
        target = self.datastore.get_by_id('iscsi.targets', id)
        target.update(updated_params)
        self.datastore.update('iscsi.targets', id, target)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'iscsi')
        self.dispatcher.call_sync('services.reload', 'iscsi')
        self.dispatcher.dispatch_event('iscsi.target.changed', {
            'operation': 'update',
            'ids': [id]
        })


@accepts(str)
class DeleteISCSITargetTask(Task):
    def verify(self, id):
        if not self.datastore.exists('iscsi.targets', ('id', '=', id)):
            raise VerifyException(errno.ENOENT, 'Target {0} does not exist'.format(id))

        return ['service:ctl']

    def run(self, id):
        self.datastore.delete('iscsi.targets', id)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'iscsi')
        self.dispatcher.call_sync('services.reload', 'iscsi')
        self.dispatcher.dispatch_event('iscsi.target.changed', {
            'operation': 'delete',
            'ids': [id]
        })


@accepts(
    h.all_of(
        h.ref('iscsi-auth-group'),
        h.required('name', 'type')
    )
)
class CreateISCSIAuthGroupTask(Task):
    def verify(self, auth_group):
        return ['service:ctl']

    def run(self, auth_group):
        normalize(auth_group, {
            'users': None,
            'initiators': None,
            'networks': None
        })

        id = self.datastore.insert('iscsi.auth', auth_group)
        self.dispatcher.dispatch_event('iscsi.auth.changed', {
            'operation': 'create',
            'ids': [id]
        })


@accepts(str, h.ref('iscsi-auth-group'))
class UpdateISCSIAuthGroupTask(Task):
    def verify(self, id, updated_params):
        if not self.datastore.exists('iscsi.auth', ('id', '=', id)):
            raise VerifyException(errno.ENOENT, 'Auth group {0} does not exist'.format(id))

        return ['service:ctl']

    def run(self, id, updated_params):
        ag = self.datastore.get_by_id('iscsi.auth', id)
        ag.update(updated_params)
        self.datastore.update('iscsi.auth', id, ag)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'iscsi')
        self.dispatcher.call_sync('services.reload', 'iscsi')
        self.dispatcher.dispatch_event('iscsi.auth.changed', {
            'operation': 'update',
            'ids': [id]
        })


@accepts(str)
class DeleteISCSIAuthGroupTask(Task):
    def verify(self, id):
        if not self.datastore.exists('iscsi.auth', ('id', '=', id)):
            raise VerifyException(errno.ENOENT, 'Auth group {0} does not exist'.format(id))

        return ['service:ctl']

    def run(self, id):
        self.datastore.delete('iscsi.auth', id)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'iscsi')
        self.dispatcher.call_sync('services.reload', 'iscsi')
        self.dispatcher.dispatch_event('iscsi.auth.changed', {
            'operation': 'delete',
            'ids': [id]
        })


def generate_naa():
    return '0x6589cfc000000{0}'.format(hashlib.sha256(str(uuid.uuid4())).hexdigest()[0:19])


def convert_share_target(target):
    if target[0] == '/':
        return target

    return os.path.join('/dev/zvol', target)


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
            'naa': {'type': 'string'},
            'size': {'type': 'integer'},
            'block_size': {
                'type': 'integer',
                'enum': [512, 1024, 2048, 4096]
            },
            'physical_block_size': {'type': 'boolean'},
            'available_space_threshold': {'type': 'integer'},
            'tpc': {'type': 'boolean'},
            'vendor_id': {'type': ['string', 'null']},
            'device_id': {'type': ['string', 'null']},
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
            'auth_group': {'type': 'string'},
            'auth_type': {'type': 'string'},
            'extents': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {
                        'name': {'type': 'string'},
                        'number': {'type': 'integer'}
                    }
                },
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

    plugin.register_schema_definition('iscsi-auth-group', {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'id': {'type': 'string'},
            'description': {'type': 'string'},
            'type': {
                'type': 'string',
                'enum': ['NONE', 'DENY', 'CHAP', 'CHAP_MUTUAL']
            },
            'users': {
                'type': ['array', 'null'],
                'items': {'$ref': 'iscsi-user'}
            },
            'initiators': {
                'type': ['array', 'null'],
                'items': {'type': 'string'}
            },
            'networks': {
                'type': ['array', 'null'],
                'items': {'type': 'string'}
            },
        }
    })

    plugin.register_schema_definition('iscsi-user', {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'name': {'type': 'string'},
            'secret': {'type': 'string'},
            'peer_name': {'type': ['string', 'null']},
            'peer_secret': {'type': ['string', 'null']}
        }
    })

    plugin.register_task_handler("share.iscsi.create", CreateISCSIShareTask)
    plugin.register_task_handler("share.iscsi.update", UpdateISCSIShareTask)
    plugin.register_task_handler("share.iscsi.delete", DeleteiSCSIShareTask)
    plugin.register_task_handler("share.iscsi.target.create", CreateISCSITargetTask)
    plugin.register_task_handler("share.iscsi.target.update", UpdateISCSITargetTask)
    plugin.register_task_handler("share.iscsi.target.delete", DeleteISCSITargetTask)
    plugin.register_task_handler("share.iscsi.auth.create", CreateISCSIAuthGroupTask)
    plugin.register_task_handler("share.iscsi.auth.update", UpdateISCSIAuthGroupTask)
    plugin.register_task_handler("share.iscsi.auth.delete", DeleteISCSIAuthGroupTask)

    plugin.register_provider("shares.iscsi", ISCSISharesProvider)
    plugin.register_provider("shares.iscsi.target", ISCSITargetsProvider)
    plugin.register_provider("shares.iscsi.auth", ISCSIAuthProvider)
    plugin.register_event_type('shares.iscsi.changed')
