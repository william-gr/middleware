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

import errno
import os
import logging
import tempfile
import shutil
import bsd
import bsd.kld
from lib.system import system, SubprocessException
from lib.freebsd import fstyp
from task import Provider, Task, ProgressTask, TaskException, VerifyException, query
from dispatcher.rpc import (
    RpcException, description, accepts, returns, private, SchemaHelper as h
    )
from utils import first_or_default
from datastore import DuplicateKeyException
from fnutils import include, exclude, normalize
from fnutils.query import wrap
from fnutils.copytree import count_files, copytree


VOLUMES_ROOT = '/mnt'
DEFAULT_ACLS = [
    {'text': 'owner@:rwxpDdaARWcCos:fd:allow'},
    {'text': 'group@:rwxpDdaARWcCos:fd:allow'},
    {'text': 'everyone@:rxaRc:fd:allow'}
]
logger = logging.getLogger('VolumePlugin')


@description("Provides access to volumes information")
class VolumeProvider(Provider):
    @query('volume')
    def query(self, filter=None, params=None):
        def is_upgraded(pool):
            if pool['properties.version.value'] != '-':
                return False

            for feat in pool['features']:
                if feat['state'] == 'DISABLED':
                    return False

            return True

        def extend_dataset(ds):
            ds = wrap(ds)
            return {
                'name': ds['name'],
                'type': ds['type'],
                'mountpoint': ds['mountpoint'],
                'volsize': ds.get('properties.volsize.rawvalue'),
                'properties': include(
                    ds['properties'],
                    'used', 'available', 'compression', 'atime', 'dedup',
                    'quota', 'refquota', 'reservation', 'refreservation',
                    'casesensitivity', 'volsize', 'volblocksize',
                ),
                'share_type': ds.get('properties.org\\.freenas:share_type.value'),
                'permissions_type':  ds.get('properties.org\\.freenas:permissions_type.value'),
            }

        def extend(vol):
            config = wrap(self.get_config(vol['name']))
            if not config:
                vol['status'] = 'UNKNOWN'
            else:
                topology = config['groups']
                for vdev, _ in iterate_vdevs(topology):
                    try:
                        vdev['path'] = self.dispatcher.call_sync(
                            'disks.partition_to_disk',
                            vdev['path']
                        )
                    except RpcException as err:
                        if err.code == errno.ENOENT:
                            pass

                vol.update({
                    'description': None,
                    'mountpoint': None,
                    'datasets': None,
                    'upgraded': None,
                    'topology': topology,
                    'root_vdev': config['root_vdev'],
                    'status': config['status'],
                    'scan': config['scan'],
                    'properties': config['properties']
                })

                if config['status'] != 'UNAVAIL':
                    vol.update({
                        'description': config.get('root_dataset.properties.org\\.freenas:description.value'),
                        'mountpoint': config['root_dataset.properties.mountpoint.value'],
                        'datasets': list(map(extend_dataset, flatten_datasets(config['root_dataset']))),
                        'upgraded': is_upgraded(config),
                    })

            return vol

        return self.datastore.query('volumes', *(filter or []), callback=extend, **(params or {}))

    @description("Finds volumes available for import")
    @accepts()
    @returns(h.array(
        h.object(properties={
            'id': str,
            'name': str,
            'topology': h.ref('zfs-topology'),
            'status': str
        })
    ))
    def find(self):
        result = []
        for pool in self.dispatcher.call_sync('zfs.pool.find'):
            topology = pool['groups']
            for vdev, _ in iterate_vdevs(topology):
                try:
                    vdev['path'] = self.dispatcher.call_sync(
                        'disks.partition_to_disk',
                        vdev['path']
                    )
                except RpcException:
                    pass

            if self.datastore.exists('volumes', ('id', '=', pool['guid'])):
                continue

            result.append({
                'id': str(pool['guid']),
                'name': pool['name'],
                'topology': topology,
                'status': pool['status']
            })

        return result

    @returns(h.array(h.ref('importable-disk')))
    def find_media(self):
        result = []

        for disk in wrap(self.dispatcher.call_sync('disks.query', [('path', 'in', self.get_available_disks())])):
            # Try whole disk first
            typ, label = fstyp(disk['path'])
            if typ:
                result.append({
                    'path': disk['path'],
                    'size': disk['mediasize'],
                    'fstype': typ,
                    'label': label or disk['description']
                })
                continue

            for part in disk['status.partitions']:
                path = part['paths'][0]
                typ, label = fstyp(path)
                if typ:
                    result.append({
                        'path': path,
                        'size': part['mediasize'],
                        'fstype': typ,
                        'label': label or disk['description']
                    })

        return result

    @accepts(str)
    @returns(str)
    def resolve_path(self, volname, path):
        volume = self.query([('name', '=', volname)], {'single': True})
        if not volume:
            raise RpcException(errno.ENOENT, 'Volume {0} not found'.format(volname))

        return os.path.join(volume['mountpoint'], path)

    @accepts(str, str)
    @returns(str)
    def get_dataset_path(self, volname, dsname):
        return os.path.join(VOLUMES_ROOT, dsname)

    @description("Extracts volume name, dataset name and relative path from full path")
    @accepts(str)
    @returns(h.tuple(str, str, str))
    def decode_path(self, path):
        path = os.path.normpath(path)[1:]
        tokens = path.split(os.sep)

        if tokens[0] != VOLUMES_ROOT[1:]:
            raise RpcException(errno.EINVAL, 'Invalid path')

        volname = tokens[1]
        config = self.get_config(volname)
        if config:
            datasets = [d['name'] for d in flatten_datasets(config['root_dataset'])]
        else:
            raise RpcException(errno.ENOENT, "Volume '{0}' does not exist".format(volname))
        n = len(tokens)

        while n > 0:
            fragment = '/'.join(tokens[1:n])
            if fragment in datasets:
                return volname, fragment, '/'.join(tokens[n:])

            n -= 1

        raise RpcException(errno.ENOENT, 'Cannot look up path')

    @description("Returns Disks associated with Volume specified in the call")
    @accepts(str)
    @returns(h.array(str))
    def get_volume_disks(self, name):
        result = []
        for dev in self.dispatcher.call_sync('zfs.pool.get_disks', name):
            try:
                result.append(self.dispatcher.call_sync('disks.partition_to_disk', dev))
            except RpcException:
                pass

        return result

    @description("Returns dataset tree for given pool")
    @accepts(str)
    @returns(h.ref('zfs-dataset'))
    def get_dataset_tree(self, name):
        pool = self.dispatcher.call_sync(
            'zfs.pool.query',
            [('name', '=', name)],
            {"single": True})

        if not pool:
            return None

        return pool['root_dataset']

    @description("Returns the list of disks currently not used by any Volume")
    @accepts()
    @returns(h.array(str))
    def get_available_disks(self):
        disks = set([d['path'] for d in self.dispatcher.call_sync('disks.query')])
        for pool in self.dispatcher.call_sync('zfs.pool.query'):
            for dev in self.dispatcher.call_sync('zfs.pool.get_disks', pool['name']):
                try:
                    disk = self.dispatcher.call_sync('disks.partition_to_disk', dev)
                except RpcException:
                    continue

                disks.remove(disk)

        return list(disks)

    @description("Returns allocation of given disk")
    @accepts(h.array(str))
    @returns(h.ref('disks-allocation'))
    def get_disks_allocation(self, disks):
        ret = {}
        boot_pool_name = self.configstore.get('system.boot_pool_name')
        boot_devs = self.dispatcher.call_sync('zfs.pool.get_disks', boot_pool_name)

        for dev in boot_devs:
            boot_disk = self.dispatcher.call_sync('disks.partition_to_disk', dev)
            if boot_disk in disks:
                ret[boot_disk] = {'type': 'BOOT'}

        for vol in self.dispatcher.call_sync('volumes.query'):
            for dev in self.dispatcher.call_sync('volumes.get_volume_disks', vol['name']):
                if dev in disks:
                    ret[dev] = {
                        'type': 'VOLUME',
                        'name': vol['name']
                    }

        return ret

    @description("Returns Information about all the possible attributes of" +
                 " the Volume (name, guid, zfs properties, datasets, etc...)")
    @accepts(str)
    @returns(h.ref('zfs-pool'))
    def get_config(self, volume):
        return self.dispatcher.call_sync(
            'zfs.pool.query',
            [('name', '=', volume)],
            {'single': True}
        )

    @accepts(str, str)
    @returns(h.ref('zfs-vdev'))
    def vdev_by_guid(self, volume, guid):
        vdev = self.dispatcher.call_sync('zfs.pool.vdev_by_guid', volume, guid)
        vdev['path'] = self.dispatcher.call_sync(
            'disks.partition_to_disk',
            vdev['path']
        )

        return vdev

    @description("Describes the various capacibilities of a Volumes given" +
                 "What type of Volume it is (example call it with 'zfs'")
    @accepts(str)
    @returns(h.object())
    def get_capabilities(self, type):
        if type == 'zfs':
            return self.dispatcher.call_sync('zfs.pool.get_capabilities')

        raise RpcException(errno.EINVAL, 'Invalid volume type')

    @accepts()
    @returns(str)
    @private
    def get_volumes_root(self):
        return VOLUMES_ROOT


