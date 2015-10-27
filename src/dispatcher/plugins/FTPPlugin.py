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

logger = logging.getLogger('FTPPlugin')


@description('Provides info about FTP service configuration')
class FTPProvider(Provider):
    @accepts()
    @returns(h.ref('service-ftp'))
    def get_config(self):
        return ConfigNode('service.ftp', self.configstore)


@description('Configure FTP service')
@accepts(h.ref('service-ftp'))
class FTPConfigureTask(Task):
    def describe(self, share):
        return 'Configuring FTP service'

    def verify(self, ftp):
        errors = []

        node = ConfigNode('service.ftp', self.configstore).__getstate__()
        node.update(ftp)

        pmin = node['passive_ports_min']
        if 'passive_ports_min' in ftp:
            if pmin and (pmin < 1024 or pmin > 65535):
                errors.append(
                    ('passive_ports_min', errno.EINVAL, 'This value must be between 1024 and 65535, inclusive.')
                )

        pmax = node['passive_ports_max']
        if 'passive_ports_max' in ftp:
            if pmax and (pmax < 1024 or pmax > 65535):
                errors.append(
                    ('passive_ports_max', errno.EINVAL, 'This value must be between 1024 and 65535, inclusive.')
                )
            elif pmax and pmin and pmin >= pmax:
                errors.append(
                    ('passive_ports_max', errno.EINVAL, 'This value must be higher than minimum passive port.')
                )

        if node['only_anonymous'] and not node['anonymous_path']:
            errors.append(
                ('anonymous_path', errno.EINVAL, 'This field is required for anonymous login.')
            )

        if node['tls'] is True and not node['tls_ssl_certificate']:
            errors.append(('tls_ssl_certificate', errno.EINVAL, 'TLS specified without certificate.'))

        if node['tls_ssl_certificate']:
            cert = self.dispatcher.call_sync('crypto.certificates.query', [('id', '=', node['tls_ssl_certificate'])])
            if not cert:
                errors.append(('tls_ssl_certificate', errno.EINVAL, 'SSL Certificate not found.'))

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, ftp):
        try:
            node = ConfigNode('service.ftp', self.configstore)
            node.update(ftp)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'ftp')
            self.dispatcher.dispatch_event('service.ftp.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException as e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure FTP: {0}'.format(str(e))
            )

        return 'RESTART'


def _depends():
    return ['CryptoPlugin', 'ServiceManagePlugin']


def _init(dispatcher, plugin):

    # Register schemas
    plugin.register_schema_definition('service-ftp', {
        'type': 'object',
        'properties': {
            'port': {'type': 'integer'},
            'max_clients': {'type': 'integer'},
            'ip_connections': {'type': ['integer', 'null']},
            'login_attempt': {'type': 'integer'},
            'timeout': {'type': 'integer'},
            'root_login': {'type': 'boolean'},
            'anonymous_path': {'type': ['string', 'null']},
            'only_anonymous': {'type': 'boolean'},
            'only_local': {'type': 'boolean'},
            'display_login': {'type': ['string', 'null']},
            'filemask': {'type': 'string'},
            'dirmask': {'type': 'string'},
            'fxp': {'type': 'boolean'},
            'resume': {'type': 'boolean'},
            'chroot': {'type': 'boolean'},
            'ident': {'type': 'boolean'},
            'reverse_dns': {'type': 'boolean'},
            'masquerade_address': {'type': ['string', 'null']},
            'passive_ports_min': {'type': ['integer', 'null']},
            'passive_ports_max': {'type': ['integer', 'null']},
            'local_up_bandwidth': {'type': ['integer', 'null']},
            'local_down_bandwidth': {'type': ['integer', 'null']},
            'anon_up_bandwidth': {'type': ['integer', 'null']},
            'anon_down_bandwidth': {'type': ['integer', 'null']},
            'tls': {'type': 'boolean'},
            'tls_policy': {'type': 'string', 'enum': [
                'ON',
                'OFF',
                'DATA',
                '!DATA',
                'AUTH',
                'CTRL',
                'CTRL+DATA',
                'CTRL+!DATA',
                'AUTH+DATA',
                'AUTH+!DATA',
            ]},
            'tls_options': {'type': 'array', 'items': {
                'type': 'string',
                'enum': [
                    'ALLOW_CLIENT_RENEGOTIATIONS',
                    'ALLOW_DOT_LOGIN',
                    'ALLOW_PER_USER',
                    'COMMON_NAME_REQUIRED',
                    'ENABLE_DIAGNOSTICS',
                    'EXPORT_CERTIFICATE_DATA',
                    'NO_CERTIFICATE_REQUEST',
                    'NO_EMPTY_FRAGMENTS',
                    'NO_SESSION_REUSE_REQUIRED',
                    'STANDARD_ENV_VARS',
                    'DNS_NAME_REQUIRED',
                    'IP_ADDRESS_REQUIRED',
                ],
            }},
            'tls_ssl_certificate': {'type': ['string', 'null']},
            'auxiliary': {'type': ['string', 'null']},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.ftp", FTPProvider)

    # Register tasks
    plugin.register_task_handler("service.ftp.configure", FTPConfigureTask)
