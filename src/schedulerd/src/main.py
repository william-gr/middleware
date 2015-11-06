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

import sys
import json
import time
import logging
import setproctitle
import argparse
import socket
import uuid
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.mongodb import MongoDBJobStore
from datastore import get_datastore, DatastoreException
from datastore.config import ConfigStore
from dispatcher.rpc import RpcService, RpcException, private
from dispatcher.client import Client, ClientError
from fnutils import exclude, configure_logging
from fnutils.query import wrap
from fnutils.debug import DebugService


DEFAULT_CONFIGFILE = '/usr/local/etc/middleware.conf'
context = None


def job(*args, **kwargs):
    return context.run_job(*args, **kwargs)


class ManagementService(RpcService):
    def __init__(self, context):
        self.context = context

    @private
    def query(self, filter=None, params=None):
        def serialize(job):
            last_task = None
            current_task = None
            current_progress = None
            schedule = {f.name: f for f in job.trigger.fields}
            schedule['coalesce'] = job.coalesce

            last_run = self.context.datastore.query(
                'schedulerd.runs',
                ('job_id', '=', job.id),
                sort='created_at',
                single=True
            )

            if last_run:
                last_task = self.context.datastore.get_by_id('tasks', last_run['task_id'])

            if job.id in self.context.active_tasks:
                current_task_id = self.context.active_tasks[job.id]
                current_task = self.context.client.call_sync('task.status', current_task_id)
                if 'progress' in current_task:
                    current_progress = current_task['progress']

            return {
                'id': job.id,
                'description': job.name,
                'name': job.args[0],
                'args': job.args[1:],
                'enabled': job.next_run_time is not None,
                'status': {
                    'next_run_time': job.next_run_time,
                    'last_run_status': last_task['state'] if last_task else None,
                    'current_run_status': current_task['state'] if current_task else None,
                    'current_run_progress': current_progress
                },
                'schedule': schedule
            }

        return wrap(list(map(serialize, self.context.scheduler.get_jobs()))).query(*(filter or []), **(params or {}))

    @private
    def add(self, task):
        if 'id' not in task:
            count = len(self.context.scheduler.get_jobs())
            task_id = 'task{0}'.format(count + 1)
        else:
            task_id = task['id']

        self.context.logger.info('Adding new job with ID {0}'.format(task_id))
        self.context.scheduler.add_job(
            job,
            trigger='cron',
            id=task_id,
            args=[task['name']] + task['args'],
            kwargs={'id': task_id},
            **task['schedule']
        )

        return task_id

    @private
    def delete(self, job_id):
        self.context.logger.info('Deleting job with ID {0}'.format(job_id))
        self.context.scheduler.remove_job(job_id)

    @private
    def update(self, job_id, updated_params):
        job = self.context.scheduler.get_job(job_id)
        self.context.logger.info('Updating job with ID {0}'.format(job_id))

        if 'name' in updated_params or 'args' in updated_params:
            name = updated_params.get('name', job.args[0])
            args = updated_params.get('args', job.args[1:])
            self.context.scheduler.modify_job(job_id, args=[name] + args)

        if 'enabled' in updated_params:
            if updated_params['enabled']:
                self.context.scheduler.resume_job(job_id)
            else:
                self.context.scheduler.pause_job(job_id)

        if 'schedule' in updated_params:
            if 'coalesce' in updated_params['schedule']:
                self.context.scheduler.modify_job(
                    job_id,
                    coalesce=updated_params['schedule']['coalesce'])

            self.context.scheduler.reschedule_job(
                job_id,
                trigger='cron',
                **exclude(updated_params['schedule'], 'coalesce')
            )

    @private
    def run(self, job_id):
        self.context.logger.info('Running job {0} manualy'.format(job_id))
        job = self.context.scheduler.get_job(job_id)
        self.context.scheduler.add_job(
            id=job_id + '-temp',
            args=job.args,
            kwargs=job.kwargs,
        )


