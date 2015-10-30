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

from dispatcher.rpc import (
    accepts,
    description,
    returns,
    SchemaHelper as h
)

from task import (
    Provider,
    Task,
    query
)

logger = logging.getLogger('DirectoryServicePlugin')

class DirectoryServicesProvider(Provider):
    @query('directoryservice')
    def query(self, filter=None, params=None):
        def extend(directoryservice):
            return directoryservice
        return self.datastore.query('directoryservices', *(filter or []), 
            callback=extend, **(params or {}))


@description("Create directory service")
@accepts(h.all_of(
    h.ref('directoryservice'),
    #h.required(),
    #h.forbidden('id')
))
class CreateDirectoryServiceTask(Task):
    def verify(self, *args):
        logger.debug("XXX: CreateDirectoryServiceTask.verify(): args = %s", args)
        return ['system']

    def run(self, *args):
        logger.debug("XXX: CreateDirectoryServiceTask.run(): args = %s", args)


@description("Update directory service")
class UpdateDirectoryServiceTask(Task):
    pass


@description("Delete directory service")
class DeleteDirectoryServiceTask(Task):
    pass


def _init(dispatcher, plugin):
    plugin.register_schema_definition('directoryservice',  {
        'type': 'object',
        'properties': {
            'id': { 'type': 'string' },
            'name': { 'type': 'string' },
            'description': { 'type': 'string' },
            'type': { 'type': 'string' }

            # Other shit goes here...
        }
    })

    dispatcher.require_collection('directoryservices')

    plugin.register_provider('directoryservices', DirectoryServicesProvider)

    plugin.register_task_handler('directoryservice.create', CreateDirectoryServiceTask)
    plugin.register_task_handler('directoryservice.update', UpdateDirectoryServiceTask)
    plugin.register_task_handler('directoryservice.delete', DeleteDirectoryServiceTask)
