#+
# Copyright 2014 iXsystems, Inc.
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
######################################################################

import unittest
import json
import sys

from freenas.dispatcher.rpc import RpcException
from shared import BaseTestCase

__doc__ = """  This group is tests are to verify that
the query return values are sane, 
but are good for debug purposes, 
just pass -v option to print the return values, example:

    python test_query.py -v QueryTest.test_query_volumes

"""

class QueryTest(BaseTestCase):
    def tearDown(self):
        super(QueryTest, self).tearDown()

    def test_query_volumes(self):
        volumes = self.conn.call_sync('volumes.query')
        self.pretty_print(volumes)

    def test_query_sessions(self):
        sessions = self.conn.call_sync('sessions.query')
        self.pretty_print(sessions)
    
        
    def test_disks_query(self):
        disks = self.conn.call_sync('disks.query')
        self.pretty_print(disks)
        self.assertIsInstance(disks, list)

    def test_boot_envoronments_query(self):
        res = self.conn.call_sync('boot.environments.query')
        self.pretty_print(res)
        self.assertTrue(len(res))
        self.assertIsInstance(res, list)
        self.assertIsInstance(res[0], dict)

    def test_zfs_pool_query(self):
        res = self.conn.call_sync('zfs.pool.query')
        self.pretty_print(res)
        self.assertIsInstance(res, list)    

    def atest_get_disks_allocation(self, disk):
        disks = self.conn.call_sync('volumes.get_disks_allocation', )
        self.pretty_print(disks)  
        disks = self.conn.call_sync('volumes.find_media')
        self.pretty_print(disks) 

    def test_scheduler_management_query(self):
        res = self.conn.call_sync('scheduler.management.query')
        self.pretty_print(res)
        self.assertIsInstance(res, list) 

    def test_system_advanced_get_config(self):
        res = self.conn.call_sync('system.advanced.get_config')
        self.pretty_print(res)
        self.assertIsInstance(res, dict)

    def test_system_ui_get_config(self):
        res = self.conn.call_sync('system.ui.get_config')
        self.pretty_print(res)
        self.assertIsInstance(res, dict)    

    def test_networkd_configuration_query_interfaces(self):
        res = self.conn.call_sync('networkd.configuration.query_interfaces')
        self.pretty_print(res)
        self.assertIsInstance(res, dict)    

    def test_service_ssh_get_config(self):
        res = self.conn.call_sync('service.ssh.get_config')
        self.pretty_print(res)
        self.assertIsInstance(res, dict) 

    def test_service_ttfp_get_config(self):
        res = self.conn.call_sync('service.tftp.get_config')
        self.pretty_print(res)
        self.assertIsInstance(res, dict) 

    def test_service_smartd_get_config(self):
        '''
        note: the 'enable' is always True
        in return value, it does not 
        actually show if the service is running
        or not. It suppose to always run,
        unless stopped by user for cli for example:
         "service smartd stop" 
        '''
        res = self.conn.call_sync('service.smartd.get_config')
        self.pretty_print(res)
        self.assertIsInstance(res, dict) 
        self.assertTrue(res['enable'])

    def test_statd_output_get_data_sources(self):
        res = self.conn.call_sync('statd.output.get_data_sources')
        self.pretty_print(res)
        self.assertIsInstance(res, list)
        self.assertNotEqual(res, [])             

    def test_shares_iscsi_target_query(self):
        res = self.conn.call_sync('shares.iscsi.target.query')
        self.pretty_print(res)
        self.assertIsInstance(res, list)

    def test_shares_query(self):
        res = self.conn.call_sync('shares.query')
        self.pretty_print(res)
        self.assertIsInstance(res, list)
        if len(res):
            self.assertIsInstance(res[0], dict)  

# ZFS
    def test_qfs_dataset_query(self):
        # all boots should be listed in here too
        res = self.conn.call_sync('zfs.dataset.query')
        self.pretty_print(res)
        self.assertIsInstance(res, list)
        if len(res):
            self.assertIsInstance(res[0], dict)  

    def test_etcd_generation_get_managed_files(self):
        '''
        TODO: testing on server side
        '''
        res = self.conn.call_sync('etcd.generation.get_managed_files')
        self.pretty_print(res)
        self.assertIsInstance(res, dict)

    def test_shares_query(self):
        '''
        '''
        res = self.conn.call_sync('shares.query')
        self.pretty_print(res)
        self.assertIsInstance(res, list)    


if __name__ == '__main__':
    unittest.main()
