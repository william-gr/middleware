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

DIRECTORY_TYPES = {
    'activedirectory': { 
    },
    'ldap': { 
    }
}

class DirectoryServicesProvider(Provider):
    @query('directoryservice')
    def query(self, filter=None, params=None):
        def extend(directoryservice):
            logger.debug("XXX: extend: directoryservice = %s", directoryservice)
            return directoryservice
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
        logger.debug("XXX: DirectoryServiceCreateTask.verify: 111 directoryservice= %s", directoryservice)

        type = directoryservice['type']
        dstypes = self.dispatcher.call_sync('dsd.configuration.get_supported_directories')
        if type not in dstypes:
            raise VerifyException(errno.ENXIO, 'Unknown directory service type {0}'.format(directoryservice[type]))

        if self.datastore.exists(
            'directoryservices', ('name', '=', directoryservice['name'])):
            raise VerifyException(errno.EEXIST, 'directoryservice {0} exists'.format(directoryservice['name']))

        return ['directoryservice']

    def run(self, directoryservice):
        #type = directoryservice['type']
        #name = directoryservice['name']
        #domain = directoryservice['domain']

        f = open('/tmp/foo.log', 'a')

        try:
            id = self.datastore.insert('directoryservices', directoryservice, pkey=directoryservice['name'])  
        except Exception as e:
            f.write("XXX: CreateDirectoryServiceTask FAIL: %s" % e)

        # If valid config, sync with dsd

        f.write("XXX: CreateDirectoryServiceTask.run(): directoryservice = %s\n" % directoryservice)
        f.close()

        # etcd sync... 

@description("Update directory service")
class DirectoryServiceUpdateTask(Task):
    def verify(self, id, updated_fields):
        logger.debug("XXX: DirectoryServiceUpdateTask.verify: id = %s, updated_fields = %s", id, updated_fields)

        directoryservice = self.datastore.get_by_id('directoryservices', id)
        if not directoryservice:
            raise VerifyException(errno.ENOENT, 'Directory service not found')

        logger.debug("XXX: DirectoryServiceUpdateTask.verify: id = %s, updated_fields = %s", id, updated_fields)

        # Other verifications ?

        return ['directoryservice']

    def run(self, id, updated_fields):

        f = open('/tmp/foo.log', 'a')
        f.write("XXX: UpdateDirectoryServiceTask.run(): id = %s, updated_fields = %s\n" % (id, updated_fields))

        try: 
            directoryservice = self.datastore.get_by_id('directoryservices', id)
            directoryservice.update(updated_fields)
            self.datastore.update('directoryservices', id, directoryservice)

        except Exception as e:
            f.write("XXX: UpdateDirectoryServiceTask FAIL: %s" % e)
    

        f.close()

        # etcd sync... 


@description("Delete directory service")
class DirectoryServiceDeleteTask(Task):
    def verify(self, id):
        directoryservice = self.datastore.get_by_id('directoryservices', id)
        if not directoryservice:
            raise VerifyException(errno.ENOENT, 'Directory service not found')

        return ['directoryservice']

    def run(self, id):
        try:
            self.datastore.delete('directoryservices', id) 
            
            # etcd sync... 

        except DatastoreException as e:
            raise TaskException(errno.EBADMSG, 'Cannot delete directoryservice: {0}'.format(str(e)))


@description("Enable directory service")
class DirectoryServiceEnableTask(Task):
    def verify(self, id):
        logger.debug("XXX: DirectoryServiceEnableTask.verify: id = %s", id)

        directoryservice = self.datastore.get_by_id('directoryservices', id)
        if not directoryservice:
            raise VerifyException(errno.ENOENT, 'Directory service not found')

        logger.debug("XXX: directoryservice = %s", directoryservice)

        return ['directoryservice']

    def run(self, id):
        directoryservice = self.datastore.get_by_id('directoryservices', id)

        # DSD enable and etcd sync
        #  self.dispatcher.call_sync('dsd.configuration.)
        #dstypes = self.dispatcher.call_sync('dsd.configuration.get_supported_directories')


        # XXX 
        self.dispatcher.call_sync('dsd.configuration.enable', id)


@description("Disablle directory service")
class DirectoryServiceDisableTask(Task):
    def verify(self, id):
        logger.debug("XXX: DirectoryServiceDisableTask.verify: id = %s", id)

        directoryservice = self.datastore.get_by_id('directoryservices', id)
        if not directoryservice:
            raise VerifyException(errno.ENOENT, 'Directory service not found')

        logger.debug("XXX: directoryservice = %s", directoryservice)

        return ['directoryservice']

    def run(self, id):

        # DSD disable and etcd sync

        # XXX 
        self.dispatcher.call_sync('dsd.configuration.disable', id)


@description("Get directory service servers")
class DirectoryServiceGetTask(Task):
    def verify(self, args):
        logger.debug("XXX: DirectoryServiceGetTask.verify: args = %s", args)

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

        logger.debug("XXX: DirectoryServiceConfigureTask.verify: args = %s, id = %s, what = %s", args, id, what)
        return ['directoryservice']

    def run(self, args):
        id = args[0] 
        what = args[1]
        if what not in ['dcs', 'gcs', 'kdcs', 'hostname', 'hosts', 
            'kerberos', 'nsswitch', 'openldap', 'nssldap', 'sssd',
            'samba', 'pam', 'activedirectory', 'ldap']:
            raise VerifyException(errno.ENOENT, 'No such configuration!')

        self.dispatcher.call_sync('dsd.configuration.configure_%s' % what, id)
        return [ 'ship' ]


@description("Obtain a Kerberos ticket")
class DirectoryServiceKerberosTicketTask(Task):
    def verify(self, id):
        logger.debug("XXX: DirectoryServiceKerberosTicketTask.verify: id = %s", id)
        return ['directoryservice']

    def run(self, id):

        # XXX 
        self.dispatcher.call_sync('dsd.configuration.get_kerberos_ticket', id)

        return [ 'stack' ]


@description("Join an Active Directory")
class DirectoryServiceJoinActiveDirectoryTask(Task):
    def verify(self, id):
        logger.debug("XXX: DirectoryServiceJoinActiveDirectory.verify: id = %s", id)
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

    dispatcher.require_collection('directoryservices')
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
