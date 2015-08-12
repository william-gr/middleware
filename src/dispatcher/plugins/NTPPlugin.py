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
from task import Task, Provider, TaskException, ValidationException, query
from dispatcher.rpc import RpcException, accepts, description, returns
from dispatcher.rpc import SchemaHelper as h
from lib.system import system, SubprocessException

logger = logging.getLogger('NTPPlugin')


@description("Provides access to NTP Servers configuration")
class NTPServersProvider(Provider):
    @query('ntp-server')
    def query(self, filter=None, params=None):
        return self.datastore.query('ntpservers', *(filter or []), **(params or {}))


@description("Adds new NTP Server")
@accepts(h.ref('ntp-server'), bool)
class CreateNTPServerTask(Task):
    def describe(self, ntp):
        return "Creating NTP Server {0}".format(ntp['name'])

    def verify(self, ntp, force=False):

        errors = []

        try:
            system('ntpdate', '-q', ntp['address'])
        except SubprocessException:
            if not force:
                errors.append((
                    'address',
                    errno.EINVAL,
                    'Server could not be reached. Check "Force" to continue regardless.'))

        minpoll = ntp.get('minpoll', 6)
        maxpoll = ntp.get('maxpoll', 10)

        if not maxpoll > minpoll:
            errors.append(('maxpoll', errno.EINVAL, 'Max Poll should be higher than Min Poll'))

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, ntp, force=False):
        try:
            pkey = self.datastore.insert('ntpservers', ntp)
            #self.dispatcher.call_sync('etcd.generation.generate_group', 'ntp')
            #self.dispatcher.call_sync('services.ensure_started', 'ntpd')
            #self.dispatcher.call_sync('services.reload', 'ntpd')
            self.dispatcher.dispatch_event('ntpservers.changed', {
                'operation': 'create',
                'ids': [pkey]
            })
        except DatastoreException, e:
            raise TaskException(errno.EBADMSG, 'Cannot create NTP Server: {0}'.format(str(e)))
        except RpcException, e:
            raise TaskException(errno.ENXIO, 'Cannot generate certificate: {0}'.format(str(e)))
        return pkey


def _init(dispatcher, plugin):
    plugin.register_schema_definition('ntp-server', {
        'type': 'object',
        'properties': {
            'id': {'type': 'string'},
            'address': {'type': 'string'},
            'burst': {'type': 'boolean'},
            'iburst': {'type': 'boolean'},
            'prefer': {'type': 'boolean'},
            'minpoll': {'type': 'integer'},
            'maxpoll': {'type': 'integer'},
        },
        'required': ['address'],
        'additionalProperties': False,
    })

    # Require collection used by the plugin
    dispatcher.require_collection('ntpservers')

    # Register events
    plugin.register_event_type('ntpservers.changed')

    # Register provider
    plugin.register_provider("ntpservers", NTPServersProvider)

    # Register tasks
    plugin.register_task_handler("ntpservers.create", CreateNTPServerTask)
