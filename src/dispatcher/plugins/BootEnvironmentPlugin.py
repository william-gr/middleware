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
#####################################################################

import sys
from fnutils.query import wrap
from task import Provider, Task


sys.path.append('/usr/local/lib')
from freenasOS.Update import ListClones


class BootEnvironmentsProvider(Provider):
    def query(self, filter=None, params=None):
        def extend(obj):
            nr = obj['active']
            obj['active'] = 'N' in nr
            obj['on_reboot'] = 'R' in nr
            obj['id'] = obj.pop('name')
            return obj

        return wrap(ListClones()).query(*(filter or []), callback=extend, **(params or {}))


class BootEnvironmentCreate(Task):
    pass


class BootEnvironmentActivate(Task):
    pass


class BootEnvironmentsDelete(Task):
    pass


def _init(dispatcher, plugin):
    plugin.register_schema_definition('boot-environment', {
        'type': 'object',
        'properties': {
            'id': {'type': 'string'},
            'realname': {'type': 'string'},
            'active': {'type': 'boolean'},
            'on_reboot': {'type': 'boolean'},
            'mountpoint': {'type': 'string'},
            'space': {'type': 'integer'},
            'created': {'type': 'string'}
        }
    })

    plugin.register_provider('boot_environments', BootEnvironmentsProvider)
