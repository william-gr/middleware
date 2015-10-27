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

import crypt
import errno
import os
import random
import string
from task import Provider, Task, TaskException, ValidationException, VerifyException, query
from dispatcher.rpc import RpcException, description, accepts, returns, SchemaHelper as h
from datastore import DuplicateKeyException, DatastoreException
from lib.system import SubprocessException, system


def check_unixname(name):
    """Helper method to check if a given name is a valid unix name
        1. Cannot start with dashes
        2. $ is only valid as a final character
        3. Cannot contain any of the following:  ,\t:+&#%\^()!@~\*?<>=|\\/"

    Returns: an array of errors [composed of a tuple (error code, error message)]
    """

    errors = []

    if name.startswith('-'):
        errors.append((errno.EINVAL, 'Your name cannot start with "-"'))

    if name.find('$') not in (-1, len(name) - 1):
        errors.append((errno.EINVAL, 'The character $ is only allowed as the final character'))

    invalids = []
    for char in name:
        if char in ' ,\t:+&#%\^()!@~\*?<>=|\\/"' and char not in invalids:
            invalids.append(char)
    if invalids:
        errors.append((
            errno.EINVAL,
            'Your name contains invalid characters ({0}).'.format(''.join(invalids))
            ))

    return errors


def crypted_password(cleartext):
    return crypt.crypt(cleartext, '$6$' + ''.join([
        random.choice(string.ascii_letters + string.digits) for _ in range(16)]))


@description("Provides access to users database")
class UserProvider(Provider):
    @description("Lists users present in the system")
    @query('user')
    def query(self, filter=None, params=None):
        def extend(user):
            # If there's no 'attributes' property, put empty dict in that place
            if 'attributes' not in user:
                user['attributes'] = {}

            # If there's no 'groups' property, put empty array in that place
            if 'groups' not in user:
                user['groups'] = []

            return user

        return self.datastore.query('users', *(filter or []), callback=extend, **(params or {}))

    def get_profile_picture(self, uid):
        pass

    @description("Retrieve the next UID available")
    @returns(int)
    def next_uid(self):
        start_uid, end_uid = self.dispatcher.configstore.get('accounts.local_uid_range')
        uid = None
        for i in range(start_uid, end_uid):
            if not self.datastore.exists('users', ('id', '=', i)):
                uid = i
                break

        if not uid:
            raise RpcException(errno.ENOSPC, 'No free UIDs available')

        return uid


@description("Provides access to groups database")
class GroupProvider(Provider):
    @description("Lists groups present in the system")
    @query('group')
    def query(self, filter=None, params=None):
        def extend(group):
            group['members'] = [x['id'] for x in self.datastore.query(
                'users',
                ('or', (
                    ('groups', 'in', group['id']),
                    ('group', '=', group['id'])
                ))
            )]
            return group

        return self.datastore.query('groups', *(filter or []), callback=extend, **(params or {}))

    @description("Retrieve the next GID available")
    @returns(int)
    def next_gid(self):
        start_gid, end_gid = self.dispatcher.configstore.get('accounts.local_gid_range')
        gid = None
        for i in range(start_gid, end_gid):
            if not self.datastore.exists('groups', ('id', '=', i)):
                gid = i
                break

        if not gid:
            raise RpcException(errno.ENOSPC, 'No free GIDs available')

        return gid