class SnapshotProvider(Provider):
    def query(self, filter=None, params=None):
        boot_pool = self.configstore.get('system.boot_pool_name')

        def extend(snapshot):
            dataset, _, name = snapshot['name'].partition('@')
            pool = dataset.partition('/')[0]

            if pool == boot_pool:
                return None

            return {
                'id': snapshot['name'],
                'pool': pool,
                'dataset': dataset,
                'name': name,
                'properties': include(
                    snapshot['properties'],
                    'used', 'referenced', 'compressratio', 'clones'
                ),
                'holds': snapshot['holds']
            }

        return wrap(self.dispatcher.call_sync('zfs.snapshot.query')).query(
            *(filter or []),
            callback=extend,
            **(params or {})
        )


@description("Creates new volume")
@accepts(h.ref('volume'))
class VolumeCreateTask(ProgressTask):
    def verify(self, volume):
        if self.datastore.exists('volumes', ('name', '=', volume['name'])):
            raise VerifyException(errno.EEXIST, 'Volume with same name already exists')

        return ['disk:{0}'.format(i) for i, _ in get_disks(volume['topology'])]

    def run(self, volume):
        name = volume['name']
        type = volume.get('type', 'zfs')
        params = volume.get('params') or {}
        mountpoint = params.pop(
            'mountpoint',
            os.path.join(VOLUMES_ROOT, volume['name'])
        )

        if type != 'zfs':
            raise TaskException(errno.EINVAL, 'Invalid volume type')

        self.set_progress(10)

        if self.configstore.get("middleware.parallel_disk_format"):
            subtasks = []
            for dname, dgroup in get_disks(volume['topology']):
                subtasks.append(self.run_subtask('disks.format.gpt', dname, 'freebsd-zfs', {
                    'blocksize': params.get('blocksize', 4096),
                    'swapsize': params.get('swapsize', 2048) if dgroup == 'data' else 0
                }))

            self.join_subtasks(*subtasks)
        else:
            for dname, dgroup in get_disks(volume['topology']):
                self.join_subtasks(self.run_subtask('disks.format.gpt', dname, 'freebsd-zfs', {
                    'blocksize': params.get('blocksize', 4096),
                    'swapsize': params.get('swapsize', 2048) if dgroup == 'data' else 0
                }))

        self.set_progress(40)

        with self.dispatcher.get_lock('volumes'):
            self.join_subtasks(self.run_subtask(
                'zfs.pool.create',
                name,
                convert_topology_to_gptids(
                    self.dispatcher,
                    volume['topology']
                ),
                {'mountpoint': mountpoint}
            ))

            self.join_subtasks(self.run_subtask(
                'zfs.configure',
                name, name,
                {
                    'org.freenas:share_type': {'value': 'UNIX'},
                    'org.freenas:permissions_type': {'value': 'PERM'}
                }
            ))

            self.set_progress(60)
            self.join_subtasks(self.run_subtask('zfs.mount', name))
            self.set_progress(80)

            pool = self.dispatcher.call_sync('zfs.pool.query', [('name', '=', name)]).pop()
            id = self.datastore.insert('volumes', {
                'id': str(pool['guid']),
                'name': name,
                'type': type,
                'mountpoint': mountpoint,
                'attributes': volume.get('attributes', {})
            })

        self.set_progress(90)
        self.dispatcher.dispatch_event('volumes.changed', {
            'operation': 'create',
            'ids': [id]
        })


