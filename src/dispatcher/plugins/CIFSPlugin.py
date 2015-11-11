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
import errno
import logging
import re
import smbconf
import enum
from datastore.config import ConfigNode
from dispatcher.rpc import RpcException, SchemaHelper as h, description, accepts, returns
from lib.system import system, SubprocessException
from lib.freebsd import get_sysctl
from task import Task, Provider, TaskException, ValidationException

logger = logging.getLogger('CIFSPlugin')


class LogLevel(enum.IntEnum):
    NONE = 0
    MINIMUM = 1
    NORMAL = 2
    FULL = 3
    DEBUG = 10


def validate_netbios_name(netbiosname):
    regex = re.compile(r"^[a-zA-Z0-9\.\-_!@#\$%^&\(\)'\{\}~]{1,15}$")
    return regex.match(netbiosname)


@description('Provides info about CIFS service configuration')
class CIFSProvider(Provider):
    @accepts()
    @returns(h.ref('service-cifs'))
    def get_config(self):
        return ConfigNode('service.cifs', self.configstore)


@description('Configure CIFS service')
@accepts(h.ref('service-cifs'))
class CIFSConfigureTask(Task):
    def describe(self, cifs):
        return 'Configuring CIFS service'

    def verify(self, cifs):
        errors = []

        node = ConfigNode('service.cifs', self.configstore).__getstate__()

        netbiosname = cifs.get('netbiosname')
        if netbiosname is not None:
            for n in netbiosname:
                if not validate_netbios_name(n):
                    errors.append(('netbiosname', errno.EINVAL, 'Invalid name {0}'.format(n)))
        else:
            netbiosname = node['netbiosname']

        workgroup = cifs.get('workgroup')
        if workgroup is not None:
            if not validate_netbios_name(workgroup):
                errors.append(('workgroup', errno.EINVAL, 'Invalid name'))
        else:
            workgroup = node['workgroup']

        if workgroup.lower() in [i.lower() for i in netbiosname]:
            errors.append(('netbiosname', errno.EEXIST, 'NetBIOS and Workgroup must be unique'))

        dirmask = cifs.get('dirmask')
        if dirmask and (int(dirmask, 8) & ~0o11777):
            errors.append(('dirmask', errno.EINVAL, 'This is not a valid mask'))

        filemask = cifs.get('filemask')
        if filemask and (int(filemask, 8) & ~0o11777):
            errors.append(('filemask', errno.EINVAL, 'This is not a valid mask'))

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, cifs):
        try:
            action = 'NONE'
            node = ConfigNode('service.cifs', self.configstore)
            node.update(cifs)
            configure_params(node.__getstate__())

            # XXX: Is restart to change netbios name/workgroup *really* needed?
            if 'netbiosname' in cifs or 'workgroup' in cifs:
                action = 'RESTART'

            self.dispatcher.dispatch_event('service.cifs.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException as e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure CIFS: {0}'.format(str(e))
            )

        return action


def yesno(val):
    return 'yes' if val else 'no'


