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

logger = logging.getLogger('LLDPPlugin')


@description('Provides info about LLDP service configuration')
class LLDPProvider(Provider):
    @accepts()
    @returns(h.ref('service-lldp'))
    def get_config(self):
        return ConfigNode('service.lldp', self.configstore)


@description('Configure LLDP service')
@accepts(h.ref('service-lldp'))
class LLDPConfigureTask(Task):
    def describe(self, share):
        return 'Configuring LLDP service'

    def verify(self, lldp):
        errors = []

        node = ConfigNode('service.lldp', self.configstore).__getstate__()
        node.update(lldp)

        # Lazy load pycountry due to extra verbose DEBUG logging
        import pycountry
        if node['country_code'] and node['country_code'] not in pycountry.countries.indices['alpha2']:
            errors.append(('country_code', errno.EINVAL, 'Invalid ISO-3166 alpha 2 code'))

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, lldp):
        try:
            node = ConfigNode('service.lldp', self.configstore)
            node.update(lldp)
            self.dispatcher.dispatch_event('service.lldp.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException, e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure LLDP: {0}'.format(str(e))
            )

        return 'RELOAD'


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):

    # Register schemas
    plugin.register_schema_definition('service-lldp', {
        'type': 'object',
        'properties': {
            'save_description': {'type': 'boolean'},
            'country_code': {'type': ['string', 'null']},
            'location': {'type': ['string', 'null']},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.lldp", LLDPProvider)

    # Register tasks
    plugin.register_task_handler("service.lldp.configure", LLDPConfigureTask)
