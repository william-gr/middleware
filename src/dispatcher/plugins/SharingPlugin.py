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
#####################################################################

import os
import errno
from dispatcher.rpc import description, accepts, returns, private
from dispatcher.rpc import SchemaHelper as h
from task import Task, TaskException, VerifyException, Provider, RpcException, query
from fnutils import normalize


class SharesProvider(Provider):
    @query('share')
    def query(self, filter=None, params=None):
        def extend(share):
            share['dataset_path'] = os.path.join(share['target'], share['type'], share['name'])
            share['filesystem_path'] = self.translate_path(
                share['type'],
                share['target'],
                share['name']
            )

            return share

        return self.datastore.query('shares', *(filter or []), callback=extend, **(params or {}))

    @private
    def translate_path(self, type, target, name):
        root = self.dispatcher.call_sync('volumes.get_volumes_root')
        return os.path.join(root, target, type, name)

    @private
    def translate_dataset(self, type, target, name):
        return self.dispatcher.call_sync(
            'zfs.dataset.query',
            [('name', '=', os.path.join(target, type, name))],
            {'single': True}
        )

    @description("Returns list of supported sharing providers")
    @returns(h.array(str))
    def supported_types(self):
        result = {}
        for p in list(self.dispatcher.plugins.values()):
            if p.metadata and p.metadata.get('type') == 'sharing':
                result[p.metadata['method']] = {
                    'subtype': p.metadata['subtype'],
                    'perm_type': p.metadata.get('perm_type')
                }

        return result

    @description("Returns list of clients connected to particular share")
    @accepts(str)
    @returns(h.array(h.ref('share-client')))
    def get_connected_clients(self, share_name):
        share = self.datastore.get_by_id('shares', share_name)
        if not share:
            raise RpcException(errno.ENOENT, 'Share not found')

        return self.dispatcher.call_sync('shares.{0}.get_connected_clients'.format(share['type']), share_name)

    @description("Get shares dependent on provided volume")
    @accepts(str)
    @returns(h.array('share'))
    def get_dependencies(self, volume):
        return self.query([
            ('target', '=', volume)
        ])


@description("Creates new share")
@accepts(h.all_of(
    h.ref('share'),
    h.required('name', 'type', 'target', 'properties'),
    h.forbidden('id')
))
class CreateShareTask(Task):
    def verify(self, share, skip_dataset=False):
        if not self.dispatcher.call_sync('shares.supported_types').get(share['type']):
            raise VerifyException(errno.ENXIO, 'Unknown sharing type {0}'.format(share['type']))

        if not self.dispatcher.call_sync('volumes.query', [('name', '=', share['target'])], {'single': True}):
            raise VerifyException(errno.ENXIO, 'Volume {0} doesn\'t exist'.format(share['target']))

        if self.datastore.exists(
            'shares',
            ('type', '=', share['type']),
            ('name', '=', share['name'])
        ):
            raise VerifyException(errno.EEXIST, 'Share {0} of type {1} already exists'.format(
                share['name'],
                share['type']
            ))

        return ['system']

    def run(self, share, skip_dataset=False):
        with self.dispatcher.get_lock('sharing'):
            pool = share['target']
            root_ds = os.path.join(pool, share['type'])
            ds_name = os.path.join(root_ds, share['name'])
            share_type = self.dispatcher.call_sync('shares.supported_types').get(share['type'])

            normalize(share, {
                'enabled': True,
                'compression': 'lz4',
                'description': ''
            })

            if not share_type:
                raise TaskException('Unsupported sharing type {0}'.format(share['type']))

            if not skip_dataset:
                if not self.dispatcher.call_sync('zfs.dataset.query', [('name', '=', root_ds)], {'single': True}):
                    # Create root dataset for given sharing type
                    self.join_subtasks(self.run_subtask('volume.dataset.create', pool, root_ds, 'FILESYSTEM'))

                if share_type['subtype'] == 'file':
                    self.join_subtasks(self.run_subtask('volume.dataset.create', pool, ds_name, 'FILESYSTEM', {
                        'permissions_type': share_type['perm_type'],
                        'properties': {
                            'compression': {'value': share['compression']}
                        }
                    }))

                if share_type['subtype'] == 'block':
                    self.join_subtasks(self.run_subtask('volume.dataset.create', pool, ds_name, 'VOLUME', {
                        'volsize': share['properties']['size'],
                        'properties': {
                            'compression': {'value': share['compression']}
                        }
                    }))

            ids = self.join_subtasks(self.run_subtask('share.{0}.create'.format(share['type']), share))
            self.dispatcher.dispatch_event('shares.changed', {
                'operation': 'create',
                'ids': ids
            })

            return ids[0]