@description("Creates new volume and automatically guesses disks layout")
@accepts(str, str, h.array(str), h.object())
class VolumeAutoCreateTask(Task):
    def verify(self, name, type, disks, params=None):
        if self.datastore.exists('volumes', ('name', '=', name)):
            raise VerifyException(errno.EEXIST,
                                  'Volume with same name already exists')

        return ['disk:{0}'.format(os.path.join('/dev', i)) for i in disks]

    def run(self, name, type, disks, params=None):
        vdevs = []
        if len(disks) % 3 == 0:
            for i in range(0, len(disks), 3):
                vdevs.append({
                    'type': 'raidz1',
                    'children': [{'type': 'disk', 'path': os.path.join('/dev', i)} for i in disks[i:i+3]]
                })
        elif len(disks) % 2 == 0:
            for i in range(0, len(disks), 2):
                vdevs.append({
                    'type': 'mirror',
                    'children': [{'type': 'disk', 'path': os.path.join('/dev', i)} for i in disks[i:i+2]]
                })
        else:
            vdevs = [{'type': 'disk', 'path': os.path.join('/dev', i)} for i in disks]

        self.join_subtasks(self.run_subtask('volume.create', {
            'name': name,
            'type': type,
            'topology': {'data': vdevs},
            'params': params
        }))


