#!/usr/bin/env python2
# Copyright (c) 2015 iXsystems, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
from freenas.dispatcher.client import Client
from logging import config
import logging
import os
import sys

logger = logging.getLogger('custom-upssched-cmd')


def main(name, *args):
    connection = Client()
    connection.connect('127.0.0.1')
    connection.login_service('ups')

    connection.emit_event('service.ups.signal', {
        'name': name,
        'type': os.environ['NOTIFYTYPE'],
    })

    connection.disconnect()


if __name__ == '__main__':
    config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '%(levelname)s %(module)s(%(process)d): %(message)s'
            },
        },
        'handlers': {
            'stdout': {
                'class': 'logging.StreamHandler',
                'stream': sys.stdout,
                'formatter': 'verbose',
            },
            'syslog': {
                'class': 'logging.handlers.SysLogHandler',
                'address': '/var/run/log',
                'formatter': 'verbose',
            },
        },
        'loggers': {
            '': {
                'handlers': ['syslog', 'stdout'],
                'level': logging.DEBUG,
                'propagate': True,
            },
        }
    })

    main(*sys.argv[1:])
