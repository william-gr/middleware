#!/usr/local/bin/python2.7
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
import sys
import json
import enum
import logging
import datetime
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from bsd import sysctl


REPORTS_PATH = '/var/tmp/crash'
API_ENDPOINT_PATH = 'https://ext-data.ixsystems.com/wormhole/api/v1/errors/add/index.php'
logger = logging.getLogger('crashd')


class ReportType(enum.IntEnum):
    EXCEPTION = 1
    ERROR = 2


class Handler(FileSystemEventHandler):
    def __init__(self, context):
        self.context = context

    def on_created(self, event):
        name, ext = os.path.splitext(os.path.basename(event.src_path))

        try:
            with open(event.src_path) as f:
                data = f.read()
        except:
            return

        if ext == '.json':
            try:
                jdata = json.loads(data)
                jdata['type'] = getattr(ReportType, jdata['type'].upper())
            except ValueError:
                logger.warning('Cannot decode JSON from {0}'.format(event.src_path))
                os.unlink(event.src_path)
                return

        elif ext == '.log':
            jdata = {
                'timestamp': datetime.datetime.now(),
                'type': int(ReportType.ERROR)
            }

        else:
            logger.warning('Unknown file type: {0}, removing {1}'.format(ext, event.src_path))
            os.unlink(event.src_path)
            return

        jdata['uuid'] = self.context.hostuuid
        jdata['format'] = 'json'

        try:
            requests.post(API_ENDPOINT_PATH, json=jdata)
        except:
            pass


class Main(object):
    def __init__(self):
        self.observer = None
        self.hostuuid = sysctl.sysctlbyname('kern.hostuuid')

    def main(self):
        self.observer = Observer()
        self.observer.schedule(Handler(self), path=REPORTS_PATH, recursive=False)
        self.observer.join()


if __name__ == '__main__':
    m = Main()
    m.main()
