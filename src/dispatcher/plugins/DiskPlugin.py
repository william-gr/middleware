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

import os
import re
import errno
import logging
import gevent
import gevent.monkey
import geom
from collections import defaultdict
from fnutils import first_or_default
from cam import CamDevice
from cache import CacheStore
from lib.geom import confxml
from lib.system import system, SubprocessException
from task import Provider, Task, TaskStatus, TaskException, VerifyException, query
from dispatcher.rpc import RpcException, accepts, returns, description
from dispatcher.rpc import SchemaHelper as h

# Note the following monkey patch is required for pySMART to work correctly
gevent.monkey.patch_subprocess()
from pySMART import Device


diskinfo_cache = CacheStore()
logger = logging.getLogger('DiskPlugin')


class DiskProvider(Provider):
    @query('disk')
    def query(self, filter=None, params=None):
        def extend(disk):
            disk['online'] = self.is_online(disk['path'])
            disk['status'] = diskinfo_cache.get(disk['id'])

            return disk

        return self.datastore.query('disks', *(filter or []), callback=extend, **(params or {}))

    @accepts(str)
    @returns(bool)
    def is_online(self, name):
        return os.path.exists(name)

    @accepts(str)
    @returns(str)
    def partition_to_disk(self, part_name):
        # Is it disk name?
        d = get_disk_by_path(part_name)
        if d:
            return part_name

        part = self.get_partition_config(part_name)
        return part['disk']

    @accepts(str)
    @returns(str)
    def disk_to_data_partition(self, disk_name):
        disk = diskinfo_cache.get(disk_name)
        return disk['data_partition_path']

    @accepts(str)
    def get_disk_config(self, name):
        disk = diskinfo_cache.get(name)
        if not disk:
            raise RpcException(errno.ENOENT, "Disk {0} not found".format(name))

        return disk

    @accepts(str)
    def get_partition_config(self, part_name):
        for name, disk in diskinfo_cache.itervalid():
            for part in disk['partitions']:
                if part_name in part['paths']:
                    result = part.copy()
                    result['disk'] = disk['path']
                    return result

        raise RpcException(errno.ENOENT, "Partition {0} not found".format(part_name))


@accepts(str, str, h.object())
class DiskGPTFormatTask(Task):
    def describe(self, disk, fstype, params=None):
        return "Formatting disk {0}".format(os.path.basename(disk))

    def verify(self, disk, fstype, params=None):
        if not diskinfo_cache.exists(disk):
            raise VerifyException(errno.ENOENT, "Disk {0} not found".format(disk))

        if fstype not in ['freebsd-zfs']:
            raise VerifyException(errno.EINVAL, "Unsupported fstype {0}".format(fstype))

        return ['disk:{0}'.format(disk)]

    def run(self, disk, fstype, params=None):
        if params is None:
            params = {}

        blocksize = params.pop('blocksize', 4096)
        swapsize = params.pop('swapsize', 2048)
        bootcode = params.pop('bootcode', '/boot/pmbr-datadisk')

        try:
            system('/sbin/gpart', 'destroy', '-F', disk)
        except SubprocessException:
            # ignore
            pass

        try:
            system('/sbin/gpart', 'create', '-s', 'gpt', disk)
            if swapsize > 0:
                system('/sbin/gpart', 'add', '-a', str(blocksize), '-b', '128', '-s', '{0}M'.format(swapsize), '-t', 'freebsd-swap', disk)
                system('/sbin/gpart', 'add', '-a', str(blocksize), '-t', fstype, disk)
            else:
                system('/sbin/gpart', 'add', '-a', str(blocksize), '-b', '128', '-t', fstype, disk)

            system('/sbin/gpart', 'bootcode', '-b', bootcode, disk)
        except SubprocessException, err:
            raise TaskException(errno.EFAULT, 'Cannot format disk: {0}'.format(err.err))

        generate_disk_cache(self.dispatcher, disk)


