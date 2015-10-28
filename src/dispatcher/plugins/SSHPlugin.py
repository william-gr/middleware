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

logger = logging.getLogger('SSHPlugin')


@description('Provides info about SSH service configuration')
class SSHProvider(Provider):
    @accepts()
    @returns(h.ref('service-ssh'))
    def get_config(self):
        return ConfigNode('service.sshd', self.configstore)


@description('Configure SSH service')
@accepts(h.ref('service-ssh'))
class SSHConfigureTask(Task):
    def describe(self, share):
        return 'Configuring SSH service'

    def verify(self, ssh):
        return ['system']

    def run(self, ssh):
        try:
            node = ConfigNode('service.sshd', self.configstore)
            node.update(ssh)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'sshd')
            self.dispatcher.call_sync('services.reload', 'sshd')
            self.dispatcher.dispatch_event('service.ssh.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException, e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure SSH: {0}'.format(str(e))
            )


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):
    # Register schemas
    plugin.register_schema_definition('service-ssh', {
        'type': 'object',
        'properties': {
            'port': {'type': 'integer'},
            'permit_root_login': {'type': 'boolean'},
            'allow_password_auth': {'type': 'boolean'},
            'allow_port_forwarding': {'type': 'boolean'},
            'compression': {'type': 'boolean'},
            'sftp_log_level': {'type': 'string', 'enum': [
                'QUIET',
                'FATAL',
                'ERROR',
                'INFO',
                'VERBOSE',
                'DEBUG',
                'DEBUG2',
                'DEBUG3',
            ]},
            'sftp_log_facility': {'type': 'string', 'enum': [
                'DAEMON',
                'USER',
                'AUTH',
                'LOCAL0',
                'LOCAL1',
                'LOCAL2',
                'LOCAL3',
                'LOCAL4',
                'LOCAL5',
                'LOCAL6',
                'LOCAL7',
            ]},
            'auxiliary': {'type': ['string', 'null']},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.ssh", SSHProvider)

    # Register tasks
    plugin.register_task_handler("service.ssh.configure", SSHConfigureTask)
