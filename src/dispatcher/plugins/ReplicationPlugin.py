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

import enum
import os
import io
import errno
import re
import logging
import subprocess
import tempfile
import paramiko
from paramiko import RSAKey
from datetime import datetime
from dateutil.parser import parse as parse_datetime
from task import Provider, Task, ProgressTask, VerifyException, TaskException
from dispatcher.rpc import RpcException, SchemaHelper as h, description, accepts, returns, private
from dispatcher.client import Client, ClientError
from lib.system import SubprocessException, system
from fnutils import to_timedelta, first_or_default
from fnutils.query import wrap
from lib import sendzfs

"""
# Bandwidth Limit.
if  bandlim != 0:
    throttle = '/usr/local/bin/throttle -K %d | ' % bandlim
else:
    throttle = ''

#
# Build the SSH command
#

# Cipher
if cipher == 'fast':
    sshcmd = ('/usr/bin/ssh -c arcfour256,arcfour128,blowfish-cbc,'
              'aes128-ctr,aes192-ctr,aes256-ctr -i /data/ssh/replication'
              ' -o BatchMode=yes -o StrictHostKeyChecking=yes'
              # There's nothing magical about ConnectTimeout, it's an average
              # of wiliam and josh's thoughts on a Wednesday morning.
              # It will prevent hunging in the status of "Sending".
              ' -o ConnectTimeout=7'
             )
elif cipher == 'disabled':
    sshcmd = ('/usr/bin/ssh -ononeenabled=yes -ononeswitch=yes -i /data/ssh/replication -o BatchMode=yes'
              ' -o StrictHostKeyChecking=yes'
              ' -o ConnectTimeout=7')
else:
    sshcmd = ('/usr/bin/ssh -i /data/ssh/replication -o BatchMode=yes'
              ' -o StrictHostKeyChecking=yes'
              ' -o ConnectTimeout=7')

# Remote IP/hostname and port.  This concludes the preparation task to build SSH command
sshcmd = '%s -p %d %s' % (sshcmd, remote_port, remote)
"""

logger = logging.getLogger(__name__)
SYSTEM_RE = re.compile('^[^/]+/.system.*')
AUTOSNAP_RE = re.compile(
    '^(?P<prefix>\w+)-(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})'
    '.(?P<hour>\d{2})(?P<minute>\d{2})-(?P<lifetime>\d+[hdwmy])(-(?P<sequence>\d+))?$'
)
SSH_OPTIONS = {
    'NONE': [
        '-ononeenabled=yes',
        '-ononeswitch=yes',
        '-o BatchMode=yes',
        '-o ConnectTimeout=7'
    ],
    'FAST': [
        '-c arcfour256,arcfour128,blowfish-cbc,aes128-ctr,aes192-ctr,aes256-ctr',
        '-o BatchMode=yes',
        '-o ConnectTimeout=7'
    ],
    'NORMAL': [
        '-o BatchMode=yes',
        '-o ConnectTimeout=7'
    ]
}


class ReplicationActionType(enum.Enum):
    SEND_STREAM = 1
    DELETE_SNAPSHOTS = 2
    DELETE_DATASET = 3


class ReplicationAction(object):
    def __init__(self, type, localfs, remotefs, **kwargs):
        self.type = type
        self.localfs = localfs
        self.remotefs = remotefs
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __getstate__(self):
        d = dict(self.__dict__)
        d['type'] = d['type'].name
        return d


#
# Return a pair of compression and decompress pipe commands
#
map_compression = {
    'pigz': ('/usr/local/bin/pigz', '/usr/local/bin/pigz -d'),
    'plzip': ('/usr/local/bin/plzip', '/usr/local/bin/plzip -d'),
    'lz4': ('/usr/local/bin/lz4c', '/usr/local/bin/lz4c -d'),
    'xz': ('/usr/bin/xz', '/usr/bin/xzdec'),
}