class DiskBootFormatTask(Task):
    def describe(self, disk):
        return "Formatting bootable disk {0}".format(disk)

    def verify(self, disk):
        if not diskinfo_cache.exists(disk):
            raise VerifyException(errno.ENOENT, "Disk {0} not found".format(disk))

        return ['disk:{0}'.format(disk)]

    def run(self, disk):
        try:
            system('/sbin/gpart', 'destroy', '-F', disk)
        except SubprocessException:
            # ignore
            pass

        try:
            system('/sbin/gpart', 'create', '-s', 'gpt', disk)
            system('/sbin/gpart', 'add', '-t', 'bios-boot', '-i', '1', '-s', '512k', disk)
            system('/sbin/gpart', 'add', '-t', 'freebsd-zfs', '-i', '2', '-a', '4k', disk)
            system('/sbin/gpart', 'set', '-a', 'active', disk)
        except SubprocessException, err:
            raise TaskException(errno.EFAULT, 'Cannot format disk: {0}'.format(err.err))


class DiskInstallBootloaderTask(Task):
    def describe(self, disk):
        return "Installing bootloader on disk {0}".format(disk)

    def verify(self, disk):
        if not diskinfo_cache.exists(disk):
            raise VerifyException(errno.ENOENT, "Disk {0} not found".format(disk))

        return ['disk:{0}'.format(disk)]

    def run(self, disk):
        try:
            disk = os.path.join('/dev', disk)
            system('/usr/local/sbin/grub-install', "--modules='zfs part_gpt'", disk)
        except SubprocessException, err:
            raise TaskException(errno.EFAULT, 'Cannot install GRUB: {0}'.format(err.err))


@accepts(str, bool)
class DiskEraseTask(Task):
    def __init__(self, dispatcher):
        super(DiskEraseTask, self).__init__(dispatcher)
        self.started = False
        self.mediasize = 0
        self.remaining = 0

    def verify(self, disk, erase_data=False):
        if not diskinfo_cache.exists(disk):
            raise VerifyException(errno.ENOENT, "Disk {0} not found".format(disk))

        return ['disk:{0}'.format(disk)]

    def run(self, disk, erase_data=False):
        try:
            system('/sbin/zpool', 'labelclear', '-f', disk)
            generate_disk_cache(self.dispatcher, disk)
            if (self.dispatcher.call_sync("disks.get_disk_config", disk)['partitions']):
                system('/sbin/gpart', 'destroy', '-F', disk)
        except SubprocessException, err:
            raise TaskException(errno.EFAULT, 'Cannot erase disk: {0}'.format(err.err))

        if erase_data:
            diskinfo = diskinfo_cache.get(disk)
            fd = open(disk, 'w')
            zeros = b'\0' * (1024 * 1024)
            self.mediasize = diskinfo['mediasize']
            self.remaining = self.mediasize
            self.started = True

            while self.remaining > 0:
                amount = min(len(zeros), self.remaining)
                fd.write(zeros[:amount])
                fd.flush()
                self.remaining -= amount

        generate_disk_cache(self.dispatcher, disk)

    def get_status(self):
        if not self.started:
            return TaskStatus(0, 'Erasing disk...')

        return TaskStatus(self.remaining / self.mediasize, 'Erasing disk...')


@accepts({
    'allOf': [
        {'$ref': 'disk'},
        {'not': {'required': ['name', 'serial', 'description', 'mediasize']}}
    ]
})
class DiskConfigureTask(Task):
    def verify(self, name, updated_fields):
        return [os.path.basename(name)]

    def run(self, name, updated_fields):
        disk = self.datastore.query('disks', ('name', '=', name))
        diskinfo_cache.invalidate(disk)


class DiskDeleteTask(Task):
    def verify(self, name):
        pass

    def run(self, name):
        pass


def get_twcli(controller):
    re_port = re.compile(r'^p(?P<port>\d+).*?\bu(?P<unit>\d+)\b', re.S | re.M)
    output, err = system("/usr/local/sbin/tw_cli", "/c{0}".format(controller), "show")

    units = {}
    for port, unit in re_port.findall(output):
        units[int(unit)] = int(port)

    return units


