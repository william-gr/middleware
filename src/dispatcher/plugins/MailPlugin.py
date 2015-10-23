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
import base64
import errno
import logging
import os
import smtplib
import socket
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.Utils import formatdate

from datastore.config import ConfigNode
from dispatcher.rpc import (
    RpcException, SchemaHelper as h, accepts, description, returns
)
from task import Provider, Task, TaskException

logger = logging.getLogger('MailPlugin')


@description("Provides Information about the mail configuration")
class MailProvider(Provider):

    @returns(h.ref('mail'))
    def get_config(self):
        return ConfigNode('mail', self.configstore)

    @accepts(h.ref('mail-message'), h.ref('mail'))
    def send(self, mailmessage, mail=None):

        if mail is None:
            mail = ConfigNode('mail', self.configstore).__getstate__()
        if not mail.get('server') or not mail.get('port'):
            raise RpcException(
                errno.EINVAL,
                'You must provide an outgoing server and port when sending mail',
            )

        to = mailmessage.get('to')
        attachments = mailmessage.get('attachments')
        subject = mailmessage.get('subject')
        extra_headers = mailmessage.get('extra_headers')

        if not to:
            to = self.dispatcher.call_sync(
                'users.query', [('username', '=', 'root')], {'single': True})
            if to and to.get('email'):
                to = [to['email']]

        if attachments:
            msg = MIMEMultipart()
            msg.preamble = mailmessage['message']
            map(lambda attachment: msg.attach(attachment), attachments)
        else:
            msg = MIMEText(mailmessage['message'], _charset='utf-8')
        if subject:
            msg['Subject'] = subject

        msg['From'] = mailmessage['from'] if mailmessage.get('from') else mail['from']
        msg['To'] = ', '.join(to)
        msg['Date'] = formatdate()

        local_hostname = socket.gethostname()
        version = self.dispatcher.call_sync('system.info.version').split('-')[0].lower()

        msg['Message-ID'] = "<{0}-{1}.{2}@{3}>".format(
            version,
            datetime.utcnow().strftime("%Y%m%d.%H%M%S.%f"),
            base64.urlsafe_b64encode(os.urandom(3)),
            local_hostname)

        if not extra_headers:
            extra_headers = {}
        for key, val in extra_headers.items():
            if key in msg:
                msg.replace_header(key, val)
            else:
                msg[key] = val
        msg = msg.as_string()

        try:
            if mail['encryption'] == 'SSL':
                klass = smtplib.SMTP_SSL
            else:
                klass = smtplib.SMTP
            server = klass(mail['server'], mail['port'], timeout=300, local_hostname=local_hostname)
            if mail['encryption'] == 'TLS':
                server.starttls()

            if mail['auth']:
                server.login(mail['user'], mail['pass'])
            server.sendmail(mail['from'], to, msg)
            server.quit()
        except smtplib.SMTPAuthenticationError as e:
            raise RpcException(errno.EACCES, 'Authentication error: {0} {1}'.format(
                e.smtp_code, e.smtp_error))
        except Exception as e:
            logger.error('Failed to send email: {0}'.format(str(e)), exc_info=True)
            raise RpcException(errno.EFAULT, 'Email send error: {0}'.format(str(e)))
        except:
            raise RpcException(errno.EFAULT, 'Unexpected error')


@accepts(h.ref('mail'))
class MailConfigureTask(Task):

    def verify(self, mail):
        return []

    def run(self, mail):
        node = ConfigNode('mail', self.configstore)
        node.update(mail)


def _init(dispatcher, plugin):

    plugin.register_schema_definition('mail', {
        'type': 'object',
        'properties': {
            'from': {'type': 'string'},
            'server': {'type': 'string'},
            'port': {'type': 'integer'},
            'auth': {'type': 'boolean'},
            'encryption': {
                'type': 'string',
                'enum': ['PLAIN', 'TLS', 'SSL'],
            },
            'user': {'type': ['string', 'null']},
            'pass': {'type': ['string', 'null']},
        },
        'additionalProperties': False,
    })

    plugin.register_schema_definition('mail-message', {
        'type': 'object',
        'properties': {
            'from': {'type': 'string'},
            'to': {
                'type': 'array',
                'items': {'type': 'string'},
            },
            'subject': {'type': 'string'},
            'message': {'type': 'string'},
            'attachments': {
                'type': 'array',
                'items': {'type': 'string'},
            },
            'extra_headers': {'type': 'object'},
        },
        'additionalProperties': False,
    })

    # Register providers
    plugin.register_provider('mail', MailProvider)

    # Register task handlers
    plugin.register_task_handler('mail.configure', MailConfigureTask)
