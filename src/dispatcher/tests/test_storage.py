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
from freenas.dispatcher.rpc import RpcException
from shared import BaseTestCase
import os


class VolumeTest(BaseTestCase):
    def setUp(self):
        super(VolumeTest, self).setUp()
        self.task_timeout = 100

    def tearDown(self):
        # try to delete all volumes created with test
        for u in self.conn.call_sync('volumes.query', [('name', '~', 'Test*')]):
            self.assertTaskCompletion(self.submitTask('volume.destroy', u['name']))
        super(VolumeTest, self).tearDown()

    def test_query_volumes(self):
        volumes = self.conn.call_sync('volumes.query', [])
        self.assertIsInstance(volumes, list)
        self.pretty_print(volumes)

    def test_create_volume_auto_stripe(self):
        '''
        Create, test, destroy
        '''
        volname = 'TestVolumeAuto'
        v =  self.conn.call_sync('volumes.query', [('name', '=', volname)])
        # destroy leftovers so that test do not fail
        if len(v):
            tid = self.submitTask('volume.destroy', volname)
            self.assertTaskCompletion(tid)
        available = self.conn.call_sync('volumes.get_available_disks')    
        if available:
            tid = self.submitTask('volume.create_auto', volname, 'zfs', available[:1])
            self.assertTaskCompletion(tid)
        else:
            raise unittest.SkipTest("No disks are available for creating volume, test did not run")  
         
        v =  self.conn.call_sync('volumes.query', [('name', '=', volname)])
        self.pretty_print(v)
        self.assertEqual(v[0]['name'], volname)
        

    def test_volumes_find(self):
        exported =  self.conn.call_sync('volumes.find')    

        
    def test_create_volume_auto_available_disks(self):
        volname = 'TestVolumeAuto'
        v =  self.conn.call_sync('volumes.query', [('name', '=', volname)])
        if len(v):
            tid = self.submitTask('volume.destroy', volname)
            self.assertTaskCompletion(tid)
        
        available = self.conn.call_sync('volumes.get_available_disks')
        if not available:
            raise unittest.SkipTest("No disks are available for creating volume, test did not run")
        else:
            tid = self.submitTask('volume.create_auto', volname, 'zfs', available)
            self.assertTaskCompletion(tid)

    
    def test_create_stripe(self):
        volname = "TestVolume"
        v =  self.conn.call_sync('volumes.query', [('name', '=', volname)])
        if len(v):
            tid = self.submitTask('volume.destroy', volname)
            self.assertTaskCompletion(tid)
        
        available = self.conn.call_sync('volumes.get_available_disks')
        if available:
            vdevs =  [{'type': 'disk', 'path': str(available[0])}]
            payload = {
                "name": volname,
                "type": 'zfs',
                "topology": {'data': vdevs},                    
            }
            tid = self.submitTask('volume.create', payload)
            self.assertTaskCompletion(tid)
            #  get_dataset_path( string volname, string dsname )
            # if volume is created, so is dataset?
            #v =  self.conn.call_sync('volumes.get_dataset_path', [('name', '=', volname)])
        else:
            raise unittest.SkipTest("No disks are available for creating volume, test did not run")       
                

    def test_create_mirror(self):
        volname = "TestVolumeMirror"
        v =  self.conn.call_sync('volumes.query', [('name', '=', volname)])
        if len(v):
            tid = self.submitTask('volume.destroy', volname)
            self.assertTaskCompletion(tid)
        
        available = self.conn.call_sync('volumes.get_available_disks')
        
        if len(available) >= 2:   
            vdevs =  [
            {'type': 'disk', 'path': str(available[0])}, 
            {'type': 'disk', 'path': str(available[1])} ]
            payload = {
                "name": volname,
                "type": 'zfs',
                "topology": {'data': vdevs},                    
            }
            tid = self.submitTask('volume.create', payload)
            self.assertTaskCompletion(tid)
        else:
            raise unittest.SkipTest("No disks are available for creating volume, test did not run")     


    def test_create_RAIDZ(self):
        volname = "TestVolume"
        v =  self.conn.call_sync('volumes.query', [('name', '=', volname)])
        if len(v):
            tid = self.submitTask('volume.destroy', volname)
            self.assertTaskCompletion(tid)
        available = self.conn.call_sync('volumes.get_available_disks')

        if len(available) < 3:
            raise unittest.SkipTest("No disks are available for creating volume, test did not run")   
            
        else:    
            vdevs =  [{'type': 'disk', 'path': str(available[0])}, 
            {'type': 'disk', 'path': (available[1])},
            {'type': 'disk', 'path': (available[2])}]
            payload = {
                "name": volname,
                "type": 'zfs',
                "topology": {'data': vdevs},                    
            }
            tid = self.submitTask('volume.create', payload)
            self.assertTaskCompletion(tid)
            disks =  self.conn.call_sync('volumes.get_volume_disks', volname)
            self.assertEqual(disks, available[:3])

 
    def atest_get_volume_disks(self):
        pass


    def get_available_disks(self):
        disks = self.conn.call_sync('volumes.get_available_disks')
        return disks   

    def test_volumes_find(self):
        found = self.conn.call_sync('volumes.find')
        
        self.assertIsInstance(found, list)
        if len(found):
            self.assertIsInstance(found[0], dict)            
        
    def atest_get_disk_path(self, disk):
        disks = self.conn.call_sync('volumes.get_disks_allocation')
        self.pretty_print(disks)  
    

    def atest_detach_reimport_all_volumes(self):
        # detach all volumes created with test
        vols = self.conn.call_sync('volumes.query')
        for v in vols:
            print 'Detaching ' + str(v['name'])
            tid = self.submitTask('volume.detach', v['name'])
        detached = self.conn.call_sync('volumes.find')
        for v in detached:
            if not v['status'] == 'DEGRADED':
                payload = [{'id': str(v['id']), 'new_name': 'new_' + str(v['name']), 'params': {} }]
                tid = self.submitTask('volume.import', payload)
            imported =  self.conn.call_sync('volumes.query', [('name', '=', v['name'])])    
                    

    def test_create_manual_snapshot(self):
        snapshots = self.conn.call_sync('volumes.snapshots.query')
        self.pretty_print(snapshots)
        self.assertIsInstance(snapshots, list)
           

    def atest_import_disk(self):
        pass

    def test_create_volume2(self):
        '''
        Specify different topology
               "topology": {
            "cache": [], 
            "data": [
                {
                    "children": [], 
                    "guid": "10725309058824566037", 
                    "path": "/dev/da5", 
                    "stats": {
                        "bytes": [
                            0, 
                            483328, 
                            1673216, 
                            8704, 
                            0
                        ], 
                        "checksum_errors": 0, 
                        "configured_ashift": 9, 
                        "fragmentation": 18446744073709551615, 
                        "logical_ashift": 9, 
                        "ops": [
                            1, 
                            7, 
                            72, 
                            11, 
                            0
                        ], 
                        "physical_ashift": 0, 
                        "read_errors": 0, 
                        "timestamp": 7390003153, 
                        "write_errors": 0
                    }, 
                    "status": "ONLINE", 
                    "type": "disk"
                }

        ''' 
        pass
        