@description("Destroys active volume")
@accepts(str)
class VolumeDestroyTask(Task):
    def verify(self, name):
        if not self.datastore.exists('volumes', ('name', '=', name)):
            raise VerifyException(errno.ENOENT, 'Volume {0} not found'.format(id))

        try:
            disks = self.dispatcher.call_sync('volumes.get_volume_disks', name)
            return ['disk:{0}'.format(d) for d in disks]
        except RpcException:
            return []

    def run(self, name):
        vol = self.datastore.get_one('volumes', ('name', '=', name))
        config = self.dispatcher.call_sync('volumes.get_config', name)

        self.dispatcher.run_hook('volumes.pre_destroy', {'name': name})

        if config:
            self.join_subtasks(self.run_subtask('zfs.umount', name))
            self.join_subtasks(self.run_subtask('zfs.pool.destroy', name))

        self.datastore.delete('volumes', vol['id'])

        self.dispatcher.dispatch_event('volumes.changed', {
            'operation': 'delete',
            'ids': [vol['id']]
        })


@description("Updates configuration of existing volume")
@accepts(str, h.ref('volume'))
class VolumeUpdateTask(Task):
    def verify(self, name, updated_params):
        if not self.datastore.exists('volumes', ('name', '=', name)):
            raise VerifyException(errno.ENOENT, 'Volume {0} not found'.format(name))

        topology = updated_params.get('topology')
        if not topology:
            disks = self.dispatcher.call_sync('volumes.get_volume_disks', name)
            return ['disk:{0}'.format(d) for d in disks]

        return ['disk:{0}'.format(i) for i, _ in get_disks(topology)]

    def run(self, name, updated_params):
        volume = self.datastore.get_one('volumes', ('name', '=', name))
        if not volume:
            raise TaskException(errno.ENOENT, 'Volume {0} not found'.format(name))

        if 'name' in updated_params:
            # Renaming pool. Need to export and import again using different name
            new_name = updated_params['name']
            self.join_subtasks(self.run_subtask('zfs.pool.export', name))
            self.join_subtasks(self.run_subtask('zfs.pool.import', volume['id'], new_name))

            # Rename mountpoint
            self.join_subtasks(self.run_subtask('zfs.configure', new_name, new_name, {
                'mountpoint': {'value': '{0}/{1}'.format(VOLUMES_ROOT, new_name)}
            }))

            volume['name'] = new_name
            self.datastore.update('volumes', volume['id'], volume)

        if 'topology' in updated_params:
            new_vdevs = {}
            updated_vdevs = {}
            params = {}
            subtasks = []

            for group, vdevs in list(updated_params['topology'].items()):
                for vdev in vdevs:
                    if 'guid' not in vdev:
                        new_vdevs.setdefault(group, []).append(vdev)
                        continue

                # look for vdev in existing configuration using guid
                pass

            for vdev, group in iterate_vdevs(new_vdevs):
                if vdev['type'] == 'disk':
                    subtasks.append(self.run_subtask('disks.format.gpt', vdev['path'], 'freebsd-zfs', {
                        'blocksize': params.get('blocksize', 4096),
                        'swapsize': params.get('swapsize', 2048) if group == 'data' else 0
                    }))

            self.join_subtasks(*subtasks)

            new_vdevs = convert_topology_to_gptids(self.dispatcher, new_vdevs)
            self.join_subtasks(self.run_subtask(
                'zfs.pool.extend',
                name,
                new_vdevs,
                updated_vdevs)
            )


