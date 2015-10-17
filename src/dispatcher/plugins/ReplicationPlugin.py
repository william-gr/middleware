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


from task import Task
from dispatcher.rpc import RpcException, SchemaHelper as h, description, accepts, returns
from lib.system import SubprocessException, system
from shlex import split as shlex_split
import re

# Pattern to match the system dataset.
system_re = re.compile('^[^/]+/.system.*')

#
# Parse a list of 'zfs list -H -t snapshot -p -o name,creation' output
# and place the result in a map of dataset name to a list of snapshot
# name and timestamp.
#
def mapfromdata(input):
    m = {}
    for line in input:
        if line == '':
            continue
        snapname, timestamp = line.split('\t')
        dataset, snapname = snapname.split('@')
        if m.has_key(dataset):
            m[dataset].append((snapname, timestamp))
        else:
            m[dataset] = [(snapname, timestamp)]
    return m

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

def rcro(is_truenas):
    if is_truenas:
        return '-o readonly=on '
    else:
        return ''

#
# Attempt to send a snapshot or increamental stream to remote.
#
def sendzfs(fromsnap, tosnap, dataset, localfs, remotefs, compression, throttle, reached_last, is_truenas = False):
    global results
    global templog

    # progressfile = '/tmp/.repl_progress_%d' % replication.id
    progressfile = '/tmp/.repl_progress_0' # XXX
    cmd = ['/sbin/zfs', 'send', '-Vp']
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
    replcmd = '%s%s/bin/dd obs=1m 2> /dev/null | /bin/dd obs=1m 2> /dev/null | %s "%s/sbin/zfs receive -F -d %s\'%s\' && echo Succeeded"' % (compress, throttle, sshcmd, decompress, rcro(is_truenas), remotefs)
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
    log.debug("Replication result: %s" % (msg))
    # XXX results[replication.id] = msg
    # if reached_last and msg == "Succeeded":
    #    replication.repl_lastsnapshot = tosnap
    #    replication.save()
    return (msg == "Succeeded")

class SnapshotDatasetTask(Task):
    def verify(self, pool, dataset, recursive, exclude_system, lifetime):
        # XXX: check whether pool exists
        return ['zpool:{0}'.format(pool)]

    def run(self, pool, dataset, recursive, exclude_system, lifetime):
        pass

