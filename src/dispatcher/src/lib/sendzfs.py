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

import libzfs
import os
import threading
import subprocess
import tempfile
import errno


class SendZFS(object):

    def __init__(self):
        self.buffer = b''
        self.zfs = libzfs.ZFS()

    def send(self, remote, hostkey, fromsnap, tosnap, dataset, remotefs, compression, throttle, buffer_size, metrics_cb):

        snap = self.zfs.get_snapshot('%s@%s' % (dataset, tosnap))

        readfd, writefd = os.pipe()
        thread = threading.Thread(target=snap.send, args=(writefd,fromsnap))
        thread.start()

        with tempfile.NamedTemporaryFile('w') as hostsfile:
            print(hostkey, file=hostsfile.file)

        sshcmd = '/usr/bin/ssh -i /etc/replication/key -o BatchMode=yes' \
            ' -o UserKnownHostsFile=%s' \
            ' -o StrictHostKeyChecking=yes' \
            ' -o ConnectTimeout=7 %s ' % (hostsfile.name, remote)

        replcmd = '%s/sbin/zfs receive -F \'%s\'' % (sshcmd, remotefs)

        replproc = subprocess.Popen(
            replcmd,
            shell=True,
            stdin=subprocess.PIPE,
        )

        while True:
            new_data = os.read(readfd, (buffer_size - len(buffer)))

            if len(new_data):
                buffer = buffer + new_data
            else:
                if metrics_cb:
                    self.write_pipe(replproc.stdin)
                    if metrics_cb:
                        metrics_cb(len(buffer))
                    break

            if len(buffer) == buffer_size:
                self.write_pipe(replproc.stdin)
                self.buffer = b''
                if metrics_cb:
                    metrics_cb(buffer_size)

        replproc.stdin.close()
        replproc.wait()

    def write_pipe(self, pipe):
        try:
            pipe.write(self.buffer)
            pipe.flush()
        except IOError as e:
            if e.errno == errno.EPIPE or e.errno == errno.EINVAL:
                # Stop loop on "Invalid pipe" or "Invalid argument".
                # No sense in continuing with broken pipe.
                #break????
                raise
            else:
                # Raise any other error.
                raise
