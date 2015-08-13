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
from datastore import DatastoreException
from task import Task, Provider, TaskException, ValidationException, VerifyException, query
from dispatcher.rpc import RpcException, accepts, description, returns
from dispatcher.rpc import SchemaHelper as h

logger = logging.getLogger('TunablePlugin')


@description("Provides access to OS tunables")
class TunablesProvider(Provider):
    @query('tunable')
    def query(self, filter=None, params=None):
        return self.datastore.query('tunables', *(filter or []), **(params or {}))


def _init(dispatcher, plugin):
    plugin.register_schema_definition('tunable', {
        'type': 'object',
        'properties': {
            'id': {'type': 'string'},
            'type': {'type': 'string', 'enum': [
                'LOADER', 'RC', 'SYSCTL',
            ]},
            'var': {'type': 'string'},
            'value': {'type': 'string'},
            'comment': {'type': 'string'},
            'enabled': {'type': 'boolean'},
        },
        'additionalProperties': False,
    })

    # Require collection used by the plugin
    dispatcher.require_collection('tunables')

    # Register events
    plugin.register_event_type('tunables.changed')

    # Register provider
    plugin.register_provider("tunables", TunablesProvider)

    # Register tasks
