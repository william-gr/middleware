#
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
from datastore import DatastoreException
from task import Task, Provider, TaskException, ValidationException, VerifyException, query
from dispatcher.rpc import RpcException, accepts, description, returns
from dispatcher.rpc import SchemaHelper as h
from lib.system import SubprocessException, system
from bsd import sysctl

logger = logging.getLogger('TunablePlugin')


VAR_SYSCTL_RE = re.compile('[a-z][a-z0-9_]+\.([a-z0-9_]+\.)*[a-z0-9_]+', re.I)
VAR_LOADER_RC_RE = re.compile('[a-z][a-z0-9_]+', re.I)

VAR_SYSCTL_FORMAT = '''Sysctl variable names must:
1. Start with a letter.
2. Contain at least one period.
3. End with a letter or number.
4. Can contain a combination of alphanumeric characters, numbers and/or underscores.'''

VAR_LOADER_RC_FORMAT = '''Loader and RC variable names must:
1. Start with a letter or underscore.
2. Can contain a combination of alphanumeric characters, numbers and/or underscores.'''


def sysctl_set(name, value):
    # Make sure sysctl name exists
    sysctl.sysctlnametomib(name)

    # FIXME: sysctl module doesn't handle types very well
    # sysctl.sysctl(mib, new=value)
    try:
        system('sysctl', '{0}={1}'.format(name, str(value)))
    except SubprocessException as e:
        # sysctl module compatibility
        raise OSError(str(e.err))


@description("Provides access to OS tunables")
class TunablesProvider(Provider):
    @query('tunable')
    def query(self, filter=None, params=None):
        return self.datastore.query('tunables', *(filter or []), **(params or {}))


@description("Adds Tunable")
@accepts(h.all_of(
    h.ref('tunable'),
    h.required('var', 'value', 'type'),
))
class TunableCreateTask(Task):
    def describe(self, tunable):
        return "Creating Tunable {0}".format(tunable['var'])

    def verify(self, tunable):

        errors = []
        if self.datastore.exists('tunables', ('var', '=', tunable['var'])):
            errors.append(('var', errno.EEXIST, 'This variable already exists.'))

        if '"' in tunable['value'] or "'" in tunable['value']:
            errors.append(('value', errno.EINVAL, 'Quotes are not allowed'))

        if tunable['type'] in ('LOADER', 'RC') and not VAR_LOADER_RC_RE.match(tunable['var']):
            errors.append(('var', errno.EINVAL, VAR_SYSCTL_FORMAT))
        elif tunable['type'] == 'SYSCTL':
            if not VAR_SYSCTL_RE.match(tunable['var']):
                errors.append(('var', errno.EINVAL, VAR_LOADER_RC_FORMAT))
            try:
                sysctl.sysctlnametomib(tunable['var'])
            except OSError:
                errors.append(('var', errno.EINVAL, 'Sysctl variable does not exist'))

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, tunable):
        try:
            if 'enabled' not in tunable:
                tunable['enabled'] = True

            if tunable['enabled'] and tunable['type'] == 'SYSCTL':
                sysctl_set(tunable['var'], tunable['value'])

            pkey = self.datastore.insert('tunables', tunable)
            self.dispatcher.dispatch_event('tunables.changed', {
                'operation': 'create',
                'ids': [pkey]
            })

            if tunable['enabled']:
                if tunable['type'] == 'LOADER':
                    self.dispatcher.call_sync('etcd.generation.generate_group', 'loader')
                elif tunable['type'] == 'RC':
                    self.dispatcher.call_sync('etcd.generation.generate_group', 'services')
        except DatastoreException as e:
            raise TaskException(errno.EBADMSG, 'Cannot create Tunable: {0}'.format(str(e)))
        except RpcException as e:
            raise TaskException(errno.ENXIO, 'Cannot generate tunable: {0}'.format(str(e)))
        except OSError as e:
            raise TaskException(errno.ENXIO, 'Failed to set sysctl: {0}'.format(str(e)))
        return pkey


