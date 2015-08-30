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
from fnutils.query import wrap


DEFAULT_CONFIGFILE = '/usr/local/etc/middleware.conf'
context = None


def job(*args, **kwargs):
    result = wrap(context.client.call_task_sync(*args))
    if result['state'] != 'FINISHED':
        pass

    context.datastore.insert('calendar_task_runs', {
        'id': kwargs['id'],
        'task_id': result['id']
    })


class ManagementService(RpcService):
    def __init__(self, context):
        self.context = context

    @private
    def query(self, filter=None, params=None):
        def serialize(job):
            return job.__getstate__()

        return wrap(map(serialize, self.context.scheduler.get_jobs())).query(*(filter or []), **(params or {}))

    @private
    def add(self, task):
        task_id = str(uuid.uuid4())
        self.context.scheduler.add_job(
            job,
            trigger='cron',
            id=task_id,
            args=[task['name']] + task['args'],
            **task['schedule'])

    @private
    def delete(self, job_id):
        pass

    @private
    def update(self, job_id, job):
        pass


class Context(object):
    def __init__(self):
        self.logger = logging.getLogger('schedulerd')
        self.config = None
        self.datastore = None
        self.configstore = None
        self.client = None
        self.scheduler = None

    def init_datastore(self):
        try:
            self.datastore = get_datastore(self.config['datastore']['driver'], self.config['datastore']['dsn'])
        except DatastoreException, err:
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
            'id': {'type': 'string'},
            'name': {'type': 'string'},
            'args': {'type': 'array'},
            'status': {'$ref': 'calendar-task-status'},
            'schedule': {
                'coalesce': {'type': ['boolean', 'null']},
                'year': {'type': ['string', 'null']},
                'month': {'type': ['string', 'null']},
                'day': {'type': ['string', 'null']},
                'week': {'type': ['string', 'null']},
                'day_of_week': {'type': ['string', 'null']},
                'hour': {'type': ['string', 'null']},
                'minute': {'type': ['string', 'null']},
                'second': {'type': ['string', 'null']}
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
                self.client.resume_service('scheduler.management')
                return
            except socket.error, err:
                self.logger.warning('Cannot connect to dispatcher: {0}, retrying in 1 second'.format(str(err)))
                time.sleep(1)

    def parse_config(self, filename):
        try:
            f = open(filename, 'r')
            self.config = json.load(f)
            f.close()
        except IOError, err:
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
        logging.basicConfig(level=logging.DEBUG)
        setproctitle.setproctitle('schedulerd')
        self.parse_config(args.c)
        self.init_datastore()
        self.init_scheduler()
        self.init_dispatcher()
        self.client.wait_forever()


if __name__ == '__main__':
    global context

    c = Context()
    context = c
    c.main()

