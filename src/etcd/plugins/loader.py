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
import sys
import subprocess

if '/usr/local/www' not in sys.path:
    sys.path.append('/usr/local/www')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freenasUI.settings')
if 'DJANGO_LOGGING_DISABLE' not in os.environ:
    os.environ['DJANGO_LOGGING_DISABLE'] = 'true'

# Make sure to load all modules
from django.db.models.loading import cache
cache.get_apps()

from freenasUI.system.models import Advanced

LOADER_CONF = '/boot/loader.conf.local'
FIRST_INSTALL_SENTINEL = '/data/first-boot'


def generate_loader_conf(context):

    output = []
    advanced = Advanced.objects.order_by('-id')[0]
    if advanced.adv_serialconsole:
        output.extend([
            'comconsole_port="{0}"'.format(advanced.adv_serialport),
            'comconsole_speed="{0}"'.format(advanced.adv_serialspeed),
            'boot_multicons="YES"',
            'console="comconsole,vidconsole"',
        ])
    if advanced.adv_debugkernel:
        output.extend([
            'kernel="kernel-debug"',
            'module_path="/boot/kernel-debug;/boot/modules;/usr/local/modules"',
        ])
    else:
        output.extend([
            'kernel="kernel"',
            'module_path="/boot/kernel;/boot/modules;/usr/local/modules"',
        ])

    for tun in context.client.call_sync('tunables.query', [('type', '=', 'LOADER')]):
        if tun.get('enabled') is False:
            continue
        output.append('{0}="{1}"'.format(tun['var'], tun['value']))

    return '\n'.join(output)


def get_current_loader_conf():

    if not os.path.exists(LOADER_CONF):
        return ''

    with open(LOADER_CONF, 'r') as f:
        return f.read().strip('\n')


def run(context):

    current = get_current_loader_conf()
    generated = generate_loader_conf(context)

    grub = False
    if current != generated:
        # FIXME: changes to loader.conf requires a reboot, post an alert about it
        grub = True
        with open(LOADER_CONF, 'w') as f:
            f.write(generated)
            f.write('\n')

    # This is just to make sure we don't run grub-mkconfig twice
    # We should create a seperate firstinstall plugin if we add more things later.
    if os.path.exists(FIRST_INSTALL_SENTINEL):
        grub = True
        try:
            os.unlink(FIRST_INSTALL_SENTINEL)
        except:
            pass
        # Creating pristine boot environment from the "default"
        context.logger.info('Creating "Initial-Install" boot environment...')
        context.client.call_task_sync('boot.environments.create', 'Initial-Install', 'default')

    if grub:
        proc = subprocess.Popen(
            ['/usr/local/sbin/grub-mkconfig', '-o', '/boot/grub/grub.cfg'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={
                'PATH': '/sbin:/bin:/usr/sbin:/usr/bin:/usr/local/sbin:/usr/local/bin',
            })
        out, err = proc.communicate()
        context.logger.info('grub-mkconfig ran, return code %d', proc.returncode)
        if proc.returncode != 0:
            context.logger.warn('grub-mkconfig stdout: %s', out)
            context.logger.warn('grub-mkconfig stderr: %s', err)
