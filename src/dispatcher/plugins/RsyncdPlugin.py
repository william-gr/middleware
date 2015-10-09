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
import errno
import logging
import re
import os
from fcntl import flock, LOCK_EX, LOCK_NB, LOCK_UN
from gevent import subprocess
from tempfile import TemporaryFile

from datastore import DatastoreException
from datastore.config import ConfigNode
from dispatcher.rpc import RpcException, SchemaHelper as h, description, accepts, returns
from task import (
    Task, ProgressTask, Provider, TaskException, query,
    ValidationException, VerifyException,
)

logger = logging.getLogger('RsyncdPlugin')


@description('Provides info about Rsyncd service configuration')
class RsyncdProvider(Provider):
    @accepts()
    @returns(h.ref('service-rsyncd'))
    def get_config(self):
        return ConfigNode('service.rsyncd', self.configstore)


@description("Provides access to rsyncd modules database")
class RsyncdModuleProvider(Provider):
    @description("Lists rsyncd modules present in the system")
    @query('rsyncd-module')
    def query(self, filter=None, params=None):
        return self.datastore.query('rsyncd-module', *(filter or []), **(params or {}))


@description('Configure Rsyncd service')
@accepts(h.ref('service-rsyncd'))
class RsyncdConfigureTask(Task):
    def describe(self, share):
        return 'Configuring Rsyncd service'

    def verify(self, rsyncd):
        errors = []

        node = ConfigNode('service.rsyncd', self.configstore).__getstate__()
        node.update(rsyncd)

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, rsyncd):
        try:
            node = ConfigNode('service.rsyncd', self.configstore)
            node.update(rsyncd)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'services')
            self.dispatcher.call_sync('services.restart', 'rsyncd')
            self.dispatcher.dispatch_event('service.rsyncd.changed', {
                'operation': 'updated',
                'ids': None,
            })
        except RpcException, e:
            raise TaskException(
                errno.ENXIO, 'Cannot reconfigure Rsyncd: {0}'.format(str(e))
            )


@description("Create a rsync module in the system")
@accepts(h.all_of(
    h.ref('rsyncd-module'),
    h.required('name', 'path'),
))
class RsyncdModuleCreateTask(Task):
    def describe(self, rsyncmod):
        return 'Adding rsync module'

    def verify(self, rsyncmod):
        errors = []

        if re.search(r'[/\]]', rsyncmod['name']):
            errors.append('name', errno.EINVAL, 'The name cannot contain slash or a closing square backet.')

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, rsyncmod):

        try:
            uuid = self.datastore.insert('rsyncd-module', rsyncmod)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'rsyncd')
            self.dispatcher.call_sync('services.restart', 'rsyncd')
        except DatastoreException as e:
            raise TaskException(errno.EBADMSG, 'Cannot add rsync module: {0}'.format(str(e)))
        except RpcException as e:
            raise TaskException(errno.ENXIO, 'Cannot regenerate rsyncd {0}'.format(str(e)))
        self.dispatcher.dispatch_event('service.rsyncd.module.changed', {
            'operation': 'create',
            'ids': [uuid]
        })
        return uuid


@description("Update a rsync module in the system")
@accepts(str, h.all_of(
    h.ref('rsyncd-module'),
))
class RsyncdModuleUpdateTask(Task):
    def describe(self, uuid, updated_fields):
        return 'Updating rsync module'

    def verify(self, uuid, updated_fields):

        rsyncmod = self.datastore.get_by_id('rsyncd-module', uuid)
        if rsyncmod is None:
            raise VerifyException(errno.ENOENT, 'Rsync module {0} does not exists'.format(uuid))
        rsyncmod.update(updated_fields)

        errors = []

        if re.search(r'[/\]]', rsyncmod['name']):
            errors.append('name', errno.EINVAL, 'The name cannot contain slash or a closing square backet.')

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, uuid, updated_fields):

        rsyncmod = self.datastore.get_by_id('rsyncd-module', uuid)
        try:
            rsyncmod.update(updated_fields)
            self.datastore.update('rsyncd-module', uuid, rsyncmod)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'rsyncd')
            self.dispatcher.call_sync('services.restart', 'rsyncd')
        except DatastoreException as e:
            raise TaskException(errno.EBADMSG, 'Cannot update rsync module: {0}'.format(str(e)))
        except RpcException as e:
            raise TaskException(errno.ENXIO, 'Cannot regenerate rsyncd {0}'.format(str(e)))

        self.dispatcher.dispatch_event('service.rsyncd.module.changed', {
            'operation': 'update',
            'ids': [uuid]
        })


