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

from bsd import sysctl
from lib.system import system, SubprocessException


def get_sysctl(name):
    return sysctl.sysctlbyname(name)


def fstyp(device):
    try:
        out, _ = system('/usr/sbin/fstyp', '-l', device)
        ret = out.strip().split()
        if len(ret) == 1:
            return ret[0], None

        return ret
    except SubprocessException:
        return None, None


def sockstat(only_connected=False, ports=None):
    args = ['/usr/bin/sockstat', '-46']

    if only_connected:
        args.append('-c')

    if ports:
        args.append('-p')
        args.append(','.join([str(p) for p in ports]))

    out, _ = system(*args)
    for line in out.strip().splitlines()[1:]:
        items = line.split()
        yield {
            'user': items[0],
            'command': items[1],
            'pid': items[2],
            'proto': items[4],
            'local': items[5],
            'remote': items[6]
        }
