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
import errno
import gevent
import gevent.pool
import logging

from task import Task, Provider, TaskException, VerifyException, query
from resources import Resource
from dispatcher.rpc import RpcException, description, accepts, private, returns
from dispatcher.rpc import SchemaHelper as h
from datastore.config import ConfigNode
from lib.system import system, SubprocessException

logger = logging.getLogger('ServiceManagePlugin')


@description("Provides info about available services and their state")
class ServiceInfoProvider(Provider):
    @description("Lists available services")
    @query("service")
    def query(self, filter=None, params=None):
        def extend(i):
            state, pid = get_status(self.dispatcher, i)
            entry = {
                'name': i['name'],
                'state': state,
            }

            if pid is not None:
                entry['pid'] = pid

            entry['builtin'] = i['builtin']
            return entry

        # Running extend sequentially might take too long due to the number of services
        # and `service ${name} onestatus`. To workaround that run it in parallel using gevent
        result = self.datastore.query('service_definitions', *(filter or []), **(params or {}))
        if result is None:
            return result
        single = (params or {}).get('single')
        if single is True:
            jobs = {gevent.spawn(extend, result): result}
        else:
            jobs = {
                gevent.spawn(extend, entry): entry
                for entry in result
            }
        gevent.joinall(jobs.keys(), timeout=15)
        group = gevent.pool.Group()

        def result(greenlet):
            if greenlet.value is None:
                entry = jobs.get(greenlet)
                return {
                    'name': entry['name'],
                    'state': 'UNKNOWN',
                    'builtin': entry['builtin'],
                }
            else:
                return greenlet.value

        result = group.map(result, jobs)
        return result[0] if single is True else result

    @accepts(str)
    @returns(h.object())
    def get_service_config(self, service):
        svc = self.datastore.get_one('service_definitions', ('name', '=', service))
        if not svc:
            raise RpcException(errno.EINVAL, 'Invalid service name')

        node = ConfigNode('service.{0}'.format(service), self.configstore)
        return node

    @private
    @accepts(str)
    @returns()
    def ensure_started(self, service):
        # XXX launchd!
        svc = self.datastore.get_one('service_definitions', ('name', '=', service))
        if not svc:
            raise RpcException(errno.ENOENT, 'Service {0} not found'.format(service))

        if 'rcng' not in svc:
            return

        rc_scripts = svc['rcng']['rc-scripts']

        try:
            if type(rc_scripts) is unicode:
                system("/usr/sbin/service", rc_scripts, 'onestart')

            if type(rc_scripts) is list:
                for i in rc_scripts:
                    system("/usr/sbin/service", i, 'onestart')
        except SubprocessException:
            pass

    @private
    @accepts(str)
    def ensure_stopped(self, service):
        # XXX launchd!
        svc = self.datastore.get_one('service_definitions', ('name', '=', service))
        if not svc:
            raise RpcException(errno.ENOENT, 'Service {0} not found'.format(service))

        if 'rcng' not in svc:
            return

        rc_scripts = svc['rcng']['rc-scripts']

        try:
            if type(rc_scripts) is unicode:
                system("/usr/sbin/service", rc_scripts, 'onestop')

            if type(rc_scripts) is list:
                for i in rc_scripts:
                    system("/usr/sbin/service", i, 'onestop')
        except SubprocessException:
            pass

    @private
    @accepts(str)
    def reload(self, service):
        svc = self.datastore.get_one('service_definitions', ('name', '=', service))
        status = self.query([('name', '=', service)], {'single': True})
        if not svc:
            raise RpcException(errno.ENOENT, 'Service {0} not found'.format(service))

        rc_scripts = svc['rcng']['rc-scripts']
        reload_scripts = svc['rcng'].get('reload', rc_scripts)

        if status['state'] != 'RUNNING':
            return

        if type(rc_scripts) is unicode:
            try:
                system("/usr/sbin/service", rc_scripts, 'onereload')
            except SubprocessException:
                pass

        if type(rc_scripts) is list:
            for i in rc_scripts:
                if i not in reload_scripts:
                        continue

                try:
                    system("/usr/sbin/service", i, 'onereload')
                except SubprocessException:
                    pass

    @private
    @accepts(str)
    def restart(self, service):
        svc = self.datastore.get_one('service_definitions', ('name', '=', service))
        status = self.query([('name', '=', service)], {'single': True})
        if not svc:
            raise RpcException(errno.ENOENT, 'Service {0} not found'.format(service))

        if status['state'] != 'RUNNING':
            return

        hook_rpc = svc.get('restart_rpc')
        if hook_rpc:
            try:
                self.dispatcher.call_sync(hook_rpc)
            except RpcException:
                pass
            return

        rc_scripts = svc['rcng']['rc-scripts']

        try:
            if type(rc_scripts) is unicode:
                system("/usr/sbin/service", rc_scripts, 'onerestart')

            if type(rc_scripts) is list:
                for i in rc_scripts:
                    system("/usr/sbin/service", i, 'onerestart')
        except SubprocessException:
            pass

    @private
    @accepts(str)
    def apply_state(self, service):
        svc = self.datastore.get_one('service_definitions', ('name', '=', service))
        if not svc:
            raise RpcException(errno.ENOENT, 'Service {0} not found'.format(service))

        state, pid = get_status(self.dispatcher, svc)
        node = ConfigNode('service.{0}'.format(service), self.configstore)

        if node['enable'].value and state != 'RUNNING':
            logger.info('Starting service {0}'.format(service))
            self.dispatcher.call_sync('services.ensure_started', service)

        if not node['enable'].value and state != 'STOPPED':
            logger.info('Stopping service {0}'.format(service))
            self.dispatcher.call_sync('services.ensure_stopped', service)


