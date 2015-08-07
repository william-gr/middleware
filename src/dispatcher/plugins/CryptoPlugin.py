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

import errno
from dispatcher.rpc import RpcException, description, accepts, returns
from dispatcher.rpc import SchemaHelper as h
from task import Provider, Task, TaskException, VerifyException, query

from OpenSSL import crypto


def generate_key(key_length):
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, key_length)
    return k


def create_certificate(cert_info):
    cert = crypto.X509()
    cert.get_subject().C = cert_info['country']
    cert.get_subject().ST = cert_info['state']
    cert.get_subject().L = cert_info['city']
    cert.get_subject().O = cert_info['organization']
    cert.get_subject().CN = cert_info['common']
    cert.get_subject().emailAddress = cert_info['email']

    serial = cert_info.get('serial')
    if serial is not None:
        cert.set_serial_number(serial)

    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(cert_info['lifetime'] * (60 * 60 * 24))

    cert.set_issuer(cert.get_subject())
    return cert


@description("Provider for certificates")
class CertificateProvider(Provider):
    @query('crypto-certificate')
    def query(self, filter=None, params=None):
        return self.datastore.query('crypto.certificates', *(filter or []), **(params or {}))


@accepts(h.all_of(
    h.ref('crypto-certificate'),
    h.required('name', 'country', 'state', 'city', 'organization', 'email', 'common'),
))
class CAInternalCreateTask(Task):
    def verify(self, certificate):

        if self.datastore.exists('crypto.certificates', ('name', '=', certificate['name'])):
            raise VerifyException(errno.EEXIST, 'Certificate with given name already exists')

        return ['system']

    def run(self, certificate):

        certificate['key_length'] = certificate.get('key_length', 2048)
        certificate['digest_algorithm'] = certificate.get('digest_algorithm', 'SHA256')
        certificate['lifetime'] = certificate.get('lifetime', 3650)

        key = generate_key(certificate['key_length'])
        cert = create_certificate(certificate)
        cert.set_pubkey(key)
        cert.add_extensions([
            crypto.X509Extension("basicConstraints", True, "CA:TRUE, pathlen:0"),
            crypto.X509Extension("keyUsage", True, "keyCertSign, cRLSign"),
            crypto.X509Extension("subjectKeyIdentifier", False, "hash", subject=cert),
        ])
        cert.set_serial_number(1)
        cert.sign(key, certificate['digest_algorithm'])

        certificate['type'] = 'CA_INTERNAL'
        certificate['certificate'] = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)
        certificate['privatekey'] = crypto.dump_privatekey(crypto.FILETYPE_PEM, key)
        certificate['serial'] = 1

        self.datastore.insert('crypto.certificates', certificate)
        try:
            pass
            #self.dispatcher.call_sync('etcd.generation.generate_group', 'crypto')
        except RpcException, e:
            raise TaskException(errno.ENXIO, 'Cannot generate certificate: {0}'.format(str(e)))


def _init(dispatcher, plugin):
    plugin.register_schema_definition('crypto-certificate', {
        'type': 'object',
        'properties': {
            'type': {'type': 'string', 'enum': [
                'CA_EXISTING',
                'CA_INTERMEDIATE',
                'CA_INTERNAL',
                'CERT_EXISTING',
                'CERT_INTERMEDIATE',
                'CERT_INTERNAL',
            ]},
            'name': {'type': 'string'},
            'certificate': {'type': 'string'},
            'privatekey': {'type': 'string'},
            'csr': {'type': 'string'},
            'key_length': {'type': 'integer'},
            'digest_algorithm': {'type': 'string', 'enum': [
                'SHA1',
                'SHA224',
                'SHA256',
                'SHA384',
                'SHA512',
            ]},
            'lifetime': {'type': 'integer'},
            'country': {'type': 'string'},
            'state': {'type': 'string'},
            'city': {'type': 'string'},
            'organization': {'type': 'string'},
            'email': {'type': 'string'},
            'common': {'type': 'string'},
            'serial': {'type': 'integer'},
            'signedby': {'type': 'string'},
        },
        'additionalProperties': False,
    })

    dispatcher.require_collection('crypto.certificates')

    plugin.register_provider('crypto.certificates', CertificateProvider)

    plugin.register_task_handler('crypto.certificates.ca_internal_create', CAInternalCreateTask)
