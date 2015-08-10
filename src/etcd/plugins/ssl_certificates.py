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


def run(context):

    for cert in context.client.call_sync('crypto.certificates.query'):

        if cert['type'].startswith('CA_'):
            cert_root_path = '/etc/certificates/CA'
        else:
            cert_root_path = '/etc/certificates'

        if not os.path.exists(cert_root_path):
            os.makedirs(cert_root_path, 0755)

        certificate = cert.get('certificate')
        if certificate:
            certificate_path = os.path.join(cert_root_path, '{0}.crt'.format(cert['name']))
            with open(certificate_path, 'w') as f:
                f.write(certificate)

            context.emit_event('etcd.file_generated', {
                'filename': certificate_path
            })

        privatekey = cert.get('privatekey')
        if privatekey:
            privatekey_path = os.path.join(cert_root_path, '{0}.key'.format(cert['name']))
            with open(privatekey_path, 'w') as f:
                f.write(privatekey)

            context.emit_event('etcd.file_generated', {
                'filename': privatekey_path
            })

        csr = cert.get('csr')
        if csr and csr['type'] == 'CERT_CSR':
            csr_path = os.path.join(cert_root_path, '{0}.csr'.format(cert['name']))
            with open(csr_path, 'w') as f:
                f.write(csr)

            context.emit_event('etcd.file_generated', {
                'filename': csr_path
            })
