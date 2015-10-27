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

import os
import errno
import re
import logging
import subprocess
from datetime import datetime
from dateutil.parser import parse as parse_datetime
from task import Task, VerifyException, TaskException
from dispatcher.rpc import RpcException, SchemaHelper as h, description, accepts, returns
from dispatcher.client import Client, ClientError
from lib.system import SubprocessException, system
from fnutils import to_timedelta, first_or_default
from fnutils.query import wrap


logger = logging.getLogger(__name__)
SYSTEM_RE = re.compile('^[^/]+/.system.*')
AUTOSNAP_RE = re.compile(
    '^auto-(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})'
    '.(?P<hour>\d{2})(?P<minute>\d{2})-(?P<lifetime>\d+[hdwmy])$'
)


class DatasetAction(object):
    def __init__(self, **kwargs):
        self.localfs = None
        self.remotefs = None
        self.initialize = False
        self.create = False
        self.anchor_snapshot = None
        self.snapshots = []
        self.delete = []
        for k, v in kwargs.items():
            setattr(self, k, v)


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
    if map_compression.has_key(compression):
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
def sendzfs(remote, fromsnap, tosnap, dataset, remotefs, compression, throttle):
    templog = '/tmp/templog'
    sshcmd = '/usr/bin/ssh -i /data/ssh/replication -o BatchMode=yes' \
        ' -o StrictHostKeyChecking=yes' \
        ' -o ConnectTimeout=7 %s ' % remote

    # progressfile = '/tmp/.repl_progress_%d' % replication.id
    progressfile = '/tmp/.repl_progress_0' # XXX
    cmd = ['/sbin/zfs', 'send', '-p']
    if fromsnap is None:
        cmd.append("%s@%s" % (dataset, tosnap))
    else:
        cmd.extend(['-i', "%s@%s" % (dataset, fromsnap), "%s@%s" % (dataset, tosnap)])
    # subprocess.Popen does not handle large stream of data between
    # processes very well, do it on our own
    readfd, writefd = os.pipe()
    zproc_pid = os.fork()
    if zproc_pid == 0:
        os.close(readfd)
        os.dup2(writefd, 1)
        os.close(writefd)
        os.execv('/sbin/zfs', cmd)
        # NOTREACHED
    else:
        with open(progressfile, 'w') as f2:
            f2.write(str(zproc_pid))
        os.close(writefd)

    compress, decompress = compress_pipecmds(compression)
    replcmd = '%s%s/bin/dd obs=1m 2> /dev/null | /bin/dd obs=1m 2> /dev/null | %s "%s/sbin/zfs receive -F \'%s\' && echo Succeeded"' % (compress, throttle, sshcmd, decompress, remotefs)
    with open(templog, 'w+') as f:
        readobj = os.fdopen(readfd, 'r', 0)
        proc = subprocess.Popen(
            replcmd,
            shell=True,
            stdin=readobj,
            stdout=f,
            stderr=subprocess.STDOUT,
        )
        proc.wait()
        os.waitpid(zproc_pid, os.WNOHANG)
        readobj.close()
        os.remove(progressfile)
        f.seek(0)
        msg = f.read().strip('\n').strip('\r')
    os.remove(templog)
    msg = msg.replace('WARNING: enabled NONE cipher\n', '')
    logger.debug("Replication result: %s" % (msg))
    # XXX results[replication.id] = msg
    # if reached_last and msg == "Succeeded":
    #    replication.repl_lastsnapshot = tosnap
    #    replication.save()
    return msg == "Succeeded"


@accepts(str, str, bool, str)
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

            delta = to_timedelta(match.group('lifetime'))
            creation = parse_datetime(snapshot['properties.creation.value'])
            return creation + delta < datetime.now()

        snapshots = filter(is_expired, wrap(self.dispatcher.call_sync('zfs.dataset.get_snapshots', dataset)))
        snapname = '{0}-{1:%Y%m%d.%H%M}-{2}'.format(prefix, datetime.now(), lifetime)
        params = {'org.freenas:replicate': {'value': 'yes'}} if replicable else None

        self.join_subtasks(
            self.run_subtask('zfs.create_snapshot', pool, dataset, snapname, recursive, params),
            *map(lambda s: self.run_subtask('zfs.destroy', s['name']), snapshots)
        )


