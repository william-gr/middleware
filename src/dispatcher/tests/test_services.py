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
import inspect
from shared import BaseTestCase


class ServicesTest(BaseTestCase):
    # SSHD
    def test_start_stop_sshd(self):
        # will fail if trying to stop from stopped state
        sname = inspect.stack()[0][3].split('_')[-1]
        if self.isRunning(sname):  # service['state'] != 'STOPPED':
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'stop'))
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))

    def test_sshd_restart(self):
    	sname = str(inspect.stack()[0][3].split('_')[-1])
        if self.isRunning('sshd'): 
            self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))
        self.assertTaskCompletion(self.submitTask('service.manage', 'sshd', 'restart'))
            
    def test_configure_sshd(self):
    	self.assertTaskCompletion(self.submitTask('service.manage', 'sshd', 'restart'))
        self.assertTaskCompletion(self.submitTask('service.configure', 'sshd', {'port': 9922}))
        self.assertTaskCompletion(self.submitTask('service.configure', 'sshd', {"port": 22, "compression": 'no'}))

  
# dydns
    def test_start_stop_dyndns(self):
        # will fail if trying to stop from stopped state
        sname = inspect.stack()[0][3].split('_')[-1]
        if self.isRunning(sname):  
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'stop'))
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))

    def test_restart_dyndns(self):
    	sname = str(inspect.stack()[0][3].split('_')[-1])
        if self.isRunning(sname): 
            self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'restart'))
            
    def atest_configure_dydns(self):
    	self.assertTaskCompletion(self.submitTask('service.manage', 'dydns', 'restart'))
        self.assertTaskCompletion(self.submitTask('service.configure', \
        	'dydns', {'username': 'root', 'password': 'abcd1234', 'update_period': 60, 'forced_update_period': 80}))
        
    
# dydns
    def test_start_stop_ipfs(self):
        # will fail if trying to stop from stopped state
        sname = inspect.stack()[0][3].split('_')[-1]
        if self.isRunning(sname):  
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'stop'))
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))

    def test_restart_ipfs(self):
    	sname = str(inspect.stack()[0][3].split('_')[-1])
        if self.isRunning(sname): 
            self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'restart'))
            
    def atest_configure_ipfs(self):
    	self.assertTaskCompletion(self.submitTask('service.manage', 'ipfs', 'restart'))
        self.assertTaskCompletion(self.submitTask('service.configure', 'ipfs', {'path': 'mnt/tank/smth'}))
        

    ############# AFP    
    def test_start_stop_afp(self):
    	sname = inspect.stack()[0][3].split('_')[-1]
    	if self.isRunning(sname):
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'stop'))
    	self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))

    def test_restart_afp(self):
    	sname = inspect.stack()[0][3].split('_')[-1]
    	if not self.isRunning(sname):
            self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))        
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'restart'))

    def atest_configure_afp(self):
    	'''
        Tests that the afp service 
        restart and configure working. 
        Not a functional test, 
    	'''
    	sname = inspect.stack()[0][3].split('_')[-1]
        if not self.isRunning(sname):
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))
    	self.assertTaskCompletion(self.submitTask('service.configure', 'afp', \
    		{"connections_limit": 20, 'guest_enable': True, 'guest_user': 'nobody'}))

    ############# SNMP    
    def test_start_stop_snmp(self):
    	sname = inspect.stack()[0][3].split('_')[-1]
    	if self.isRunning(sname):
    		self.assertTaskCompletion(self.submitTask('service.manage', sname, 'stop'))
    	# and then start    
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))

    def test_restart_snmp(self):
    	sname = inspect.stack()[0][3].split('_')[-1]
    	
    	if not self.isRunning(sname):
           self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))   
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'restart'))    

    def test_configure_snmp(self):
    	'''
        Tests that the afp service 
        restart and configure working. 
        Not a functional test, 
    	'''
    	sname = inspect.stack()[0][3].split('_')[-1]
        if not self.isRunning(sname):
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))
        self.assertTaskCompletion(self.submitTask('service.configure', sname, \
    		{'contact': 'nobody', 'v3_password': 'abcd1234', 'v3_privacy_passphrase': 'abcd1234'}))	

    ################# CIFS
    def test_start_stop_cifs(self):
        '''
        Can start from stopped state
        '''
        sname = inspect.stack()[0][3].split('_')[-1]
        #service = self.conn.call_sync('services.query', [('name', '=', sname)], {'single': True})
        if self.isRunning(sname):
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'stop'))
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))

    def test_restart_cifs(self):
    	'''
    	Can restart
    	'''
    	sname = inspect.stack()[0][3].split('_')[-1]
    	if not self.isRunning(sname):
            self.assertTaskCompletion(self.submitTask('service.manage', 'cifs', 'start'))
        self.assertTaskCompletion(self.submitTask('service.manage', 'cifs', 'restart'))

    def atest_configure_cifs(self):
    	'''
        NOT WORKING
    	'''
    	sname = inspect.stack()[0][3].split('_')[-1]
    	#service = self.conn.call_sync('services.query', [('name', '=', 'cifs')], {'single': True})
    	#print service
    	if not self.isRunning(sname):
    		self.assertTaskCompletion(self.submitTask('service.manage', 'cifs', 'start'))
    	self.assertTaskCompletion(self.submitTask('service.manage', 'cifs', 'reload'))
    	self.assertTaskCompletion(self.submitTask('service.configure', 'cifs', \
    		{"zeroconf": False, 'log_level': 'mininum', 'netbiosname': ['freenas']}))
	
    
