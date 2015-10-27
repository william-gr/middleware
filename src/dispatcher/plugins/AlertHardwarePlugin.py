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
from collections import defaultdict
import logging

from bsd import sysctl

logger = logging.getLogger('AlertHardwarePlugin')


def _depends():
    return ['AlertPlugin']


def _init(dispatcher, plugin):

    def avago_firmware(driver):

        devs = defaultdict(dict)
        try:
            sysctls = list(sysctl.filter('{0}.mps'.format(driver)))
        except OSError:
            return

        for k, v in sysctls:
            mibs = k.split('.', 3)
            if len(mibs) < 4:
                continue

            number, mib = mibs[2:4]

            try:
                major = int(v.split('.', 1)[0])
                devs[number][mib] = major
            except:
                continue

        for number, mibs in list(devs.items()):
            firmware_ver = mibs.get('firmware_version')
            driver_ver = mibs.get('driver_version')
            if int(firmware_ver) != int(driver_ver):
                dispatcher.rpc.call_sync('alerts.emit', {
                    'name': 'hardware.controller.firmware_mismatch',
                    'description': 'Firmware version {0} does not match driver version {1} for {2}'.format(
                        firmware_ver,
                        driver_ver,
                        driver,
                    ),
                    'severity': 'WARNING',
                })

    dispatcher.rpc.call_sync(
        'alerts.register_alert', 'hardware.controller.firmware_mismatch', 'Controller Firmware Version Mismatch'
    )

    avago_firmware('mps')
    avago_firmware('mpr')