@description("Delete a rsync module in the system")
@accepts(str)
class RsyncdModuleDeleteTask(Task):
    def describe(self, uuid):
        return 'Deleting rsync module'

    def verify(self, uuid):

        rsyncmod = self.datastore.get_by_id('rsyncd-module', uuid)
        if rsyncmod is None:
            raise VerifyException(errno.ENOENT, 'Rsync module {0} does not exists'.format(uuid))

        return ['system']

    def run(self, uuid):

        try:
            self.datastore.delete('rsyncd-module', uuid)
            self.dispatcher.call_sync('etcd.generation.generate_group', 'rsyncd')
            self.dispatcher.call_sync('services.restart', 'rsyncd')
        except DatastoreException as e:
            raise TaskException(errno.EBADMSG, 'Cannot delete rsync module: {0}'.format(str(e)))
        except RpcException as e:
            raise TaskException(errno.ENXIO, 'Cannot regenerate rsyncd {0}'.format(str(e)))

        self.dispatcher.dispatch_event('service.rsyncd.module.changed', {
            'operation': 'delete',
            'ids': [uuid]
        })


def demote(user_uid, user_gid):
    """
    Helper function to call the subprocess as the specific user.
    Taken from: https://gist.github.com/sweenzor/1685717
    Pass the function 'set_ids' to preexec_fn, rather than just calling
    setuid and setgid. This will change the ids for that subprocess only"""

    def set_ids():
        os.setgid(user_gid)
        os.setuid(user_uid)

    return set_ids


