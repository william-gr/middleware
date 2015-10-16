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

from __future__ import print_function
import os
import sys
import json
import io
import datetime
import tempfile
import subprocess
import setproctitle


def main():
    if len(sys.argv) < 2:
        print("Usage: crash-wrapper <path to executable> [args...]", file=sys.stderr)
        exit(1)

    setproctitle.setproctitle('crash-wrapper')
    name = os.path.basename(sys.argv[1])
    null = open('/dev/null', 'r')
    log = open('/var/tmp/{0}.{1}.log'.format(name, os.getpid()), 'a+')
    proc = subprocess.Popen(sys.argv[1:], stdin=null, stdout=log, stderr=subprocess.STDOUT, close_fds=True)
    proc.wait()

    if proc.returncode != 0:
        # Prepare error report
        log.seek(0, io.SEEK_SET)
        report = {
            'application': name,
            'type': 'error',
            'timestamp': str(datetime.datetime.now()),
            'message': log.read()
        }

        try:
            with tempfile.NamedTemporaryFile(dir='/var/tmp/crash', suffix='.json', prefix='report-', delete=False) as f:
                json.dump(report, f, indent=4)
        except:
            # at least we tried
            pass

    null.close()
    log.close()
    return proc.returncode


if __name__ == '__main__':
    main()
