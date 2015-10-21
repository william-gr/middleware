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
from dispatcher.rpc import RpcException
from shared import BaseTestCase


class TestSystem(BaseTestCase):
    def tearDown(self):
        # set timeout value to original
        super(TestSystem, self).tearDown()

    def test_get_config_general(self):
        info = self.conn.call_sync('system.general.get_config')
        #print info 
        self.assertIsInstance(info, dict)
        self.assertGreater(len(info), 0)

    def test_query_system_general_timezones(self):
        info = self.conn.call_sync('system.general.timezones')
        self.assertIsInstance(info, list)
        self.assertGreater(len(info), 0)
    
    def test_query_system_general_keymaps(self):
        info = self.conn.call_sync('system.general.keymaps')
        self.assertIsInstance(info, list)
        self.assertGreater(len(info), 0)
        self.assertIsInstance(info[0], list)                   

    def test_query_get_config_system_ui(self):
        info = self.conn.call_sync('system.ui.get_config')
        self.assertIsInstance(info, dict)
        self.assertGreater(len(info), 0)
        #print info

    def test_query_system_advanced_get_config(self):
        info = self.conn.call_sync('system.advanced.get_config')
        #print info 
        self.assertIsInstance(info, dict)
        self.assertGreater(len(info), 0)
    
    def test_query_system_advanced_serial_ports(self):
        info = self.conn.call_sync('system.advanced.serial_ports')
        #print info 
        self.assertIsInstance(info, list)
    
    def test_query_system_info_hardware(self):
        info = self.conn.call_sync('system.info.hardware')
        #print info    # debug
        self.assertIsInstance(info, dict)
        self.assertGreater(len(info), 0)

    def test_query_system_info_load_avg(self):
        info = self.conn.call_sync('system.info.load_avg')
        #print info    # debug
        self.assertIsInstance(info, list)
        self.assertEqual(len(info), 3)

    def test_query_system_info_time(self):
        info = self.conn.call_sync('system.info.time')
        #print info    # debug
        self.assertIsInstance(info, dict)
        self.assertGreater(len(info), 0)        

    def test_query_system_info_version(self):
        info = self.conn.call_sync('system.info.version')
        #print info    # debug
        self.assertIsInstance(info, unicode)
        self.assertGreater(len(info), 0)    
        
    def test_query_system_info_uname_full(self):
        info = self.conn.call_sync('system.info.uname_full')
        self.assertIsInstance(info, list)
        self.assertGreater(len(info), 0)
        #print info
        
    


if __name__ == '__main__':
    unittest.main()	
