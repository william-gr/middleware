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

import os
import libzfs
import bsd


zfs = libzfs.ZFS()
root_mount = bsd.statfs('/')
boot_pool, be_prefix = root_mount.source.split('/')[:2]
root_ds = zfs.get_dataset('/'.join([boot_pool, be_prefix]))


class BootEnvironment(object):
    def __init__(self, name):
        self.ds = zfs.get_dataset(root_ds.name + '/' + name)

    def __str__(self):
        return "<be.BootEnvironment name '{0}'>".format(self.name)

    def __repr__(self):
        return str(self)

    def __getstate__(self):
        return {
            'name': self.name,
            'fullname': self.fullname,
            'created': self.created,
            'active': self.active,
            'boot': self.boot,
        }

    @property
    def name(self):
        return self.ds.name.split('/')[-1]

    @property
    def fullname(self):
        return self.ds.name

    @property
    def active(self):
        return self.fullname == root_mount.source

    @property
    def boot(self):
        pool = zfs.get(boot_pool)
        return self.fullname == pool.properties['bootfs'].value

    @property
    def created(self):
        return self.ds.properties['creation'].value

    @property
    def mountpoint(self):
        return self.ds.properties['mountpoint'].value

    def activate(self):
        pool = zfs.get(boot_pool)
        pool.properties['bootfs'].value = self.fullname

    def rename(self, new_name):
        self.ds.rename('/'.join([boot_pool, be_prefix, new_name]))

    def mount(self, path=None):
        if not path:
            path = os.tmpfile()

        bsd.nmount(
            source=self.fullname,
            fspath=path,
            fstype='zfs'
        )

        return path

    def unmount(self):
        self.ds.umount()

    def delete(self):
        if self.active or self.boot:
            raise IOError('Cannot delete active boot environment')

        self.ds.delete()


def create(name, origin=None):
    if not origin:
        origin = active_be()

    raise NotImplementedError()

def active_be():
    return BootEnvironment(root_mount.source)


def list():
    for i in root_ds.children:
        yield BootEnvironment(i.name.split('/')[-1])
