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

logger = logging.getLogger('ldap')

class LDAP(object):
    class LDAPHandle(object):
        def __init__(self, host, binddn, bindpw):
            self.__host = host
            self.__binddn = binddn
            self.__bindpw = bindpw
            self.__ldap_handle = self.get_ldap_handle()

        def get_connection_handle(self, host, port, binddn, bindpw):
            server = ldap3.Server(host, port=port, get_info=ldap3.ALL)
            conn = ldap3.Connection(server, user=binddn, password=bindpw,
                authentication=ldap3.AUTH_SIMPLE, auto_bind=True)
            return conn

        @property
        def ldap_handle(self):
            return self.__ldap_handle

        def get_ldap_handle(self):
            return self.get_connection_handle(
                self.__host,
                389,
                self.__binddn,
                self.__bindpw
            )

    def __init__(self, *args,  **kwargs):
        self.dispatcher = kwargs.get('dispatcher')
        self.datastore = kwargs.get('datastore')

        sys.path.extend(['/usr/local/lib/dsd/modules/'])
        from dsdns import DSDNS

        self.dsdns = DSDNS(
            dispatcher=self.dispatcher,
            datastore=self.datastore,
        )

    def get_directory_type(self):
        return "ldap"

    def get_connection_handle(self, host, binddn, bindpw):
        return self.LDAPHandle(host, binddn, bindpw)

    def get_ldap_servers(self, domain):
        ldap_servers = []
        if not domain:
            return dcs

        host = "_ldap._tcp.%s" % domain

        logger.debug("get_ldap_servers: host = %s", host)
        ldap_servers = self.dsdns.get_SRV_records(host)

        for lds in ldap_servers:
            logger.debug("get_ldap_servers: found %s", lds)

        return ldap_servers

    def get_rootDSE(self, handle):
        ldap_handle = handle.ldap_handle

        ldap_handle.search('',
            '(objectclass=*)',
            search_scope=ldap3.BASE,
            attributes=ldap3.ALL_ATTRIBUTES,
        )

        if not ldap_handle.result:
            return None

        if not ldap_handle.response:
            return None

        results = ldap_handle.response[0]
        if not results:
            return None

        attributes = results.get('attributes', None)
        if not attributes:
            return None

        return attributes

    def get_baseDN(self, handle):
        rootDSE = self.get_rootDSE(handle)
        if not rootDSE:
            return None

        baseDN = rootDSE.get('defaultNamingContext', None)
        if not baseDN:
            return None

        baseDN = baseDN[0].strip()
        logger.debug("get_baseDN: baseDN = %s", baseDN)

        return baseDN

    def get_users(self, handle, **kwargs):
        ldap_handle = handle.ldap_handle

        baseDN = self.get_baseDN(handle)
        filter = '(&(|(objectclass=person)' \
            '(objectclass=posixaccount)' \
            '(objectclass=account))(uid=*))'
        logger.debug("get_users: filter = %s", filter)

        ldap_handle.search(
            baseDN,
            filter,
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )

        users = []
        if not ldap_handle.result:
            return users

        filter_func = None
        if 'filter' in kwargs and kwargs['filter']:
            filter_func = kwargs['filter']

        for result in ldap_handle.response:
            attributes = result.get('attributes', None)
            if not attributes:
                continue

            attributes['dn'] = result.get('dn')
            if filter_func:
                if filter_func(attributes):
                    continue

            users.append(attributes)

        return users

    def get_groups(self, handle, **kwargs):
        ldap_handle = handle.ldap_handle

        baseDN = self.get_baseDN(handle)
        filter = '(&(|(objectclass=posixgroup)' \
            '(objectclass=group))' \
            '(gidnumber=*))'
        logger.debug("get_groups: filter = %s", filter)

        ldap_handle.search(
            baseDN,
            filter,
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )

        groups = []
        if not ldap_handle.result:
            return groups

        filter_func = None
        if 'filter' in kwargs and kwargs['filter']:
            filter_func = kwargs['filter']

        for result in ldap_handle.response:
            attributes = result.get('attributes', None)
            if not attributes:
                continue

            attributes['dn'] = result.get('dn')
            if filter_func:
                if filter_func(attributes):
                    continue

            groups.append(attributes)

        return groups

    def get_user(self, handle, user):
        ldap_handle = handle.ldap_handle

        baseDN = self.get_baseDN(handle)
        if user.isdigit():
            filter = '(&(|(objectclass=person)' \
                '(objectclass=posixaccount)' \
                '(objectclass=account))' \
                '(uidnumber=%s))' % user
        else:
            filter = '(&(|(objectclass=person)' \
                '(objectclass=posixaccount)' \
                '(objectclass=account))' \
                '(|(uid=%s)(cn=%s)))' % (user, user)
        logger.debug("get_user: filter = %s", filter)

        ldap_handle.search(
            baseDN,
            filter,
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )

        if not ldap_handle.result:
            return []

        if not ldap_handle.response:
            return []

        results = ldap_handle.response[0]
        if not results:
            return []

        attributes = results.get('attributes', None)
        if not attributes:
            return []

        if 'dn' in results:
            attributes['dn'] = results['dn']

        return attributes

    def get_group(self, handle, group):
        ldap_handle = handle.ldap_handle

        baseDN = self.get_baseDN(handle)
        if group.isdigit():
            filter = '(&(|(objectclass=posixgroup)' \
                '(objectclass=group))' \
                '(gidnumber=%s))' % group
        else:
            filter = '(&(|(objectclass=posixgroup)' \
                '(objectclass=group))' \
                '(cn=%s))' % group
        logger.debug("get_group: filter = %s", filter)

        ldap_handle.search(
            baseDN,
            filter,
            search_scope=ldap3.SUBTREE,
            attributes=ldap3.ALL_ATTRIBUTES
        )

        if not ldap_handle.result:
            return []

        if not ldap_handle.response:
            return []

        results = ldap_handle.response[0]
        if not results:
            return []

        attributes = results.get('attributes', None)
        if not attributes:
            return []

        if 'dn' in results:
            attributes['dn'] = results['dn']

        return attributes

    def get_userDN(self, handle, user):
        user = self.get_user(handle, user)
        if not user:
            return None

        userDN = user['dn'].strip()
        logger.debug("get_userDN: userDN = %s", userDN)

        return userDN

    def get_groupDN(self, handle, group):
        group = self.get_group(handle, group)
        if not group:
            return None


        groupDN = group['dn'].strip()
        logger.debug("get_groupDN: groupDN = %s", groupDN)

        return groupDN


def _init(dispatcher, datastore):
    return LDAP(
        dispatcher=dispatcher,
        datastore=datastore
    ) 
