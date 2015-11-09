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

import ldap3
import logging
import sys

logger = logging.getLogger('activedirectory')

#
# domainFunctionality, forestFunctionality, domainControllerFunctionality
#
DS_BEHAVIOR_WIN2000 = 0
DS_BEHAVIOR_WIN2003_WITH_MIXED_DOMAINS = 1
DS_BEHAVIOR_WIN2003 = 2
DS_BEHAVIOR_WIN2008 = 3
DS_BEHAVIOR_WIN2008R2 = 4
DS_BEHAVIOR_WIN2012 = 5
DS_BEHAVIOR_WIN2012R2 = 6
DS_BEHAVIOR_WINTHRESHOLD = 7

#
# sAMAccountType
#
SAM_DOMAIN_OBJECT             = 0x00000000
SAM_GROUP_OBJECT              = 0x10000000
SAM_NON_SECURITY_GROUP_OBJECT = 0x10000001
SAM_ALIAS_OBJECT              = 0x20000000
SAM_NON_SECURITY_ALIAS_OBJECT = 0x20000001
SAM_USER_OBJECT               = 0x30000000
SAM_MACHINE_ACCOUNT           = 0x30000001
SAM_TRUST_ACCOUNT             = 0x30000002
SAM_APP_BASIC_GROUP           = 0x40000000
SAM_APP_QUERY_GROUP           = 0x40000001
SAM_ACCOUNT_TYPE_MAX          = 0x7fffffff

#
# groupType
#
GROUP_TYPE_BUILTIN_LOCAL_GROUP = 0x00000001 
GROUP_TYPE_ACCOUNT_GROUP       = 0x00000002
GROUP_TYPE_RESOURCE_GROUP      = 0x00000004
GROUP_TYPE_UNIVERSAL_GROUP     = 0x00000008
GROUP_TYPE_APP_BASIC_GROUP     = 0x00000010
GROUP_TYPE_APP_QUERY_GROUP     = 0x00000020
GROUP_TYPE_SECURITY_ENABLED    = 0x80000000

def _v(mydict, key):
    if key in mydict and mydict[key]:
        return mydict[key]
    return None

