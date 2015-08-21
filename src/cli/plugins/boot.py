# +
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


from namespace import EntityNamespace, Command, RpcBasedLoadMixin
from namespace import TaskBasedSaveMixin, Namespace, IndexCommand, description
from output import ValueType


@description("Boot Environment Namespace")
class BootEnvironmentNamespace(TaskBasedSaveMixin, RpcBasedLoadMixin,
                               EntityNamespace):
    def __init__(self, name, context):
        super(BootEnvironmentNamespace, self).__init__(name, context)
        self.create_task = 'boot.environments.create'
        self.delete_task = 'boot.environments.delete'
        self.query_call = 'boot.environments.query'
        self.primary_key_name = 'name'

        self.localdoc['CreateEntityCommand'] = ("""\
            Usage: create name=<bootenv name>

            Example: create name=foo

            Creates a boot environment""")

        self.entity_localdoc['SetEntityCommand'] = ("""\
            Usage: set name=<newname>

            Example: set name=foo

            Set the name of the current boot environment""")

        self.skeleton_entity = {
            'name': None,
            'realname': None
        }

        self.add_property(
            descr='Boot Environment ID',
            name='name',
            get='id',
            set='id',
            list=True
            )

        self.add_property(
            descr='Boot Environment Name',
            name='realname',
            get='realname',
            list=True
            )

        self.add_property(
            descr='Active',
            name='active',
            get='active',
            list=True,
            type=ValueType.BOOLEAN
            )

        self.add_property(
            descr='On Reboot',
            name='onreboot',
            get='on_reboot',
            list=True,
            type=ValueType.BOOLEAN
            )

        self.add_property(
            descr='Mount point',
            name='mountpoint',
            get='mountpoint',
            list=True
            )

        self.add_property(
            descr='Space used',
            name='space',
            get='space',
            list=True
            )

        self.add_property(
            descr='Date created',
            name='created',
            get='created',
            list=True
            )

        self.primary_key = self.get_mapping('name')

        self.entity_commands = lambda this: {
            'activate': ActivateBootEnvCommand(this),
        }

    def get_one(self, name):
        return self.context.connection.call_sync(
            self.query_call,
            [('id', '=', name)],
            {'single': True})

    def delete(self, name):
        self.context.submit_task('boot.environments.delete', [name])

    def save(self, this, new=False):
        if new:
            self.context.submit_task('boot.environments.create',
                                     this.entity['id'])
            return
        else:
            if this.entity['id'] != this.orig_entity['id']:
                self.context.submit_task('boot.environments.rename',
                                         this.orig_entity['id'],
                                         this.entity['id'],
                                         callback=lambda s:
                                         self.post_save(this, s))
            return

    def post_save(self, this, status):
        if status == 'FINISHED':
            this.modified = False
            this.saved = True


@description("Activates a boot environment")
class ActivateBootEnvCommand(Command):
    """
    Usage: activate

    Activates the current boot environment
    """
    def __init__(self, parent):
        self.parent = parent

    def run(self, context, args, kwargs, opargs):
        context.submit_task('boot.environments.activate',
                            self.parent.entity['id'])


@description("Boot pool namespace")
class BootPoolNamespace(Namespace):
    def __init__(self, name, context):
        super(BootPoolNamespace, self).__init__(name)

    def commands(self):
        return {
            '?': IndexCommand(self),
            'show-disks': BootPoolShowDisksCommand(),
            'attach-disk': BootPoolAttachDiskCommand(),
            'detach-disk': BootPoolDetachDiskCommand(),
        }


@description("Shows the disks in the boot pool")
class BootPoolShowDisksCommand(Command):
    """
    Usage: show-disks

    Shows the disks in the boot pool
    """
    def run(self, context, args, kwargs, opargs):
        # to be implemented
        return


@description("Attaches a disk to the boot pool")
class BootPoolAttachDiskCommand(Command):
    """
    Usage: attach-disk <disk>

    Example: attach-disk ada1

    Attaches a disk to the boot pool.
    """
    def run(self, context, args, kwargs, opargs):
        # to be implemented
        return


@description("Detaches a disk from the boot pool")
class BootPoolDetachDiskCommand(Command):
    """
    Usage: detach-disk <disk>

    Example: detach-disk ada1

    Detaches a disk from the boot pool.
    """
    def run(self, context, args, kwargs, opargs):
        # to be implemented
        return


@description("Boot namespace")
class BootNamespace(Namespace):
    def __init__(self, name, context):
        super(BootNamespace, self).__init__(name)
        self.context = context

    def commands(self):
        return {
            '?': IndexCommand(self)
        }

    def namespaces(self):
        return [
            BootPoolNamespace('pool', self.context),
            BootEnvironmentNamespace('env', self.context)
        ]

        
def _init(context):
    context.attach_namespace('/', BootNamespace('boot', context))