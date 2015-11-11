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
import logging
from task import Task, Provider
from dispatcher.rpc import RpcException, description, accepts, private
from dispatcher.rpc import SchemaHelper as h


logger = logging.getLogger(__name__)


@description("Provides info about configured WebDAV shares")
class WebDAVSharesProvider(Provider):
    @private
    @accepts(str)
    def get_connected_clients(self, share_id=None):
        # FIXME
        result = []
        return result


@description("Adds new WebDAV share")
@accepts(h.ref('webdav-share'))
class CreateWebDAVShareTask(Task):
    def describe(self, share):
        return "Creating WebDAV share {0}".format(share['name'])

    def verify(self, share):
        return ['service:webdav']

    def run(self, share):
        id = self.datastore.insert('shares', share)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'webdav')
        self.dispatcher.call_sync('services.reload', 'webdav')
        self.dispatcher.dispatch_event('shares.webdav.changed', {
            'operation': 'create',
            'ids': [id]
        })

        return id


@description("Updates existing WebDAV share")
@accepts(str, h.ref('webdav-share'))
class UpdateWebDAVShareTask(Task):
    def describe(self, name, updated_fields):
        return "Updating WebDAV share {0}".format(name)

    def verify(self, name, updated_fields):
        return ['service:webdav']

    def run(self, name, updated_fields):
        share = self.datastore.get_by_id('shares', name)
        share.update(updated_fields)
        self.datastore.update('shares', name, share)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'webdav')
        self.dispatcher.call_sync('services.reload', 'webdav')
        self.dispatcher.dispatch_event('shares.webdav.changed', {
            'operation': 'update',
            'ids': [name]
        })


@description("Removes WebDAV share")
@accepts(str)
class DeleteWebDAVShareTask(Task):
    def describe(self, name):
        return "Deleting WebDAV share {0}".format(name)

    def verify(self, name):
        return ['service:webdav']

    def run(self, name):
        share = self.datastore.get_by_id('shares', name)
        self.datastore.delete('shares', name)
        self.dispatcher.call_sync('etcd.generation.generate_group', 'webdav')
        self.dispatcher.call_sync('services.reload', 'webdav')
        self.dispatcher.dispatch_event('shares.webdav.changed', {
            'operation': 'delete',
            'ids': [name]
        })


def _metadata():
    return {
        'type': 'sharing',
        'subtype': 'file',
        'perm_type': 'PERMS',
        'method': 'webdav'
    }


def _depends():
    return ['ZfsPlugin', 'SharingPlugin']


def _init(dispatcher, plugin):
    plugin.register_schema_definition('webdav-share-properties', {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'read_only': {'type': 'boolean'},
            'permission': {'type': 'boolean'},
        }
    })

    plugin.register_task_handler("share.webdav.create", CreateWebDAVShareTask)
    plugin.register_task_handler("share.webdav.update", UpdateWebDAVShareTask)
    plugin.register_task_handler("share.webdav.delete", DeleteWebDAVShareTask)
    plugin.register_provider("shares.webdav", WebDAVSharesProvider)
    plugin.register_event_type('shares.webdav.changed')