@description("Imports previously exported volume")
@accepts(str, str, h.object())
class VolumeImportTask(Task):
    def verify(self, id, new_name, params=None):
        if self.datastore.exists('volumes', ('id', '=', id)):
            raise VerifyException(
                errno.ENOENT,
                'Volume with id {0} already exists'.format(id)
            )

        if self.datastore.exists('volumes', ('name', '=', new_name)):
            raise VerifyException(
                errno.ENOENT,
                'Volume with name {0} already exists'.format(new_name)
            )

        return self.verify_subtask('zfs.pool.import', id)

    def run(self, id, new_name, params=None):
        with self.dispatcher.get_lock('volumes'):
            mountpoint = os.path.join(VOLUMES_ROOT, new_name)
            self.join_subtasks(self.run_subtask('zfs.pool.import', id, new_name, params))
            self.join_subtasks(self.run_subtask(
                'zfs.configure',
                new_name,
                new_name,
                {'mountpoint': {'value': mountpoint}}
            ))

            self.join_subtasks(self.run_subtask('zfs.mount', new_name))

            new_id = self.datastore.insert('volumes', {
                'id': id,
                'name': new_name,
                'type': 'zfs',
                'mountpoint': mountpoint
            })

            self.dispatcher.dispatch_event('volumes.changed', {
                'operation': 'create',
                'ids': [new_id]
            })


@description("Imports non-ZFS disk contents info existing volume")
@accepts(str, str, str)
class VolumeDiskImportTask(ProgressTask):
    def verify(self, src, dest_path, fstype=None):
        disk = self.dispatcher.call_sync('disks.partition_to_disk', src)
        if not disk:
            raise VerifyException(errno.ENOENT, "Partition {0} not found".format(src))

        return ['disk:{0}'.format(disk)]

    def run(self, src, dest_path, fstype=None):
        if not fstype:
            try:
                fstype, _ = system('/usr/sbin/fstyp', src)
            except SubprocessException:
                raise TaskException(errno.EINVAL, 'Cannot figure out filesystem type')

        if fstype == 'ntfs':
            try:
                bsd.kld.kldload('/boot/kernel/fuse.ko')
            except OSError as err:
                raise TaskException(err.errno, err.message)

        src_mount = tempfile.mkdtemp()

        try:
            bsd.nmount(source=src, fspath=src_mount, fstype=fstype)
        except OSError as err:
            raise TaskException(err.errno, "Cannot mount disk: {0}".format(str(err)))

        def callback(srcfile, dstfile):
            self.set_progress(self.copied / self.nfiles * 100, "Copying {0}".format(os.path.basename(srcfile)))

        self.set_progress(0, "Counting files...")
        self.nfiles = count_files(src_mount)
        self.copied = 0
        failures = []

        try:
            copytree(src_mount, dest_path, progress_callback=callback)
        except shutil.Error as err:
            failures = err.message

        try:
            bsd.unmount(src_mount, bsd.MountFlags.FORCE)
        except OSError:
            pass

        bsd.kld.kldunload('fuse')
        os.rmdir(src_mount)
        return failures


@description("Exports active volume")
@accepts(str)
class VolumeDetachTask(Task):
    def verify(self, name):
        if not self.datastore.exists('volumes', ('name', '=', name)):
            raise VerifyException(errno.ENOENT, 'Volume {0} not found'.format(name))

        return ['disk:{0}'.format(d) for d in self.dispatcher.call_sync('volumes.get_volume_disks', name)]

    def run(self, name):
        vol = self.datastore.get_one('volumes', ('name', '=', name))
        self.join_subtasks(self.run_subtask('zfs.umount', name))
        self.join_subtasks(self.run_subtask('zfs.pool.export', name))
        self.datastore.delete('volumes', vol['id'])

        self.dispatcher.dispatch_event('volumes.changed', {
            'operation': 'delete',
            'ids': [vol['id']]
        })


@description("Upgrades volume to newest ZFS version")
@accepts(str)
class VolumeUpgradeTask(Task):
    def verify(self, name):
        if not self.datastore.exists('volumes', ('name', '=', name)):
            raise VerifyException(errno.ENOENT, 'Volume {0} not found'.format(name))

        return ['disk:{0}'.format(d) for d in self.dispatcher.call_sync('volumes.get_volume_disks', name)]

    def run(self, name):
        vol = self.datastore.get_one('volumes', ('name', '=', name))
        self.join_subtasks(self.run_subtask('zfs.pool.upgrade', name))
        self.dispatcher.dispatch_event('volumes.changed', {
            'operation': 'update',
            'ids': [vol['id']]
        })