def device_to_identifier(doc, name, serial=None):
    if serial:
        return "serial:{0}".format(serial)

    search = doc.xpath("//class[name = 'PART']/..//*[name = '{0}']//config[type = 'freebsd-zfs']/rawuuid".format(name))
    if len(search) > 0:
        return "uuid:{0}".format(search[0].text)

    search = doc.xpath("//class[name = 'PART']/geom/..//*[name = '{0}']//config[type = 'freebsd-ufs']/rawuuid".format(name))
    if len(search) > 0:
        return "uuid:{0}".format(search[0].text)

    search = doc.xpath("//class[name = 'LABEL']/geom[name = '{0}']/provider/name".format(name))
    if len(search) > 0:
        return "label:{0}".format(search[0].text)

    search = doc.xpath("//class[name = 'DEV']/geom[name = '{0}']".format(name))
    if len(search) > 0:
        return "devicename:{0}".format(name)

    return ''


def info_from_device(devname):
    disk_info = {
        'serial': None,
        'max_rotation': None,
        'smart_enabled': False,
        'smart_capable': False,
        'smart_status': None,
        'model': None,
        'is_ssd': False,
        'interface': None}

    # TODO, fix this to deal with above generated args for interface
    dev_smart_info = Device(os.path.join('/dev/', devname))
    disk_info['is_ssd'] = dev_smart_info.is_ssd
    disk_info['smart_capable'] = dev_smart_info.smart_capable
    if dev_smart_info.smart_capable:
        disk_info['serial'] = dev_smart_info.serial
        disk_info['model'] = dev_smart_info.model
        disk_info['max_rotation'] = dev_smart_info.rotation_rate
        disk_info['interface'] = dev_smart_info.interface
        disk_info['smart_enabled'] = dev_smart_info.smart_enabled
        if dev_smart_info.smart_enabled:
            disk_info['smart_status'] = dev_smart_info.assessment

    return disk_info


def get_disk_by_path(path):
    for ident, disk in diskinfo_cache.itervalid():
        if disk['path'] == path:
            return disk

        if disk['is_multipath']:
            if path in disk['multipath_members']:
                return disk

    return None


def clean_multipaths():
    geom.scan()
    for i in geom.class_by_name('MULTIPATH').geoms:
        logger.info('Destroying multipath device %s', i.name)
        system('/sbin/gmultipath', 'destroy', i.name)


def get_multipath_name():
    geom.scan()
    return 'multipath{0}'.format(len(list(geom.class_by_name('MULTIPATH').geoms)))


def attach_to_multipath(dispatcher, disk, path):
    logger.info("Device node %s is another path to disk <%s> (%s)", path, disk['identifier'], disk['description'])

    ds_disk = dispatcher.datastore.get_by_id('disks', disk['identifier'])

    if disk['is_multipath']:
        if path in disk['multipath_members']:
            # Already added
            return

        # Attach new disk
        system('/sbin/gmultipath', 'add', disk['multipath_node'], path)
        ret = {
            'multipath_members': disk['multipath_members'] + [path]
        }
    else:
        # Create new multipath
        logger.info('Creating new multipath device')

        # If disk was previously tied to specific cdev path (/dev/multipath[0-9]+)
        # reuse that path. Otherwise pick up first multipath device name available
        if ds_disk and ds_disk['is_multipath']:
            nodename = os.path.basename(ds_disk['path'])
            logger.info('Reusing %s path', nodename)
        else:
            nodename = get_multipath_name()
            logger.info('Using new %s path', nodename)

        system('/sbin/gmultipath', 'create', nodename, disk['path'], path)
        ret = {
            'is_multipath': True,
            'multipath_node': nodename,
            'multipath_members': [disk['path'], path],
            'path': os.path.join('/dev', nodename)
        }

    return ret


