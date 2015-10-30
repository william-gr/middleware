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

import os
import sys
import argparse
import json
import logging
import subprocess
import setproctitle
import socket
import threading
import time

from datastore import get_datastore, DatastoreException
from datastore.config import ConfigStore
from dispatcher.client import Client, ClientError
from dispatcher.rpc import RpcService, RpcException, private

from fnutils import configure_logging
from fnutils.debug import DebugService

DEFAULT_CONFIGFILE = '/usr/local/etc/middleware.conf'

class DSDConfigurationService(RpcService):
    def __init__(self, context):
        self.context = context
        self.logger = context.logger
        self.config = context.configstore
        self.datastore = context.datastore
        self.client = context.client

    def configure_hostname(self):
        self.logger.debug('DSDConfigurationSerivce.configure_hostname()')
        self.client.call_sync('etcd.generation.generate_group', 'hostname')

    def configure_hosts(self):
        self.logger.debug('DSDConfigurationSerivce.configure_hosts()')
        self.client.call_sync('etcd.generation.generate_group', 'hosts')

    def configure_kerberos(self):
        self.logger.debug('DSDConfigurationSerivce.configure_kerberos()')
        self.client.call_sync('etcd.generation.generate_group', 'kerberos')

    def get_kerberos_ticket(self):
        self.logger.debug('DSDConfigurationSerivce.get_kerberos_ticket()')

    def configure_nsswitch(self):
        self.logger.debug('DSDConfigurationSerivce.configure_nsswitch()')
        self.client.call_sync('etcd.generation.generate_group', 'nsswitch')

    def configure_openldap(self):
        self.logger.debug('DSDConfigurationSerivce.configure_openldap()')
        self.client.call_sync('etcd.generation.generate_group', 'openldap')

    def configure_nss_ldap(self):
        self.logger.debug('DSDConfigurationSerivce.configure_nssldap()')
        self.client.call_sync('etcd.generation.generate_group', 'nss_ldap')

    def configure_sssd(self):
        self.logger.debug('DSDConfigurationSerivce.configure_sssd()')
        self.client.call_sync('etcd.generation.generate_group', 'sssd')

    def configure_samba(self):
        self.logger.debug('DSDConfigurationSerivce.configure_samba()')
        #self.client.call_sync('etcd.generation.generate_group', 'samba')

    def join_activedirectory(self):
        self.logger.debug('DSDConfigurationSerivce.join_activedirectory()')

    def configure_pam(self):
        self.logger.debug('DSDConfigurationSerivce.configure_pam()')
        self.client.call_sync('etcd.generation.generate_group', 'pam')

    def configure_activedirectory(self):
        self.logger.debug('DSDConfigurationSerivce.configure_activedirectory()')
        self.client.call_sync('etcd.generation.generate_group', 'activedirectory')

    def configure_ldap(self):
        self.logger.debug('DSDConfigurationSerivce.configure_ldap()')
        self.client.call_sync('etcd.generation.generate_group', 'ldap')


class Main(object):
    def __init__(self):
        self.config = None
        self.client = None
        self.datastore = None
        self.configstore = None
        self.rstock_thread = None
        self.logger = logging.getLogger('dsd')

    def parse_config(self, filename):
        try:
            f = open(filename, 'r')
            self.config = json.load(f)
            f.close()
        except IOError, err:
            self.logger.error('Cannot read config file: %s', err.message)
            sys.exit(1)
        except ValueError, err:
            self.logger.error('Config file has unreadable format (not valid JSON)')
            sys.exit(1)

    def init_datastore(self, resume=False):
        try:
            self.datastore = get_datastore(self.config['datastore']['driver'],
                self.config['datastore']['dsn'])
        except DatastoreException, err:
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
            except socket.error, err:
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

    def main(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-c', metavar='CONFIG', default=DEFAULT_CONFIGFILE, help='Middleware config file')
        args = parser.parse_args()
        configure_logging('/var/log/dsd.log', 'DEBUG')
        setproctitle.setproctitle('dsd')
        self.parse_config(args.c)
        self.init_datastore()
        self.init_dispatcher()
        #self.client_wait_forever()


if __name__ == '__main__':
    m = Main()
    m.main()
