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
import psutil
from task import Task, TaskStatus, Provider, TaskException
from resources import Resource
from dispatcher.rpc import RpcException, description, accepts, returns, private
from dispatcher.rpc import SchemaHelper as h
from freenas.utils import first_or_default, normalize


@description("Provides info about configured AFP shares")
class AFPSharesProvider(Provider):
    @private
    def get_connected_clients(self, share_id=None):
        result = []
        for i in psutil.process_iter():
            if i.name() != 'afpd':
                continue

            conns = [c for c in psutil.net_connections('inet') if c.pid == i.pid]
            conn = first_or_default(lambda c: c.laddr[1] == 548, conns)

            if not conn:
                continue

            result.append({
                'host': conn.laddr[0],
                'share': None,
                'user': i.username()
            })


@description("Adds new AFP share")
@accepts(h.ref('afp-share'))
class CreateAFPShareTask(Task):
    def describe(self, share):
        return "Creating AFP share {0}".format(share['name'])

    def verify(self, share):
        return ['service:afp']

    def run(self, share):
        normalize(share['properties'], {
            'read_only': False,
            'time_machine': False,
            'zero_dev_numbers': False,
            'no_stat': False,
            'afp3_privileges': False,
            'ro_list': None,
            'rw_list': None,
            'users_allow': None,
            'users_deny': None,
            'hosts_allow': None,
            'hosts_deny': None
        })

        id = self.datastore.insert('shares', share)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'afp')
        self.dispatcher.call_sync('services.reload', 'afp')
        self.dispatcher.dispatch_event('shares.afp.changed', {
            'operation': 'create',
            'ids': [id]
        })

        return id


@description("Updates existing AFP share")
@accepts(str, h.ref('afp-share'))
class UpdateAFPShareTask(Task):
    def describe(self, id, updated_fields):
        return "Updating AFP share {0}".format(id)

    def verify(self, id, updated_fields):
        return ['service:afp']

    def run(self, id, updated_fields):
        share = self.datastore.get_by_id('shares', id)
        share.update(updated_fields)
        self.datastore.update('shares', id, share)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'afp')
        self.dispatcher.call_sync('services.reload', 'afp')
        self.dispatcher.dispatch_event('shares.afp.changed', {
            'operation': 'update',
            'ids': [id]
        })


@description("Removes AFP share")
@accepts(str)
class DeleteAFPShareTask(Task):
    def describe(self, name):
        return "Deleting AFP share {0}".format(name)

    def verify(self, id):
        return ['service:afp']

    def run(self, id):
        self.datastore.delete('shares', id)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'afp')
        self.dispatcher.call_sync('services.reload', 'afp')
        self.dispatcher.dispatch_event('shares.afp.changed', {
            'operation': 'delete',
            'ids': [id]
        })


def _depends():
    return ['AFPPlugin', 'SharingPlugin']


def _metadata():
    return {
        'type': 'sharing',
        'subtype': 'file',
        'perm_type': 'PERMS',
        'method': 'afp'
    }


def _init(dispatcher, plugin):
    plugin.register_schema_definition('afp-share', {
        'type': 'object',
        'properties': {
            'comment': {'type': 'string'},
            'read_only': {'type': 'boolean'},
            'time_machine': {'type': 'boolean'},
            'zero_dev_numbers': {'type': 'boolean'},
            'no_stat': {'type': 'boolean'},
            'afp3_privileges': {'type': 'boolean'},
            'default_file_perms': {'$ref': 'unix-permissions'},
            'default_directory_perms': {'$ref': 'unix-permissions'},
            'default_umask': {'$ref': 'unix-permissions'},
            'ro_list': {
                'type': 'array',
                'items': {'type': 'string'}
            },
            'rw_list': {
                'type': ['array', 'null'],
                'items': {'type': 'string'}
            },
            'users_allow': {
                'type': ['array', 'null'],
                'items': {'type': 'string'}
            },
            'users_deny': {
                'type': ['array', 'null'],
                'items': {'type': 'string'}
            },
            'hosts_allow': {
                'type': ['array', 'null'],
                'items': {'type': 'string'}
            },
            'hosts_deny': {
                'type': ['array', 'null'],
                'items': {'type': 'string'}
            }
        }
    })

    plugin.register_task_handler("share.afp.create", CreateAFPShareTask)
    plugin.register_task_handler("share.afp.update", UpdateAFPShareTask)
    plugin.register_task_handler("share.afp.delete", DeleteAFPShareTask)
    plugin.register_provider("shares.afp", AFPSharesProvider)
    plugin.register_event_type('shares.afp.changed')
