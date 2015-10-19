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

import json


def convert_rpm(rpm):
    if rpm == 'UNKNOWN':
        return '0'

    if rpm == 'SSD':
        return '1'

    return str(rpm)


def redact(config):
    for i in config['auth-group']:
        i['secret'] = 'REDACTED'
        i['peer-secret'] = 'REDACTED'


def generate_luns(context):
    result = {}

    for share in context.datastore.query('shares', ('type', '=', 'iscsi')):
        props = share['properties']
        extent = {
            'path': share['target'],
            'blocksize': props['block_size'],
            'serial': props['serial'],
            'options': {
                'device-id': 'iSCSI Disk {0}'.format(props['serial']),
                'vendor': 'FreeNAS',
                'product': 'iSCSI Disk',
                'revision': '0123',
                'naa': props['naa'],
                'rpm': convert_rpm(props['rpm'])
            }
        }

        if props.get('vendor_id'):
            extent['options']['vendor'] = props['vendor_id']

        if props.get('device_id'):
            extent['options']['device-id'] = props['device_id']

        if props.get('size'):
            extent['size'] = props['size']

        if props.get('tpc'):
            extent['options']['insescure_tpc'] = 'on'

        result[share['id']] = extent

    return result


def generate_targets(context):
    result = {}

    for i in context.datastore.query('iscsi.targets'):
        target = {
            'lun': i['extents']
        }

        if i.get('description'):
            target['alias'] = i['description']

        result[i['id']] = target

    return result


def generate_auth_groups(context):
    result = {}

    def generate_chap_user(user):
        return {
            'user': user['name'],
            'secret': user['secret']
        }

    for i in context.datastore.query('iscsi.auth'):
        group = {}

        # Check if group is in use
        if not context.datastore.exists('iscsi.targets', ('auth_group', '=', i['id'])):
            continue

        if i.get('users'):
            group['chap'] = map(generate_chap_user, i['users'])
            group['chap-mutual'] = map(generate_chap_user, i['users'])

        if i.get('initiators'):
            group['initiator-name'] = i['initiators']

        if i.get('networks'):
            group['initiator-portal'] = i['networks']

        result[i['id']] = group

    return result


def generate_portal_groups(context):
    result = {}

    if not context.configstore.get('service.iscsi.enable'):
        return result

    for i in context.datastore.query('iscsi.portals'):
        portal = {
            'listen': map(lambda l: '{0}:{1}'.format(l['address'], l['port']), i['listen']),
        }

        if i.get('discovery_auth_group'):
            portal['discovery-auth-group'] = i['discovery_auth_group']

        if i.get('discovery_auth_method'):
            portal['discovery-auth-method'] = i['discovery_auth_method']

        result[i['id']] = portal

    return result


def run(context):
    config = {
        'lun': generate_luns(context),
        'target': generate_targets(context),
        'auth-group': generate_auth_groups(context),
        'portal-group': generate_portal_groups(context)
    }

    with open('/etc/ctl.conf', 'w') as f:
        json.dump(config, f, indent=4)

    with open('/etc/ctl.conf.shadow', 'w') as f:
        json.dump(redact(config), f, indent=4)

    context.emit_event('etcd.file_generated', {
        'name': '/etc/ctl.conf'
    })