def compress_pipecmds(compression):
    if compression in map_compression:
        compress, decompress = map_compression[compression]
        compress = compress + ' | '
        decompress = decompress + ' | '
    else:
        compress = ''
        decompress = ''
    return (compress, decompress)


#
# Attempt to send a snapshot or increamental stream to remote.
#
def send_dataset(remote, hostkey, fromsnap, tosnap, dataset, remotefs, compression, throttle):
    zfs = sendzfs.SendZFS()
    zfs.send(remote, hostkey, fromsnap, tosnap, dataset, remotefs, compression, throttle, 1024*1024, None)


class ReplicationProvider(Provider):
    def get_public_key(self):
        return self.configstore.get('replication.key.public')

    def scan_keys_on_host(self, hostname):
        return self.dispatcher.call_task_sync('replication.scan_hostkey', hostname)


@accepts(str)
class ScanHostKeyTask(Task):
    def verify(self, hostname):
        return []

    def run(self, hostname):
        transport = paramiko.transport.Transport(hostname)
        transport.start_client()
        key = transport.get_remote_server_key()
        return {
            'name': key.get_name(),
            'key': key.get_base64()
        }


@accepts(str, str, bool, str, str, bool)
@returns(str)
class SnapshotDatasetTask(Task):
    def verify(self, pool, dataset, recursive, lifetime, prefix='auto', replicable=False):
        if not self.dispatcher.call_sync('zfs.dataset.query', [('name', '=', dataset)], {'single': True}):
            raise VerifyException(errno.ENOENT, 'Dataset {0} not found'.format(dataset))

        return ['zfs:{0}'.format(dataset)]

    def run(self, pool, dataset, recursive, lifetime, prefix='auto', replicable=False):
        def is_expired(snapshot):
            match = AUTOSNAP_RE.match(snapshot['snapshot_name'])
            if not match:
                return False

            if snapshot['holds']:
                return False

            if match.group('prefix') != prefix:
                return False

            delta = to_timedelta(match.group('lifetime'))
            creation = parse_datetime(snapshot['properties.creation.value'])
            return creation + delta < datetime.now()

        snapshots = list(filter(is_expired, wrap(self.dispatcher.call_sync('zfs.dataset.get_snapshots', dataset))))
        snapname = '{0}-{1:%Y%m%d.%H%M}-{2}'.format(prefix, datetime.now(), lifetime)
        params = {'org.freenas:replicate': {'value': 'yes'}} if replicable else None
        base_snapname = snapname

        # Pick another name in case snapshot already exists
        for i in range(1, 99):
            if self.dispatcher.call_sync(
                'zfs.snapshot.query',
                [('name', '=', '{0}@{1}'.format(dataset, snapname))],
                {'count': True}
            ):
                snapname = '{0}-{1}'.format(base_snapname, i)
                continue

            break

        self.join_subtasks(
            self.run_subtask('zfs.create_snapshot', pool, dataset, snapname, recursive, params),
            self.run_subtask(
                'zfs.delete_multiple_snapshots',
                pool,
                dataset,
                list(map(lambda s: s['snapshot_name'], snapshots)),
                True
            )
        )


