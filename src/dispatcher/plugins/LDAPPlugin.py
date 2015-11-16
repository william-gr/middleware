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

import logging

from freenas.dispatcher.rpc import (
    accepts,
    description,
    returns,
    SchemaHelper as h
)

from task import (
    Provider,
    Task
)

logger = logging.getLogger('LDAPPlugin')

@description("Provides access to LDAP configuration")
class LDAPProvider(Provider):

    @returns(h.ref('ldap-config'))
    def get_config(self):
        pass


@description("Updates LDAP settings")
@accepts(h.ref('ldap-config'))
class LDAPConfigureTask(Task):

    def verify(self, config):
        return ['system'] 

    def run(self, config):
        pass


def _init(dispatcher, plugin):
    plugin.register_schema_definition('ldap-config',  {
        'type': 'object',
        'properties': {
            'hostname': { 'type': 'string' },
            'binddn': { 'type': 'string' },
            'bindpw': { 'type': 'string' }
        }
    })

    plugin.register_provider('directoryservice.ldap', LDAPProvider)

    plugin.register_task_handler('directoryservice.ldap.configure',
        LDAPConfigureTask)