def generate_disk_cache(dispatcher, path):
    geom.scan()
    name = os.path.basename(path)
    gdisk = geom.geom_by_name('DISK', name)
    gpart = geom.geom_by_name('PART', name)
    gmultipath = geom.geom_by_name('MULTIPATH', path.split('/')[-1])
    multipath_info = None

    if gmultipath:
        # MEDIACHANGE event on /dev/multipath/multipath%d
        # -> use first member for hardware queries
        cons = gmultipath.consumers.next()
        gdisk = cons.provider.geom

    if not gdisk:
        return

    disk_info = info_from_device(gdisk.name)
    serial = disk_info['serial']

    # Path repesents disk device (not multipath device) and has serial number attached
    if serial and not gmultipath:
        # Check if device could be part of multipath configuration
        d = diskinfo_cache.get('serial:{0}'.format(serial))
        if d and d['path'] != path:
            multipath_info = attach_to_multipath(dispatcher, d, path)

    provider = gdisk.providers.next()
    partitions = []

    if gpart:
        for p in gpart.providers:
            paths = [os.path.join("/dev", p.name)]
            label = p.config['label']
            uuid = p.config['rawuuid']

            if label:
                paths.append(os.path.join("/dev/gpt", label))

            if uuid:
                paths.append(os.path.join("/dev/gptid", uuid))

            partitions.append({
                'name': p.name,
                'paths': paths,
                'mediasize': int(p.mediasize),
                'uuid': uuid,
                'type': p.config['type'],
                'label': p.config.get('label')
            })

    identifier = device_to_identifier(confxml(), name, serial)
    data_part = first_or_default(lambda x: x['type'] == 'freebsd-zfs', partitions)
    data_uuid = data_part["uuid"] if data_part else None
    swap_part = first_or_default(lambda x: x['type'] == 'freebsd-swap', partitions)
    swap_uuid = swap_part["uuid"] if swap_part else None
    camdev = CamDevice(gdisk.name)

    disk = {
        'path': path,
        'mediasize': provider.mediasize,
        'sectorsize': provider.sectorsize,
        'description': provider.config['descr'],
        'identifier': identifier,
        'serial': serial,
        'max_rotation': disk_info['max_rotation'],
        'smart_capable': disk_info['smart_capable'],
        'smart_enabled': disk_info['smart_enabled'],
        'smart_status': disk_info['smart_status'],
        'model': disk_info['model'],
        'interface': disk_info['interface'],
        'is_ssd': disk_info['is_ssd'],
        'is_multipath': False,
        'id': identifier,
        'schema': gpart.config.get('scheme') if gpart else None,
        'controller': camdev.__getstate__(),
        'partitions': partitions,
        'data_partition_uuid': data_uuid,
        'data_partition_path': os.path.join("/dev/gptid", data_uuid) if data_uuid else None,
        'swap_partition_uuid': swap_uuid,
        'swap_partition_path': os.path.join("/dev/gptid", swap_uuid) if swap_uuid else None
    }

    if multipath_info:
        disk.update(multipath_info)

    diskinfo_cache.put(identifier, disk)
    ds_disk = dispatcher.datastore.get_by_id('disks', identifier)

    if ds_disk is None:
        dispatcher.datastore.insert('disks', {
            'id': identifier,
            'path': path,
            'mediasize': disk['mediasize'],
            'serial': disk['serial'],
            'is_multipath': disk['is_multipath'],
            'data_partition_uuid': disk['data_partition_uuid']
        })

        dispatcher.dispatch_event('disks.changed', {
            'operation': 'created',
            'ids': [identifier]
        })
    else:
        if ds_disk['id'] != identifier or disk['data_partition_uuid'] != ds_disk['data_partition_uuid']:
            oldid = ds_disk['id']
            ds_disk.update({
                'id': identifier,
                'serial': disk['serial'],
                'data_partition_uuid': disk['data_partition_uuid'],
                'is_multipath': disk['is_multipath']
            })

            dispatcher.datastore.update('disks', oldid, ds_disk)

            dispatcher.dispatch_event('disks.changed', {
                'operation': 'update',
                'ids': [identifier]
            })

    logger.info('Added <%s> (%s) to disk cache', identifier, disk['description'])