@description("Runs an ZFS Replication Task with the specified arguments")
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
class ReplicateDatasetTask(Task):
    def verify(self, pool, localds, options, dry_run=False):
        return ['zfs:{0}'.format(localds)]

    def run(self, pool, localds, options, dry_run=False):
        remote = options['remote']
        remoteds = options['remotefs']
        followdelete = options.get('followdelete', False)
        recursive = options.get('recursive', False)
        lifetime = options.get('lifetime', '1y')


        """
        remote = "127.0.0.1"    # Remote IP address
        remote_port = "22"      # SSH port number
        cipher = "Normal"       # or "fast", "disabled"
        remotefs = "tank"       # Receiving dataset
        localfs = "tank"        # Local dataset
        compression = ""        # See map_compression
        bandlim = 0             # Bandwidth limit
        """

        self.join_subtasks(self.run_subtask(
            'replication.snapshot_dataset',
            pool,
            localds,
            True,
            lifetime,
            'repl'
        ))

        datasets = [localds]
        actions = []
        remote_client = Client()
        remote_client.connect(options['remote'])
        remote_client.login_service('replicator')

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

        if recursive:
            datasets = self.dispatcher.call_sync(
                'zfs.dataset.query',
                [('name', '~', '^{0}(/|$)'.format(localds))],
                {'select': 'name'}
            )

        for ds in datasets:
            localfs = ds
            remotefs = localfs.replace(localds, remoteds, 1)
            local_snapshots = wrap(self.dispatcher.call_sync('zfs.dataset.get_snapshots', localfs))

            try:
                remote_snapshots = wrap(remote_client.call_sync('zfs.dataset.get_snapshots', remotefs))
            except RpcException as err:
                remote_snapshots = None

            snapshots = local_snapshots[:]
            delete = []
            found = None

            def is_replicated(snapshot):
                if snapshot.get('properties.org\\.freenas:replicate.value') != 'yes':
                    # Snapshot is not subject to replication
                    return False

            def matches(pair):
                src, tgt = pair
                srcsnap = src['snapshot_name']
                tgtsnap = tgt['snapshot_name']
                return srcsnap == tgtsnap and src['properties.creation.rawvalue'] == tgt['properties.creation.rawvalue']

            if remote_snapshots:
                # Find out the last common snapshot.
                pairs = filter(matches, zip(local_snapshots, remote_snapshots))
                if pairs:
                    pairs.sort(key=lambda p: int(p[0]['properties.creation.rawvalue']), reverse=True)
                    found, _ = first_or_default(None, pairs)

                if found:
                    if followdelete:
                        for snap in remote_snapshots:
                            rsnap = snap['snapshot-name']
                            if not first_or_default(lambda s: s['snapshot-name'] == rsnap, local_snapshots):
                                delete.append(snap)

                    index = local_snapshots.index(found)
                    actions.append(DatasetAction(
                        localfs=localfs,
                        remotefs=remotefs,
                        initialize=False,
                        anchor_snapshot=local_snapshots[index],
                        snapshots=local_snapshots[index+1:],
                        delete=delete
                    ))
                else:
                    actions.append(DatasetAction(
                        localfs=localfs,
                        remotefs=remotefs,
                        delete=remote_snapshots[:],
                        initialize=True,
                        snapshots=snapshots
                    ))
            else:
                logger.info('New dataset {0} -> {1}:{2}'.format(localfs, remote, remotefs))
                actions.append(DatasetAction(
                    localfs=localfs,
                    remotefs=remotefs,
                    initialize=True,
                    create=True,
                    snapshots=snapshots
                ))

        for action in actions:
            if action.delete:
                for snap in action.delete:
                    snapname = snap['snapshot_name']
                    logger.info('Will delete {0}:{1}@{2}'.format(
                        remote,
                        action.remotefs,
                        snapname
                    ))

                # Remove snapshots on remote side
                remote_client.call_task_sync(
                    'zfs.delete_multiple_snapshots',
                    action.remotefs.split('/')[0],
                    action.remotefs,
                    map(lambda s: s['name'], action.delete)
                )

            start_full = action.create or action.initialize

            for idx, snap in enumerate(action.snapshots):
                snapname = snap['snapshot_name']
                full = idx == 0 and start_full

                logger.info('Will {4} replicate {0}@{1} to {2}:{3}@{1}'.format(
                    action.localfs,
                    snapname,
                    remote,
                    action.remotefs,
                    'fully' if full else 'incrementally'
                ))

                if full:
                    sendzfs(remote, None, snapname, action.localfs, action.remotefs, '', '')
                else:
                    prev = action.snapshots[idx - 1] if idx > 0 else action.anchor_snapshot
                    sendzfs(remote, prev['snapshot_name'], snapname, action.localfs, action.remotefs, '', '')


def _init(dispatcher, plugin):
    plugin.register_task_handler('replication.snapshot_dataset', SnapshotDatasetTask)
    plugin.register_schema_definition('replication', {
        'type': 'object',
        'properties': {
            'remote': {'type': 'string'},
            'remote_port': {'type': 'string'},
            'cipher': {
                'type': 'string',
                'enum': ['NORMAL', 'FAST', 'DISABLED']
            },
            'localfs': {'type': 'string'},
            'remotefs': {'type': 'string'},
            'compression': {
                'type': 'string',
                'enum': ['none', 'pigz', 'plzip', 'lz4', 'xz']
            },
            'bandlim' : {'type': 'string'},
            'followdelete': {'type': 'boolean'},
            'recursive': {'type': 'boolean'},
        },
        'additionalProperties': False,
    })

    plugin.register_task_handler('replication.snapshot_dataset', SnapshotDatasetTask)
    plugin.register_task_handler('replication.replicate_dataset', ReplicateDatasetTask)
