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

from datastore.config import ConfigNode
from dispatcher.rpc import RpcException, SchemaHelper as h, description, accepts, returns
from resources import Resource
from task import Task, Provider, TaskException


@description('Provides info about AFP service configuration')
class AFPProvider(Provider):
    @accepts()
    @returns(h.ref('service-afp'))
    def get_config(self):
        return ConfigNode('service.afp', self.configstore)


@description('Configure AFP service')
@accepts(h.ref('service-afp'))
class AFPConfigureTask(Task):
    def describe(self, share):
        return 'Configuring AFP service'

    def verify(self, afp):
        return ['system']

    def run(self, afp):
        try:
            node = ConfigNode('service.afp', self.configstore)
            node.update(afp)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'afp')
            self.dispatcher.call_sync('services.reload', 'afp')
            self.dispatcher.dispatch_event('service.afp.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException, e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure AFP: {0}'.format(str(e))
            )


def _init(dispatcher, plugin):
    # Register schemas
    plugin.register_schema_definition('service-afp', {
        'type': 'object',
        'properties': {
            'guest': {'type': 'boolean'},
            'guest_user': {'type': 'string'},
            'bind_addresses': {
                'type': ['array', 'null'],
                'items': {'type': 'string'},
            },
            'connections_limit': {'type': 'integer'},
            'homedir': {'type': 'boolean'},
            'homedir_path': {'type': 'string'},
            'homedir_name': {'type': 'string'},
            'dbpath': {'type': 'string'},
            'auxiliary': {'type': 'string'},

        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.afp", AFPProvider)

    # Register tasks
    plugin.register_task_handler("service.afp.configure", AFPConfigureTask)

    # Register resources
    plugin.register_resource(Resource('service:afp'), ['system'])