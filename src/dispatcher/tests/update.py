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
import subprocess
import os

from dispatcher.rpc import RpcException
from shared import BaseTestCase


__doc__ = '''
This script is not really a unit testcase,
but rather a utility to update already 
installed train on the server
SHould be running prior to other tests
'''

class Updater(BaseTestCase):
    def tearDown(self):
        # set timeout value to original
        super(Updater, self).tearDown()

    
    def check_for_update(self):
        tid = self.submitTask('update.check', {
            'check_now': False,
            })
        self.assertTaskCompletion(tid)
        
    
    def verify(self):
    	'''
        verify the system
    	'''
    	self.task_timeout = 300
        tid = self.submitTask('update.verify')
        self.assertTaskCompletion(tid)

    def isUp(self):
        testhost = os.getenv('TESTHOST')
        command = 'ping -c 2 ' + testhost
        command = 'ping -c 2 -a -W 0.1 ' + testhost
        #try:
        #    out = subprocess.check_output(command.split())
        #except subprocess.CalledProcessError, data:
        res = os.system(command)
        if res:
            return False
        else:
            print 'OK'
            return True    

    def test_update_system(self):
        '''
        checks, updates, reboots, verifies
        '''
        self.task_timeout = 600
        payload = {'reboot_post_install': True}
        tid = self.submitTask('update.check')
        self.assertTaskCompletion(tid)
        train = self.conn.call_sync('update.get_current_train')
        pre_version = self.conn.call_sync('system.info.version')


        if self.conn.call_sync('update.is_update_available'):
            print 'Update available, downloading...'
            tid = self.submitTask('update.download') 
            self.assertTaskCompletion(tid)
            
            print 'Applying update...'
            tid = self.submitTask('update.update') 
            self.assertTaskCompletion(tid)
            
            print 'System will reboot...'
            while not self.isUp():
                time.sleep(10)
            # DEBUG
            #print self.conn.call_sync('update.update_info')     
        else:
            print 'No update available at this time...'    
        
        #print 'Verifying system...' 
        post_version = self.conn.call_sync('system.info.version')
        self.assertTrue(pre_version.split('-')[-1] <= post_version.split('-')[-1])  
        # disable until fixed
        #tid = self.submitTask('update.verify')
        #self.assertTaskCompletion(tid)    
            
           


if __name__ == '__main__':
    unittest.main()	
