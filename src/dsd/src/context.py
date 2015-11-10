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

class ContextBase(object):
    def __init__(self, context):
        self.context = context
        self.logger = context.logger
        self.config = context.configstore
        self.datastore = context.datastore
        self.client = context.client


class ActiveDirectoryContext(ContextBase):
    def __init__(self, context, domain, binddn, bindpw, modules):
        super(ActiveDirectoryContext, self).__init__(context)
        
        self.domain = domain
        self.binddn = binddn
        self.bindpw = bindpw
        self.realm = domain.upper()
        self.baseDN = None
        self.netbiosname = None
        self.handle = None
        self.dcs = []
        self.gcs = []
        self.kdcs = []

        self.modules = modules
        self.ad = modules['activedirectory'].instance
        self.kc = modules['kerberos'].instance

        self.error = None

    def context_init(self):

        try:
            self.handle = self.ad.get_connection_handle(
                self.domain,
                '%s@%s' % (self.binddn, self.domain),
                self.bindpw
            )

        except Exception as e:
            self.error = e
            return False
        

        self.dcs = self.ad.get_domain_controllers(self.domain)
        self.gcs = self.ad.get_global_catalog_servers(self.domain)
        self.kdcs = self.kc.get_kerberos_servers(self.domain)

        self.baseDN = self.ad.get_baseDN(self.handle)
        self.netbiosname = self.ad.get_domain_netbiosname(self.handle)

        return True

    def context_update(self, updated_fields):
        if 'domain' in updated_fields:
            return self.context_init()
        elif 'binddn' in updated_fields:
            return self.context_init()
        elif 'bindpw' in updated_fields:
            return self.context_init()

        return True

    def context_fini(self):
        self.domain = None
        self.binddn = None
        self.bindpw = None
        self.baseDN = None
        self.netbiosname = None
        self.dcs = None
        self.gcs = None
        self.kdcs = None
        self.handle = None
        self.modules = None
        self.ad = None
        self.kc = None
        self.error = None
        return True
     

class KerberosContext(object):
    pass

class LDAPContext(object):
    pass

class DirectoryContext(object):
    pass