@description("Runs a replication task with the specified arguments")
#@accepts(h.all_of(
#    h.ref('autorepl'),
#    h.required(
#        'remote',
#        'remote_port',
#        'dedicateduser',
#        'cipher',
#        'localfs',
#        'remotefs',
#        'compression',
#        'bandlim',
#        'followdelete',
#        'recursive',
#    ),
#))
class ReplicateDatasetTask(ProgressTask):
    def verify(self, pool, localds, options, dry_run=False):
        return ['zfs:{0}'.format(localds)]

    def run(self, pool, localds, options, dry_run=False):
        remote = options['remote']
        remoteds = options['remote_dataset']
        followdelete = options.get('followdelete', False)
        recursive = options.get('recursive', False)
        lifetime = options.get('lifetime', '1y')

        self.join_subtasks(self.run_subtask(
            'volume.snapshot_dataset',
            pool,
            localds,
            True,
            lifetime,
            'repl',
            True
        ))

        datasets = [localds]
        actions = []

        with open('/etc/replication/key') as f:
            pkey = RSAKey.from_private_key(f)

        remote_client = Client()
        remote_client.connect('ws+ssh://{0}'.format(options['remote']), pkey=pkey)
        remote_client.login_service('replicator')

        def is_replicated(snapshot):
            if snapshot.get('properties.org\\.freenas:replicate.value') != 'yes':
                # Snapshot is not subject to replication
                return False

            return True

        def matches(pair):
            src, tgt = pair
            srcsnap = src['snapshot_name']
            tgtsnap = tgt['snapshot_name']
            return srcsnap == tgtsnap and src['properties.creation.rawvalue'] == tgt['properties.creation.rawvalue']

        if recursive:
            datasets = self.dispatcher.call_sync(
                'zfs.dataset.query',
                [('name', '~', '^{0}(/|$)'.format(localds))],
                {'select': 'name'}
            )

        self.set_progress(0, 'Reading replication state from remote side...')

        for ds in datasets:
            localfs = ds
            remotefs = localfs.replace(localds, remoteds, 1)
            local_snapshots = list(filter(
                is_replicated,
                wrap(self.dispatcher.call_sync('zfs.dataset.get_snapshots', localfs))
            ))

            try:
                remote_snapshots_full = wrap(remote_client.call_sync('zfs.dataset.get_snapshots', remotefs))
                remote_snapshots = list(filter(is_replicated, remote_snapshots_full))
            except RpcException as err:
                raise TaskException(err.code, 'Cannot contact {0}: {1}'.format(remote, err.message))

            snapshots = local_snapshots[:]
            found = None

            if remote_snapshots_full:
                # Find out the last common snapshot.
                pairs = list(filter(matches, zip(local_snapshots, remote_snapshots)))
                if pairs:
                    pairs.sort(key=lambda p: int(p[0]['properties.creation.rawvalue']), reverse=True)
                    found, _ = first_or_default(None, pairs)

                if found:
                    if followdelete:
                        delete = []
                        for snap in remote_snapshots:
                            rsnap = snap['snapshot_name']
                            if not first_or_default(lambda s: s['snapshot_name'] == rsnap, local_snapshots):
                                delete.append(rsnap)

                        actions.append(ReplicationAction(
                            ReplicationActionType.DELETE_SNAPSHOTS,
                            localfs,
                            remotefs,
                            snapshots=delete
                        ))

                    index = local_snapshots.index(found)

                    for idx in range(index + 1, len(local_snapshots)):
                        actions.append(ReplicationAction(
                            ReplicationActionType.SEND_STREAM,
                            localfs,
                            remotefs,
                            incremental=True,
                            anchor=local_snapshots[idx - 1]['snapshot_name'],
                            snapshot=local_snapshots[idx]['snapshot_name']
                        ))
                else:
                    actions.append(ReplicationAction(
                        ReplicationActionType.DELETE_SNAPSHOTS,
                        localfs,
                        remotefs,
                        snapshots=map(lambda s: s['snapshot_name'], remote_snapshots_full)
                    ))

                    for idx in range(0, len(snapshots)):
                        actions.append(ReplicationAction(
                            ReplicationActionType.SEND_STREAM,
                            localfs,
                            remotefs,
                            incremental=idx > 0,
                            anchor=snapshots[idx - 1]['snapshot_name'] if idx > 0 else None,
                            snapshot=snapshots[idx]['snapshot_name']
                        ))
            else:
                logger.info('New dataset {0} -> {1}:{2}'.format(localfs, remote, remotefs))
                for idx in range(0, len(snapshots)):
                    actions.append(ReplicationAction(
                        ReplicationActionType.SEND_STREAM,
                        localfs,
                        remotefs,
                        incremental=idx > 0,
                        anchor=snapshots[idx - 1]['snapshot_name'] if idx > 0 else None,
                        snapshot=snapshots[idx]['snapshot_name']
                    ))

        # 1st pass - estimate send size
        self.set_progress(0, 'Estimating send size...')
        total_send_size = 0
        done_send_size = 0

        for action in actions:
            if action.type == ReplicationActionType.SEND_STREAM:
                size = self.dispatcher.call_sync(
                    'zfs.dataset.estimate_send_size',
                    action.localfs,
                    action.snapshot,
                    getattr(action, 'anchor', None)
                )

                action.send_size = size
                total_send_size += size

        if dry_run:
            return actions

        # 2nd pass - actual send
        for idx, action in enumerate(actions):
            progress = float(idx) / len(actions) * 100

            if action.type == ReplicationActionType.DELETE_SNAPSHOTS:
                self.set_progress(progress, 'Removing snapshots on remote dataset {0}'.format(action.remotefs))
                # Remove snapshots on remote side
                result = remote_client.call_task_sync(
                    'zfs.delete_multiple_snapshots',
                    action.remotefs.split('/')[0],
                    action.remotefs,
                    list(action.snapshots)
                )

                if result['state'] != 'FINISHED':
                    raise TaskException(errno.EFAULT, 'Failed to destroy snapshots on remote end: {0}'.format(
                        result['error']['message']
                    ))

            if action.type == ReplicationActionType.SEND_STREAM:
                self.set_progress(progress, 'Sending {0} stream of snapshot {1}/{2}'.format(
                    'incremental' if action.incremental else 'full',
                    action.localfs,
                    action.snapshot
                ))

                if not action.incremental:
                    send_dataset(remote, options.get('remote_hostkey'), None, action.snapshot, action.localfs, action.remotefs, '', 0)
                else:
                    send_dataset(remote, options.get('remote_hostkey'), action.anchor, action.snapshot, action.localfs, action.remotefs, '', 0)

            if action.type == ReplicationActionType.DELETE_DATASET:
                self.set_progress(progress, 'Removing remote dataset {0}'.format(action.remotefs))
                result = remote_client.call_task_sync(
                    'zfs.destroy',
                    action.remotefs.split('/')[0],
                    action.remotefs
                )

                if result['status'] != 'FINISHED':
                    raise TaskException(errno.EFAULT, 'Failed to destroy dataset {0} on remote end: {1}'.format(
                        action.remotefs,
                        result['error']['message']
                    ))

        return actions


