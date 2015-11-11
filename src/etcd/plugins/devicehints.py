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
import os
import re
from bsd import devinfo

DEVICE_HINTS = '/boot/device.hints'


def generate_device_hints(context, current, config):

    output = re.sub(r'.*uart.*flags="0x10"\n', '', current.strip('\n'))
    dinfo = devinfo.DevInfo()

    uart = None
    for name, ports in dinfo.resource_managers['I/O ports'].items():
        if not name.startswith('uart'):
            continue
        for port in ports:
            if config['serial_port'] == hex(port.start):
                uart = port
                break

    if uart is None:
        context.logger.warn('uart number not found for %s', config['serial_port'])
        return current
    unit = re.sub(r'[a-z]', '', uart.name)

    irq = dinfo.resource_managers['Interrupt request lines'].get(uart.name)
    if irq is None:
        context.logger.warn('irq not found for %s', config['serial_port'])
        return current
    irq = irq[0].start

    output = re.sub(r'hint\.uart\.%s.*\n' % unit, '', output)

    output += '''
hint.uart.{0}.at="isa"
hint.uart.{0}.port="{1}"
hint.uart.{0}.flags="0x10"
hint.uart.{0}.irq="{2}"
hint.uart.{0}.baud="{3}"
'''.format(unit, config['serial_port'], irq, config['serial_speed'])

    return output


def get_device_hints():

    if not os.path.exists(DEVICE_HINTS):
        return ''

    with open(DEVICE_HINTS, 'r') as f:
        return f.read()


def run(context):

    config = context.client.call_sync('system.advanced.get_config')
    if not config['serial_console']:
        return

    current = get_device_hints()
    generated = generate_device_hints(context, current, config)

    if current.strip('\n') == generated.strip('\n'):
        return

    with open(DEVICE_HINTS, 'w') as f:
        f.write(generated)

    context.emit_event('etcd.file_generated', {'filename': DEVICE_HINTS})