@description("Create an user in the system")
@accepts(h.all_of(
    h.ref('user'),
    h.required('username', 'group'),
    h.forbidden('builtin'),
    h.object({'password': {'type': 'string'}}),
    h.any_of(
        h.required('password'),
        h.required('unixhash', 'smbhash'),
        h.required('password_disabled')),
))
class UserCreateTask(Task):
    def describe(self, user):
        return "Adding user {0}".format(user['username'])

    def verify(self, user):

        errors = []

        for code, message in check_unixname(user['username']):
            errors.append(('name', code, message))

        if self.datastore.exists('users', ('username', '=', user['username'])):
            raise VerifyException(errno.EEXIST, 'User with given name already exists')

        if 'id' in user and self.datastore.exists('users', ('id', '=', user['id'])):
            raise VerifyException(errno.EEXIST, 'User with given UID already exists')

        if 'groups' in user and len(user['groups']) > 64:
            errors.append(
                ('groups', errno.EINVAL, 'User cannot belong to more than 64 auxiliary groups'))

        if 'full_name' in user and ':' in user['full_name']:
            errors.append(('full_name', errno.EINVAL, 'The character ":" is not allowed'))

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, user):
        if 'id' not in user:
            # Need to get next free UID
            uid = self.dispatcher.call_sync('users.next_uid')
        else:
            uid = user.pop('id')

        try:
            user['builtin'] = False
            user['unixhash'] = user.get('unixhash', '*')
            user['full_name'] = user.get('full_name', 'User &')
            user['shell'] = user.get('shell', '/bin/sh')
            # user['home'] = user.get('home', os.path.join('/home', user['username']))
            user['home'] = user.get('home', '/nonexistent')
            user.setdefault('groups', [])
            user.setdefault('attributes', {})

            password = user.pop('password', None)
            if password:
                user['unixhash'] = crypted_password(password)

            self.datastore.insert('users', user, pkey=uid)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'accounts')

            if password:
                system(
                    'smbpasswd', '-D', '0', '-s', '-a', user['username'],
                    stdin='{0}\n{1}\n'.format(password, password))
                user['smbhash'] = system('pdbedit', '-d', '0', '-w', user['username'])[0]
                self.datastore.update('users', uid, user)

        except SubprocessException as e:
            raise TaskException(
                errno.ENXIO,
                'Could not generate samba password. stdout: {0}\nstderr: {1}'.format(e.out, e.err))
        except DuplicateKeyException, e:
            raise TaskException(errno.EBADMSG, 'Cannot add user: {0}'.format(str(e)))
        except RpcException, e:
            raise TaskException(
                errno.ENXIO, 'Cannot regenerate users file, etcd service is offline'
                )
        volumes_root = self.dispatcher.call_sync('volumes.get_volumes_root')
        if user['home'].startswith(volumes_root):
            if not os.path.exists(user['home']):
                try:
                    self.dispatcher.call_sync('volumes.decode_path', user['home'])
                except RpcException as err:
                    raise TaskException(err.code, err.message)
                os.makedirs(user['home'])
            os.chown(user['home'], uid, user['group'])
            os.chmod(user['home'], 0755)
        elif not user['builtin'] and user['home'] not in (None, '/nonexistent'):
            raise TaskException(
                errno.ENOENT,
                "Invalid mountpoint specified for home directory: {0}.".format(user['home']) +
                " Use '{0}' instead as the mountpoint".format(volumes_root)
                )

        self.dispatcher.dispatch_event('users.changed', {
            'operation': 'create',
            'ids': [uid]
        })

        return uid


@description("Deletes an user from the system")
@accepts(int)
class UserDeleteTask(Task):
    def describe(self, uid):
        user = self.datastore.get_by_id('users', uid)
        return "Deleting user {0}".format(user['username'] if user else uid)

    def verify(self, uid):
        user = self.datastore.get_by_id('users', uid)

        if user is None:
            raise VerifyException(errno.ENOENT, 'User with UID {0} does not exists'.format(uid))

        if user['builtin']:
            raise VerifyException(errno.EPERM, 'Cannot delete builtin user {0}'.format(user['username']))

        return ['system']

    def run(self, uid):
        try:
            self.datastore.delete('users', uid)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'accounts')
        except DatastoreException, e:
            raise TaskException(errno.EBADMSG, 'Cannot delete user: {0}'.format(str(e)))

        self.dispatcher.dispatch_event('users.changed', {
            'operation': 'delete',
            'ids': [uid]
        })


