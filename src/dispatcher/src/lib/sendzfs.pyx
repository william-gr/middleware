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
import cython
from libc.stdlib cimport malloc, free

cdef extern from "sys/types.h":
    ctypedef char int8_t
    ctypedef unsigned char uint8_t
    ctypedef unsigned char uchar_t
    ctypedef short int16_t
    ctypedef unsigned short uint16_t
    ctypedef int int32_t
    ctypedef int int_t
    ctypedef unsigned int uint_t
    ctypedef unsigned int uint32_t
    ctypedef long long int64_t
    ctypedef unsigned long long uint64_t
    ctypedef int boolean_t
    ctypedef long long hrtime_t

cdef extern from "unistd.h":
    int write(int fd, uint8_t *buf, int nbytes)
    int read(int fd, uint8_t *buf, int nbytes)

cdef class SendZFS(object):

    def __init__(self):
        self.zfs = libzfs.ZFS()
        self.throttle = 0
        self.bytes_avaliable = 0
        self.running = False
        self.throttle_buffer = threading.Event()

    cdef uint8_t *buffer
    cdef int buffer_position

    @staticmethod
    cdef int read_fd(int fd, uint8_t *buf, int nbytes, int curr_pos):
        cdef int ret
        cdef int done = 0

        while done < nbytes:
            try:
                ret = read(fd, <uint8_t *>(buf + curr_pos + done), nbytes - done)
                if ret == 0:
                    return 0
            except IOError as e:
                if e.errno == errno.EINTR or e.errno == errno.EAGAIN:
                    continue
                else:
                    raise

            done += ret

        return done

    @staticmethod
    cdef int write_fd(int fd, uint8_t *buf, int nbytes):
        cdef int ret
        cdef int done = 0

        while done < nbytes:
            try:
                ret = write(fd, <uint8_t *>(buf + done), nbytes - done)
            except IOError as e:
                if e.errno == errno.EINTR or e.errno == errno.EAGAIN:
                    continue
                elif e.errno == errno.EPIPE or e.errno == errno.EINVAL:
                    return -1
                else:
                    raise

            done += ret

        return done

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

        self.buffer = <uint8_t *>malloc(buffer_size * sizeof(uint8_t))
        self.buffer_position = 0

        self.throttle = throttle
        snap = self.zfs.get_snapshot('%s@%s' % (dataset, tosnap))

        zfs_readfd, zfs_writefd = os.pipe()
        snap_send_thread = threading.Thread(target=self.zfs_snap_send, args=(snap, zfs_writefd, fromsnap))
        snap_send_thread.setDaemon(True)
        snap_send_thread.start()

        hostsfile = tempfile.NamedTemporaryFile('w')
        hostsfile.write(hostkey)
        hostsfile.close()

        sshcmd = '/usr/bin/ssh -i /etc/replication/key -o BatchMode=yes' \
            ' -o UserKnownHostsFile=%s' \
            ' -o StrictHostKeyChecking=yes' \
            ' -o ConnectTimeout=7 %s ' % (hostsfile.name, remote)

        replcmd = '%s/sbin/zfs receive -F \'%s\'' % (sshcmd, remotefs)

        ssh_readfd, ssh_writefd = os.pipe()
        replproc = subprocess.Popen(
            replcmd,
            shell=True,
            stdin=ssh_readfd,
        )

        self.running = True
        throttle_thread = threading.Thread(target=self.throttle_timer)
        throttle_thread.setDaemon(True)
        throttle_thread.start()

        while self.running:
            if self.throttle:
                left_buffer_size = buffer_size - self.buffer_position + 1
                if left_buffer_size > self.bytes_avaliable:
                    fetch_size = self.bytes_avaliable
                else:
                    fetch_size = left_buffer_size
            else:
                fetch_size = buffer_size - self.buffer_position + 1

            if fetch_size:
                read_size = SendZFS.read_fd(zfs_readfd, self.buffer, fetch_size, self.buffer_position)
                if read_size > 0:
                    self.bytes_avaliable -= read_size
                    self.buffer_position += read_size
                elif read_size == 0:
                    write_size = SendZFS.write_fd(ssh_writefd, self.buffer, (self.buffer_position + 1))
                    if write_size == -1:
                        self.running = False
                        break
                    self.buffer_position -= (write_size - 1)
                    if metrics_cb:
                        metrics_cb(write_size)
                    break

                if (self.buffer_position + 1) == buffer_size:
                    write_size = SendZFS.write_fd(ssh_writefd, self.buffer, (self.buffer_position + 1))
                    if write_size == -1:
                        self.running = False
                        break
                    self.buffer_position -= (write_size - 1)
                    if metrics_cb:
                        metrics_cb(write_size)
            else:
                write_size = SendZFS.write_fd(ssh_writefd, self.buffer, (self.buffer_position + 1))
                if write_size == -1:
                    self.running = False
                    break
                self.buffer_position -= (write_size - 1)
                if metrics_cb:
                    metrics_cb(write_size)
                self.throttle_buffer.wait()
                self.throttle_buffer.clear()

        replproc.stdin.close()
        replproc.wait()
        self.running = False
        free(self.buffer)