############# riak
    def test_start_stop_riak_cs(self):
    	#sname = inspect.stack()[0][3].split('_')[-1]
    	if self.isRunning('riak_cs'): 
    	    self.assertTaskCompletion(self.submitTask('service.manage', 'riak_cs', 'stop'))
    	self.assertTaskCompletion(self.submitTask('service.manage', 'riak_cs', 'start'))

    def test_restart_riak_cs(self):
    	#sname = inspect.stack()[0][3].split('_')[-1]
    	service = self.conn.call_sync('services.query', [('name', '=', 'riak_cs')], {'single': True})
    	if not self.isRunning('riak_cs'):
           self.assertTaskCompletion(self.submitTask('service.manage', 'riak_cs', 'start')) 
        self.assertTaskCompletion(self.submitTask('service.manage', 'riak_cs', 'restart'))    

###################### FTP
    def test_start_stop_ftp(self):
    	sname = inspect.stack()[0][3].split('_')[-1]
    	if self.isRunning(sname):
    		self.assertTaskCompletion(self.submitTask('service.manage', sname, 'stop'))
    	# and then start    
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))

    def test_restart_ftp(self):
    	sname = inspect.stack()[0][3].split('_')[-1]
    	
    	if self.isRunning(sname):
            self.assertTaskCompletion(self.submitTask('service.manage', sname, 'restart'))    

    def atest_configure_ftp(self):
    	'''
        Tests that the ftp service 
        restart and configure working. 
        Not a functional test, 
    	'''
    	sname = inspect.stack()[0][3].split('_')[-1]
        if self.isRunning(sname):
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'restart'))
    	else:
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))    
    	self.assertTaskCompletion(self.submitTask('service.configure', sname, \
    	 {"only_anonymous": True, 'ip_connections': 15, 'reverse_dns': False}))
        
    
    ####################### NFS
    def test_start_stop_nfs(self):
    	sname = inspect.stack()[0][3].split('_')[-1]
    	if self.isRunning(sname):
    		self.assertTaskCompletion(self.submitTask('service.manage', sname, 'stop'))
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))

    def test_restart_nfs(self):
    	sname = inspect.stack()[0][3].split('_')[-1]
    	if self.isRunning(sname):
            self.assertTaskCompletion(self.submitTask('service.manage', sname, 'restart'))

    def test_configure_nfs(self):
    	'''
        Tests that the ftp service 
        restart and configure working. 
        Not a functional test, 
    	'''
    	self.assertTaskCompletion(self.submitTask('service.manage', 'nfs', 'restart'))
    	self.assertTaskCompletion(self.submitTask('service.configure', 'nfs', \
    		{"udp": True, 'v4': True, 'rpclockd_port': 22, 'nonroot': False}))


    ############# SMARTD
    def atest_start_stop_smartd(self):
    	sname = str(inspect.stack()[0][3].split('_')[-1])
    	if self.isRunning(sname): 
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'stop'))
    	self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))

    def atest_restart_smartd(self):
    	sname = str(inspect.stack()[0][3].split('_')[-1])
    	
    	#if not self.isRunning(sname):
        #    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start')) 
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'restart'))    

    def atest_configure_smartd(self):
    	'''
        Configure service
    	'''
        sname = inspect.stack()[0][3].split('_')[-1]
        if not self.isRunning(sname):
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))
    	# uncomment
    	#self.assertTaskCompletion(self.submitTask('service.configure', 'webdav', \
    	#	{"connections_limit": 20, 'guest_enable': True, 'guest_user': 'nobody'}))    	

############# rsyncd   
    def test_start_stop_rsyncd(self):
    	sname = str(inspect.stack()[0][3].split('_')[-1])
    	if self.isRunning(sname): 
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'stop'))
    	self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))

    def test_restart_rsyncd(self):
    	sname = str(inspect.stack()[0][3].split('_')[-1])
    	
    	if not self.isRunning(sname):
            self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start')) 
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'restart'))    

    def test_configure_rsyncd(self):
    	'''
        Configure service
    	'''
        sname = inspect.stack()[0][3].split('_')[-1]
        if not self.isRunning(sname):
    	    self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))
    	self.assertTaskCompletion(self.submitTask('service.configure', sname, \
    		{"port": 875})) 

############# webdav   
    def test_start_stop_webdav(self):
        sname = str(inspect.stack()[0][3].split('_')[-1])
        if self.isRunning(sname): 
            self.assertTaskCompletion(self.submitTask('service.manage', sname, 'stop'))
        self.assertTaskCompletion(self.submitTask('service.manage', sname, 'start'))

    def test_restart_webdav(self):
        sname = str(inspect.stack()[0][3].split('_')[-1])
        
        if not self.isRunning(sname):
            tid = self.submitTask('service.manage', sname, 'start')
            self.assertTaskCompletion(tid) 
        tid = self.submitTask('service.manage', sname, 'restart')    
        self.assertTaskCompletion(tid)    

    def atest_configure_webdav(self):
        '''
        Configure service
        '''
        sname = inspect.stack()[0][3].split('_')[-1]
        if not self.isRunning(sname):
            tid = self.submitTask('service.manage', sname, 'start')
            self.assertTaskCompletion(tid)
        tid = self.submitTask('service.configure', sname, {"port": 80})    
        self.assertTaskCompletion(tid) 

## ISCI
    def test_service_iscsi_get_config(self):
        '''
        Configure service
        '''
        config = self.conn.call_sync('service.iscsi.get_config')
        self.assertIsInstance(config, dict)
        
    
######## HELPERS
    def isRunning(self, sname):
        service = self.conn.call_sync('services.query', [('name', '=', str(sname))], {'single': True})
        if service['state'] == 'RUNNING':
            return True
        return False		

    ######################### QUERY
    def test_query_all_services(self):
        services = self.conn.call_sync('services.query')
        for s in services:
            print s
        self.assertIsInstance(services, list)






if __name__ == '__main__':
    unittest.main()
