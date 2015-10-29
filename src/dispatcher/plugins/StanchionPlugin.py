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

logger = logging.getLogger('StanchionPlugin')


@description('Provides info about Stanchion service configuration')
class StanchionProvider(Provider):
    @accepts()
    @returns(h.ref('service-stanchion'))
    def get_config(self):
        return ConfigNode('service.stanchion', self.configstore)


@description('Configure Stanchion KV service')
@accepts(h.ref('service-stanchion'))
class StanchionConfigureTask(Task):
    def describe(self, share):
        return 'Configuring Stanchion KV service'

    def verify(self, stanchion):
        errors = []

        node = ConfigNode('service.stanchion', self.configstore).__getstate__()
        node.update(stanchion)

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, stanchion):
        try:
            node = ConfigNode('service.stanchion', self.configstore)
            node.update(stanchion)
            self.dispatcher.dispatch_event('service.stanchion.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException, e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure Stanchion: {0}'.format(str(e))
            )

        return 'RESTART'


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):

    # Register schemas
    plugin.register_schema_definition('service-stanchion', {
        'type': 'object',
        'properties': {
            'listener_ip': {'type': ['string', 'null']},
            'listener_port': {'type': ['integer', 'null']},
            'riak_host_ip': {'type': ['string', 'null']},
            'riak_host_port': {'type': ['integer', 'null']},
            'nodename': {'type': ['string', 'null']},
            'node_ip': {'type': ['string', 'null']},
            'log_console_level': {'type': ['string'], 'enum': ['NONE', 'DEBUG', 'INFO', 'WARNING', 'CRITICAL', 'ALERT',  'EMERGENCY', 'ERROR']},
            'admin_key': {'type': ['string', 'null']},
            'admin_secret': {'type': ['string', 'null']},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.stanchion", StanchionProvider)

    # Register tasks
    plugin.register_task_handler("service.stanchion.configure", StanchionConfigureTask)