@description("Updates existing share")
@accepts(
    str, h.all_of(
        h.ref('share'),
        h.forbidden('id')
    )
)
class UpdateShareTask(Task):
    def verify(self, id, updated_fields):
        share = self.datastore.get_by_id('shares', id)
        if not share:
            raise VerifyException(errno.ENOENT, 'Share not found')

        share_types = self.dispatcher.call_sync('shares.supported_types')
        oldtype = share_types.get(share['type'])
        newtype = share_types.get(updated_fields.get('type', share['type']))
        share.update(updated_fields)

        if not newtype:
            raise VerifyException(errno.ENXIO, 'Unknown sharing type {0}'.format(share['type']))

        if oldtype['subtype'] != newtype['subtype']:
            raise VerifyException(errno.EINVAL, 'Cannot convert from {0} sharing to {1} sharing'.format(
                oldtype['subtype'],
                newtype['subtype']
            ))

        if not self.dispatcher.call_sync('volumes.query', [('name', '=', share['target'])], {'single': True}):
            raise VerifyException(errno.ENXIO, 'Volume {0} doesn\'t exist'.format(share['target']))

        return ['system']

    def run(self, id, updated_fields):
        with self.dispatcher.get_lock('sharing'):
            share = self.datastore.get_by_id('shares', id)
            pool = share['target']

            if 'name' in updated_fields:
                old_ds_name = os.path.join(pool, share['type'], share['name'])
                new_ds_name = os.path.join(pool, share['type'], updated_fields['name'])
                self.join_subtasks(self.run_subtask('zfs.rename', old_ds_name, new_ds_name))

            old_type = share['type']
            old_ds_name = os.path.join(pool, share['type'], share['name'])
            share.update(updated_fields)

            if 'compression' in updated_fields:
                self.run_subtask('volume.dataset.update', pool, old_ds_name, {
                    'properties': {
                        'compression': {'value': share['compression']}
                    }
                })

            if 'type' in updated_fields:
                # Rename dataset and convert share type
                new_root_ds = root_ds = os.path.join(pool, share['type'])
                new_ds_name = os.path.join(new_root_ds, share['name'])
                new_share_type = self.dispatcher.call_sync('shares.supported_types').get(updated_fields['type'])

                # Ensure that parent dataset for new type exists
                if not self.dispatcher.call_sync('zfs.dataset.query', [('name', '=', root_ds)], {'single': True}):
                    # Create root dataset for given sharing type
                    self.join_subtasks(self.run_subtask('volume.dataset.create', pool, root_ds, 'FILESYSTEM'))

                self.join_subtasks(
                    self.run_subtask('volume.dataset.update', pool, old_ds_name, {
                        'name': new_ds_name,
                        'permissions_type': new_share_type['perm_type']
                    })
                )

                self.join_subtasks(self.run_subtask('share.{0}.delete'.format(old_type), id))
                self.join_subtasks(self.run_subtask('share.{0}.create'.format(share['type']), share))
            else:
                self.join_subtasks(self.run_subtask('share.{0}.update'.format(share['type']), id, updated_fields))

            self.dispatcher.dispatch_event('shares.changed', {
                'operation': 'update',
                'ids': [share['id']]
            })


@description("Deletes share")
@accepts(str)
class DeleteShareTask(Task):
    def verify(self, id, skip_dataset=False):
        share = self.datastore.get_by_id('shares', id)
        if not share:
            raise VerifyException(errno.ENOENT, 'Share not found')

        return ['system']

    def run(self, id, skip_dataset=False):
        share = self.datastore.get_by_id('shares', id)
        ds_name = os.path.join(share['target'], share['type'], share['name'])

        self.join_subtasks(self.run_subtask('share.{0}.delete'.format(share['type']), id))

        if not skip_dataset:
            self.join_subtasks(self.run_subtask('volume.dataset.delete', share['target'], ds_name))

        self.dispatcher.dispatch_event('shares.changed', {
            'operation': 'delete',
            'ids': [id]
        })


