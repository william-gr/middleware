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


import errno
import psutil
import smbconf
from task import Task, TaskStatus, Provider, TaskException
from resources import Resource
from dispatcher.rpc import RpcException, description, accepts, returns, private
from dispatcher.rpc import SchemaHelper as h
from utils import first_or_default, normalize


@description("Provides info about configured CIFS shares")
class CIFSSharesProvider(Provider):
    @private
    def get_connected_clients(self, share_name):
        pass


@description("Adds new CIFS share")
@accepts(h.ref('cifs-share'))
class CreateCIFSShareTask(Task):
    def describe(self, share):
        return "Creating CIFS share {0}".format(share['id'])

    def verify(self, share):
        return ['service:cifs']

    def run(self, share):
        normalize(share['properties'], {
            'read_only': False,
            'guest_ok': False,
            'guest_only': False,
            'browseable': True,
            'recyclebin': False,
            'show_hidden_files': False,
            'vfs_objects': [],
            'hosts_allow': None,
            'hosts_deny': None
        })
        
        self.datastore.insert('shares', share)

        try:
            smb_conf = smbconf.SambaConfig('registry')
            smb_share = smbconf.SambaShare()
            convert_share(smb_share, share['target'], share['properties'])
            smb_conf.shares[share['id']] = smb_share
        except smbconf.SambaConfigException:
            raise TaskException(errno.EFAULT, 'Cannot access samba registry')

        self.dispatcher.call_sync('services.ensure_started', 'cifs')
        self.dispatcher.dispatch_event('shares.cifs.changed', {
            'operation': 'create',
            'ids': [share['id']]
        })


@description("Updates existing CIFS share")
@accepts(str, h.ref('CIFS-share'))
class UpdateCIFSShareTask(Task):
    def describe(self, name, updated_fields):
        return "Updating CIFS share {0}".format(name)

    def verify(self, name, updated_fields):
        return ['service:cifs']

    def run(self, name, updated_fields):
        share = self.datastore.get_by_id('shares', name)
        share.update(updated_fields)
        self.datastore.update('shares', name, share)

        try:
            smb_conf = smbconf.SambaConfig('registry')
            smb_share = smb_conf.shares[share['id']]
            convert_share(smb_share, share['target'], share['properties'])
            smb_share.save()
        except smbconf.SambaConfigException:
            raise TaskException(errno.EFAULT, 'Cannot access samba registry')

        self.dispatcher.dispatch_event('shares.cifs.changed', {
            'operation': 'update',
            'ids': [name]
        })


@description("Removes CIFS share")
@accepts(str)
class DeleteCIFSShareTask(Task):
    def describe(self, name):
        return "Deleting CIFS share {0}".format(name)

    def verify(self, name):
        return ['service:CIFS']

    def run(self, name):
        self.datastore.delete('shares', name)

        try:
            smb_conf = smbconf.SambaConfig('registry')
            del smb_conf.shares[name]
        except smbconf.SambaConfigException:
            raise TaskException(errno.EFAULT, 'Cannot access samba registry')

        self.dispatcher.dispatch_event('shares.cifs.changed', {
            'operation': 'delete',
            'ids': [name]
        })


def yesno(val):
    return 'yes' if val else 'no'


def convert_share(ret, target, share):
    vfs_objects = []
    ret.clear()
    ret['path'] = target
    ret['guest ok'] = yesno(share.get('guest_ok', False))
    ret['guest only'] = yesno(share.get('guest_only', False))
    ret['read only'] = yesno(share.get('read_only', False))
    ret['browseable'] = yesno(share.get('browseable', True))
    ret['hide dot files'] = yesno(not share.get('show_hidden_files', False))
    ret['printable'] = 'no'
    ret['nfs4:mode'] = 'special'
    ret['nfs4:acedup'] = 'merge'
    ret['nfs4:chown'] = 'true'
    ret['zfsacl:acesort'] = 'dontcare'

    if share.get('hosts_allow'):
        ret['hosts allow'] = ','.join(share['hosts_allow'])

    if share.get('hosts_deny'):
        ret['hosts deny'] = ','.join(share['hosts_deny'])

    if share.get('recyclebin'):
        ret['recycle:repository'] = '.recycle/%U'
        ret['recycle:keeptree'] = 'yes'
        ret['recycle:versions'] = 'yes'
        ret['recycle:touch'] = 'yes'
        ret['recycle:directory_mode'] = '0777'
        ret['recycle:subdir_mode'] = '0700'

    ret['vfs objects'] = ' '.join(vfs_objects)


def _depends():
    return ['CIFSPlugin']


def _metadata():
    return {
        'type': 'sharing',
        'method': 'cifs'
    }


def _init(dispatcher, plugin):
    plugin.register_schema_definition('cifs-share', {
        'type': 'object',
        'properties': {
            'comment': {'type': 'string'},
            'read_only': {'type': 'boolean'},
            'guest_ok': {'type': 'boolean'},
            'guest_only': {'type': 'boolean'},
            'browseable': {'type': 'boolean'},
            'recyclebin': {'type': 'boolean'},
            'show_hidden_files': {'type': 'boolean'},
            'vfs_objects': {
                'type': 'array',
                'items': {'type': 'string'}
            },
            'hosts_allow': {
                'type': ['array', 'null'],
                'items': {'type': 'string'}
            },
            'hosts_deny': {
                'type': ['array', 'null'],
                'items': {'type': 'string'}
            }
        }
    })

    plugin.register_task_handler("share.cifs.create", CreateCIFSShareTask)
    plugin.register_task_handler("share.cifs.update", UpdateCIFSShareTask)
    plugin.register_task_handler("share.cifs.delete", DeleteCIFSShareTask)
    plugin.register_provider("shares.cifs", CIFSSharesProvider)
    plugin.register_event_type('shares.cifs.changed')

    # Sync samba registry with our database
    smb_conf = smbconf.SambaConfig('registry')
    smb_conf.shares.clear()

    for s in dispatcher.datastore.query('shares', ('type', '=', 'cifs')):
        smb_share = smbconf.SambaShare()
        convert_share(smb_share, s['target'], s.get('properties', {}))
        smb_conf.shares[s['id']] = smb_share
