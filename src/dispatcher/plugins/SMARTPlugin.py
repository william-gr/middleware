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
from dispatcher.rpc import RpcException, SchemaHelper as h, description, accepts, returns
from task import Task, Provider, TaskException, ValidationException

logger = logging.getLogger('SMARTPlugin')


@description('Provides info about SMART service configuration')
class SMARTProvider(Provider):
    @accepts()
    @returns(h.ref('service-smartd'))
    def get_config(self):
        return ConfigNode('service.smartd', self.configstore)


@description('Configure SMART service')
@accepts(h.ref('service-smartd'))
class SMARTConfigureTask(Task):
    def describe(self, share):
        return 'Configuring SMART service'

    def verify(self, smartd):
        errors = []

        node = ConfigNode('service.smartd', self.configstore).__getstate__()
        node.update(smartd)

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, smartd):
        try:
            node = ConfigNode('service.smartd', self.configstore)
            node.update(smartd)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'services')
            self.dispatcher.dispatch_event('service.smartd.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException, e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure SMART: {0}'.format(str(e))
            )

        return 'RESTART'


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):

    # Register schemas
    plugin.register_schema_definition('service-smartd', {
        'type': 'object',
        'properties': {
            'interval': {'type': 'integer'},
            'power_mode': {'type': 'string', 'enum': [
                'NEVER',
                'SLEEP',
                'STANDBY',
                'IDLE',
            ]},
            'temp_difference': {'type': ['integer', 'null']},
            'temp_informational': {'type': ['integer', 'null']},
            'temp_critical': {'type': ['integer', 'null']},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.smartd", SMARTProvider)

    # Register tasks
    plugin.register_task_handler("service.smartd.configure", SMARTConfigureTask)