@description("Updates Tunable")
@accepts(str, h.ref('tunable'))
class TunableUpdateTask(Task):
    def verify(self, id, updated_fields):

        tunable = self.datastore.get_by_id('tunables', id)
        if tunable is None:
            raise VerifyException(errno.ENOENT, 'Tunable with given ID does not exist')

        errors = []

        if 'var' in updated_fields and self.datastore.exists(
            'tunables', ('and', [('var', '=', updated_fields['var']), ('id', '!=', id)])
        ):
            errors.append(('var', errno.EEXIST, 'This variable already exists.'))

        if 'value' in updated_fields and '"' in updated_fields['value'] or "'" in updated_fields['value']:
            errors.append(('value', errno.EINVAL, 'Quotes are not allowed'))

        if 'type' in updated_fields:
            if updated_fields['type'] in ('LOADER', 'RC') and not VAR_LOADER_RC_RE.match(tunable['var']):
                errors.append(('var', errno.EINVAL, VAR_SYSCTL_FORMAT))
            elif updated_fields['type'] == 'SYSCTL':
                if not VAR_SYSCTL_RE.match(tunable['var']):
                    errors.append(('var', errno.EINVAL, VAR_LOADER_RC_FORMAT))
                try:
                    sysctl.sysctlnametomib(tunable['var'])
                except OSError:
                    errors.append(('var', errno.EINVAL, 'Sysctl variable does not exist'))

        if errors:
            raise ValidationException(errors)

        return ['system']

    def run(self, id, updated_fields):
        try:
            tunable = self.datastore.get_by_id('tunables', id)
            tunable.update(updated_fields)

            if tunable.get('enabled') and tunable['type'] == 'SYSCTL':
                sysctl_set(tunable['var'], tunable['value'])

            self.datastore.update('tunables', id, tunable)
            self.dispatcher.dispatch_event('tunables.changed', {
                'operation': 'update',
                'ids': [id]
            })

            # Could be enabled and now disabled, so generate either way
            if tunable['type'] == 'LOADER':
                self.dispatcher.call_sync('etcd.generation.generate_group', 'loader')
            elif tunable['type'] == 'RC':
                self.dispatcher.call_sync('etcd.generation.generate_group', 'services')
        except DatastoreException as e:
            raise TaskException(errno.EBADMSG, 'Cannot update Tunable: {0}'.format(str(e)))
        except RpcException as e:
            raise TaskException(errno.ENXIO, 'Cannot generate tunable: {0}'.format(str(e)))
        except OSError as e:
            raise TaskException(errno.ENXIO, 'Failed to set sysctl: {0}'.format(str(e)))


@description("Deletes Tunable")
@accepts(str)
class TunableDeleteTask(Task):
    def verify(self, id):

        tunable = self.datastore.get_by_id('tunables', id)
        if tunable is None:
            raise VerifyException(errno.ENOENT, 'Tunable with given ID does not exist')

        return ['system']

    def run(self, id):
        tunable = self.datastore.get_by_id('tunables', id)

        try:
            self.datastore.delete('tunables', id)
            self.dispatcher.dispatch_event('tunables.changed', {
                'operation': 'delete',
                'ids': [id]
            })
            if tunable['type'] == 'LOADER':
                self.dispatcher.call_sync('etcd.generation.generate_group', 'loader')
            elif tunable['type'] == 'RC':
                self.dispatcher.call_sync('etcd.generation.generate_group', 'services')
        except DatastoreException as e:
            raise TaskException(errno.EBADMSG, 'Cannot delete Tunable: {0}'.format(str(e)))
        except RpcException as e:
            raise TaskException(errno.ENXIO, 'Cannot generate tunable: {0}'.format(str(e)))


def _init_sysctls(dispatcher):

    for ctl in dispatcher.call_sync('tunables.query', [('type', '=', 'SYSCTL')]):
        if ctl.get('enabled') is False:
            continue
        try:
            sysctl_set(ctl['var'], ctl['value'])
        except OSError as e:
            logger.error('Cannot set sysctl {0} to {1}: {2}'.format(
                ctl['var'], ctl['value'], str(e)))


def _init(dispatcher, plugin):
    plugin.register_schema_definition('tunable', {
        'type': 'object',
        'properties': {
            'id': {'type': 'string'},
            'type': {'type': 'string', 'enum': [
                'LOADER', 'RC', 'SYSCTL',
            ]},
            'var': {'type': 'string'},
            'value': {'type': 'string'},
            'comment': {'type': 'string'},
            'enabled': {'type': 'boolean'},
        },
        'additionalProperties': False,
    })

    # Register events
    plugin.register_event_type('tunables.changed')

    # Register provider
    plugin.register_provider('tunables', TunablesProvider)

    # Register tasks
    plugin.register_task_handler('tunables.create', TunableCreateTask)
    plugin.register_task_handler('tunables.update', TunableUpdateTask)
    plugin.register_task_handler('tunables.delete', TunableDeleteTask)

    # Set all configured sysctls
    _init_sysctls(dispatcher)
