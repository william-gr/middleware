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
import select
import fcntl
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
    int write(int fd, uint8_t *buf, int nbytes) nogil
    int read(int fd, uint8_t *buf, int nbytes) nogil

cdef class SendZFS(object):
    cdef object zfs
    cdef int throttle
    cdef int bytes_avaliable
    cdef int running
    cdef object throttle_buffer

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

        try:
            with nogil:
                ret = read(fd, <uint8_t *>(buf + curr_pos), nbytes)
        except IOError as e:
            if e.errno == errno.EINTR or e.errno == errno.EAGAIN:
                continue
            else:
                raise

        return ret

    @staticmethod
    cdef int write_fd(int fd, uint8_t *buf, int nbytes, int term_readfd):
        cdef int ret
        cdef int done = 0

        try:
            while True:
                input = [term_readfd]
                output = [fd]
                inputready,outputready,exceptready = select.select(input, output, [])

                if outputready:
                    try:
                        with nogil:
                            ret = write(fd, <uint8_t *>(buf + done), nbytes - done)
                    except IOError as e:
                        if e.errno == errno.EINTR or e.errno == errno.EAGAIN:
                            continue
                        elif e.errno == errno.EPIPE or e.errno == errno.EINVAL:
                            return -1
                        else:
                            raise

                    done += ret

                    if done == nbytes:
                        return done
                if inputready:
                    return -1
        except OSError:
            return -1

    def zfs_snap_send(self, snap, term_writefd, writefd, fromsnap):
        try:
            snap.send(writefd, fromsnap)
        except libzfs.ZFSException:
            self.running = False
            os.write(term_writefd, b'1')
            os.close(term_writefd)
            raise
        os.close(writefd)

    def throttle_timer(self):
        if self.throttle != 0 :
            while self.running is True:
                self.bytes_avaliable = self.throttle
                self.throttle_buffer.set()
                time.sleep(1)
            self.bytes_avaliable = 0
            self.throttle = 0

    def check_ssh_output(self, term_writefd, ssh_writefd, proc):
        output = b''
        while True:
            newline = proc.stdout.readline()
            if newline == b'':
                break
            output += newline
        self.running = False
        os.close(ssh_writefd)
        proc.stdout.close()
        proc.wait()
        os.write(term_writefd, b'1')
        os.close(term_writefd)
        if proc.poll() != 0:
            raise ChildProcessError(output.decode('utf-8'))

    def send(self, remote, hostkey, fromsnap, tosnap, dataset, remotefs, compression, throttle, buffer_size, metrics_cb):

        self.buffer = <uint8_t *>malloc(buffer_size * sizeof(uint8_t))
        self.buffer_position = 0

        self.throttle = throttle

        snap = self.zfs.get_snapshot('{0}@{1}'.format(dataset, tosnap))
        if fromsnap is None:
            fsnap = fromsnap
        else:
            fsnap = '{0}@{1}'.format(dataset, fromsnap)

        term_readfd, term_writefd = os.pipe()

        zfs_readfd, zfs_writefd = os.pipe()
        snap_send_thread = threading.Thread(target=self.zfs_snap_send, args=(snap, term_writefd, zfs_writefd, fsnap))
        snap_send_thread.setDaemon(True)
        snap_send_thread.start()

        with tempfile.NamedTemporaryFile('w') as hostsfile:

            if hostkey is None:
                h_file = '/dev/null'
                h_check = 'no'
            else:
                hostsfile.write(hostkey)
                hostsfile.flush()
                h_file = hostsfile.name
                h_check = 'yes'

            sshcmd = '/usr/bin/ssh -i /etc/replication/key -o BatchMode=yes' \
                ' -o UserKnownHostsFile=%s' \
                ' -o StrictHostKeyChecking=%s' \
                ' -o ConnectTimeout=7 %s ' % (h_file, h_check, remote)

            replcmd = '%s/sbin/zfs receive -F \'%s\'' % (sshcmd, remotefs)

            ssh_readfd, ssh_writefd = os.pipe()
            fl = fcntl.fcntl(ssh_writefd, fcntl.F_GETFL)
            fcntl.fcntl(ssh_writefd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            try:
                replproc = subprocess.Popen(
                    replcmd,
                    shell=True,
                    stdin=ssh_readfd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                self.running = True
            except (OSError, ValueError):
                self.running = False
                raise

            throttle_thread = threading.Thread(target=self.throttle_timer)
            throttle_thread.setDaemon(True)
            throttle_thread.start()

            check_ssh_stat_thread = threading.Thread(target=self.check_ssh_output,
                                                    args=(term_writefd, ssh_writefd, replproc))
            check_ssh_stat_thread.start()

            while self.running:
                if self.throttle:
                    left_buffer_size = buffer_size - self.buffer_position
                    if left_buffer_size > self.bytes_avaliable:
                        fetch_size = self.bytes_avaliable
                    else:
                        fetch_size = left_buffer_size
                else:
                    fetch_size = buffer_size - self.buffer_position

                if fetch_size:
                    read_size = SendZFS.read_fd(zfs_readfd, self.buffer, fetch_size, self.buffer_position)
                    if read_size > 0:
                        self.bytes_avaliable -= read_size
                        self.buffer_position += read_size
                    elif read_size == 0:
                        write_size = SendZFS.write_fd(ssh_writefd, self.buffer, self.buffer_position, term_readfd)
                        if write_size == -1:
                            self.running = False
                            break
                        self.buffer_position -= write_size
                        if metrics_cb:
                            metrics_cb(write_size)
                        break

                    if self.buffer_position == buffer_size:
                        write_size = SendZFS.write_fd(ssh_writefd, self.buffer, self.buffer_position, term_readfd)
                        if write_size == -1:
                            self.running = False
                            break
                        self.buffer_position -= write_size
                        if metrics_cb:
                            metrics_cb(write_size)
                else:
                    write_size = SendZFS.write_fd(ssh_writefd, self.buffer, self.buffer_position, term_readfd)
                    if write_size == -1:
                        self.running = False
                        break
                    self.buffer_position -= write_size
                    if metrics_cb:
                        metrics_cb(write_size)
                    self.throttle_buffer.wait()
                    self.throttle_buffer.clear()

            self.running = False
            free(self.buffer)