@description("Creates a dataset in an existing volume")
@accepts(str, str, h.ref('dataset-type'), h.object())
class DatasetCreateTask(Task):
    def verify(self, pool_name, path, type, params=None):
        if not self.datastore.exists('volumes', ('name', '=', pool_name)):
            raise VerifyException(errno.ENOENT, 'Volume {0} not found'.format(pool_name))

        return ['zpool:{0}'.format(pool_name)]

    def run(self, pool_name, path, type, params=None):
        if params:
            normalize(params, {
                'properties': {}
            })

        if type == 'VOLUME':
            params['properties']['volsize'] = {'value': params['volsize']}

        self.join_subtasks(self.run_subtask(
            'zfs.create_dataset',
            pool_name,
            path,
            type,
            {k: v['value'] for k, v in list(params['properties'].items())} if params else {}
        ))

        if params:
            props = {}
            if 'share_type' in params:
                props['org.freenas:share_type'] = {'value': params['share_type']}

            if 'permissions_type' in params:
                props['org.freenas:permissions_type'] = {'value': params['permissions_type']}

            self.join_subtasks(self.run_subtask('zfs.configure', pool_name, path, props))

        self.join_subtasks(self.run_subtask('zfs.mount', path))


@description("Deletes an existing Dataset from a Volume")
@accepts(str, str)
class DatasetDeleteTask(Task):
    def verify(self, pool_name, path):
        if not self.datastore.exists('volumes', ('name', '=', pool_name)):
            raise VerifyException(errno.ENOENT, 'Volume {0} not found'.format(pool_name))

        return ['zpool:{0}'.format(pool_name)]

    def run(self, pool_name, path):
        self.join_subtasks(self.run_subtask('zfs.umount', path))
        self.join_subtasks(self.run_subtask('zfs.destroy', path))


@description("Configures/Updates an existing Dataset's properties")
@accepts(str, str, h.object())
class DatasetConfigureTask(Task):
    def verify(self, pool_name, path, updated_params):
        if not self.datastore.exists('volumes', ('name', '=', pool_name)):
            raise VerifyException(errno.ENOENT, 'Volume {0} not found'.format(pool_name))

        return ['zpool:{0}'.format(pool_name)]

    def switch_to_acl(self, pool_name, path):
        fs_path = self.dispatcher.call_sync('volumes.get_dataset_path', pool_name, path)
        self.join_subtasks(
            self.run_subtask('zfs.configure', pool_name, path, {
                'aclmode': {'value': 'restricted'},
                'org.freenas:permissions_type': {'value': 'ACL'}
            }),
            self.run_subtask('file.set_permissions', fs_path, {
                'acl': DEFAULT_ACLS
            }, True)
        )

    def switch_to_chmod(self, pool_name, path):
        self.join_subtasks(self.run_subtask('zfs.configure', pool_name, path, {
            'aclmode': {'value': 'passthrough'},
            'org.freenas:permissions_type': {'value': 'PERMS'}
        }))

    def run(self, pool_name, path, updated_params):
        ds = wrap(self.dispatcher.call_sync('zfs.dataset.query', [('name', '=', path)], {'single': True}))

        if 'name' in updated_params:
            self.join_subtasks(self.run_subtask('zfs.rename', ds['name'], updated_params['name']))
            ds['name'] = updated_params['name']

        if 'properties' in updated_params:
            props = exclude(updated_params['properties'], 'used', 'available', 'dedup', 'casesensitivity')
            self.join_subtasks(self.run_subtask('zfs.configure', pool_name, ds['name'], props))

        if 'share_type' in updated_params:
            self.join_subtasks(self.run_subtask('zfs.configure', pool_name, ds['name'], {
                'org.freenas:share_type': {'value': updated_params['share_type']}
            }))

        if 'permissions_type' in updated_params:
            share_typ = ds['properties.org\\.freenas:share_type.value']
            oldtyp = ds['properties.org\\.freenas:permissions_type.value']
            typ = updated_params['permissions_type']

            if share_typ == 'WINDOWS' and typ == 'PERMS':
                raise TaskException(errno.EINVAL, 'Cannot use unix permissions with Windows share type')

            if share_typ == 'MAC' and typ == 'ACL':
                raise TaskException(errno.EINVAL, 'Cannot use acls with Mac share type')

            if oldtyp != 'ACL' and typ == 'ACL':
                self.switch_to_acl(pool_name, ds['name'])

            if oldtyp != 'PERMS' and typ == 'PERMS':
                self.switch_to_chmod(pool_name, ds['name'])


