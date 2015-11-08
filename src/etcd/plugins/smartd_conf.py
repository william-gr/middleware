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

from pySMART import Device


def run(context):
    SMARTD_CONF = []
    smartd_config = context.client.call_sync('service.smartd.get_config')
    smartd_common_line = "-n {0} -W {1},{2},{3} -m root\n".format(
        smartd_config['power_mode'].lower(),
        0 if smartd_config['temp_difference'] is None else smartd_config['temp_difference'],
        0 if smartd_config['temp_informational'] is None else smartd_config['temp_informational'],
        0 if smartd_config['temp_critical'] is None else smartd_config['temp_critical']
    )
    # Get all SMART capable disk's info
    all_disks_info = context.client.call_sync(
        'disks.query',
        [('status.smart_capable', '=', True)]
    )
    for single_disk in all_disks_info:
        device_smart_handle = Device(single_disk['path'])
        # Check if the disk's smart enabled value is the same as that in the database
        # if not try to DTRT it
        if single_disk['smart'] != device_smart_handle.smart_enabled:
            # toggle_result is a tuple containing:
            # (Action succeded: True/False, Error message if first is False)
            toggle_result = device_smart_handle.smart_toggle(
                'on' if single_disk['smart'] else 'off'
            )
            if not toggle_result[0]:
                # Log this failure in etcd's log and continue
                # Cause we might be able to configure atleast for the other disks
                context.logger.error(
                    "smartd_conf.py: {0} -> Tried to toggle disk's ".format(single_disk['path']) +
                    " SMART enabled to: {0} and failed with error: {1}".format(
                        single_disk['smart'],
                        toggle_result[1]
                    )
                )
                continue

        if single_disk['smart']:
            smartd_line = "{0} -a {1}".format(
                single_disk['path'],
                smartd_common_line
            )

            SMARTD_CONF.append(smartd_line)
    with open("/usr/local/etc/smartd.conf", "w+") as f:
        for line in SMARTD_CONF:
            f.write(line)
    context.emit_event('etcd.file_generated', {'filename': "/usr/local/etc/smartd.conf"})