class ActiveDirectory(object):
    class ActiveDirectoryHandle(object):
        def __init__(self, host, binddn, bindpw):
            self.__host = host
            self.__binddn = binddn
            self.__bindpw = bindpw
            self.__dchandle = self.get_dc_handle()
            self.__gchandle = self.get_gc_handle()

        def get_connection_handle(self, host, port, binddn, bindpw):
            server = ldap3.Server(host, port=port, get_info=ldap3.ALL)
            conn = ldap3.Connection(server, user=binddn, password=bindpw,
                authentication=ldap3.AUTH_SIMPLE, auto_bind=True)
            return conn

        @property
        def dchandle(self):
            return self.__dchandle

        def get_dc_handle(self):
            return self.get_connection_handle(
                self.__host,
                389,
                self.__binddn,
                self.__bindpw
            )

        @property
        def gchandle(self):
            return self.__gchandle

        def get_gc_handle(self):
            return self.get_connection_handle(
                self.__host,
                3268,
                self.__binddn,
                self.__bindpw
            )

    def __init__(self, *args,  **kwargs):
        self.dispatcher = kwargs['dispatcher']
        self.datastore = kwargs['datastore']

        sys.path.extend(['/usr/local/lib/dsd/modules/'])
        from dsdns import DSDNS

        self.dsdns = DSDNS(
            dispatcher=self.dispatcher,
            datastore=self.datastore,
        )

    def get_directory_type(self):
        return "activedirectory"

    def get_connection_handle(self, host, binddn, bindpw):
        return self.ActiveDirectoryHandle(host, binddn, bindpw)

    def get_ldap_servers(self, domain, site=None):
        dcs = []
        if not domain:
            return dcs

        host = "_ldap._tcp.%s" % domain
        if site:
            host = "_ldap._tcp.%s._sites.%s" % (site, domain)

        dcs = self.dsdns.get_SRV_records(host)
        return dcs

    def get_domain_controllers(self, domain, site=None):
        dcs = []
        if not domain:
            return dcs

        host = "_ldap._tcp.dc._msdcs.%s" % domain
        if site:
            host = "_ldap._tcp.%s._sites.dc._msdcs.%s" % (site, domain)

        dcs = self.dsdns.get_SRV_records(host)
        return dcs

    def get_primary_domain_controllers(self, domain):
        pdcs = []
        if not domain:
            return pdcs

        host = "_ldap._tcp.pdc._msdcs.%s"

        pdcs = self.dsdns.get_SRV_records(host)
        return pdcs

    def get_global_catalog_servers(self, domain, site=None):
        gcs = []
        if not domain:
            return gcs

        host = "_gc._tcp.%s" % domain
        if site:
            host = "_gc._tcp.%s._sites.%s" % (site, domain)

        gcs = self.dsdns.get_SRV_records(host)
        return gcs

    def get_forest_global_catalog_servers(self, forest, site=None):
        fgcs = []
        if not forest:
            return fgcs

        host = "_ldap._tcp.gc._msdcs.%s" % forest
        if site:
            host = "_ldap._tcp.%s._sites.gc._msdcs.%s" % (site, forest)

        fgcs = self.dsdns.get_SRV_records(host)
        return fgcs

    def get_rootDSE(self, handle):
        dchandle = handle.dchandle

        dchandle.search('',
            '(objectclass=*)',
            search_scope=ldap3.BASE,
            attributes=ldap3.ALL_ATTRIBUTES,
        )

        if not dchandle.result:
            return None

        return dchandle.response[0]

    def get_rootDN(self, handle):
        rootDSE = self.get_rootDSE(handle)
        if not rootDSE:
            return None

        attributes = _v(rootDSE, 'attributes')
        if not attributes:
            return None

        rootDN = _v(attributes, 'rootDomainNamingContext')
        if not rootDN:
            return None

        return rootDN[0].strip()
        
    def get_baseDN(self, handle):
        rootDSE = self.get_rootDSE(handle)
        if not rootDSE:
            return None

        attributes = _v(rootDSE, 'attributes')
        if not attributes:
            return None

        baseDN = _v(attributes, 'defaultNamingContext')
        if not baseDN:
            return None

        return baseDN[0].strip()

    def get_configurationDN(self, handle):
        rootDSE = self.get_rootDSE(handle)
        if not rootDSE:
            return None

        attributes = _v(rootDSE, 'attributes')
        if not attributes:
            return None

        configurationDN = _v(attributes, 'configurationNamingContext')
        if not configurationDN:
            return None

        return configurationDN[0].strip()

    def get_forest_functionality(self, handle):
        rootDSE = self.get_rootDSE(handle)
        if not rootDSE:
            return None

        attributes = _v(rootDSE, 'attributes')
        if not attributes:
            return None

        forest_functionality = _v(attributes, 'forestFunctionality')
        if not forest_functionality:
            return None

        return int(forest_functionality[0].strip())

    def get_domain_functionality(self, handle):
        rootDSE = self.get_rootDSE(handle)
        if not rootDSE:
            return None

        attributes = _v(rootDSE, 'attributes')
        if not attributes:
            return None

        domain_functionality = _v(attributes, 'domainFunctionality')
        if not domain_functionality:
            return None

        return int(domain_functionality[0].strip())

    def get_domain_controller_functionality(self, handle):
        rootDSE = self.get_rootDSE(handle)
        if not rootDSE:
            return None

        attributes = _v(rootDSE, 'attributes')
        if not attributes:
            return None

        domain_controller_functionality = _v(attributes, 'domainControllerFunctionality')
        if not domain_controller_functionality:
            return None

        return int(domain_controller_functionality[0].strip())

    def get_domain_netbiosname(self, handle):
        dchandle = handle.dchandle

        baseDN = self.get_baseDN(handle)
        configurationDN = self.get_configurationDN(handle)

        filter = "(&(objectcategory=crossref)(nCName=%s))" % baseDN.encode('utf-8')
        dchandle.search(configurationDN,
            filter,
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )

        if not dchandle.result:
            return None

        attributes = _v(dchandle.response[0], 'attributes')
        if not attributes:
            return None

        netbiosname = _v(attributes, 'nETBIOSName')
        if not netbiosname:
            return None

        return netbiosname.strip()

    def get_partitions(self, handle, **kwargs):
        dchandle = handle.dchandle

        configurationDN = self.get_configurationDN(handle)
        baseDN = "CN=Partitions,%s" % configurationDN

        filter = None
        keys = ['netbiosname', 'name', 'cn', 'dn', 'distinguishedname', 'ncname']
        for k in keys:
            if kwargs.has_key(k) and kwargs[k]:
                filter = "(%s=%s)" % (k, kwargs[k].encode('utf-8'))
                break

        if filter is None:
            filter = "(cn=*)"

        dchandle.search(baseDN,
            filter, 
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES,
        )

        if not dchandle.result:
            return None

        partitions = []
        for result in dchandle.response:
            attributes = _v(result, 'attributes')
            if not attributes: 
                continue
            partitions.append(attributes)

        return partitions

    def get_root_domain(self, handle):
        rootDN = self.get_rootDN(handle)
        partitions = self.get_partitions(handle, ncname=rootDN)
        if not partitions:
            return None

        domain = None
        try: 
            domain = partitions[0]['dnsRoot'][0]

        except: 
            return None

        return domain.strip()

    def get_domain(self, handle, **kwargs):
        partitions = self.get_partitions(handle, **kwargs)
        if not partitions:
            return None 

        domain = None
        try:
            domain = partitions[0]['dnsRoot'][0]

        except:
            return None

        return domain.strip()

    def get_domains(self, handle, **kwargs):
        dchandle = handle.dchandle
        gchandle = handle.gchandle

        gchandle.search('',
            '(objectclass=domain)',
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )

        if not gchandle.result:
            return None

        domains = []
        for result in gchandle.response:
            attributes = _v(result, 'attributes')
            if not attributes: 
                continue
 
            domains.append(attributes)

        configurationDN = self.get_configurationDN(handle)
        results = []

        haskey = False
        keys = ['netbiosname', 'name', 'cn', 'dn', 'distinguishedname', 'ncname']
        for domain in domains:
            dn = _v(domain, 'distinguishedName')
            if not dn:
                continue
            dn = dn.strip()

            filter = None
            if len(kwargs) > 0:
                haskey = True
                for k in keys: 
                    if kwargs.has_key(k) and kwargs[k]:
                        filter = "(&(objectcategory=crossref)(%s=%s))" % (k, kwargs[k].encode('utf-8'))
                        break

            if filter is None:
                filter = "(&(objectcategory=crossref)(nCName=%s))" % dn.encode('utf-8')

            dchandle.search(
                configurationDN,
                filter,
                search_scope=ldap3.SUBTREE,
                attributes=ldap3.ALL_ATTRIBUTES
            )

            if not dchandle.result:
                continue

            for result in dchandle.response:
                attributes = _v(result, 'attributes')
                if not attributes: 
                    continue

                results.append(attributes)

            if haskey:
                break 

        return results

    def get_subnets(self, handle, **kwargs):
        dchandle = handle.dchandle

        configurationDN = self.get_configurationDN(handle)
        baseDN = "CN=Subnets,CN=Sites,%s" % configurationDN.encode('utf-8')
        filter = '(objectClass=subnet)'

        keys = ['distinguishedname', 'cn', 'name', 'siteobjectbl']
        for k in keys:
            if kwargs.has_key(k) and kwargs[k]:
                filter = "(&%s(%s=%s))" % (filter, k, kwargs[k].encode('utf-8'))

        subnets = []
        dchandle.search(
            configurationDN,
            filter,
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )

        if not dchandle.result:
            return subnets

        for result in dchandle.response:
            attributes = _v(result, 'attributes')
            if not attributes: 
                return subnets

            subnets.append(attributes)

        return subnets

    def get_sites(self, handle, **kwargs):
        dchandle = handle.dchandle

        configurationDN = self.get_configurationDN(handle)
        baseDN = "CN=Sites,%s" % configurationDN.encode('utf-8')
        filter = '(objectClass=site)'

        keys = ['distinguishedname', 'cn', 'name', 'siteobjectbl']
        for k in keys:
            if kwargs.has_key(k) and kwargs[k]:
                filter = "(&%s(%s=%s))" % (filter, k, kwargs[k].encode('utf-8'))

        sites = []
        dchandle.search(
            configurationDN,
            filter,
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )

        if not dchandle.result:
            return sites

        for result in dchandle.response:
            attributes = _v(result, 'attributes')
            if not attributes: 
                return sites

            sites.append(attributes)

        return sites

    def get_machine_account(self, handle, hostname):
        dchandle = handle.dchandle

        hostname = hostname.split('.')[0]
        baseDN = self.get_baseDN(handle) 
        filter = '(&(objectClass=computer)(sAMAccountName=%s$))' % hostname.encode('utf-8')

        dchandle.search(
            baseDN,
            filter,
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )

        if not dchandle.result:
            return None

        attributes = _v(dchandle.response[0], 'attributes')
        if not attributes: 
            return None

        return attributes

    def get_users(self, handle, **kwargs):
        dchandle = handle.dchandle

        baseDN = self.get_baseDN(handle) 
        filter = '(&(|(objectclass=user)(objectclass=person))(sAMAccountName=*))'

        dchandle.search(
            baseDN,
            filter,
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )
         
        users = []
        if not dchandle.result:
            return users

        filter_func = lambda x: 'sAMAccountType' in x and \
            (long(x['sAMAccountType']) != SAM_USER_OBJECT)

        if 'filter' in kwargs and kwargs['filter']:
            filter_func = kwargs['filter']

        for result in dchandle.response:
            attributes = _v(result, 'attributes')
            if not attributes: 
                continue

            if filter_func:
                if filter_func(attributes):
                    continue

            users.append(attributes)
 
        return users
         
    def get_groups(self, handle, **kwargs):
        dchandle = handle.dchandle

        baseDN = self.get_baseDN(handle) 
        filter = '(&(objectclass=group)(sAMAccountName=*))'

        dchandle.search(
            baseDN,
            filter,
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )
         
        groups = []
        if not dchandle.result:
            return groups

        filter_func = lambda x: 'groupType' in x and \
            (long(x['groupType']) & GROUP_TYPE_BUILTIN_LOCAL_GROUP)

        if 'filter' in kwargs and kwargs['filter']:
            filter_func = kwargs['filter']

        for result in dchandle.response:
            attributes = _v(result, 'attributes')
            if not attributes: 
                continue

            if filter_func:
                if filter_func(attributes):
                    continue

            groups.append(attributes)

        return groups

    def get_user(self, handle, user):
        dchandle = handle.dchandle

        baseDN = self.get_baseDN(handle)
        filter = '(&(|(objectclass=user)(objectclass=person))' \
            '(sAMAccountName=%s))' % user.encode('utf-8')

        dchandle.search(
            baseDN,
            filter,
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )

        if not dchandle.result:
            return []

        attributes = _v(dchandle.response[0], 'attributes')
        if not attributes: 
            return []

        return attributes  

    def get_group(self, handle, group):
        dchandle = handle.dchandle

        baseDN = self.get_baseDN(handle)
        filter = '(&(objectclass=group)(sAMAccountName=%s))' % \
            group.encode('utf-8')

        dchandle.search(
            baseDN,
            filter,
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )

        if not dchandle.result:
            return []

        attributes = _v(dchandle.response[0], 'attributes')
        if not attributes: 
            return []

        return attributes  

    def get_userDN(self, handle, user):
        user = self.get_user(handle, user)
        if not user: 
            return None

        return user['distinguishedName'].strip()

    def get_groupDN(self, handle, group):
        group = self.get_group(handle, group)
        if not group: 
            return None

        return group['distinguishedName'].strip()


def _init(dispatcher, datastore):
    return ActiveDirectory(
        dispatcher=dispatcher,
        datastore=datastore
    ) 
