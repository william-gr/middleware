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
import cStringIO
import csv
import errno
import logging
import os
import re

from datastore.config import ConfigNode
from dispatcher.rpc import RpcException, SchemaHelper as h, description, accepts, returns
from task import Task, Provider, TaskException, ValidationException

logger = logging.getLogger('UPSPlugin')


@description('Provides info about UPS service configuration')
class UPSProvider(Provider):
    @accepts()
    @returns(h.ref('service-ups'))
    def get_config(self):
        return ConfigNode('service.ups', self.configstore)

    @accepts()
    @returns(h.array(h.array(str)))
    def drivers(self):
        driver_list = '/usr/local/libexec/nut/driver.list'
        if not os.path.exists(driver_list):
            return []
        drivers = []
        with open(driver_list, 'rb') as f:
            d = f.read()
        r = cStringIO.StringIO()
        for line in re.sub(r'[ \t]+', ' ', d, flags=re.M).split('\n'):
            r.write(line.strip() + '\n')
        r.seek(0)
        reader = csv.reader(r, delimiter=' ', quotechar='"')
        for row in reader:
            if len(row) == 0 or row[0].startswith('#'):
                continue
            if row[-2] == '#':
                last = -3
            else:
                last = -1
            if row[last].find(' (experimental)') != -1:
                row[last] = row[last].replace(' (experimental)', '').strip()
            for i, field in enumerate(list(row)):
                row[i] = field.decode('utf8')
            drivers.append(('$'.join([row[last], row[3]]), '{0} ({1})'.format(
                ' '.join(row[0:last]), row[last]
            )))
        return drivers


@description('Configure UPS service')
@accepts(h.ref('service-ups'))
class UPSConfigureTask(Task):
    def describe(self, share):
        return 'Configuring UPS service'

    def verify(self, ups):
        errors = []

        node = ConfigNode('service.ups', self.configstore).__getstate__()
        node.update(ups)

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, ups):
        try:
            node = ConfigNode('service.ups', self.configstore)
            node.update(ups)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'services')
            self.dispatcher.call_sync('services.restart', 'ups')
            self.dispatcher.dispatch_event('service.ups.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException, e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure UPS: {0}'.format(str(e))
            )


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):

    # Register schemas
    plugin.register_schema_definition('service-ups', {
        'type': 'object',
        'properties': {
            'mode': {'type': 'string', 'enum': [
                'MASTER',
                'SLAVE',
            ]},
            'identifier': {'type': 'string'},
            'remote_host': {'type': ['string', 'null']},
            'remote_port': {'type': 'integer'},
            'driver': {'type': 'string'},
            'driver_port': {'type': 'string'},
            'description': {'type': ['string', 'null']},
            'shutdown_mode': {'type': 'string', 'enum': [
                'LOWBATT',
                'BATT',
            ]},
            'shutdown_timer': {'type': 'integer'},
            'monitor_user': {'type': 'string'},
            'monitor_password': {'type': 'string'},
            'monitor_remote': {'type': 'boolean'},
            'auxiliary_users': {'type': ['string', 'null']},
            'email_notify': {'type': 'boolean'},
            'email_recipients': {'type': 'array', 'items': {'$ref': 'email'}},
            'email_subject': {'type': 'string'},
            'powerdown': {'type': 'boolean'},
            'auxiliary': {'type': ['string', 'null']},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.ups", UPSProvider)

    # Register tasks
    plugin.register_task_handler("service.ups.configure", UPSConfigureTask)