#
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

from datastore.config import ConfigNode
from dispatcher.rpc import RpcException, SchemaHelper as h, description, accepts, returns, private
from task import Task, Provider, TaskException, ValidationException


logger = logging.getLogger('ISCSIPlugin')


@description('Provides info about ISCSI service configuration')
class ISCSIProvider(Provider):
    @accepts()
    @returns(h.ref('service-iscsi'))
    def get_config(self):
        node = ConfigNode('service.iscsi', self.configstore).__getstate__()
        node['portals'] = self.datastore.query('iscsi.portals')
        return node


@description('Configure ISCSI service')
@accepts(h.ref('service-iscsi'))
class ISCSIConfigureTask(Task):
    def describe(self, iscsi):
        return 'Configuring iSCSI service'

    def verify(self, iscsi):
        return ['system']

    def run(self, iscsi):
        try:
            node = ConfigNode('service.iscsi', self.configstore)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'services')
            self.dispatcher.call_sync('etcd.generation.generate_group', 'ctl')
            self.dispatcher.call_sync('services.apply_state', 'iscsi')

            self.dispatcher.dispatch_event('service.iscsi.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException as e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure iSCSI: {0}'.format(str(e))
            )


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):
    # Register schemas
    plugin.register_schema_definition('service-iscsi', {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'enable': {'type': 'boolean'},
            'base_name': {'type': 'string'},
            'pool_space_threshold': {'type': ['integer', 'null']},
            'isns_servers': {
                'type': 'array',
                'items': {'type': 'string'}
            }
        }
    })

    # Register providers
    plugin.register_provider("service.iscsi", ISCSIProvider)

    # Register tasks
    plugin.register_task_handler("service.iscsi.configure", ISCSIConfigureTask)
