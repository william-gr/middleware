#+
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

import os
import re
import errno
from dispatcher.rpc import RpcException, description, accepts, returns
from dispatcher.rpc import SchemaHelper as h
from datastore.config import ConfigNode
from task import Provider, Task, TaskException, VerifyException
from lib.system import system, SubprocessException


RE_ATTRS = re.compile(r'^(?P<key>^.+?)\s+?:\s+?(?P<val>.+?)\r?$', re.M)
IPMI_ATTR_MAP = {
    'IP Address Source': 'dhcp',
    'IP Address': 'address',
    'Subnet Mask': 'netmask',
    'Default Gateway IP': 'gateway',
    '802.1q VLAN ID': 'vlan_id'
}


class IPMIProvider(Provider):
    @accepts()
    @returns(bool)
    def is_ipmi_loaded(self):
        return os.path.exists('/dev/ipmi0')

    @accepts()
    @returns(h.array(int))
    def channels(self):
        ret = []
        for i in range(1, 17):
            try:
                system('/usr/local/bin/ipmitool', 'lan', 'print', str(i))
            except SubprocessException:
                continue

            ret.append(i)

        return ret

    @accepts(int)
    @returns(h.ref('ipmi-configuration'))
    def get_config(self, channel):
        if not self.is_ipmi_loaded():
            raise RpcException(errno.ENXIO, 'The IPMI device could not be found')

        if channel not in self.dispatcher.call_sync('ipmi.channels'):
            raise RpcException(errno.ENXIO, 'Invalid channel')

        try:
            out, err = system('/usr/local/bin/ipmitool', 'lan', 'print', str(channel))
        except SubprocessException, e:
            raise RpcException(errno.EFAULT, 'Cannot receive IPMI configuration: {0}'.format(e.err.strip()))

        raw = {k.strip(): v.strip() for k, v in RE_ATTRS.findall(out)}
        ret = {IPMI_ATTR_MAP[k]: v for k, v in raw.items() if k in IPMI_ATTR_MAP}
        ret['channel'] = channel
        ret['vlan_id'] = None if ret['vlan_id'] == 'Disabled' else ret['vlan_id']
        ret['dhcp'] = True if ret['dhcp'] == 'DHCP Address' else False
        return ret


@accepts(h.ref('ipmi-configuration'))
@description("Configures IPMI module")
class ConfigureIPMITask(Task):
    def verify(self, channel, updated_params):
        if not self.dispatcher.call_sync('ipmi.is_ipmi_loaded'):
            raise VerifyException(errno.ENXIO, 'No IPMI module loaded')

        if channel not in self.dispatcher.call_sync('ipmi.channels'):
            raise VerifyException(errno.ENXIO, 'Invalid channel')

        return ['system']

    def run(self, channel, updated_params):
        config = self.dispatcher.call_sync('ipmi.get_config', channel)
        config.update(updated_params)


def _init(dispatcher, plugin):
    plugin.register_schema_definition('ipmi-configuration', {
        'type': 'object',
        'properties': {
            'channel': {'type': 'number'},
            'password': {'type': 'string'},
            'dhcp': {'type': 'boolean'},
            'address': {'type': 'string'},
            'netmask': {'type': 'string'},
            'gateway': {'type': 'string'},
            'vlan_id': {'type': 'number'}
        }
    })

    plugin.register_provider('ipmi', IPMIProvider)
