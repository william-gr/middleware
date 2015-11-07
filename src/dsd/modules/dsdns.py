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

from dns import resolver

class DSDNS(object):
    def __init__(self, *args, **kwargs):
        self.dispatcher = kwargs['dispatcher']
        self.datastore = kwargs['datastore']

    def get_A_records(self, host):
        A_records = []

        if not host:
            return A_records

        try:
            A_records = resolver.query(host, 'A')

        except:
            A_records = []

        return A_records

    def get_AAAA_records(self, host):
        AAAA_records = []

        if not host:
            return AAAA_records

        try:
            AAAA_records = resolver.query(host, 'AAAA')

        except:
            AAAA_records = []

        return AAAA_records

    def get_SRV_records(self, host):
        srv_records = []

        if not host:
            return srv_records

        try:
            answers = resolver.query(host, 'SRV')
            srv_records = sorted(answers, key=lambda a: (int(a.priority),
                int(a.weight)))

        except:
            srv_records = []

        return srv_records

def _init(dispatcher, datastore):
    return DSDNS(
        dispatcher=dispatcher,
        datastore=datastore
    ) 