def _init(dispatcher, plugin):
    plugin.register_schema_definition('replication', {
        'type': 'object',
        'properties': {
            'remote': {'type': 'string'},
            'remote_port': {'type': 'string'},
            'remote_hostkey': {'type': 'string'},
            'remote_dataset': {'type': 'string'},
            'cipher': {
                'type': 'string',
                'enum': ['NORMAL', 'FAST', 'DISABLED']
            },
            'compression': {
                'type': 'string',
                'enum': ['none', 'pigz', 'plzip', 'lz4', 'xz']
            },
            'bandwidth_limit': {'type': 'string'},
            'followdelete': {'type': 'boolean'},
            'recursive': {'type': 'boolean'},
        },
        'additionalProperties': False,
    })

    plugin.register_provider('replication', ReplicationProvider)
    plugin.register_task_handler('volume.snapshot_dataset', SnapshotDatasetTask)
    plugin.register_task_handler('replication.scan_hostkey', ScanHostKeyTask)
    plugin.register_task_handler('replication.replicate_dataset', ReplicateDatasetTask)

    # Generate replication key pair on first run
    if not dispatcher.configstore.get('replication.key.private') or not dispatcher.configstore.get('replication.key.public'):
        key = RSAKey.generate(bits=2048)
        buffer = io.StringIO()
        key.write_private_key(buffer)
        dispatcher.configstore.set('replication.key.private', buffer.getvalue())
        dispatcher.configstore.set('replication.key.public', key.get_base64())

    dispatcher.call_sync('etcd.generation.generate_group', 'replication')