@description('Updates an user')
@accepts(
    int,
    h.all_of(
        h.ref('user'),
        h.forbidden('builtin'),
        h.object({'password': {'type': 'string'}}),
    )
)
class UserUpdateTask(Task):
    def verify(self, uid, updated_fields):
        if not self.datastore.exists('users', ('id', '=', uid)):
            raise VerifyException(errno.ENOENT, 'User does not exists')

        errors = []
        if 'groups' in updated_fields and len(updated_fields['groups']) > 64:
            errors.append(
                ('groups', errno.EINVAL, 'User cannot belong to more than 64 auxiliary groups'))

        if 'full_name' in updated_fields and ':' in updated_fields['full_name']:
            errors.append(('full_name', errno.EINVAL, 'The character ":" is not allowed'))

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, uid, updated_fields):
        try:
            user = self.datastore.get_by_id('users', uid)

            if user.get('builtin'):
                # Ignore home changes for builtin users
                if 'home' in updated_fields:
                    updated_fields.pop('home')
                # Similarly ignore uid changes for builtin users
                if 'id' in updated_fields:
                    updated_fields.pop('id')

            home_before = user.get('home')
            user.update(updated_fields)

            password = user.pop('password', None)
            if password:
                user['unixhash'] = crypted_password(password)

            self.datastore.update('users', uid, user)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'accounts')

            if password:
                system(
                    'smbpasswd', '-D', '0', '-s', '-a', user['username'],
                    stdin='{0}\n{1}\n'.format(password, password))
                user['smbhash'] = system('pdbedit', '-d', '0', '-w', user['username'])[0]
                self.datastore.update('users', uid, user)

        except SubprocessException as e:
            raise TaskException(
                errno.ENXIO,
                'Could not generate samba password. stdout: {0}\nstderr: {1}'.format(e.out, e.err))
        except DatastoreException, e:
            raise TaskException(errno.EBADMSG, 'Cannot update user: {0}'.format(str(e)))
        except RpcException, e:
            raise TaskException(errno.ENXIO, 'Cannot regenerate users file, etcd service is offline')

        volumes_root = self.dispatcher.call_sync('volumes.get_volumes_root')
        if user['home'].startswith(volumes_root):
            if not os.path.exists(user['home']):
                try:
                    self.dispatcher.call_sync('volumes.decode_path', user['home'])
                except RpcException as err:
                    raise TaskException(err.code, err.message)
                if (home_before != '/nonexistent' and home_before != user['home']
                   and os.path.exists(home_before)):
                    system('mv', home_before, user['home'])
                else:
                    os.makedirs(user['home'])
                    os.chown(user['home'], uid, user['group'])
                    os.chmod(user['home'], 0755)
            elif user['home'] != home_before:
                os.chown(user['home'], uid, user['group'])
                os.chmod(user['home'], 0755)
        elif not user['builtin'] and user['home'] not in (None, '/nonexistent'):
            raise TaskException(
                errno.ENOENT,
                "Invalid mountpoint specified for home directory: {0}.".format(user['home']) +
                " Use '{0}' instead as the mountpoint".format(volumes_root)
                )

        self.dispatcher.dispatch_event('users.changed', {
            'operation': 'update',
            'ids': [uid]
        })


@description("Creates a group")
@accepts(h.all_of(
    h.ref('group'),
    h.required('name')
))
class GroupCreateTask(Task):
    def describe(self, group):
        return "Adding group {0}".format(group['name'])

    def verify(self, group):
        errors = []

        for code, message in check_unixname(group['name']):
            errors.append(('name', code, message))

        if self.datastore.exists('groups', ('name', '=', group['name'])):
            errors.append(
                ("name", errno.EEXIST, 'Group {0} already exists'.format(group['name']))
            )

        if 'id' in group and self.datastore.exists('groups', ('id', '=', group['id'])):
            errors.append(
                ("id", errno.EEXIST, 'Group with GID {0} already exists'.format(group['id']))
            )

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, group):
        if 'id' not in group:
            # Need to get next free GID
            gid = self.dispatcher.call_sync('groups.next_gid')
        else:
            gid = group.pop('id')

        try:
            group['builtin'] = False
            group.setdefault('sudo', False)
            self.datastore.insert('groups', group, pkey=gid)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'accounts')
        except DatastoreException, e:
            raise TaskException(errno.EBADMSG, 'Cannot add group: {0}'.format(str(e)))
        except RpcException, e:
            raise TaskException(errno.ENXIO, 'Cannot regenerate groups file, etcd service is offline')

        self.dispatcher.dispatch_event('groups.changed', {
            'operation': 'create',
            'ids': [gid]
        })

        return gid


