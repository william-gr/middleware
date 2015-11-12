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

import logging
import os
import sys
import tempfile
import time

from fnutils.pipesubr import (
    pipeopen,
    run
)

logger = logging.getLogger("kerberos")

class Kerberos(object):
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
        return "kerberos"

    def get_kerberos_servers(self, domain, proto='tcp'):
        kerberos_servers = []

        if not domain:
            return kerberos_servers
        if proto is None:
            proto = ['tcp', 'udp']
            
        if 'tcp' in proto:
            tcp_host = "_kerberos._tcp.%s" % domain
            
            logger.debug("get_kerberos_servers: tcp_host = %s", tcp_host)
            tcp_kerberos_servers = self.dsdns.get_SRV_records(tcp_host)
            if tcp_kerberos_servers:
                kerberos_servers += tcp_kerberos_servers

        if 'udp' in proto:
            udp_host = "_kerberos._tcp.%s" % domain

            logger.debug("get_kerberos_servers: udp_host = %s", udp_host)
            udp_kerberos_servers = self.dsdns.get_SRV_records(tcp_host)
            if udp_kerberos_servers:
                kerberos_servers += udp_kerberos_servers

        for ks in kerberos_servers:
            logger.debug("get_kerberos_servers: found %s", ks)

        return kerberos_servers

    def get_kpasswd_servers(self, domain, proto='tcp'):
        kpasswd_servers = []

        if not domain:
            return kpasswd_servers
        if proto is None:
            proto = ['tcp', 'udp']

        if 'tcp' in proto:
            tcp_host = "_kpasswd._tcp.%s" % domain

            logger.debug("get_kpasswd_servers: tcp_host = %s", tcp_host)
            tcp_kpasswd_servers = self.dsdns.get_SRV_records(tcp_host)
            if tcp_kpasswd_servers:
                kpasswd_servers += tcp_kpasswd_servers

        if 'udp' in proto:
            udp_host = "_kpasswd._udp.%s" % domain

            logger.debug("get_kpasswd_servers: udp_host = %s", udp_host)
            udp_kpasswd_servers = self.dsdns.get_SRV_records(udp_host)
            if udp_kpasswd_servers:
                kpasswd_servers += udp_kpasswd_servers

        for kpws in kpasswd_servers:
            logger.debug("get_kpasswd_servers: found %s", kpws)

        return kpasswd_servers

    def get_kerberos_master_servers(self, domain, proto='tcp'):
        kerberos_master_servers = []

        if not domain:
            return kerberos_master_servers
        if proto is None:
            proto = ['tcp', 'udp']

        if 'tcp' in proto:
            tcp_host = "_kerberos-master._tcp.%s" % domain

            logger.debug("get_kerberos_master_servers: tcp_host = %s", tcp_host)
            tcp_kerberos_master_servers = self.dsdns.get_SRV_records(tcp_host)
            if tcp_kerberos_master_servers:
                kerberos_master_servers += tcp_kerberos_master_servers

        if 'udp' in proto:
            udp_host = "_kerberos-master._tcp.%s" % domain

            logger.debug("get_kerberos_master_servers: udp_host = %s", udp_host)
            udp_kerberos_master_servers = self.dsdns.get_SRV_records(tcp_host)
            if udp_kerberos_master_servers:
                kerberos_master_servers += udp_kerberos_master_servers

        for kms in kerberos_master_servers:
            logger.debug("get_kerberos_master_servers: found %s", kms)

        return kerberos_master_servers

    def get_kerberos_admin_servers(self, domain, proto='tcp'):
        kerberos_admin_servers = []

        if not domain:
            return kerberos_admin_servers
        if proto is None:
            proto = ['tcp', 'udp']

        if 'tcp' in proto:
            tcp_host = "_kerberos-adm._tcp.%s" % domain

            logger.debug("get_kerberos_admin_servers: tcp_host = %s", tcp_host)
            tcp_kerberos_admin_servers = self.dsdns.get_SRV_records(tcp_host)
            if tcp_kerberos_admin_servers:
                kerberos_admin_servers += tcp_kerberos_admin_servers

        if 'udp' in proto:
            udp_host = "_kerberos-adm._tcp.%s" % domain

            logger.debug("get_kerberos_admin_servers: udp_host = %s", udp_host)
            udp_kerberos_admin_servers = self.dsdns.get_SRV_records(tcp_host)
            if udp_kerberos_admin_servers:
                kerberos_admin_servers += udp_kerberos_admin_servers

        for kms in kerberos_admin_servers:
            logger.debug("get_kerberos_admin_servers: found %s", kms)

        return kerberos_admin_servers

    def cache_has_ticket(self):
        res = False

        p = pipeopen("/usr/bin/klist -t")
        p.communicate()
        if p.returncode == 0:
            res = True

        return res

    def get_principal_from_cache(self):
        principal = None

        p = pipeopen("klist")
        klist_out = p.communicate()
        if p.returncode != 0:
            return None

        klist_out = klist_out[0]
        lines = klist_out.splitlines()
        for line in lines:
            line = line.strip()
            if line.startswith(bytes("Principal", "UTF-8")):
                parts = line.split(bytes(":", "UTF-8"))
                if len(parts) > 1:
                    principal = parts[1].strip()

        return principal

    def get_ticket(self, realm, binddn, bindpw):
        krb_principal = self.get_principal_from_cache()
        principal = "%s@%s" % (binddn, realm)

        res = kinit = False

        if krb_principal and krb_principal.upper() == principal.upper():
            return True

        (fd, tmpfile) = tempfile.mkstemp(dir="/tmp")
        os.fchmod(fd, 600)
        os.write(fd, bytes(bindpw, "UTF-8"))
        os.close(fd)

        args = [
            "/usr/bin/kinit",
            "--renewable",
            "--password-file=%s" % tmpfile,
            "%s" % principal
        ]

        # XXX this needs to be configurable
        timeout = 30

        (returncode, stdout, stderr) = run(' '.join(args), timeout=timeout)
        if returncode == 0:
            res = True

        if res != False:
            kinit = True

        os.unlink(tmpfile)

        if kinit:
            i = 0
            while i < timeout:
                if self.cache_has_ticket():
                    res = True
                    break

                time.sleep(1)
                i += 1

        return res

def _init(dispatcher, datastore):
    return Kerberos(
        dispatcher=dispatcher,
        datastore=datastore
    ) 
