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
from freenas.dispatcher.rpc import RpcException, SchemaHelper as h, description, accepts, returns
from task import Task, Provider, TaskException, ValidationException

logger = logging.getLogger('RIAKCSPlugin')


@description('Provides info about RIAK CS service configuration')
class RIAKCSProvider(Provider):
    @accepts()
    @returns(h.ref('service-riak_cs'))
    def get_config(self):
        return ConfigNode('service.riak_cs', self.configstore)


@description('Configure RIAK CS service')
@accepts(h.ref('service-riak_cs'))
class RIAKCSConfigureTask(Task):
    def describe(self, share):
        return 'Configuring RIAK CS service'

    def verify(self, riakcs):
        errors = []

        node = ConfigNode('service.riak_cs', self.configstore).__getstate__()
        node.update(riakcs)

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, riakcs):
        try:
            node = ConfigNode('service.riak_cs', self.configstore)
            node.update(riakcs)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'riak_cs')
            self.dispatcher.dispatch_event('service.riak_cs.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException as e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure RIAK CS: {0}'.format(str(e))
            )

        return 'RESTART'


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):

    # Register schemas
    plugin.register_schema_definition('service-riak_cs', {
        'type': 'object',
        'properties': {
            'listener_ip': {'type': ['string', 'null']},
            'listener_port': {'type': ['integer', 'null']},
            'riak_host_ip': {'type': ['string', 'null']},
            'riak_host_port': {'type': ['integer', 'null']},
            'stanchion_host_ip': {'type': ['string', 'null']},
            'stanchion_host_port': {'type': ['integer', 'null']},
            'nodename': {'type': ['string', 'null']},
            'node_ip': {'type': ['string', 'null']},
            'log_console_level': {'type': 'string', 'enum': ['NONE', 'DEBUG', 'INFO', 'WARNING', 'CRITICAL', 'ALERT', 'EMERGENCY', 'ERROR']},
            'anonymous_user_creation': {'type': 'boolean'},
            'admin_key': {'type': ['string', 'null']},
            'admin_secret': {'type': ['string', 'null']},
            'max_buckets_per_user': {'type': 'integer'},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.riak_cs", RIAKCSProvider)

    # Register tasks
    plugin.register_task_handler("service.riak_cs.configure", RIAKCSConfigureTask)