@description("Provides functionality to start, stop, restart or reload service")
@accepts(
    str,
    h.enum(str, ['start', 'stop', 'restart', 'reload'])
)
class ServiceManageTask(Task):
    def describe(self, name, action):
        return "{0}ing service {1}".format(action.title(), name)

    def verify(self, name, action):
        if not self.datastore.exists('service_definitions', ('name', '=', name)):
            raise VerifyException(errno.ENOENT, 'Service {0} not found'.format(name))

        return ['system']

    def run(self, name, action):
        service = self.datastore.get_one('service_definitions', ('name', '=', name))

        hook_rpc = service.get('{0}_rpc'.format(action))
        if hook_rpc:
            try:
                return self.dispatcher.call_sync(hook_rpc)
            except RpcException as e:
                raise TaskException(errno.EBUSY, 'Hook {0} for {1} failed: {2}'.format(
                    action, name, e
                ))

        rc_scripts = service['rcng'].get('rc-scripts')
        reload_scripts = service['rcng'].get('reload', rc_scripts)
        try:
            if type(rc_scripts) is unicode:
                system("/usr/sbin/service", rc_scripts, 'one' + action)

            if type(rc_scripts) is list:
                for i in rc_scripts:
                    if action == 'reload' and i not in reload_scripts:
                        continue

                    system("/usr/sbin/service", i, 'one' + action)

        except SubprocessException, e:
            raise TaskException(errno.EBUSY, e.err)


