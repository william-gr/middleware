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
import time


class SendZFS(object):

    def __init__(self):
        self.buffer = b''
        self.zfs = libzfs.ZFS()
        self.throttle = 0
        self.bytes_avaliable = 0
        self.running = False
        self.throttle_buffer = threading.Event()

    def zfs_snap_send(self, snap, writefd, fromsnap):
        snap.send(writefd, fromsnap)
        os.close(writefd)

    def throttle_timer(self):
        if self.throttle:
            while self.running:
                self.bytes_avaliable = self.throttle
                self.throttle_buffer.set()
                time.sleep(1)
            self.bytes_avaliable = 0
            self.throttle = 0

    def send(self, remote, hostkey, fromsnap, tosnap, dataset, remotefs, compression, throttle, buffer_size, metrics_cb):

        self.throttle = throttle
        snap = self.zfs.get_snapshot('%s@%s' % (dataset, tosnap))

        readfd, writefd = os.pipe()
        snap_send_thread = threading.Thread(target=self.zfs_snap_send, args=(snap, writefd, fromsnap))
        snap_send_thread.setDaemon(True)
        snap_send_thread.start()

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

        self.running = True
        throttle_thread = threading.Thread(target=self.throttle_timer)
        throttle_thread.setDaemon(True)
        throttle_thread.start()

        while self.running:
            if self.throttle:
                left_buffer_size = buffer_size - len(self.buffer)
                if left_buffer_size > self.bytes_avaliable:
                    fetch_size = self.bytes_avaliable
                else:
                    fetch_size = left_buffer_size
            else:
                fetch_size = buffer_size - len(self.buffer)

            if fetch_size:
                new_data = os.read(readfd, fetch_size)
                self.bytes_avaliable -= len(new_data)

                if len(new_data):
                    self.buffer = self.buffer + new_data
                else:
                    self.write_pipe(replproc.stdin, metrics_cb)
                    break

                if len(self.buffer) == buffer_size:
                    self.write_pipe(replproc.stdin, metrics_cb)
            else:
                self.write_pipe(replproc.stdin, metrics_cb)
                self.throttle_buffer.wait()
                self.throttle_buffer.clear()

        replproc.stdin.close()
        replproc.wait()
        self.running = False

    def write_pipe(self, pipe, metrics_cb):
        try:
            pipe.write(self.buffer)
            pipe.flush()
        except IOError as e:
            if e.errno == errno.EPIPE or e.errno == errno.EINVAL:
                self.running = False
                raise
            else:
                raise
        if metrics_cb:
            metrics_cb(len(self.buffer))
        self.buffer = b''