@description("Deletes all shares dependent on specified volume/dataset")
@accepts(str)
class DeleteDependentShares(Task):
    def verify(self, volume):
        if not self.dispatcher.call_sync('volumes.query', [('name', '=', volume)], {'single': True}):
            raise VerifyException(errno.ENXIO, 'Volume {0} doesn\'t exist'.format(volume))

        return ['system']

    def run(self, volume):
        subtasks = []
        ids = []
        for i in self.dispatcher.call_sync('shares.get_dependencies', volume):
            subtasks.append(self.run_subtask('share.delete', i['id'], True))
            ids.append(i['id'])

        self.join_subtasks(*subtasks)
        self.dispatcher.dispatch_event('shares.changed', {
            'operation': 'delete',
            'ids': ids
        })


def _depends():
    return ['VolumePlugin']


def _init(dispatcher, plugin):
    def on_dataset_create(args):
        with dispatcher.get_lock('sharing'):
            tokens = args['ds'].split('/', 3)
            if len(tokens) < 3:
                # We don't care about root dataset being created
                # neither about direct children of root datasets
                return

            types = list(dispatcher.call_sync('shares.supported_types').keys())
            pool, share_type, rest = tokens

            if share_type not in types:
                # Unknown type
                return

            if dispatcher.datastore.exists('shares',
                ('name', '=', rest),
                ('type', '=', share_type)
            ):
                return

            dispatcher.submit_task('share.create', {
                'name': rest,
                'type': share_type,
                'target': pool,
                'properties': {}
            }, True)

    def on_dataset_delete(args):
        with dispatcher.get_lock('sharing'):
            tokens = args['ds'].split('/', 3)
            if len(tokens) < 3:
                # We don't care about root dataset being created
                # neither about direct children of root datasets
                return

            types = list(dispatcher.call_sync('shares.supported_types').keys())
            pool, share_type, rest = tokens

            if share_type not in types:
                # Unknown type
                return

            share = dispatcher.datastore.get_one('shares',
                ('name', '=', rest),
                ('type', '=', share_type)
            )
            if not share:
                return

            dispatcher.submit_task('share.delete', share['id'], True)

    def on_dataset_rename(args):
        on_dataset_delete({'ds': args['ds']})
        on_dataset_create({'ds': args['new_ds']})

    def volume_pre_destroy(args):
        dispatcher.call_task_sync('share.delete_dependent', args['name'])

    plugin.register_schema_definition('share', {
        'type': 'object',
        'properties': {
            'id': {'type': 'string'},
            'name': {'type': 'string'},
            'description': {'type': 'string'},
            'enabled': {'type': 'boolean'},
            'type': {'type': 'string'},
            'target': {'type': 'string'},
            'filesystem_path': {'type': 'string'},
            'dataset_path': {'type': 'string'},
            'compression': {
                'type': 'string',
                'enum': ['off', 'on', 'lzjb', 'gzip', 'zle', 'lz4']
            },
            'properties': {'type': 'object'}
        }
    })

    plugin.register_schema_definition('share-client', {
        'type': 'object',
        'properties': {
            'host': {'type': 'string'},
            'share': {'type': 'string'},
            'user': {'type': ['string', 'null']},
            'connected_at': {'type': ['string', 'null']},
            'extra': {
                'type': 'object'
            }
        }
    })

    plugin.register_provider('shares', SharesProvider)
    plugin.register_task_handler('share.create', CreateShareTask)
    plugin.register_task_handler('share.update', UpdateShareTask)
    plugin.register_task_handler('share.delete', DeleteShareTask)
    plugin.register_task_handler('share.delete_dependent', DeleteDependentShares)
    plugin.register_event_type('shares.changed')

    plugin.register_event_handler('fs.zfs.dataset.created', on_dataset_create)
    plugin.register_event_handler('fs.zfs.dataset.deleted', on_dataset_delete)
    plugin.register_event_handler('fs.zfs.dataset.renamed', on_dataset_rename)
    plugin.attach_hook('volumes.pre_destroy', volume_pre_destroy)
    plugin.attach_hook('volumes.pre_detach', volume_pre_destroy)
