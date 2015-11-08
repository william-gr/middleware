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
        self.dispatcher = kwargs['dispatcher']
        self.datastore = kwargs['datastore']

        sys.path.extend(['/usr/local/lib/dsd/modules/'])
        from dsdns import DSDNS

        self.dsdns = DSDNS(
            dispatcher=self.dispatcher,
            datastore=self.datastore,
        )

    def get_directory_type(self):
        return "kerberos"

    def get_kerberos_servers(self, domain, site=None):
        kdcs = []
        if not domain:
            return kdcs
            
        host = "_kerberos._tcp.%s" % domain
        if site:
            host = "_kerberos._tcp.%s._sites.%s" % (site, domain)
            
        kdcs = self.dsdns.get_SRV_records(host)
        return kdcs

    def get_kerberos_domain_controllers(self, domain, site=None):
        kdcs = []
        if not domain:
            return kdcs

        host = "_kerberos._tcp.dc._msdcs.%s" % domain
        if site:
            host = "_kerberos._tcp.%s._sites.dc._msdcs.%s" % (site, domain)

        kdcs = self.dsdns.get_SRV_records(host)
        return kdcs

    def get_kpasswd_servers(self, domain):
        kpws = []
        if not domain:
            return kpws

        host = "_kpasswd._tcp.%s" % domain

        kpws = self.dsdns.get_SRV_records(host)
        return kpws

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