@description("Runs an Rsync Copy Task with the specified arguments")
@accepts(h.all_of(
    h.ref('rsync_copy'),
    h.required(
        'user',
        'path',
        'remote_host',
        'rsync_direction',
        'rsync_mode'
    ),
    h.one_of('remote_path', 'remote_module')
))
class RsyncCopyTask(ProgressTask):
    def describe(self, params):
        return 'Running Rsync Copy Task with user specified arguments'

    def verify(self, params):
        errors = []

        if self.datastore.get_one('users', ('username', '=', params.get('user'))) is None:
            raise VerifyException(
                errno.ENOENT, 'User {0} does not exists'.format(params.get('user'))
            )

        path = params.get('path')
        rmode = params.get('rsync_mode')
        remote_path = params.get('remote_path')
        remote_host = params.get('remote_host')
        remote_module = params.get('remote_module')

        if path in [None, ''] or path.isspace():
            errors.append(('path', errno.EINVAL, 'The Path is required'))
        elif not os.path.exists(path):
            raise VerifyException(
                errno.ENOENT,
                "The specified path: '{0}'' does not exist".format(params.get('path'))
            )
        if (
            params.get('remote_host') in ['127.0.0.1', 'localhost'] and
            rmode == 'ssh' and
            remote_path is not None and
            not os.path.exists(remote_path)
           ):
            raise VerifyException(
                errno.ENOENT,
                "The specified path: '{0}'' does not exist".format(remote_path)
            )

        if rmode == 'ssh' and (remote_path in [None, ''] or remote_path.isspace()):
            errors.append(('remote_path', errno.EINVAL, 'The Remote Path is required'))
        elif rmode == 'module' and (remote_module in [None, ''] or remote_module.isspace()):
            errors.append(('remote_module', errno.EINVAL, 'The Remote Module is required'))

        if remote_host in [None, ''] or remote_host.isspace():
            errors.append(('remote_host', errno.EINVAL, 'A Remote Host needs to be specified'))
        if errors:
            raise ValidationException(errors)

        return []

    def run(self, params):
        self.message = 'Starting Rsync Task'
        self.set_progress(0)
        with open(os.path.join(params['path'], '.lock'), 'wb+') as lockfile:
            # Lets try and get a lock on this path for the rsync task
            # but do not freak out if you do not get it
            try:
                flock(lockfile, LOCK_EX | LOCK_NB)
            except IOError:
                logger.warning('Rsync Task could not get a lock on {0}'.format(params['path']))

            # Execute Rsync Task here
            line = '/usr/local/bin/rsync --info=progress2 -h'
            rsync_user = self.datastore.get_one('users', ('username', '=', params.get('user')))

            rsync_properties = params.get('rsync_properties')
            if rsync_properties:
                if rsync_properties.get('recursive'):
                    line += ' -r'
                if rsync_properties.get('times'):
                    line += ' -t'
                if rsync_properties.get('compress'):
                    line += ' -z'
                if rsync_properties.get('archive'):
                    line += ' -a'
                if rsync_properties.get('preserve_permissions'):
                    line += ' -p'
                if rsync_properties.get('preserve_attributes'):
                    line += ' -X'
                if rsync_properties.get('delete'):
                    line += ' --delete-delay'
                if rsync_properties.get('delay_updates'):
                    line += ' --delay-updates'
                if rsync_properties.get('extra'):
                    line += ' {0}'.format(rsync_properties.get('extra'))

            remote_host = params.get('remote_host')
            remote_address = ''
            if '@' in remote_host:
                remote_address = remote_host
            else:
                remote_user = params.get('remote_user', params.get('user'))
                remote_address = '"{0}"@{1}'.format(remote_user, remote_host)

            if params.get('rsync_mode') == 'module':
                if params.get('rsync_direction') == 'push':
                    line += ' "{0}" {1}::"{2}"'.format(
                        params.get('path'),
                        remote_address,
                        params.get('remote_module'),
                    )
                else:
                    line += ' {0}::"{1}" "{2}"'.format(
                        remote_address,
                        params.get('remote_module'),
                        params.get('rsync_path'),
                    )
            else:
                line += ' -e "ssh -p {0} -o BatchMode=yes -o StrictHostKeyChecking=yes"'.format(
                    params.get('remote_ssh_port', 22)
                )
                if params.get('rsync_direction') == 'push':
                    line += ' "{0}" {1}:\\""{2}"\\"'.format(
                        params.get('path'),
                        remote_address,
                        params.get('remote_path'),
                    )
                else:
                    line += ' {0}:\\""{1}"\\" "{2}"'.format(
                        remote_address,
                        params.get('remote_path'),
                        params.get('path'),
                    )

            if params.get('quiet'):
                line += ' > /dev/null 2>&1'

            # Starting rsync subprocess
            logger.debug('Rsync Copy Task Command: {0}'.format(line))
            # It would be nice to get the progess but not at the cost of
            # killing this task!

            # Note this TemporaryFile hack for the subprocess stdout is needed
            # because setting Popen's `stdout=subprocess.PIPE` does not allow
            # that sstdout to be seeked on. subprocess.PIPE only allows for
            # readline() and such read methods. stdout.readline() does not
            # allow for us to catch rsync's in-place progress updates which
            # are done with the '\r' character. It is also auto garbage collected.
            proc_stdout = TemporaryFile(mode='w+', bufsize=0)
            try:
                rsync_proc = subprocess.Popen(
                    line,
                    stdout=proc_stdout.fileno(),
                    stderr=subprocess.PIPE,
                    shell=True,
                    bufsize=0,
                    preexec_fn=demote(rsync_user['id'], rsync_user['group'])
                )
                self.message = 'Executing Rsync Command'
                seek = 0
                old_seek = 0
                while rsync_proc.poll() is None:
                    proc_output = ''
                    proc_stdout.seek(seek)
                    try:
                        while True:
                            op_byte = proc_stdout.read(1)
                            if op_byte == '':
                                # In this case break before incrementing `seek`
                                break
                            seek += 1
                            if op_byte == '\r':
                                break
                            proc_output += op_byte
                            seek += 1
                        if old_seek != seek:
                            old_seek = seek
                            self.message = proc_output.strip()
                            proc_output = proc_output.split(' ')
                            progress = filter(lambda x: '%' in x, proc_output)
                            if len(progress):
                                self.set_progress(int(progress[0][:-1]))
                    except Exception as e:
                        # Catch IOERROR Errno 9 which usually arises because
                        # of already closed fileobject being used here therby
                        # raising Bad File Descriptor error. In this case break
                        # and the outer while loop will check for rsync_proc.poll()
                        # to be None or not and DTRT
                        if e[0] == 9:
                            break
                        logger.debug("Parsing error in rsync task: {0}".format(str(e)))
            except Exception as e:
                flock(lockfile, LOCK_UN)
                self.message = 'Rsync Task Failed'
                raise TaskException(
                    errno.EIO,
                    'Rsync Task failed because of Error: {0}'.format(str(e))
                )
            if rsync_proc.returncode != 0:
                self.message = 'Rsync Task Failed'
                raise TaskException(
                    errno.EIO,
                    'Rsync Task returned with non-zero returncode. Error: {0}'.format(
                        rsync_proc.stderr.read())
                )
            # Finally lets unlock that lockfile, it does not fail
            # even if did not acquire the lock in the first place
            flock(lockfile, LOCK_UN)
            self.message = 'Rsync Task Successfully Completed'
            self.set_progress(100)


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):

    # Make sure collections are present
    dispatcher.require_collection('rsyncd-module')

    # Register schemas
    plugin.register_schema_definition('service-rsyncd', {
        'type': 'object',
        'properties': {
            'port': {'type': 'integer'},
            'auxiliary': {'type': 'string'},
        },
        'additionalProperties': False,
    })
    plugin.register_schema_definition('rsyncd-module', {
        'type': 'object',
        'properties': {
            'name': {'type': 'string'},
            'description': {'type': ['string', 'null']},
            'path': {'type': 'string'},
            'mode': {'type': 'string', 'enum': [
                'READONLY',
                'WRITEONLY',
                'READWRITE',
            ]},
            'max_connections': {'type': ['integer', 'null']},
            'user': {'type': 'string'},
            'group': {'type': 'string'},
            'hosts_allow': {'type': ['string', 'null']},
            'hosts_deny': {'type': ['string', 'null']},
            'auxiliary': {'type': ['string', 'null']},
        },
        'additionalProperties': False,
    })
    plugin.register_schema_definition('rsync_copy', {
        'type': 'object',
        'properties': {
            'user': {'type': 'string'},
            'remote_user': {'type': 'string'},
            'remote_host': {'type': 'string'},
            'path': {'type': 'string'},
            'remote_path': {'type': 'string'},
            'rsync_direction': {
                'type': 'string',
                'enum': ['push', 'pull']
            },
            'rsync_mode': {
                'type': 'string',
                'enum': ['module', 'ssh']
            },
            'remote_ssh_port': {'type': 'integer'},
            'remote_module': {'type': 'string'},
            'rsync_properties': {
                'type': 'object',
                'properties': {
                    'recursive': {'type': 'boolean'},
                    'compress': {'type': 'boolean'},
                    'times': {'type': 'boolean'},
                    'archive': {'type': 'boolean'},
                    'delete': {'type': 'boolean'},
                    'preserve_permissions': {'type': 'boolean'},
                    'preserve_attributes': {'type': 'boolean'},
                    'delay_updates': {'type': 'boolean'},
                    'extra': {'type': 'string'}
                }
            },
            'quiet': {'type': 'boolean'},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider("service.rsyncd", RsyncdProvider)
    plugin.register_provider("service.rsyncd.module", RsyncdModuleProvider)

    # Register tasks
    plugin.register_task_handler("service.rsyncd.configure", RsyncdConfigureTask)
    plugin.register_task_handler("service.rsyncd.module.create", RsyncdModuleCreateTask)
    plugin.register_task_handler("service.rsyncd.module.update", RsyncdModuleUpdateTask)
    plugin.register_task_handler("service.rsyncd.module.delete", RsyncdModuleDeleteTask)
    plugin.register_task_handler("rsync.copy", RsyncCopyTask)
