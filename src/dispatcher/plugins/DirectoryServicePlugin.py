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

from dispatcher.rpc import (
    accepts,
    description,
    returns,
    SchemaHelper as h
)

from resources import Resource 

from task import (
    query,
    Provider,
    Task,
    VerifyException
)

logger = logging.getLogger('DirectoryServicePlugin')


class DirectoryServicesProvider(Provider):
    @query('directoryservice')
    def query(self, filter=None, params=None):
        def extend(directoryservice):
            return directoryservice

        # XXX Not sure why this won't work
        #return self.dispatcher.call_sync('dsd.configuration.query',
        #    *(filter or []), callback=extend, **(params or {}))

        return self.datastore.query('directoryservices', *(filter or []), 
            callback=extend, **(params or {}))


@description("Create directory service")
@accepts(
    h.all_of(
        h.ref('directoryservice'),
        h.required('name', 'domain'),
        h.forbidden('id')
    )
)
class DirectoryServiceCreateTask(Task):
    def verify(self, directoryservice):
        dstypes = self.dispatcher.call_sync('dsd.configuration.get_supported_directories')
        type = directoryservice['type']
        if type not in dstypes:
            raise VerifyException(errno.ENXIO, 'Unknown directory service type {0}'.format(directoryservice[type]))

        directoryservices = self.dispatcher.call_sync('dsd.configuration.get_directory_services')
        for ds in directoryservices:
            if ds['type'] == type:
                raise VerifyException(errno.EEXIST, 'THERE CAN ONLY BE ONE!')

        return ['directoryservice']

    def run(self, directoryservice):
        return self.dispatcher.call_sync('dsd.configuration.create', directoryservice)


@description("Update directory service")
class DirectoryServiceUpdateTask(Task):
    def verify(self, id, updated_fields):
        directoryservice = self.dispatcher.call_sync('dsd.configuration.verify', id)
        if not directoryservice:
            raise VerifyException(errno.ENOENT, 'Directory service not found')
        return ['directoryservice']

    def run(self, id, updated_fields):
        return self.dispatcher.call_sync('dsd.configuration.update', id, updated_fields)


@description("Delete directory service")
class DirectoryServiceDeleteTask(Task):
    def verify(self, id):
        directoryservice = self.dispatcher.call_sync('dsd.configuration.verify', id)
        if not directoryservice:
            raise VerifyException(errno.ENOENT, 'Directory service not found')
        return ['directoryservice']

    def run(self, id):
        return self.dispatcher.call_sync('dsd.configuration.delete', id)

@description("Enable directory service")
class DirectoryServiceEnableTask(Task):
    def verify(self, id):
        directoryservice = self.dispatcher.call_sync('dsd.configuration.verify', id)
        if not directoryservice:
            raise VerifyException(errno.ENOENT, 'Directory service not found')
        return ['directoryservice']

    def run(self, id):
        return self.dispatcher.call_sync('dsd.configuration.enable', id)


@description("Disablle directory service")
class DirectoryServiceDisableTask(Task):
    def verify(self, id):
        directoryservice = self.dispatcher.call_sync('dsd.configuration.verify', id)
        if not directoryservice:
            raise VerifyException(errno.ENOENT, 'Directory service not found')
        return ['directoryservice']

    def run(self, id):
        return self.dispatcher.call_sync('dsd.configuration.disable', id)


@description("Get directory service servers")
class DirectoryServiceGetTask(Task):
    def verify(self, args):
        id = args[0] 
        what = args[1]

        if what not in ['dcs', 'gcs', 'kdcs']:
            raise VerifyException(errno.ENOENT, 'No such configuration!')

        return ['directoryservice']

    def run(self, args):
        id = args[0] 
        what = args[1]

        return self.dispatcher.call_sync('dsd.configuration.get_%s' % what, id)
  

@description("Configure a directory service")
class DirectoryServiceConfigureTask(Task):
    def verify(self, args):
        id = args[0] 
        what = args[1]
        enable = args[2]

        return ['directoryservice']

    def run(self, args):
        id = args[0] 
        what = args[1]
        enable = args[2]

        if what not in ['hostname', 'hosts', 'kerberos',
            'nsswitch', 'openldap', 'nssldap', 'sssd',
            'samba', 'pam', 'activedirectory', 'ldap']:
            raise VerifyException(errno.ENOENT, 'No such configuration!')

        self.dispatcher.call_sync('dsd.configuration.configure_%s' % what, id, enable)
        return [ 'ship' ]


@description("Obtain a Kerberos ticket")
class DirectoryServiceKerberosTicketTask(Task):
    def verify(self, id):
        return ['directoryservice']

    def run(self, id):

        # XXX 
        self.dispatcher.call_sync('dsd.configuration.get_kerberos_ticket', id)

        return [ 'stack' ]


@description("Join an Active Directory")
class DirectoryServiceJoinActiveDirectoryTask(Task):
    def verify(self, id):
        return ['directoryservice']

    def run(self, id):

        # XXX 
        self.dispatcher.call_sync('dsd.configuration.join_activedirectory', id)

        return [ 'soup' ]


def _init(dispatcher, plugin):
    plugin.register_schema_definition('directoryservice',  {
        'type': 'object',
        'properties': {
            'id': { 'type': 'string' },
            'name': { 'type': 'string' },
            'description': { 'type': 'string' },
            'type': { 'type': 'string' }

            # Other shit goes here...
        }
    })

#    dispatcher.require_collection('directoryservices')
    dispatcher.register_resource(Resource('directoryservice'))

    plugin.register_provider('directoryservices', DirectoryServicesProvider)

    plugin.register_task_handler('directoryservice.create', DirectoryServiceCreateTask)
    plugin.register_task_handler('directoryservice.update', DirectoryServiceUpdateTask)
    plugin.register_task_handler('directoryservice.delete', DirectoryServiceDeleteTask)
    plugin.register_task_handler('directoryservice.enable', DirectoryServiceEnableTask)
    plugin.register_task_handler('directoryservice.disable', DirectoryServiceDisableTask)

    plugin.register_task_handler('directoryservice.get', DirectoryServiceGetTask)
    plugin.register_task_handler('directoryservice.configure', DirectoryServiceConfigureTask)
    plugin.register_task_handler('directoryservice.kerberosticket', DirectoryServiceKerberosTicketTask)
    plugin.register_task_handler('directoryservice.join', DirectoryServiceJoinActiveDirectoryTask)