def purge_disk_cache(dispatcher, path):
    geom.scan()
    disk = get_disk_by_path(path)

    if not disk:
        return

    if disk['is_multipath']:
        # Looks like one path was removed
        logger.info('Path %s to disk <%s> (%s) was removed', path, disk['identifier'], disk['description'])
        disk['multipath_members'].remove(path)

        # Was this last path?
        if len(disk['multipath_members']) == 0:
            logger.info('Disk %s <%s> (%s) was removed (last path is gone)', path, disk['identifier'], disk['description'])
            diskinfo_cache.remove(disk['identifier'])
        else:
            diskinfo_cache.put(disk['identifier'], disk)

    else:
        logger.info('Disk %s <%s> (%s) was removed', path, disk['identifier'], disk['description'])
        diskinfo_cache.remove(disk['identifier'])
        dispatcher.datastore.delete('disks', disk['identifier'])


def _depends():
    return ['DevdPlugin']


def _init(dispatcher, plugin):
    def on_device_attached(args):
        path = args['path']
        if re.match(r'^/dev/(da|ada)[0-9]+$', path):
            # Regenerate disk cache
            logger.info("New disk attached: {0}".format(path))
            generate_disk_cache(dispatcher, path)

    def on_device_detached(args):
        path = args['path']
        if re.match(r'^/dev/(da|ada)[0-9]+$', path):
            logger.info("Disk %s detached", path)
            purge_disk_cache(dispatcher, path)


    def on_device_mediachange(args):
        # Regenerate caches
        logger.info('Updating disk cache for device %s', args['path'])
        generate_disk_cache(dispatcher, args['path'])

    plugin.register_schema_definition('disk', {
        'type': 'object',
        'properties': {
            'name': {'type': 'string'},
            'description': {'type': 'string'},
            'serial': {'type': 'string'},
            'smart_enabled': {'type': 'boolean'},
            'mediasize': {'type': 'integer'},
            'smart': {'type': 'boolean'},
            'smart_options': {'type': 'string'},
            'standby_mode': {'type': 'string'},
            'acoustic_level': {'type': 'string'},
            'apm_mode': {'type': 'string'},
            'status': {'$ref': 'disk-status'},
        }
    })

    plugin.register_schema_definition('disk-status', {
        'type': 'object',
        'properties': {
            'mediasize': {'type': 'integer'},
            'sectorsize': {'type': 'integer'},
            'description': {'type': 'string'},
            'identifier': {'type': 'string'},
            'serial': {'type': 'string'},
            'max_rotation': {'type': 'integer'},
            'smart_capable': {'type': 'boolean'},
            'smart_enabled': {'type': 'boolean'},
            'smart_status': {'type': 'string'},
            'model': {'type': 'string'},
            'interface': {'type': 'string'},
            'is_ssd': {'type': 'boolean'},
            'is_multipath': {'type': 'boolean'},
            'id': {'type': 'string'},
            'schema': {'type': ['string', 'null']},
            'controller': {'type': 'object'},
            'partitions': {
                'type': 'array',
                'items': {'$ref': 'disk-partition'}
            },
            'multipath_node': {'type': 'string'},
            'multipath_members': {
                'type': 'aray',
                'items': 'string'
            },
            'data_partition_uuid': {'type': 'string'},
            'data_partition_path': {'type': 'string'},
            'swap_partition_uuid': {'type': 'string'},
            'swap_partition_path': {'type': 'string'},
        }
    })

    plugin.register_schema_definition('disk-partition', {
        'type': 'object',
        'properties': {

        }
    })

    dispatcher.require_collection('disks')
    plugin.register_provider('disks', DiskProvider)
    plugin.register_event_handler('system.device.attached', on_device_attached)
    plugin.register_event_handler('system.device.detached', on_device_detached)
    plugin.register_event_handler('system.device.mediachange', on_device_mediachange)
    plugin.register_task_handler('disk.erase', DiskEraseTask)
    plugin.register_task_handler('disk.format.gpt', DiskGPTFormatTask)
    plugin.register_task_handler('disk.format.boot', DiskBootFormatTask)
    plugin.register_task_handler('disk.install_bootloader', DiskInstallBootloaderTask)
    plugin.register_task_handler('disk.configure', DiskConfigureTask)
    plugin.register_task_handler('disk.delete', DiskDeleteTask)

    plugin.register_event_type('disks.changed')

    # Destroy all existing multipaths
    clean_multipaths()

    for i in dispatcher.rpc.call_sync('system.device.get_devices', 'disk'):
        on_device_attached({'path': i['path']})
