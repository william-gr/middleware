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

logger = logging.getLogger('RIAKPlugin')


@description('Provides info about RIAK service configuration')
class RIAKProvider(Provider):
    @accepts()
    @returns(h.ref('service-riak'))
    def get_config(self):
        return ConfigNode('service.riak', self.configstore)


@description('Configure RIAK KV service')
@accepts(h.ref('service-riak'))
class RIAKConfigureTask(Task):
    def describe(self, share):
        return 'Configuring RIAK KV service'

    def verify(self, riak):
        errors = []

        node = ConfigNode('service.riak', self.configstore).__getstate__()
        node.update(riak)

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, riak):
        try:
            node = ConfigNode('service.riak', self.configstore)
            node.update(riak)
            self.dispatcher.call_sync('services.restart', 'riak')
            self.dispatcher.dispatch_event('service.riak.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException as e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure RIAK: {0}'.format(str(e))
            )


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):

    # Register schemas
    plugin.register_schema_definition('service-riak', {
        'type': 'object',
        'properties': {
            'save_description': {'type': 'boolean'},
            'nodename': {'type': ['string', 'null']},
            'node_ip': {'type': ['string', 'null']},
            'log_console_level': {'type': ['string'], 'enum': ['NONE', 'DEBUG', 'INFO', 'WARNING', 'CRITICAL', 'ALERT',  'EMERGENCY', 'ERROR']},
            'storage_backend': {'type': ['string'], 'enum': ['BITCASK', 'LEVELDB', 'MEMORY', 'MULTI', 'PREFIX_MULTI']},
            'buckets_default_allow_multi': {'type': 'boolean'},
            'riak_control': {'type': 'boolean'},
            'listener_http_internal': {'type': ['string', 'null']},
            'listener_http_internal_port': {'type': ['integer', 'null']},
            'listener_protobuf_internal': {'type': ['string', 'null']},
            'listener_protobuf_internal_port': {'type': ['integer', 'null']},
            'listener_https_internal': {'type': ['string', 'null']},
            'listener_https_internal_port': {'type': ['integer', 'null']},
            'object_size_warning_threshold': {'type': ['string', 'null']},
            'object_size_maximum': {'type': ['string', 'null']},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.riak", RIAKProvider)

    # Register tasks
    plugin.register_task_handler("service.riak.configure", RIAKConfigureTask)