@description("Runs an ZFS Replication Task with the specified arguments")
@accepts(h.all_of(
    h.ref('autorepl'),
    h.required(
        'remote',
        'remote_port',
        'dedicateduser',
        'cipher',
        'localfs',
        'remotefs',
        'compression',
        'bandlim',
        'followdelete',
        'recursive',
    ),
))
class ReplicateDatasetTask(Task):
    def verify(self, pool, dataset, options):
        pass

    def run(self, pool, dataset, options):
        remote = "127.0.0.1"    # Remote IP address
        remote_port = "22"      # SSH port number
        dedicateduser = None    # If a dedicated user is used.  If not None, a username
        cipher = "Normal"       # or "fast", "disabled"
        remotefs = "tank"       # Receiving dataset
        localfs = "tank"        # Local dataset
        compression = ""        # See map_compression
        bandlim = 0             # Bandwidth limit
        followdelete = False    # Whether to "follow delete" snapshots that are deleted from source side
        recursive = True        # Whether the replication is recursive (includes children)
        is_truenas = False      # XXX

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

        # Dedicated User
        if dedicateduser:
            sshcmd = "%s -l %s" % (sshcmd, dedicateduser.encode('utf-8'))

        # Remote IP/hostname and port.  This concludes the preparation task to build SSH command
        sshcmd = '%s -p %d %s' % (sshcmd, remote_port, remote)

        #
        # Create worklist.
        #

        remotefs_final = "%s%s%s" % (remotefs, localfs.partition('/')[1],localfs.partition('/')[2])
        # Examine local list of snapshots, then remote snapshots, and determine if there is any work to do.
        log.debug("Checking dataset %s" % (localfs))

        #
        # Grab map from local system.  TODO: this should be handled by a middleware cache.
        #
        if recursive:
            output, error = system('/sbin/zfs', 'list', '-Hpt', 'snapshot', '-o', 'name,creation', '-r', str(localfs))
        else:
            output, error = system('/sbin/zfs', 'list', '-Hpt', 'snapshot', '-o', 'name,creation', '-r', '-d', '1', str(localfs))

        # Parse output from local zfs list.
        if output != '':
            snaplist = output.split('\n')
            snaplist = [x for x in snaplist if not system_re.match(x)]
            map_source = mapfromdata(snaplist)
        if is_truenas:
            # Bi-directional replication: the remote side indicates that they are
            # willing to receive snapshots by setting readonly to 'on', which prevents
            # local writes.
            #
            # We expect to see "on" in the output, or cannot open '%s': dataset does not exist
            # in the error.  To be safe, also check for children's readonly state.
            may_proceed = False
            rzfscmd = '"zfs list -H -o readonly -t filesystem,volume -r %s"' % (remotefs_final)
            try:
                output, error = system(shlex_split('%s %s' % (sshcmd, rzfscmd)))
                if output != '' and output.find('off') == -1:
                    may_proceed = True
            except SubprocessException as e:
                if e.err != '':
                    if e.err.split('\n')[0] == ("cannot open '%s': dataset does not exist" % (remotefs_final)):
                        may_proceed = True
            if not may_proceed:
                # Report the problem and continue
                error, errmsg = send_mail(
                    subject="Replication was refused by receiving system! (%s)" % remote,
                    text="""
Hello,
    The remote system have denied our replication from local ZFS
    %s to remote ZFS %s.  Please change the 'readonly' property
    of:
        %s
    as well as its children to 'on' to allow receiving replication.
                    """ % (localfs, remotefs_final, remotefs_final), interval=datetime.timedelta(hours=24), channel='autorepl')
                # XXX results[replication.id] = 'Remote system denied receiving of snapshot on %s' % (remotefs_final)
                raise # XXX

        # TODO: convert this to zfs.snapshot.query
        # Grab map from remote system
        if recursive:
            rzfscmd = '"zfs list -H -t snapshot -p -o name,creation -r \'%s\'"' % (remotefs_final)
        else:
            rzfscmd = '"zfs list -H -t snapshot -p -o name,creation -d 1 -r \'%s\'"' % (remotefs_final)
        try:
            output, error = system(shlex_split('%s %s' % (sshcmd, rzfscmd)))
            if output != '':
                snaplist = output.split('\n')
                snaplist = [x for x in snaplist if not system_re.match(x) and x != '']
                # Process snaplist so that it matches the desired form of source side
                l = len(remotefs_final)
                snaplist = [ localfs + x[l:] for x in snaplist ]
                map_target = mapfromdata(snaplist)
        except SubprocessException as e:
            if e.err != '':
                raise TaskException(e.returncode, 'Failed: %s' % (e.err))
            else:
                map_target = {}

        # Calculate what needs to be done.

        tasks = {}
        delete_tasks = {}

        # Now we have map_source and map_target, which would be used to calculate the replication
        # path from source to target.
        for dataset in map_source:
            if map_target.has_key(dataset):
                # Find out the last common snapshot.
                #
                # We have two ordered lists, list_source and list_target
                # which are ordered by the creation time.  Because they
                # are ordered, we can have two pointers and scan backward
                # until we hit one identical item, or hit the end of
                # either list.
                list_source = map_source[dataset]
                list_target = map_target[dataset]
                i = len(list_source) - 1
                j = len(list_target) - 1
                sourcesnap, sourcetime = list_source[i]
                targetsnap, targettime = list_target[j]
                while i >= 0 and j >= 0:
                    # found.
                    if sourcesnap == targetsnap and sourcetime == targettime:
                        break
                    elif sourcetime > targettime:
                        i-=1
                        if i < 0:
                            break
                        sourcesnap, sourcetime = list_source[i]
                    else:
                        j-=1
                        if j < 0:
                            break
                        targetsnap, targettime = list_target[j]
                if sourcesnap == targetsnap and sourcetime == targettime:
                    # found: i, j points to the right position.
                    # we do not care much if j is pointing to the last snapshot
                    # if source side have new snapshot(s), report it.
                    if i < len(list_source) - 1:
                        tasks[dataset] = [ m[0] for m in list_source[i:] ]
                    if followdelete:
                        # All snapshots that do not exist on the source side should
                        # be deleted when followdelete is requested.
                        delete_set = set([ m[0] for m in list_target]) - set([ m[0] for m in list_source])
                        if len(delete_set) > 0:
                            delete_tasks[dataset] = delete_set
                else:
                    # no identical snapshot found, nuke and repave.
                    tasks[dataset] = [None] + [ m[0] for m in list_source[i:] ]
            else:
                # New dataset on source side: replicate to the target.
                tasks[dataset] = [None] + [ m[0] for m in map_source[dataset] ]

        # Removed dataset(s)
        for dataset in map_target:
            if not map_source.has_key(dataset):
                tasks[dataset] = [map_target[dataset][-1][0], None]

        previously_deleted = "/"
        l = len(localfs)
        total_datasets = len(tasks.keys())
        if total_datasets == 0:
            # XXX results[replication.id] = 'Up to date'
            raise # XXX
        current_dataset = 0
        for dataset in sorted(tasks.keys()):
            tasklist = tasks[dataset]
            current_dataset += 1
            reached_last = (current_dataset == total_datasets)
            if tasklist[0] == None:
                # No matching snapshot(s) exist.  If there is any snapshots on the
                # target side, destroy all existing snapshots so we can proceed.
                if map_target.has_key(dataset):
                    list_target = map_target[dataset]
                    snaplist = [ remotefs_final + dataset[l:] + '@' + x[0] for x in list_target ]
                    failed_snapshots = []
                    for snapshot in snaplist:
                        rzfscmd = '"zfs destroy \'%s\'"' % (snapshot)
                        args = shlex_split(str('%s %s' % (sshcmd, rzfscmd)))
                        try:
                            output, error = system(args)
                        except SubprocessException:
                            log.warn("Unable to destroy snapshot %s on remote system" % (snapshot))
                            failed_snapshots.append(snapshot)
                    if len(failed_snapshots) > 0:
                        # We can't proceed in this situation, report
                        error, errmsg = send_mail(
                            subject="Replication failed! (%s)" % remote,
                            text="""
Hello,
    The replication failed for the local ZFS %s because the remote system
    has diverged snapshots with us and we were unable to remove them,
    including:
%s
                            """ % (localfs, failed_snapshots), interval=datetime.timedelta(hours=2), channel='autorepl')
                        # XXX results[replication.id] = 'Unable to destroy remote snapshot: %s' % (failed_snapshots)
                        ### rzfs destroy %s
                psnap = tasklist[1]
                success = sendzfs(None, psnap, dataset, localfs, remotefs, throttle, compression, reached_last)
                if success:
                    for nsnap in tasklist[2:]:
                        success = sendzfs(psnap, nsnap, dataset, localfs, remotefs, throttle, compression, reached_last)
                        if not success:
                            # Report the situation
                            error, errmsg = send_mail(
                                subject="Replication failed at %s@%s -> %s" % (dataset, psnap, nsnap),
                                text="""
Hello,
    The replication failed for the local ZFS %s while attempting to
    apply incremental send of snapshot %s -> %s to %s
                                """ % (dataset, psnap, nsnap, remote), interval=datetime.timedelta(hours=2), channel='autorepl')
                            # XXX results[replication.id] = 'Failed: %s (%s->%s)' % (dataset, psnap, nsnap)
                            break
                        psnap = nsnap
                else:
                    # Report the situation
                    error, errmsg = send_mail(
                        subject="Replication failed when sending %s@%s" % (dataset, psnap),
                        text="""
Hello,
    The replication failed for the local ZFS %s while attempting to
    send snapshot %s to %s
                        """ % (dataset, psnap, remote), interval=datetime.timedelta(hours=2), channel='autorepl')
                    # XXX results[replication.id] = 'Failed: %s (%s)' % (dataset, psnap)
                    # Continue to try the next task, if there is any.
                    continue
            elif tasklist[1] != None:
                # This is incremental send.  We always send psnap -> nsnap.
                psnap = tasklist[0]
                allsucceeded = True
                for nsnap in tasklist[1:]:
                    success = sendzfs(psnap, nsnap, dataset, localfs, remotefs, throttle, compression, reached_last)
                    allsucceeded = allsucceeded and success
                    if not success:
                        # Report the situation
                        error, errmsg = send_mail(
                            subject="Replication failed at %s@%s -> %s" % (dataset, psnap, nsnap),
                            text="""
Hello,
    The replication failed for the local ZFS %s while attempting to
    apply incremental send of snapshot %s -> %s to %s
                            """ % (dataset, psnap, nsnap, remote), interval=datetime.timedelta(hours=2), channel='autorepl')
                        # XXX results[replication.id] = 'Failed: %s (%s->%s)' % (dataset, psnap, nsnap)
                        # Bail out: if the receive fails, no task in the current list would succeed.
                        break
                    psnap = nsnap
                if allsucceeded and delete_tasks.has_key(dataset):
                    zfsname = remotefs_final + dataset[l:]
                    for snapshot in delete_tasks[dataset]:
                        rzfscmd = '"zfs destroy -d \'%s@%s\'"' % (zfsname, snapshot)
                        try:
                            system(shlex_split('%s %s' % (sshcmd, rzfscmd)))
                        except:
                            pass
                if allsucceeded:
                    # XXX results[replication.id] = 'Succeeded'
                    continue
            else:
                # Remove the named dataset because it's deleted from the source.
                zfsname = remotefs_final + dataset[l:]
                if zfsname.startswith(previously_deleted):
                    continue
                else:
                    rzfscmd = '"zfs destroy -r \'%s\'"' % (zfsname)
                    try:
                        system(shlex_split('%s %s' % (sshcmd, rzfscmd)))
                        previously_deleted = zfsname
                    except:
                        log.warn("Unable to destroy dataset %s on remote system" % (zfsname))

def _init(dispatcher, plugin):
    plugin.register_task_handler('replication.snapshot_dataset', SnapshotDatasetTask)
    plugin.register_schema_definition('autorepl', {
        'type': 'object',
        'properties': {
            'remote': {'type': 'string'},
            'remote_port': {'type': 'string'},
            'dedicateduser': {'type': 'string'},
            'cipher': {'type': 'string'},
            'localfs': {'type': 'string'},
            'remotefs': {'type': 'string'},
            'compression': {
                'type': 'string',
                'enum': ['none', 'pigz', 'plzip', 'lz4', 'xz']
            },
            'bandlim' : {'type': 'string'},
            'followdelete' : {'type': 'boolean'},
            'recursive' : {'type': 'boolean'},
        },
        'additionalProperties': False,
    })
    plugin.register_task_handler('replication.replicate_dataset', ReplicateDatasetTask)
