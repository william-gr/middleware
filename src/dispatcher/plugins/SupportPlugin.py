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
import json
import logging
import requests
import simplejson
from task import Task, Provider, TaskException, ValidationException, VerifyException
from freenas.dispatcher.rpc import RpcException, accepts, description, returns
from freenas.dispatcher.rpc import SchemaHelper as h
#from lib.system import SubprocessException, system

logger = logging.getLogger('SupportPlugin')
ADDRESS = 'support-proxy.ixsystems.com'


@description("Provides access support")
class SupportProvider(Provider):

    @accepts(str, str)
    @returns(h.array(str))
    def categories(self, user, password):
        sw_name = self.dispatcher.call_sync('system.info.version').split('-')[0].lower()
        try:
            r = requests.post(
                'https://%s/%s/api/v1.0/categories' % (ADDRESS, sw_name),
                data=json.dumps({
                    'user': user,
                    'password': password,
                }),
                headers={'Content-Type': 'application/json'},
                timeout=10,
            )
            data = r.json()
        except simplejson.JSONDecodeError as e:
            logger.debug('Failed to decode ticket attachment response: %s', r.text)
            raise RpcException(errno.EINVAL, 'Failed to decode ticket response')
        except requests.ConnectionError as e:
            raise RpcException(errno.ENOTCONN, 'Connection failed: {0}'.format(str(e)))
        except requests.Timeout as e:
            raise RpcException(errno.ETIMEDOUT, 'Connection timed out: {0}'.format(str(e)))

        if 'error' in data:
            raise RpcException(errno.EINVAL, data['message'])

        return data


@description("Submits a new support ticket")
@accepts(h.ref('support-ticket'))
class SupportSubmitTask(Task):
    def describe(self, ticket):
        return 'Submitting ticket'

    def verify(self, ticket):
        return ['system']

    def run(self, ticket):
        try:
            version = self.dispatcher.call_sync('system.info.version')
            sw_name = version.split('-')[0].lower()
            data = {
                'title': ticket['subject'],
                'body': ticket['description'],
                'version': version.split('-', 1)[-1],
                'category': ticket['category'],
                'type': ticket['type'],
                'user': ticket['username'],
                'password': ticket['password'],
                'debug': ticket['debug'],
            }

            r = requests.post(
                'https://%s/%s/api/v1.0/ticket' % (ADDRESS, sw_name),
                data=json.dumps(data),
                headers={'Content-Type': 'application/json'},
                timeout=10,
            )
            data = r.json()
            if r.status_code != 200:
                logger.debug('Support Ticket failed (%d): %s', r.status_code, r.text)
                raise TaskException(errno.EINVAL, 'ticket failed (0}: {1}'.format(r.status_code, r.text))

            ticketid = data.get('ticketnum')

            for attachment in ticket.get('attachments', []):
                r = requests.post(
                    'https://%s/%s/api/v1.0/ticket/attachment' % (ADDRESS, sw_name),
                    data={
                        'user': ticket['username'],
                        'password': ticket['password'],
                        'ticketnum': ticketid,
                    },
                    timeout=10,
                    files={'file': open(attachment, 'rb')},
                )

        except simplejson.JSONDecodeError as e:
            logger.debug("Failed to decode ticket attachment response: %s", r.text)
            raise TaskException(errno.EINVAL, 'Failed to decode ticket response')
        except requests.ConnectionError as e:
            raise TaskException(errno.ENOTCONN, 'Connection failed: {0}'.format(str(e)))
        except requests.Timeout as e:
            raise TaskException(errno.ETIMEDOUT, 'Connection timed out: {0}'.format(str(e)))
        except RpcException as e:
            raise TaskException(errno.ENXIO, 'Cannot submit support ticket: {0}'.format(str(e)))

        return ticketid, data.get('message')


def _depends():
    return ['SystemInfoPlugin']


def _init(dispatcher, plugin):
    plugin.register_schema_definition('support-ticket', {
        'type': 'object',
        'properties': {
            'username': {'type': 'string'},
            'password': {'type': 'string'},
            'subject': {'type': 'string'},
            'description': {'type': 'string'},
            'category': {'type': 'string'},
            'type': {'type': 'string'},
            'debug': {'type': 'boolean'},
            'attachments': {'type': 'array', 'items': {'type': 'string'}},
        },
        'additionalProperties': False,
        'required': ['username', 'password', 'subject', 'description', 'category', 'type', 'debug']
    })

    # Register events
    plugin.register_event_type('support.changed')

    # Register provider
    plugin.register_provider('support', SupportProvider)

    # Register tasks
    plugin.register_task_handler('support.submit', SupportSubmitTask)
