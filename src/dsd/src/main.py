#!/usr/local/bin/python
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

import argparse
import datetime
import imp
import json
import logging
import os
import setproctitle
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback

from datastore import get_datastore, DatastoreException
from datastore.config import ConfigStore
from dispatcher.client import Client, ClientError
from dispatcher.rpc import RpcService, RpcException, private

from fnutils import configure_logging
from fnutils.debug import DebugService

DEFAULT_CONFIGFILE = '/usr/local/etc/middleware.conf'

#
# values we care about for AD
#
# the netbios name
# the group name
# the machine name
# the base DN
#

class DSDConfigurationService(RpcService):
    def __init__(self, context):
        self.context = context
        self.logger = context.logger
        self.config = context.configstore
        self.datastore = context.datastore
        self.client = context.client
        self.modules = context.modules
        self.cache = { 
            'activedirectory': None,
            'ldap': None
        }

        self.datastore.collection_create(
            'directoryservices', pkey_type='name')

    def __cache_empty(self, cache, key):
        if not self.cache[cache]:
            return True
        if key not in self.cache[cache]:
            return True
        if not self.cache[cache][key]:
            return True
        return False 

    def __toggle_enable(self, id, name, enable):
        directoryservice = self.datastore.get_by_id('directoryservices', id)
        directoryservice[name] = enable
        self.datastore.update('directoryservices', id, directoryservice)

    def get_supported_directories(self):
        supported_directories = []
        for m in self.modules:
            module = self.modules[m]
            if hasattr(module, "get_directory_type"):
                supported_directories.append(module.get_directory_type())

        return supported_directories

    def get_directory_services(self):
        return self.datastore.query('directoryservices')

    def query(self, *args, **kwargs):
        return self.datastore.query('directoryservices', *args, **kwargs)

    def create(self, directoryservice):
        return self.datastore.insert('directoryservices', directoryservice,
            pkey=directoryservice['name'])

    def update(self, id, updated_fields):
        directoryservice = self.datastore.get_by_id('directoryservices', id)
        directoryservice.update(updated_fields)
        return self.datastore.update('directoryservices', id, directoryservice)

    def delete(self, id):
        return self.datastore.delete('directoryservices', id)

    def verify(self, id):
        return self.datastore.get_by_id('directoryservices', id)

    def configure_dcs(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_dcs(): id = %s', id)

        directoryservice = self.datastore.get_by_id('directoryservices', id)
        self.logger.debug('DSDConfigurationSerivce.configure_dcs(): directoryservice = %s', directoryservice)

        #
        # XXX pickle and cache in database, load on start, refresh periodically
        #
        ad = self.modules['activedirectory']
        dcs = ad.get_domain_controllers(directoryservice['domain'])

        if self.__cache_empty('activedirectory', 'dcs'):
            self.cache['activedirectory'] = {}
        self.cache['activedirectory']['dcs'] = dcs

    
        self.logger.debug('DSDConfigurationSerivce.configure_dcs(): dcs = %s', dcs)

    def get_dcs(self, id):
        self.logger.debug('DSDConfigurationService.get_dcs(): id = %s', id)

        if self.__cache_empty('activedirectory', 'dcs'):
            self.configure_dcs(id)

        dcs = []
        if not self.__cache_empty('activedirectory', 'dcs'):
            dcs = self.cache['activedirectory']['dcs']

        return dcs 

    def configure_gcs(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_gcs(): id = %s', id)

        directoryservice = self.datastore.get_by_id('directoryservices', id)
        self.logger.debug('DSDConfigurationSerivce.configure_gcs(): id = %s', id)
        #
        # XXX pickle and cache in database, load on start, refresh periodically
        #
        ad = self.modules['activedirectory']
        gcs = ad.get_global_catalog_servers(directoryservice['domain'])

        if self.__cache_empty('activedirectory', 'gcs'):
            self.cache['activedirectory'] = {}
        self.cache['activedirectory']['gcs'] = gcs
    
        self.logger.debug('DSDConfigurationSerivce.configure_dcs(): gcs = %s', gcs)

    def get_gcs(self, id):
        self.logger.debug('DSDConfigurationService.get_gcs(): id = %s', id)

        if self.__cache_empty('activedirectory', 'gcs'):
            self.configure_gcs(id)

        gcs = []
        if not self.__cache_empty('activedirectory', 'gcs'):
            gcs = self.cache['activedirectory']['gcs']

        return gcs 

    def configure_kdcs(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_kdcs(): id = %s', id)

        directoryservice = self.datastore.get_by_id('directoryservices', id)
        self.logger.debug('DSDConfigurationSerivce.configure_kdcs(): directoryservice = %s', directoryservice)

        #
        # XXX pickle and cache in database, load on start, refresh periodically
        #
        kc = self.modules['kerberos']
        kdcs = kc.get_kerberos_servers(directoryservice['domain'])

        if self.__cache_empty('activedirectory', 'kdcs'):
            self.cache['activedirectory'] = {}
        self.cache['activedirectory']['kdcs'] = kdcs

        if self.__cache_empty('ldap', 'kdcs'):
            self.cache['ldap'] = {}
        self.cache['ldap']['kdcs'] = kdcs
    
        self.logger.debug('DSDConfigurationSerivce.configure_kdcs(): kdcs = %s', kdcs)

    def get_kdcs(self, id):
        self.logger.debug('DSDConfigurationService.get_kdcs(): id = %s', id)

        if self.__cache_empty('activedirectory', 'kdcs'):
            self.configure_kdcs(id)

        kdcs = []
        if not self.__cache_empty('activedirectory', 'kdcs'):
            kdcs = self.cache['activedirectory']['kdcs']

        return kdcs

    def configure_hostname(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_hostname()')
        self.__toggle_enable(id, 'configure_hostname', enable)
        self.client.call_sync('etcd.generation.generate_group', 'hostname')

    def configure_hosts(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_hosts()')
        self.__toggle_enable(id, 'configure_hosts', enable)
        self.client.call_sync('etcd.generation.generate_group', 'hosts')

    def configure_kerberos(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_kerberos()')
        self.__toggle_enable(id, 'configure_kerberos', enable)
        self.client.call_sync('etcd.generation.generate_group', 'kerberos')

    def get_kerberos_ticket(self, id):
        self.logger.debug('DSDConfigurationSerivce.get_kerberos_ticket()')

        directoryservice = self.datastore.get_by_id('directoryservices', id)

        realm = directoryservice['domain'].upper()
        binddn = directoryservice['binddn'].split('@')[0]
        bindpw = directoryservice['bindpw']

        kc = self.modules['kerberos']
        kc.get_ticket(realm, binddn, bindpw)

    def configure_nsswitch(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_nsswitch()')
        self.__toggle_enable(id, 'configure_nsswitch', enable)
        self.client.call_sync('etcd.generation.generate_group', 'nsswitch')

    def configure_openldap(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_openldap()')
        self.__toggle_enable(id, 'configure_openldap', enable)
        self.client.call_sync('etcd.generation.generate_group', 'openldap')

    def configure_nssldap(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_nssldap()')
        self.__toggle_enable(id, 'configure_nssldap', enable)
        self.client.call_sync('etcd.generation.generate_group', 'nssldap')

    def configure_sssd(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_sssd()')
        self.__toggle_enable(id, 'configure_sssd', enable)
        self.client.call_sync('etcd.generation.generate_group', 'sssd')

    def configure_samba(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_samba()')
        self.__toggle_enable(id, 'configure_samba', enable)
        #self.client.call_sync('etcd.generation.generate_group', 'samba')

    def join_activedirectory(self, id):
        self.logger.debug('DSDConfigurationSerivce.join_activedirectory()')

    def configure_pam(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_pam()')
        self.__toggle_enable(id, 'configure_pam', enable)
        self.client.call_sync('etcd.generation.generate_group', 'pam')

    def configure_activedirectory(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_activedirectory()')
        self.__toggle_enable(id, 'configure_activedirectory', enable)
        self.client.call_sync('etcd.generation.generate_group', 'activedirectory')

    def configure_ldap(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_ldap()')
        self.__toggle_enable(id, 'configure_ldap', enable)
        self.client.call_sync('etcd.generation.generate_group', 'ldap')

    def enable(self, id):
        self.logger.debug('DSDConfigurationSerivce.enable()')

    def disable(self, id):
        self.logger.debug('DSDConfigurationSerivce.disable()')


class Main(object):
    def __init__(self):
        self.config = None
        self.client = None
        self.datastore = None
        self.configstore = None
        self.rstock_thread = None
        self.module_dir = '/usr/local/lib/dsd/modules'
        self.modules = {}
        self.logger = logging.getLogger('dsd')

    def parse_config(self, filename):
        try:
            f = open(filename, 'r')
            self.config = json.load(f)
            f.close()
        except IOError as err:
            self.logger.error('Cannot read config file: %s', err.message)
            sys.exit(1)
        except ValueError as err:
            self.logger.error('Config file has unreadable format (not valid JSON)')
            sys.exit(1)

    def init_datastore(self, resume=False):
        try:
            self.datastore = get_datastore(self.config['datastore']['driver'],
                self.config['datastore']['dsn'])
        except DatastoreException as err:
            self.logger.error('Cannot initialize datastore: %s', str(err))
            sys.exit(1)

        self.configstore = ConfigStore(self.datastore)

    def connect(self, resume=False):
        while True:  
            try:
                self.client.connect('127.0.0.1')
                self.client.login_service('dsd')
                self.client.enable_server()
                self.register_schemas()
                self.client.register_service('dsd.configuration', DSDConfigurationService(self))
                self.client.register_service('dsd.debug', DebugService())
                if resume:
                    self.client.resume_service('dsd.configuration')
                    self.client.resume_service('dsd.debug')

                return
            except socket.error as err:
                self.logger.warning('Cannot connect to dispatcher: {0}, retrying in 1 second'.format(str(err)))
                time.sleep(1)


    def init_dispatcher(self):
        def on_error(reason, **kwargs):
            if reason in (ClientError.CONNECTION_CLOSED, ClientError.LOGOUT):
                self.logger.warning('Connection to dispatcher lost')
                self.connect(resume=True)

        self.client = Client()
        self.client.on_error(on_error)
        self.connect()

    def register_schemas(self):
        # XXX do stuff here? To be determined ...
        pass

    def report_error(self, message, exception):
        if not os.path.isdir('/var/tmp/crash'):
            try:
                os.mkdir('/var/tmp/crash')
            except:
                return

        report = {
            'timestamp': str(datetime.datetime.now()),
            'type': 'exception',
            'application': 'dsd',
            'message': message,
            'exception': str(exception),
            'traceback': traceback.format_exc()
        }

        try:
            with tempfile.NamedTemporaryFile(dir='/var/tmp/crash', suffix='.json', prefix='report-', delete=False) as f:
                json.dump(report, f, indent=4)
        except:
            pass

    #
    # XXX implement proper plugin architecture
    # XXX for now, direct module class calls
    #
    def init_directory_service_modules(self):
        directoryservices = [ 'activedirectory', 'ldap', 'kerberos' ]
        for ds in directoryservices:
            try:
                module_path = "%s/%s.py" % (self.module_dir, ds)
                self.logger.debug("Loading module %s", module_path)
                module = imp.load_source(ds, module_path)
                self.modules[ds] = module._init(self.client, self.datastore)

            except Exception as e:
                self.logger.exception("Cannot load module %s", module)
                self.report_error("Cannot load module %s", module) 

    def main(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-c', metavar='CONFIG', default=DEFAULT_CONFIGFILE, help='Middleware config file')
        args = parser.parse_args()
        configure_logging('/var/log/dsd.log', 'DEBUG')
        setproctitle.setproctitle('dsd')
        self.parse_config(args.c)
        self.init_datastore()
        self.init_dispatcher()
        self.init_directory_service_modules() 
        self.client.resume_service('dsd.configuration')
        self.logger.info('Started')
        self.client.wait_forever()


if __name__ == '__main__':
    m = Main()
    m.main()