class SnapshotCreateTask(Task):
    def verify(self, pool_name, dataset_name, snapshot_name, recursive=False):
        return ['zfs:{0}'.format(dataset_name)]

    def run(self, pool_name, dataset_name, snapshot_name, recursive=False):
        self.join_subtasks(self.run_subtask(
            'zfs.create_snapshot',
            pool_name,
            dataset_name,
            snapshot_name,
            recursive
        ))


class SnapshotDeleteTask(Task):
    def verify(self, pool_name, dataset_name, snapshot_name):
        return ['zfs:{0}'.format(dataset_name)]

    def run(self, pool_name, dataset_name, snapshot_name):
        self.join_subtasks(self.run_subtask(
            'zfs.delete_snapshot',
            pool_name,
            dataset_name,
            snapshot_name,
        ))


def flatten_datasets(root):
    for ds in root['children']:
        for c in flatten_datasets(ds):
            yield c

    del root['children']
    yield root


def iterate_vdevs(topology):
    for name, grp in list(topology.items()):
        for vdev in grp:
            if vdev['type'] == 'disk':
                yield vdev, name
                continue

            if 'children' in vdev:
                for child in vdev['children']:
                    yield child, name


def get_disks(topology):
    for vdev, gname in iterate_vdevs(topology):
        yield vdev['path'], gname


def get_disk_gptid(dispatcher, disk):
    config = dispatcher.call_sync('disks.get_disk_config', disk)
    return config.get('data_partition_path', disk)


def convert_topology_to_gptids(dispatcher, topology):
    topology = topology.copy()
    for vdev, _ in iterate_vdevs(topology):
        vdev['path'] = get_disk_gptid(dispatcher, vdev['path'])

    return topology


def _depends():
    return ['DevdPlugin', 'ZfsPlugin']


