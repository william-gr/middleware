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
import copy
import datetime
import glob
import imp
import json
import logging
import os
import smbconf
import setproctitle
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback

from datastore import get_datastore, DatastoreException
from datastore.config import ConfigNode, ConfigStore
from dispatcher.client import Client, ClientError
from dispatcher.rpc import RpcService, RpcException, private
from fnutils import configure_logging
from fnutils.debug import DebugService
from fnutils.pipesubr import pipeopen, run

sys.path.extend(['/usr/local/lib/dsd/src'])

from context import (
    ActiveDirectoryContext,
    KerberosContext,
    LDAPContext
)
from module import DSDModule

DEFAULT_CONFIGFILE = '/usr/local/etc/middleware.conf'


class DSDConfigurationService(RpcService):
    def __init__(self, context):
        self.context = context
        self.logger = context.logger
        self.config = context.configstore
        self.datastore = context.datastore
        self.client = context.client
        self.module_dir = '/usr/local/lib/dsd/modules'
        self.modules = {}
        self.directoryservices = {}
        self.state = {}

        self.load_modules()

        for ds in self.get_supported_directories():
            self.directoryservices[ds] = None
        self.load_directoryservices()

        self.directory_context_init()

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

    #
    # XXX implement proper plugin architecture
    # XXX for now, direct module class calls
    #
    def load_modules(self):
        for f in glob.glob1(self.module_dir, "*.py"):
            module_path = "%s/%s" % (self.module_dir, f)
            self.logger.debug("Loading module %s", module_path)

            try:
                ds = f.split('.')[0]
                module = imp.load_source(ds, module_path)
                instance = module._init(self.client, self.datastore)
                self.modules[ds] = DSDModule(
                    self.context,
                    name=ds,
                    instance=instance
                )

            except Exception as e:
                self.logger.exception("Cannot load module %s", module_path)
                #self.report_error("Cannot load module %s", module_path)

    def directory_context_init(self):
        if self.directoryservices.get('activedirectory'):
            self.activedirectory_context_init()

        if self.directoryservices.get('kerberos'):
            self.kerberos_context_init()

        if self.directoryservices.get('ldap'):
            self.ldap_context_init()

    def directory_context_update(self, updated_fields):
        if self.directoryservices.get('activedirectory'):
            self.activedirectory_context_update(updated_fields)

        if self.directoryservices.get('kerberos'):
            self.kerberos_context_update(updated_fields)

        if self.directoryservices.get('ldap'):
            self.ldap_context_update(updated_fields)

    def directory_context_fini(self):
        if not self.directoryservices.get('activedirectory'):
            self.activedirectory_context_finis()

        if not self.directoryservices.get('kerberos'):
            self.kerberos_context_fini()

        if not self.directoryservices.get('ldap'):
            self.ldap_context_fini()

    def activedirectory_context_init(self):
        ds = self.directoryservices['activedirectory']

        self.modules['activedirectory'].context = ActiveDirectoryContext(
            self.context,
            ds['domain'],
            ds['binddn'],
            ds['bindpw'],
            self.modules
        )

        self.modules['activedirectory'].context.context_init()

    def activedirectory_context_update(self, updated_fields):
        self.modules['activedirectory'].context.context_update(updated_fields)

    def activedirectory_context_fini(self):
        self.modules['activedirectory'].context.context_fini()
        self.modules['activedirectory'].context = None

    def kerberos_context_init(self):
        pass

    def kerberos_context_update(self, updated_fields):
        self.modules['kerberos'].context.context_update(updated_fields)

    def kerberos_context_fini(self):
        self.modules['kerberos'].context.context_fini()
        self.modules['kerberos'].context = None

    def ldap_context_init(self):
        pass

    def ldap_context_update(self, updated_fields):
        self.modules['ldap'].context.context_update(updated_fields)

    def ldap_context_fini(self):
        self.modules['ldap'].context.context_fini()
        self.modules['ldap'].context = None

    def load_directoryservices(self):
        self.datastore.collection_create(
            'directoryservices', pkey_type='name')
        directoryservices = self.datastore.query('directoryservices')
        for ds in directoryservices:
            self.directoryservices[ds['type']] = ds

    def get_supported_directories(self):
        supported_directories = []
        for m in self.modules:
            module = self.modules[m].instance
            if hasattr(module, "get_directory_type"):
                supported_directories.append(module.get_directory_type())

        return supported_directories

    def get_directory_services(self):
        return self.datastore.query('directoryservices')

    def query(self, *args, **kwargs):
        return self.datastore.query('directoryservices', *args, **kwargs)

    def create(self, directoryservice):
        res = self.datastore.insert('directoryservices', directoryservice,
            pkey=directoryservice['name'])

        self.load_directoryservices()
        self.directory_context_init()

        return res

    def update(self, id, updated_fields):
        directoryservice = self.datastore.get_by_id('directoryservices', id)
        directoryservice.update(updated_fields)
        res = self.datastore.update('directoryservices', id, directoryservice)

        self.load_directoryservices()
        self.directory_context_update(updated_fields)

        return res

    def delete(self, id):
        res = self.datastore.delete('directoryservices', id)

        self.load_directoryservices()
        self.directory_context_fini()

        return res

    def verify(self, id):
        return self.datastore.get_by_id('directoryservices', id)

    def get_dcs(self, id):
        self.logger.debug('DSDConfigurationService.get_dcs(): id = %s', id)

        dcs = []
        ad_context = self.modules['activedirectory'].context
        if ad_context:
            dcs = ad_context.dcs

        return dcs 

    def get_gcs(self, id):
        self.logger.debug('DSDConfigurationService.get_gcs(): id = %s', id)

        gcs = []
        ad_context = self.modules['activedirectory'].context
        if ad_context:
            gcs = ad_context.gcs

        return gcs 

    def get_kdcs(self, id):
        self.logger.debug('DSDConfigurationService.get_kdcs(): id = %s', id)

        kdcs = []
        ad_context = self.modules['activedirectory'].context
        if ad_context:
            kdcs = ad_context.kdcs

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

    def get_kerberos_ticket(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.get_kerberos_ticket(): id = %s', id)

        directoryservice = self.datastore.get_by_id('directoryservices', id)

        realm = directoryservice['domain'].upper()
        binddn = directoryservice['binddn'].split('@')[0]
        bindpw = directoryservice['bindpw']

        kc = self.modules['kerberos'].instance
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
        self.client.call_sync('etcd.generation.generate_group', 'nss_ldap')

    def configure_sssd(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_sssd()')
        self.__toggle_enable(id, 'configure_sssd', enable)
        self.client.call_sync('etcd.generation.generate_group', 'sssd')

    def __activedirectory_smbconf(self, ad_context):
        return {
            'server role': 'member server',
            'local master': 'no',
            'domain master': 'no',
            'preferred master': 'no',
            'domain logons': 'no',
            'workgroup': ad_context.netbiosname,
            'realm': ad_context.realm,
            'security': 'ads',
            'winbind cache time': '7200',
            'winbind offline logon': 'yes',
            'winbind enum users': 'yes',
            'winbind enum groups': 'yes',
            'winbind nested groups': 'yes',
            'winbind use default domain': 'yes',
            'winbind refresh tickets': 'yes',
            'idmap config %s: backend' % ad_context.netbiosname: 'rid',
            'idmap config %s: range' % ad_context.netbiosname: '10000-90000000',
            'client use spnego': 'yes',
            'allow trusted domains': 'no',
            'client ldap sasl wrapping': 'plain',
            'template shell': '/bin/sh',
            'template homedir': '/home/%U'
        }

    def __enable_samba_activedirectory(self, id):
        ad_context = self.modules['activedirectory'].context
        if not ad_context:
            return False

        node = ConfigNode('service.cifs',
            ConfigStore(self.datastore)).__getstate__()
        conf = smbconf.SambaConfig('registry')

        saved_smbconf = {}
        ad_smbconf = self.__activedirectory_smbconf(ad_context)
        for key in ad_smbconf.keys():
            if key in conf:
                saved_smbconf[key] = conf[key]
            conf[key] = ad_smbconf[key]

        self.state['saved_smbconf'] = saved_smbconf
        return True

    def __disable_samba_activedirectory(self, id):
        ad_context = self.modules['activedirectory'].context
        if not ad_context:
            return False

        node = ConfigNode('service.cifs',
            ConfigStore(self.datastore)).__getstate__()
        conf = smbconf.SambaConfig('registry')

        saved_smbconf = self.state.get('saved_smbconf', None)
        ad_smbconf = self.__activedirectory_smbconf(ad_context)
        for key in ad_smbconf.keys():
            if key in conf:
                del conf[key]
            if saved_smbconf and key in saved_smbconf:
                conf[key.decode('utf-8')] = saved_smbconf[key]

        self.state['saved_smbconf'] = {}
        return True

    def __configure_samba_activedirectory(self, id, enable):
        if enable:
            return self.__enable_samba_activedirectory(id)
        return self.__disable_samba_activedirectory(id)

    def __enable_samba_ldap(self, id):
        ldap_context = self.modules['ldap'].context
        if not ldap_context:
            return  False

        return True

    def __disable_samba_ldap(self, id):
        ldap_context = self.modules['ldap'].context
        if not ldap_context:
            return  False

        return True

    def __configure_samba_ldap(self, id, enable):
        if enable:
            return self.__enable_samba_ldap(id)
        return self.__disable_samba_ldap(id)

    def configure_samba(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.configure_samba()')
        self.__toggle_enable(id, 'configure_samba', enable)

        ds = self.datastore.get_by_id('directoryservices', id)
        if not ds or not ds.get('type'):
            return False

        if ds.get('type') == 'activedirectory':
            return self.__configure_samba_activedirectory(id, enable)
        elif ds.get('type') == 'ldap':
            return self.__configure_samba_ldap(id, enable)

        return False

    def join_activedirectory(self, id, enable=True):
        self.logger.debug('DSDConfigurationSerivce.join_activedirectory()')

        ad_context = self.modules['activedirectory'].context
        if not ad_context:
            return False

        os.environ['LOGNAME'] = 'root'
        p = pipeopen("/usr/local/bin/net -k ads join  '%s'" % ad_context.realm)
        out = p.communicate()
        if p.returncode != 0:
            self.logger.debug('DSDConfigurationSerivce.join_activedirectory(): FAILED: %s', out)
            return False

        self.logger.debug('DSDConfigurationSerivce.join_activedirectory(): SUCCESS')
        return True

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
        self.logger.debug('DSDConfigurationSerivce.enable(): id = %s', id)

        ds = self.datastore.get_by_id('directoryservices', id)
        if 'enable' in ds and ds['enable'] == True:
            return True

        self.__toggle_enable(id, 'enable', True)
        self.load_directoryservices()

        try: 

            # thread these
            #self.configure_hostname(id, enable=True)
            #self.configure_hosts(id, enable=True)
            self.configure_kerberos(id, enable=True)
            self.get_kerberos_ticket(id, enable=True)
            self.configure_nsswitch(id, enable=True)
            self.configure_openldap(id, enable=True)
            self.configure_nssldap(id, enable=True)
            self.configure_sssd(id, enable=True)
            self.configure_samba(id, enable=True)
            self.join_activedirectory(id, enable=True)
            self.configure_pam(id, enable=True)

        except Exception as e:
            self.logger.debug("XXX: caught exception %s", e)
            self.__toggle_enable(id, 'enable', False)
            self.load_directoryservices()
            return False

        return True

    def disable(self, id):
        self.logger.debug('DSDConfigurationSerivce.disable(): id = %s', id)

        ds = self.datastore.get_by_id('directoryservices', id)
        if 'enable' in ds and ds['enable'] == False:
            return True

        self.__toggle_enable(id, 'enable', False)
        self.load_directoryservices()

        # thread these
        self.configure_pam(id, enable=False)
        self.configure_samba(id, enable=False)
        self.configure_sssd(id, enable=False)
        self.configure_nssldap(id, enable=False)
        self.configure_openldap(id, enable=False)
        self.configure_nsswitch(id, enable=False)
        #self.get_kerberos_ticket(id)
        self.configure_kerberos(id, enable=False)
        #self.configure_hosts(id, enable=True)
        #self.configure_hostname(id, enable=False)

        return True


class Main(object):
    def __init__(self):
        self.config = None
        self.client = None
        self.datastore = None
        self.configstore = None
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

    def main(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-c', metavar='CONFIG', default=DEFAULT_CONFIGFILE, help='Middleware config file')
        args = parser.parse_args()
        configure_logging('/var/log/dsd.log', 'DEBUG')
        setproctitle.setproctitle('dsd')
        self.parse_config(args.c)
        self.init_datastore()
        self.init_dispatcher()
        self.client.resume_service('dsd.configuration')
        self.logger.info('Started')
        self.client.wait_forever()


if __name__ == '__main__':
    m = Main()
    m.main()
