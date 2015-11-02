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


class TestUpdate(BaseTestCase):
    def tearDown(self):
        # set timeout value to original
        self.task_timeout = 30
        super(TestUpdate, self).tearDown()

    def test_query_update_info(self):
        check = self.conn.call_sync('update.is_update_available')
        if check:
            info = self.conn.call_sync('update.update_info')
            #print "Update info: " + str(info)  # debug 
            self.assertIsNotNone(info)

    def test_obtain_opts(self): 
        check = self.conn.call_sync('update.is_update_available')
        ops = self.conn.call_sync('update.get_update_ops')
        if check:
            self.assertIsNotNone(ops)

    def test_query_current_train(self):
        config = self.conn.call_sync('update.get_config')
        train = self.conn.call_sync('update.get_current_train')
        self.assertIsNotNone(config)
        self.assertEqual(train, config['train'])

    def test_obtain_changelog(self):
        check = self.conn.call_sync('update.is_update_available')
        print check
        changelog = self.conn.call_sync('update.obtain_changelog')
        self.pretty_print(changelog)
        if check:
            self.assertNotEqual(changelog, [u""])
        else:
            self.assertEqual(changelog, [u""])    

    def test_query_trains(self):
        trains = self.conn.call_sync('update.trains')
        self.pretty_print(trains)  
        self.assertIsNotNone(trains)

    def test_check_for_update(self):
        tid = self.submitTask('update.check', {
            'check_now': False,
            })
        self.assertTaskCompletion(tid)
        tid = self.submitTask('update.check', {
            'check_now': True,
            })
        self.assertTaskCompletion(tid)
    
    def test_update_verify(self):
    	'''
    	Verification takes long time
        so increase timeout
    	'''
    	self.task_timeout = 300
        tid = self.submitTask('update.verify')
        self.assertTaskCompletion(tid)

    

if __name__ == '__main__':
    unittest.main()	