@description("Updates a group")
@accepts(int, h.ref('group'))
class GroupUpdateTask(Task):
    def describe(self, id, updated_fields):
        return "Deleting group {0}".format(id)

    def verify(self, id, updated_fields):
        # Check if group exists
        group = self.datastore.get_one('groups', ('id', '=', id))
        if group is None:
            raise VerifyException(errno.ENOENT, 'Group with given ID does not exists')

        errors = []

        for code, message in check_unixname(group['name']):
            errors.append(('name', code, message))

        # Check if there is another group with same name being renamed to
        if self.datastore.exists('groups', ('name', '=', group['name']), ('id', '!=', id)):
            errors.append(
                ("name", errno.EEXIST, 'Group {0} already exists'.format(group['name']))
            )

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, gid, updated_fields):
        try:
            group = self.datastore.get_by_id('groups', gid)
            group.update(updated_fields)
            self.datastore.update('groups', gid, group)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'accounts')
        except DatastoreException, e:
            raise TaskException(errno.EBADMSG, 'Cannot update group: {0}'.format(str(e)))
        except RpcException, e:
            raise TaskException(errno.ENXIO, 'Cannot regenerate groups file, etcd service is offline')

        self.dispatcher.dispatch_event('groups.changed', {
            'operation': 'update',
            'ids': [gid]
        })


@description("Deletes a group")
@accepts(int)
class GroupDeleteTask(Task):
    def describe(self, name):
        return "Deleting group {0}".format(name)

    def verify(self, id):
        # Check if group exists
        group = self.datastore.get_one('groups', ('id', '=', id))
        if group is None:
            raise VerifyException(errno.ENOENT, 'Group with given ID does not exists')

        if group['builtin'] is True:
            raise VerifyException(
                errno.EINVAL, 'Group {0} is built-in and can not be deleted'.format(group['name']))

        return ['system']

    def run(self, gid):
        try:
            # Remove group from users
            for i in self.datastore.query('users', ('groups', 'in', gid)):
                i['groups'].remove(gid)
                self.datastore.update('users', i['id'], i)

            self.datastore.delete('groups', gid)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'accounts')
        except DatastoreException, e:
            raise TaskException(errno.EBADMSG, 'Cannot delete group: {0}'.format(str(e)))
        except RpcException, e:
            raise TaskException(errno.ENXIO, 'Cannot regenerate config files')

        self.dispatcher.dispatch_event('groups.changed', {
            'operation': 'delete',
            'ids': [gid]
        })


def _init(dispatcher, plugin):
    # Make sure collections are present
    dispatcher.require_collection('users', pkey_type='serial')
    dispatcher.require_collection('groups', pkey_type='serial')

    # Register definitions for objects used
    plugin.register_schema_definition('user', {
        'type': 'object',
        'properties': {
            'id': {'type': 'number'},
            'builtin': {'type': 'boolean', 'readOnly': True},
            'username': {'type': 'string'},
            'full_name': {'type': ['string', 'null']},
            'email': {'type': ['string', 'null']},
            'locked': {'type': 'boolean'},
            'sudo': {'type': 'boolean'},
            'password_disabled': {'type': 'boolean'},
            'group': {'type': 'integer'},
            'shell': {'type': 'string'},
            'home': {'type': 'string'},
            'password': {'type': ['string', 'null']},
            'unixhash': {'type': ['string', 'null']},
            'smbhash': {'type': ['string', 'null']},
            'sshpubkey': {'type': ['string', 'null']},
            'attributes': {'type': 'object'},
            'groups': {
                'type': 'array',
                'items': {
                    'type': 'integer'
                }
            },
        },
        'additionalProperties': False,
    })

    plugin.register_schema_definition('group', {
        'type': 'object',
        'properties': {
            'id': {'type': 'integer'},
            'builtin': {'type': 'boolean', 'readOnly': True},
            'name': {'type': 'string'},
            'sudo': {'type': 'boolean'},
            'members': {
                'type': 'array',
                'readOnly': True,
                'items': {'type': 'integer'}
            }
        },
        'additionalProperties': False,
    })

    # Register provider for querying accounts and groups data
    plugin.register_provider('users', UserProvider)
    plugin.register_provider('groups', GroupProvider)

    # Register task handlers
    plugin.register_task_handler('users.create', UserCreateTask)
    plugin.register_task_handler('users.update', UserUpdateTask)
    plugin.register_task_handler('users.delete', UserDeleteTask)
    plugin.register_task_handler('groups.create', GroupCreateTask)
    plugin.register_task_handler('groups.update', GroupUpdateTask)
    plugin.register_task_handler('groups.delete', GroupDeleteTask)

    # Register event types
    plugin.register_event_type('users.changed')
    plugin.register_event_type('groups.changed')