@description("Updates configuration for services")
@accepts(str, h.object())
class UpdateServiceConfigTask(Task):
    def describe(self, service, updated_fields):
        return "Updating configuration for service {0}".format(service)

    def verify(self, service, updated_fields):
        if not self.datastore.exists('service_definitions', ('name', '=', service)):
            raise VerifyException(
                errno.ENOENT,
                'Service {0} not found'.format(service))
        for x in updated_fields:
            if not self.configstore.exists(
                    'service.{0}.{1}'.format(service, x)):
                raise VerifyException(
                    errno.ENOENT,
                    'Service {0} does not have the following key: {1}'.format(
                        service, x))
        return ['system']

    def run(self, service, updated_fields):
        service_def = self.datastore.get_one('service_definitions', ('name', '=', service))

        if service_def.get('task'):
            self.join_subtasks(self.run_subtask(service_def['task'], updated_fields))
        else:
            node = ConfigNode('service.{0}'.format(service), self.configstore)
            node.update(updated_fields)

            if service_def.get('etcd-group'):
                self.dispatcher.call_sync('etcd.generation.generate_group', service_def.get('etcd-group'))

            self.dispatcher.call_sync('services.apply_state', service)

            if 'enable' in updated_fields:
                # Propagate to dependent services
                for i in service_def.get('dependencies', []):
                    self.join_subtasks(self.run_subtask('service.configure', i, {
                        'enable': updated_fields['enable']
                    }))

                if service_def.get('auto_enable'):
                    # Consult state of services dependent on us
                    for i in self.datastore.query('service_definitions', ('dependencies', 'in', service)):
                        enb = self.configstore.get('service.{0}.enable', i['name'])
                        if enb != updated_fields['enable']:
                            del updated_fields['enable']

        self.dispatcher.call_sync('etcd.generation.generate_group', 'services')
        self.dispatcher.dispatch_event('service.changed', {
            'operation': 'update',
            'ids': [service_def['id']]
        })


def get_status(dispatcher, service):
    if 'status_rpc' in service:
        state = 'RUNNING'
        pid = None
        try:
            dispatcher.call_sync(service['status_rpc'])
        except RpcException:
            state = 'STOPPED'
    elif 'pidfile' in service:
        state = 'RUNNING'
        pid = None
        pidfiles = service['pidfile'] \
            if isinstance(service['pidfile'], list) \
            else [service['pidfile']]

        for p in pidfiles:
            # Check if process is alive by reading pidfile
            try:
                with open(p, 'r') as fd:
                    pid = int(fd.read().strip())
            except IOError:
                pid = None
                state = 'STOPPED'
            except ValueError:
                pid = None
                state = 'STOPPED'
            else:
                try:
                    os.kill(pid, 0)
                except OSError:
                    state = 'UNKNOWN'

    elif 'rcng' in service and 'rc-scripts' in service['rcng']:
        rc_scripts = service['rcng']['rc-scripts']
        pid = None
        state = 'RUNNING'
        try:
            if type(rc_scripts) is unicode:
                system("/usr/sbin/service", rc_scripts, 'onestatus')

            if type(rc_scripts) is list:
                for x in rc_scripts:
                    system("/usr/sbin/service", x, 'onestatus')
        except SubprocessException:
            state = 'STOPPED'

    else:
        pid = None
        state = 'UNKNOWN'

    return state, pid


def _init(dispatcher, plugin):
    def on_rc_command(args):
        cmd = args['action']
        name = args['name']
        svc = dispatcher.datastore.get_one('service_definitions', (
            'or', (
                ('rcng.rc-scripts', '=', name),
                ('rcng.rc-scripts', 'in', name)
            )
        ))

        if svc is None:
            # ignore unknown rc scripts
            return

        if cmd not in ('start', 'stop', 'reload', 'restart'):
            # ignore unknown actions
            return

        if cmd == 'stop':
            cmd += 'p'

        dispatcher.dispatch_event('service.{0}ed'.format(cmd), {
            'name': svc['name']
        })

    plugin.register_schema_definition('service', {
        'type': 'object',
        'properties': {
            'id': {'type': 'string'},
            'name': {'type': 'string'},
            'pid': {'type': 'integer'},
            'state': {
                'type': 'string',
                'enum': ['RUNNING', 'STOPPED', 'UNKNOWN']
            }
        }
    })

    plugin.register_event_handler("service.rc.command", on_rc_command)
    plugin.register_task_handler("service.manage", ServiceManageTask)
    plugin.register_task_handler("service.configure", UpdateServiceConfigTask)
    plugin.register_provider("services", ServiceInfoProvider)

    for svc in dispatcher.datastore.query('service_definitions'):
        plugin.register_resource(Resource('service:{0}'.format(svc['name'])), parents=['system'])