class Context(object):
    def __init__(self):
        self.logger = logging.getLogger('schedulerd')
        self.config = None
        self.datastore = None
        self.configstore = None
        self.client = None
        self.scheduler = None
        self.active_tasks = {}

    def init_datastore(self):
        try:
            self.datastore = get_datastore(self.config['datastore']['driver'], self.config['datastore']['dsn'])
        except DatastoreException as err:
            self.logger.error('Cannot initialize datastore: %s', str(err))
            sys.exit(1)

        self.configstore = ConfigStore(self.datastore)

    def init_dispatcher(self):
        def on_error(reason, **kwargs):
            if reason in (ClientError.CONNECTION_CLOSED, ClientError.LOGOUT):
                self.logger.warning('Connection to dispatcher lost')
                self.connect()

        self.client = Client()
        self.client.on_error(on_error)
        self.connect()

    def init_scheduler(self):
        store = MongoDBJobStore(database='freenas', collection='calendar_tasks', client=self.datastore.client)
        self.scheduler = BackgroundScheduler(jobstores={'default': store}, timezone=pytz.utc)
        self.scheduler.start()

    def register_schemas(self):
        self.client.register_schema('calendar-task', {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'id': {'type': 'string'},
                'name': {'type': 'string'},
                'args': {'type': 'array'},
                'description': {'type': 'string'},
                'enabled': {'type': 'boolean'},
                'hidden': {'type': 'boolean'},
                'status': {'$ref': 'calendar-task-status'},
                'schedule': {
                    'type': 'object',
                    'additionalProperties': False,
                    'properties': {
                        'coalesce': {'type': ['boolean', 'integer', 'null']},
                        'year': {'type': ['string', 'integer', 'null']},
                        'month': {'type': ['string', 'integer', 'null']},
                        'day': {'type': ['string', 'integer', 'null']},
                        'week': {'type': ['string', 'integer', 'null']},
                        'day_of_week': {'type': ['string', 'integer', 'null']},
                        'hour': {'type': ['string', 'integer', 'null']},
                        'minute': {'type': ['string', 'integer', 'null']},
                        'second': {'type': ['string', 'integer', 'null']}
                    }
                }
            }
        })

        self.client.register_schema('calendar-task-status', {
            'type': 'object',
            'properties': {
                'next_run_time': {'type': 'string'},
                'last_run_status': {'type': 'string'},
                'current_run_status': {'type': ['string', 'null']},
                'current_run_progress': {'type': ['object', 'null']}
            }
        })

    def connect(self):
        while True:
            try:
                self.client.connect('127.0.0.1')
                self.client.login_service('schedulerd')
                self.client.enable_server()
                self.client.register_service('scheduler.management', ManagementService(self))
                self.client.register_service('scheduler.debug', DebugService())
                self.client.resume_service('scheduler.management')
                self.client.resume_service('scheduler.debug')
                return
            except socket.error as err:
                self.logger.warning('Cannot connect to dispatcher: {0}, retrying in 1 second'.format(str(err)))
                time.sleep(1)

    def run_job(self, *args, **kwargs):
        tid = self.client.submit_task(*args)
        self.active_tasks[kwargs['id']] = tid
        self.client.call_sync('task.wait', tid, timeout=None)
        result = self.client.call_sync('task.status', tid)
        if result['state'] != 'FINISHED':
            try:
                self.client.call_sync('alerts.emit', {
                    'name': 'scheduler.task.failed',
                    'severity': 'CRITICAL',
                    'description': 'Task {0} has failed: {1}'.format(kwargs['name'], result['error']['message']),
                })
            except RpcException as e:
                self.logger.error('Failed to emit alert', exc_info=True)

        del self.active_tasks[kwargs['id']]
        self.datastore.insert('schedulerd.runs', {
            'job_id': kwargs['id'],
            'task_id': result['id']
        })

    def parse_config(self, filename):
        try:
            f = open(filename, 'r')
            self.config = json.load(f)
            f.close()
        except IOError as err:
            self.logger.error('Cannot read config file: %s', err.message)
            sys.exit(1)
        except ValueError:
            self.logger.error('Config file has unreadable format (not valid JSON)')
            sys.exit(1)

    def emit_event(self, name, params):
        self.client.emit_event(name, params)

    def main(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-c', metavar='CONFIG', default=DEFAULT_CONFIGFILE, help='Middleware config file')
        parser.add_argument('-f', action='store_true', default=False, help='Run in foreground')
        args = parser.parse_args()
        configure_logging('/var/log/schedulerd.log', 'DEBUG')
        setproctitle.setproctitle('schedulerd')
        self.parse_config(args.c)
        self.init_datastore()
        self.init_scheduler()
        self.init_dispatcher()
        self.register_schemas()
        self.client.wait_forever()


if __name__ == '__main__':
    global context

    c = Context()
    context = c
    c.main()

