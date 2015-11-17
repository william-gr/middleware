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

from datetime import datetime
from event import EventSource
from task import Provider


class SyslogProvider(Provider):
    def query(self, filter=None, params=None):
        return self.datastore.query('syslog', *(filter or []), **(params or {}))


class SyslogEventSource(EventSource):
    def __init__(self, dispatcher):
        super(SyslogEventSource, self).__init__(dispatcher)
        self.register_event_type("syslog.changed")

    def run(self):
        # Initial call to obtain cursor
        cursor = self.datastore.listen('syslog', ('created_at', '>=', datetime.now()))

        while True:
            for i in self.datastore.tail(cursor):
                self.dispatcher.dispatch_event('syslog.changed', {
                    'operation': 'create',
                    'ids': [i['id']]
                })


def _init(dispatcher, plugin):
    plugin.register_event_source('syslog', SyslogEventSource)
    plugin.register_provider('syslog', SyslogProvider)