def _init(dispatcher, plugin):
    boot_pool = dispatcher.call_sync('zfs.pool.get_boot_pool')

    def on_pool_change(args):
        ids = [i for i in args['ids'] if i != boot_pool['guid']]
        if args['operation'] == 'delete':
            for i in ids:
                logger.info('Volume {0} is going away'.format(i))
                dispatcher.datastore.delete('volumes', i)

        if args['operation'] in ('create', 'update'):
            for i in ids:
                if args['operation'] == 'update' and dispatcher.datastore.exists('volumes', ('id', '=', i)):
                    dispatcher.dispatch_event('volumes.changed', {
                        'operation': 'update',
                        'ids': [i]
                    })
                    continue

                pool = wrap(dispatcher.call_sync(
                    'zfs.pool.query',
                    [('guid', '=', i)],
                    {'single': True}
                ))

                if not pool:
                    continue

                logger.info('New volume {0} <{1}>'.format(pool['name'], i))
                with dispatcher.get_lock('volumes'):
                    try:
                        dispatcher.datastore.insert('volumes', {
                            'id': i,
                            'name': pool['name'],
                            'type': 'zfs',
                            'attributes': {}
                        })
                    except DuplicateKeyException:
                        # already inserted by task
                        continue

                    # Set correct mountpoint
                    dispatcher.call_task_sync('zfs.configure', pool['name'], pool['name'], {
                        'mountpoint': {'value': os.path.join(VOLUMES_ROOT, pool['name'])}
                    })

                    if pool['properties.altroot.source'] != 'DEFAULT':
                        # Ouch. That pool is created or imported with altroot.
                        # We need to export and reimport it to remove altroot property
                        dispatcher.call_task_sync('zfs.pool.export', pool['name'])
                        dispatcher.call_task_sync('zfs.pool.import', pool['guid'], pool['name'])

                    dispatcher.dispatch_event('volumes.changed', {
                        'operation': 'create',
                        'ids': [i]
                    })

    def on_dataset_change(args):
        dispatcher.dispatch_event('volumes.changed', {
            'operation': 'update',
            'ids': [args['guid']]
        })

    plugin.register_schema_definition('volume', {
        'type': 'object',
        'title': 'volume',
        'additionalProperties': False,
        'properties': {
            'id': {'type': 'string'},
            'name': {'type': 'string'},
            'type': {
                'type': 'string',
                'enum': ['zfs']
            },
            'topology': {'$ref': 'zfs-topology'},
            'params': {'type': 'object'},
            'attributes': {'type': 'object'}
        }
    })

    plugin.register_schema_definition('dataset', {
        'type': 'object',
        'properties': {
            'name': {'type': 'string'},
            'mountpoint': {'type': 'string'},
            'type': {
                'type': 'string',
                'enum': ['FILESYSTEM', 'VOLUME']
            },
            'volsize': {'type': ['integer', 'null']},
            'properties': {'type': 'object'},
            'share_type': {
                'type': 'string',
                'enum': ['UNIX', 'MAC', 'WINDOWS']
            },
            'permissions_type': {
                'type': 'string',
                'enum': ['PERM', 'ACL']
            }
        }
    })

    plugin.register_schema_definition('disks-allocation', {
        'type': 'object',
        'additionalProperties': {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'type': {
                    'type': 'string',
                    'enum': ['BOOT', 'VOLUME', 'ISCSI'],
                },
                'name': {'type': 'string'}
            }
        }
    })

    plugin.register_schema_definition('importable-disk', {
        'type': 'object',
        'properties': {
            'path': {'type': 'string'},
            'fstype': {'type': 'string'},
            'size': {'type': 'integer'},
            'label': {'type': 'string'}
        }
    })

    plugin.register_provider('volumes', VolumeProvider)
    plugin.register_provider('volumes.snapshots', SnapshotProvider)
    plugin.register_task_handler('volume.create', VolumeCreateTask)
    plugin.register_task_handler('volume.create_auto', VolumeAutoCreateTask)
    plugin.register_task_handler('volume.destroy', VolumeDestroyTask)
    plugin.register_task_handler('volume.import', VolumeImportTask)
    plugin.register_task_handler('volume.import_disk', VolumeDiskImportTask)
    plugin.register_task_handler('volume.detach', VolumeDetachTask)
    plugin.register_task_handler('volume.update', VolumeUpdateTask)
    plugin.register_task_handler('volume.upgrade', VolumeUpgradeTask)
    plugin.register_task_handler('volume.dataset.create', DatasetCreateTask)
    plugin.register_task_handler('volume.dataset.delete', DatasetDeleteTask)
    plugin.register_task_handler('volume.dataset.update', DatasetConfigureTask)
    plugin.register_task_handler('volume.snapshot.create', SnapshotCreateTask)
    plugin.register_task_handler('volume.snapshot.delete', SnapshotDeleteTask)

    plugin.register_hook('volumes.pre_destroy')
    plugin.register_hook('volumes.pre_detach')
    plugin.register_hook('volumes.pre_create')
    plugin.register_hook('volumes.pre_attach')

    plugin.register_event_handler('zfs.pool.changed', on_pool_change)
    plugin.register_event_handler('fs.zfs.dataset.created', on_dataset_change)
    plugin.register_event_handler('fs.zfs.dataset.deleted', on_dataset_change)
    plugin.register_event_handler('fs.zfs.dataset.renamed', on_dataset_change)
    plugin.register_event_type('volumes.changed')

    for vol in dispatcher.datastore.query('volumes'):
        try:
            dispatcher.call_task_sync('zfs.mount', vol['name'], True)

            # XXX: check mountpoint property and correct if needed


        except TaskException as err:
            if err.code != errno.EBUSY:
                logger.warning('Cannot mount volume {0}: {1}'.format(vol['name'], str(err)))

    # Scan for sentinel files indicating share type and convert them
    # to zfs user properties
    for vol in dispatcher.call_sync('volumes.query'):
        if vol['status'] != 'ONLINE':
            continue

        for ds in vol['datasets']:
            share_type = None
            ds_name = ds['name'].split('/')[1:]
            path = os.path.join(vol['mountpoint'], *ds_name)

            if os.path.exists(os.path.join(path, '.windows')):
                os.unlink(os.path.join(path, '.windows'))
                share_type = 'WINDOWS'

            if os.path.exists(os.path.join(path, '.apple')):
                os.unlink(os.path.join(path, '.apple'))
                share_type = 'MAC'

            if share_type:
                dispatcher.call_task_sync('zfs.configure', vol['name'], ds['name'], {
                    'org.freenas:share_type': {'value': share_type}
                })
