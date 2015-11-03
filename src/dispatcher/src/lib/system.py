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

import logging
from gevent import subprocess

logger = logging.getLogger('system')


class SubprocessException(Exception):
    def __init__(self, code, out, err):
        self.returncode = code
        self.out = out
        self.err = err


def system(*args, **kwargs):
    sh = kwargs["shell"] if "shell" in kwargs else False
    stdin = kwargs.pop('stdin', None)
    proc = subprocess.Popen(args, stderr=subprocess.PIPE, shell=sh,
                            stdout=subprocess.PIPE, close_fds=True,
                            stdin=subprocess.PIPE if stdin else None)
    out, err = proc.communicate(input=stdin)

    logger.debug("Running command: %s", ' '.join(args))

    if proc.returncode != 0:
        logger.warning("Command %s failed, return code %d, stderr output: %s",
                       ' '.join(args), proc.returncode, err)
        raise SubprocessException(proc.returncode, out, err)

    return out.decode('utf8'), err.decode('utf8')


# Only use this for running background processes
# for which you do not want subprocess to wait on
# for the output or error (warning: no error handling)
def system_bg(*args, **kwargs):
    sh = False
    to_log = False
    sh = kwargs["shell"] if "shell" in kwargs else False
    to_log = kwargs["to_log"] if "to_log" in kwargs else True
    subprocess.Popen(args, stderr=subprocess.PIPE, shell=sh,
                     stdout=subprocess.PIPE, close_fds=True)
    if to_log:
        logger.debug("Started command (in background) : %s", ' '.join(args))