def configure_params(cifs):
    conf = smbconf.SambaConfig('registry')
    conf['netbios name'] = cifs['netbiosname'][0]
    conf['netbios aliases'] = ' '.join(cifs['netbiosname'][1:])

    if cifs['bind_addresses']:
        conf['interfaces'] = ' '.join(['127.0.0.1'] + cifs['bind_addresses'])

    conf['workgroup'] = cifs['workgroup']
    conf['server string'] = cifs['description']
    conf['encrypt passwords'] = 'yes'
    conf['dns proxy'] = 'no'
    conf['strict locking'] = 'no'
    conf['oplocks'] = 'yes'
    conf['deadtime'] = '15'
    conf['max log size'] = '51200'
    conf['max open files'] = str(int(get_sysctl('kern.maxfilesperproc')) - 25)

    if cifs['syslog']:
        conf['syslog only'] = 'yes'
        conf['syslog'] = '1'

    conf['load printers'] = 'no'
    conf['printing'] = 'bsd'
    conf['printcap name'] = '/dev/null'
    conf['disable spoolss'] = 'yes'
    conf['getwd cache'] = 'yes'
    conf['guest account'] = cifs['guest_user']
    conf['map to guest'] = 'Bad User'
    conf['obey pam restrictions'] = yesno(cifs['obey_pam_restrictions'])
    conf['directory name cache size'] = '0'
    conf['kernel change notify'] = 'no'
    conf['panic action'] = '/usr/local/libexec/samba/samba-backtrace'
    conf['nsupdate command'] = '/usr/local/bin/samba-nsupdate -g'
    conf['ea support'] = 'yes'
    conf['store dos attributes'] = 'yes'
    conf['lm announce'] = 'yes'
    conf['hostname lookups'] = yesno(cifs['hostlookup'])
    conf['unix extensions'] = yesno(cifs['unixext'])
    conf['time server'] = yesno(cifs['time_server'])
    conf['null passwords'] = yesno(cifs['empty_password'])
    conf['acl allow execute always'] = yesno(cifs['execute_always'])
    conf['acl check permissions'] = 'true'
    conf['dos filemode'] = 'yes'
    conf['multicast dns register'] = yesno(cifs['zeroconf'])
    conf['local master'] = yesno(cifs['local_master'])
    conf['server role'] = 'auto'
    conf['log level'] = str(getattr(LogLevel, cifs['log_level']).value)
    conf['username map'] = '/usr/local/etc/smbusers'
    conf['idmap config *: range'] = '90000001-100000000'
    conf['idmap config *: backend'] = 'tdb'


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):

    def set_cifs_sid():
        cifs = dispatcher.call_sync('service.cifs.get_config')
        if not cifs['sid']:
            try:
                sid = system('/usr/local/bin/net', 'getlocalsid')[0]
                if ':' in sid:
                    sid = sid.split(':', 1)[1].strip(' ').strip('\n')
                    if sid:
                        dispatcher.configstore.set('service.cifs.sid', sid)
                        cifs['sid'] = sid
            except SubprocessException:
                logger.error('Failed to get local sid', exc_info=True)
        try:
            if cifs['sid']:
                system('/usr/local/bin/net', 'setlocalsid', cifs['sid'])
        except SubprocessException as err:
            logger.error('Failed to set local sid: {0}'.format(err.output))

    # Register schemas
    PROTOCOLS = [
        'CORE',
        'COREPLUS',
        'LANMAN1',
        'LANMAN2',
        'NT1',
        'SMB2',
        'SMB2_02',
        'SMB2_10',
        'SMB2_22',
        'SMB2_24',
        'SMB3',
        'SMB3_00',
    ]

    plugin.register_schema_definition('service-cifs', {
        'type': 'object',
        'properties': {
            'netbiosname': {
                'type': 'array',
                'items': {'type': 'string'}
            },
            'workgroup': {'type': 'string'},
            'description': {'type': 'string'},
            'dos_charset': {'type': 'string'},
            'unix_charset': {'type': 'string'},
            'log_level': {
                'type': 'string',
                'enum': list(LogLevel.__members__.keys())
            },
            'syslog': {'type': 'boolean'},
            'local_master': {'type': 'boolean'},
            'domain_logons': {'type': 'boolean'},
            'time_server': {'type': 'boolean'},
            'guest_user': {'type': 'string'},
            'filemask': {'type': ['string', 'null']},
            'dirmask': {'type': ['string', 'null']},
            'empty_password': {'type': 'boolean'},
            'unixext': {'type': 'boolean'},
            'zeroconf': {'type': 'boolean'},
            'hostlookup': {'type': 'boolean'},
            'min_protocol': {'type': ['string', 'null'], 'enum': [None] + PROTOCOLS},
            'max_protocol': {'type': 'string', 'enum': PROTOCOLS},
            'execute_always': {'type': 'boolean'},
            'obey_pam_restrictions': {'type': 'boolean'},
            'bind_addresses': {
                'type': ['array', 'null'],
                'items': {'type': 'string'},
            },
            'auxiliary': {'type': ['string', 'null']},
            'sid': {'type': ['string', 'null']},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.cifs", CIFSProvider)

    # Register tasks
    plugin.register_task_handler("service.cifs.configure", CIFSConfigureTask)

    set_cifs_sid()
    node = ConfigNode('service.cifs', dispatcher.configstore)
    configure_params(node.__getstate__())