class DatasetTest(BaseTestCase):
    '''
    TODO: add setUpClass and tearDownClass
    '''
    
    def setUp(self):
        super(DatasetTest, self).setUp()
        self.task_timeout = 200
        self.volname = 'TestDatasetVolume'
        self.createVolume()


    @classmethod
    def tearDownOnce(cls):
        #v =  self.conn.call_sync('volumes.query', [('name', '`', "*Dataset*")])
        for v in self.conn.call_sync('volumes.query', [('name', '~', '*Dataset*')]):
            self.assertTaskCompletion(self.submitTask('volume.destroy', u['name']))
        super(DatasetTest, self).tearDownOnce()

    def tearDown(self):
        # try to delete all volumes created with test
        #for u in self.conn.call_sync('volumes.query', [('volume', '~', 'testVolume.*')]):
        #    self.assertTaskCompletion(self.submitTask('volume.detach', u['name']))
        super(DatasetTest, self).tearDown()

    

    def test_create_dataset(self):
        payload = {'type': 'FILESYSTEM'}
        tid = self.submitTask('volume.dataset.create', self.volname, self.volname + '/new_dataset', 'FILESYSTEM')
        self.assertTaskCompletion(tid)


    def test_get_dataset_tree(self):
        tree = self.conn.call_sync('volumes.get_dataset_tree', self.volname)
        self.pretty_print(tree)
        self.assertIsInstance(tree, dict)

    def test_query_zfs_dataset(self):
        datasets = self.conn.call_sync('zfs.dataset.query')
        self.pretty_print(datasets)

    def createVolume(self):
        v =  self.conn.call_sync('volumes.query', [('name', '=', self.volname)])
        
        if v:
            return
        available = self.conn.call_sync('volumes.get_available_disks')
        if not available:
            self.skip("No disks are available for creating volume, test did not run")  
        else:
            exists = self.conn.call_sync('volumes.query', [('name', '=', self.volname)])
            if not exists:
                tid = self.submitTask('volume.create_auto', self.volname, 'zfs', available)
                self.assertTaskCompletion(tid)


if __name__ == '__main__':
    unittest.main()
