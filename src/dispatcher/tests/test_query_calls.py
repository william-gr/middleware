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

from dispatcher.rpc import RpcException
from shared import BaseTestCase



class QueryTest(BaseTestCase):
    def tearDown(self):
        super(QueryTest, self).tearDown()

    def test_query_volumes(self):
        volumes = self.conn.call_sync('volumes.query')
        pretty_print(volumes)

    def test_query_sessions(self):
        sessions = self.conn.call_sync('sessions.query')
        pretty_print(sessions)
    
        
    def test_query_all_disks(self):
        disks = self.conn.call_sync('disks.query')
        pretty_print(disks)
        self.assertIsInstance(disks, list)

    def test_query_boot_envoronments(self):
        res = self.conn.call_sync('boot.environments.query')
        pretty_print(res)
        self.assertTrue(len(res))
        self.assertIsInstance(res, list)
        self.assertIsInstance(res[0], dict)

    def test_query_zfs_pool(self):
        res = self.conn.call_sync('zfs.pool.query')
        pretty_print(res)    

    def atest_get_disk_path(self, disk):
        disks = self.conn.call_sync('volumes.get_disks_allocation')
        pretty_print(disks)  
        disks = self.conn.call_sync('volumes.find_media')
        pretty_print(disks)   

# HELPER
def pretty_print(res):
    if '-v' in sys.argv:
        print json.dumps(res, indent=4, sort_keys=True)


if __name__ == '__main__':
    unittest.main()
