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
from dispatcher.rpc import RpcException, SchemaHelper as h, description, accepts, returns
from task import Task, Provider, TaskException, ValidationException

logger = logging.getLogger('HAProxyPlugin')


@description('Provides info about HAProxy service configuration')
class HAProxyProvider(Provider):
    @accepts()
    @returns(h.ref('service-haproxy'))
    def get_config(self):
        return ConfigNode('service.haproxy', self.configstore)


@description('Configure HAProxy service')
@accepts(h.ref('service-haproxy'))
class HAProxyConfigureTask(Task):
    def describe(self, share):
        return 'Configuring HAProxy service'

    def verify(self, haproxy):
        errors = []

        node = ConfigNode('service.haproxy', self.configstore).__getstate__()
        node.update(haproxy)

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, haproxy):
        try:
            node = ConfigNode('service.haproxy', self.configstore)
            node.update(haproxy)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'haproxy')
            self.dispatcher.dispatch_event('service.haproxy.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException as e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure HAProxy: {0}'.format(str(e))
            )

        return 'RESTART'


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):

    # Register schemas
    plugin.register_schema_definition('service-haproxy', {
        'type': 'object',
        'properties': {
            'global_maxconn': {'type': ['integer', 'null']},
            'defaults_maxconn': {'type': ['integer', 'null']},
            'http_ip': {'type': ['string', 'null']},
            'http_port': {'type': ['integer', 'null']},
            'https_ip': {'type': ['string', 'null']},
            'https_port': {'type': ['integer', 'null']},
            'frontend_mode': {'type': 'string', 'enum': ['HTTP','TCP']},
            'backend_mode': {'type': 'string', 'enum': ['HTTP','TCP']},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.haproxy", HAProxyProvider)

    # Register tasks
    plugin.register_task_handler("service.haproxy.configure", HAProxyConfigureTask)
