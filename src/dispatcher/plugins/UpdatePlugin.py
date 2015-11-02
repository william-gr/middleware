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

import errno
import gevent
import hashlib
import logging
import os
import signal
import sys
import random
import re
import tempfile
from resources import Resource
from cache import CacheStore
from dispatcher.rpc import RpcException, description, accepts, returns, private, SchemaHelper as h
from gevent import subprocess
from task import Provider, Task, ProgressTask, TaskException, VerifyException

if '/usr/local/lib' not in sys.path:
    sys.path.append('/usr/local/lib')
from freenasOS import Configuration, Train
from freenasOS.Exceptions import (
    UpdateManifestNotFound, ManifestInvalidSignature, UpdateBootEnvironmentException,
    UpdatePackageException,
)
from freenasOS.Update import CheckForUpdates, DownloadUpdate, ApplyUpdate

logger = logging.getLogger('UpdatePlugin')
update_cache = CacheStore()
update_resource_string = 'update:operations'


def parse_changelog(changelog, start='', end=''):
    "Utility function to parse an available changelog"
    regexp = r'### START (\S+)(.+?)### END \1'
    reg = re.findall(regexp, changelog, re.S | re.M)

    if not reg:
        return None

    changelog = None
    for seq, changes in reg:
        if not changes.strip('\n'):
            continue
        if seq == start:
            # Once we found the right one, we start accumulating
            changelog = []
        elif changelog is not None:
            changelog.append(changes.strip('\n'))
        if seq == end:
            break
    try:
        changelog = changelog[0].split('\n')
    except:
        changelog = ['']
    return changelog


def get_changelog(train, cache_dir='/var/tmp/update', start='', end=''):
    "Utility to get and eventually parse a changelog if available"
    conf = Configuration.Configuration()
    changelog = conf.GetChangeLog(train=train, save_dir=cache_dir)
    if not changelog:
        return None

    return parse_changelog(changelog.read(), start, end)


# The handler(s) below is/are taken from the freenas 9.3 code
# specifically from gui/system/utils.py
class CheckUpdateHandler(object):
    "A handler for the CheckUpdate call"

    def __init__(self):
        self.changes = []

    def call(self, op, newpkg, oldpkg):
        self.changes.append({
            'operation': op,
            'old': oldpkg,
            'new': newpkg,
        })

    def output(self):
        output = []
        for c in self.changes:
            opdict = {
                'operation': c['operation'],
                'previous_name': c['old'].Name() if c['old'] else None,
                'previous_version': c['old'].Version() if c['old'] else None,
                'new_name': c['new'].Name() if c['new'] else None,
                'new_version': c['new'].Version() if c['new'] else None,
            }
            output.append(opdict)
        return output


def check_updates(dispatcher, configstore, cache_dir=None, check_now=False):
    "Utility function to just check for Updates"
    update_cache_invalidate_list = [
        'updateAvailable', 'updateNotes', 'updateNotice',
        'updateOperations', 'changelog', 'downloaded'
        ]
    dispatcher.call_sync('update.update_cache_invalidate', update_cache_invalidate_list)

    conf = Configuration.Configuration()
    update_ops = None
    handler = CheckUpdateHandler()
    train = configstore.get('update.train')
    notes = None
    notice = None
    downloaded = False

    try:
        update = CheckForUpdates(
            handler=handler.call,
            train=train,
            cache_dir=None if check_now else cache_dir,
        )
    except Exception:
        update_cache_put_value_dict = {
            'updateAvailable': False,
            'updateNotes': None,
            'updateNotice': None,
            'updateOperations': update_ops,
            'changelog': '',
            'downloaded': downloaded,
        }
        dispatcher.call_sync('update.update_cache_putter', update_cache_put_value_dict)
        raise

    if update:
        logger.debug("An update is available")
        update_ops = handler.output()
        sys_mani = conf.SystemManifest()
        if sys_mani:
            sequence = sys_mani.Sequence()
        else:
            sequence = ''
        try:
            changelog = get_changelog(
                train, cache_dir=cache_dir, start=sequence, end=update.Sequence())
        except Exception:
            changelog = ''
        notes = update.Notes()
        notice = update.Notice()
        downloaded = False if check_now else True
    else:
        logger.debug("No update available")
        changelog = None

    update_cache_put_value_dict = {
            'updateAvailable': True if update else False,
            'updateNotes': notes,
            'updateNotice': notice,
            'updateOperations': update_ops,
            'changelog': changelog,
            'downloaded': downloaded,
        }
    dispatcher.call_sync('update.update_cache_putter', update_cache_put_value_dict)


class UpdateHandler(object):
    "A handler for Downloading and Applying Updates calls"

    def __init__(self, dispatcher, update_progress=None):
        self.progress = 0
        self.details = ''
        self.finished = False
        self.error = False
        self.indeterminate = False
        self.reboot = False
        self.pkgname = ''
        self.pkgversion = ''
        self.operation = ''
        self.filesize = 0
        self.numfilestotal = 0
        self.numfilesdone = 0
        self._baseprogress = 0
        self.master_progress = 0
        self.dispatcher = dispatcher
        # Below is the function handle passed to this by the Task so that
        # its status and progress can be updated accordingly
        self.update_progress = update_progress

    def check_handler(self, index, pkg, pkgList):
        self.pkgname = pkg.Name()
        self.pkgversion = pkg.Version()
        self.operation = 'Downloading'
        self.details = 'Downloading {0}'.format(self.pkgname)
        stepprogress = int((1.0 / float(len(pkgList))) * 100)
        self._baseprogress = index * stepprogress
        self.progress = (index - 1) * stepprogress
        # self.emit_update_details()

    def get_handler(self, method, filename, size=None, progress=None, download_rate=None):
        if progress is not None:
            self.progress = (progress * self._baseprogress) / 100
            if self.progress == 0:
                self.progress = 1
            display_size = ' Size: {0}'.format(size) if size else ''
            display_rate = ' Rate: {0} B/s'.format(download_rate) if download_rate else ''
            self.details = 'Downloading: {0} Progress:{1}{2}{3}'.format(
                self.pkgname, progress, display_size, display_rate
                )
        self.emit_update_details()

    def install_handler(self, index, name, packages):
        self.indeterminate = False
        total = len(packages)
        self.numfilesdone = index
        self.numfilesdone = total
        self.progress = int((float(index) / float(total)) * 100.0)
        self.operation = 'Installing'
        self.details = 'Installing {0}'.format(name)
        self.emit_update_details()

    def emit_update_details(self):
        # Doing the drill below as there is a small window when
        # step*progress logic does not catch up with the new value of step
        if self.progress >= self.master_progress:
            self.master_progress = self.progress
        data = {
            'indeterminate': self.indeterminate,
            'percent': self.master_progress,
            'reboot': self.reboot,
            'pkg_name': self.pkgname,
            'pkg_version': self.pkgversion,
            'filesize': self.filesize,
            'num_files_one': self.numfilesdone,
            'num_files_total': self.numfilestotal,
            'error': self.error,
            'finished': self.finished,
            'details': self.details,
        }
        if self.update_progress is not None:
            self.update_progress(self.master_progress, self.details)
        self.dispatcher.dispatch_event('update.in_progress', {
            'operation': self.operation,
            'data': data,
        })


def generate_update_cache(dispatcher, cache_dir=None):
    if cache_dir is None:
        try:
            cache_dir = dispatcher.call_sync('system_dataset.request_directory', 'update')
        except RpcException:
            cache_dir = '/var/tmp/update'
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)
    update_cache.put('cache_dir', cache_dir)
    try:
        check_updates(dispatcher, dispatcher.configstore, cache_dir=cache_dir)
    except Exception as e:
        # What to do now?
        logger.debug('generate_update_cache (UpdatePlugin) falied because of: %s', e)


@description("Provides System Updater Configuration")
class UpdateProvider(Provider):

    @accepts()
    @returns(str)
    def is_update_available(self):
        temp_updateAvailable = update_cache.get('updateAvailable', timeout=1)
        if temp_updateAvailable is not None:
            return temp_updateAvailable
        elif update_cache.is_valid('updateAvailable'):
            return temp_updateAvailable
        else:
            raise RpcException(errno.EBUSY, (
                'Update Availability flag is invalidated, an Update Check'
                ' might be underway. Try again in some time.'
            ))

    @accepts()
    @returns(h.array(str))
    def obtain_changelog(self):
        temp_changelog = update_cache.get('changelog', timeout=1)
        if temp_changelog is not None:
            return temp_changelog
        elif update_cache.is_valid('changelog'):
            return temp_changelog
        else:
            raise RpcException(errno.EBUSY, (
                'Changelog list is invalidated, an Update Check '
                'might be underway. Try again in some time.'
            ))

    @accepts()
    @returns(h.array(h.ref('update-ops')))
    def get_update_ops(self):
        temp_updateOperations = update_cache.get('updateOperations', timeout=1)
        if temp_updateOperations is not None:
            return temp_updateOperations
        elif update_cache.is_valid('updateOperations'):
            return temp_updateOperations
        else:
            raise RpcException(errno.EBUSY, (
                'Update Operations Dict is invalidated, an Update Check '
                'might be underway. Try again in some time.'
            ))

    @accepts()
    @returns(h.any_of(
        h.ref('update-info'),
        None,
    ))
    def update_info(self):
        if not update_cache.is_valid('updateAvailable'):
            raise RpcException(errno.EBUSY, (
                'Update Availability flag is invalidated, an Update Check'
                ' might be underway. Try again in some time.'
            ))
        updateAvailable = update_cache.get('updateAvailable', timeout=1)
        if not updateAvailable:
            return None
        updateOperations = update_cache.get('updateOperations', timeout=1)
        updateNotes = update_cache.get('updateNotes', timeout=1)
        updateNotice = update_cache.get('updateNotice', timeout=1)
        changelog = update_cache.get('changelog', timeout=1)
        downloaded = update_cache.get('downloaded', timeout=1)
        return {
            'changelog': changelog,
            'notes': updateNotes,
            'notice': updateNotice,
            'operations': updateOperations,
            'downloaded': downloaded,
        }

    @returns(h.any_of(
        h.array(h.ref('update-train')),
        None,
    ))
    def trains(self):
        conf = Configuration.Configuration()
        conf.LoadTrainsConfig()
        trains = conf.AvailableTrains()

        if trains is None:
            logger.debug('The AvailableTrains call returned None. Check your network connection')
            return None
        seltrain = self.dispatcher.configstore.get('update.train')

        data = []
        for name in trains.keys():
            if name in conf._trains:
                train = conf._trains.get(name)
            else:
                train = Train.Train(name)
            data.append({
                'name': train.Name(),
                'description': train.Description(),
                'sequence': train.LastSequence(),
                'current': True if name == seltrain else False,
            })
        return data

    @accepts()
    @returns(str)
    def get_current_train(self):
        conf = Configuration.Configuration()
        conf.LoadTrainsConfig()
        return conf.CurrentTrain()

    @accepts()
    @returns(h.ref('update'))
    def get_config(self):
        return {
            'train': self.dispatcher.configstore.get('update.train'),
            'check_auto': self.dispatcher.configstore.get('update.check_auto'),
            'update_server': Configuration.Configuration().UpdateServerURL(),
        }

    @private
    @accepts(h.array(str))
    @returns()
    def update_cache_invalidate(self, value_list):
        for item in value_list:
            update_cache.invalidate(item)

    @private
    @accepts(h.object())
    @returns()
    def update_cache_putter(self, value_dict):
        for key, value in value_dict.iteritems():
            update_cache.put(key, value)

    @private
    @accepts(str)
    @returns(h.any_of(None, str, bool, h.array(str)))
    def update_cache_getter(self, key):
        return update_cache.get(key, timeout=1)


@description("Set the System Updater Cofiguration Settings")
@accepts(h.ref('update'))
class UpdateConfigureTask(Task):

    def describe(self):
        return "System Updater Configure Settings"

    def verify(self, props):
        # TODO: Fix this verify's resource allocation as unique task
        block = self.dispatcher.resource_graph.get_resource(update_resource_string)
        if block is not None and block.busy:
            raise VerifyException(
                errno.EBUSY,
                'An Update Operation (Configuration/ Download/ Applying ' +
                'the Updates) is already in the queue, please retry later')

        return [update_resource_string]

    def run(self, props):

        if 'train' in props:
            train_to_set = props.get('train')
            conf = Configuration.Configuration()
            conf.LoadTrainsConfig()
            trains = conf.AvailableTrains() or []
            if trains:
                trains = trains.keys()
            if train_to_set not in trains:
                raise TaskException(errno.ENOENT, '{0} is not a valid train'.format(train_to_set))
            self.configstore.set('update.train', train_to_set)
        if 'check_auto' in props:
            self.configstore.set('update.check_auto', props.get('check_auto'))
        self.dispatcher.dispatch_event('update.changed', {
            'operation': 'update',
        })


@description((
    "Checks for Available Updates and returns if update is availabe "
    "and if yes returns information on operations that will be "
    "performed during the update"
))
@accepts(h.object(properties={
            'check_now': bool,
            }))
class CheckUpdateTask(Task):
    def describe(self):
        return "Checks for Updates and Reports Operations to be performed"

    def verify(self, conditions={}):
        # TODO: Fix this verify's resource allocation as unique task
        block = self.dispatcher.resource_graph.get_resource(update_resource_string)
        if block is not None and block.busy:
            raise VerifyException(errno.EBUSY, (
                'An Update Operation (Configuration/ Download/ Applying'
                'the Updates) is already in the queue, please retry later'
            ))

        return [update_resource_string]

    def run(self, conditions={}):
        check_now = conditions.get('check_now', True)
        cache_dir = self.dispatcher.call_sync('update.update_cache_getter', 'cache_dir')
        try:
            check_updates(
                self.dispatcher, self.configstore,
                cache_dir=cache_dir, check_now=check_now,
            )
        except UpdateManifestNotFound:
            raise TaskException(errno.ENETUNREACH, 'Update server could not be reached')
        except Exception as e:
            raise TaskException(errno.EAGAIN, '{0}'.format(str(e)))


@description("Downloads Updates for the current system update train")
@accepts()
class DownloadUpdateTask(ProgressTask):
    def describe(self):
        return "Downloads the Updates and caches them to apply when needed"

    def verify(self):
        if not update_cache.get('updateAvailable', timeout=1):
            raise VerifyException(errno.ENOENT, (
                'No updates currently available for download, try running '
                'the `update.check` task'
            ))

        block = self.dispatcher.resource_graph.get_resource(update_resource_string)
        if block is not None and block.busy:
            raise VerifyException(errno.EBUSY, (
                'An Update Operation (Configuration/ Download/ Applying'
                'the Updates) is already in the queue, please retry later'
            ))

        return [update_resource_string]

    def update_progress(self, progress, message):
        if message:
            self.message = message
        self.set_progress(progress)

    def run(self):
        self.message = 'Downloading Updates...'
        self.set_progress(0)
        handler = UpdateHandler(self.dispatcher, update_progress=self.update_progress)
        train = self.configstore.get('update.train')
        cache_dir = self.dispatcher.call_sync('update.update_cache_getter', 'cache_dir')
        if cache_dir is None:
            try:
                cache_dir = self.dispatcher.call_sync(
                    'system_dataset.request_directory', 'update'
                )
            except RpcException:
                cache_dir = '/var/tmp/update'
        try:
            download_successful = DownloadUpdate(
                train, cache_dir, get_handler=handler.get_handler,
                check_handler=handler.check_handler,
            )
        except Exception as e:
            raise TaskException(
                errno.EAGAIN, 'Got exception {0} while trying to Download Updates'.format(str(e))
            )
        if not download_successful:
            handler.error = True
            handler.emit_update_details()
            raise TaskException(
                errno.EAGAIN, 'Downloading Updates Failed for some reason, check logs'
            )
        check_updates(self.dispatcher, self.configstore, cache_dir=cache_dir, check_now=False)
        handler.finished = True
        handler.emit_update_details()
        self.message = "Updates Finished Downloading"
        self.set_progress(100)


@description("Apply a manual update file")
@accepts(str, str)
class UpdateManualTask(ProgressTask):
    def describe(self):
        return "Manual update from a file"

    def verify(self, path, sha256):

        if not os.path.exists(path):
            raise VerifyException(errno.EEXIST, 'File does not exist')

        return ['root']

    def run(self, path, sha256):
        self.message = 'Applying update...'
        self.set_progress(0)

        filehash = hashlib.sha256()
        with open(path, 'rb') as f:
            while True:
                read = f.read(65536)
                if not read:
                    break
                filehash.update(read)

        if filehash.hexdigest() != sha256:
            raise TaskException(errno.EINVAL, 'SHA 256 hash does not match file')

        os.chdir(os.path.dirname(path))

        size = os.stat(path).st_size
        temperr = tempfile.NamedTemporaryFile()

        proc = subprocess.Popen(
            ["/usr/bin/tar", "-xSJpf", path],
            stdout=subprocess.PIPE,
            stderr=temperr,
            close_fds=False)
        RE_TAR = re.compile(r"^In: (\d+)", re.M | re.S)
        while True:
            if proc.poll() is not None:
                break
            try:
                os.kill(proc.pid, signal.SIGINFO)
            except:
                break
            gevent.sleep(1)
            with open(temperr.name, 'r') as f:
                line = f.read()
            reg = RE_TAR.findall(line)
            if reg:
                current = float(reg[-1])
                percent = ((current / size) * 100)
                self.set_progress(percent / 3)
        temperr.close()
        proc.communicate()
        if proc.returncode != 0:
            raise TaskException(errno.EINVAL, 'Image is invalid, make sure to use .txz file')

        try:
            subprocess.check_output(
                ['bin/install_worker.sh', 'pre-install'], stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as cpe:
            raise TaskException(errno.EINVAL, (
                'The firmware does not meet the pre-install criteria: {0}'.format(cpe.output)))

        try:
            subprocess.check_output(
                ['bin/install_worker.sh', 'install'], stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as cpe:
            raise TaskException(errno.EFAULT, 'The update failed: {0}'.format(cpe.output))

        # FIXME: New world order
        open('/data/need-update').close()

        self.set_progress(100)


@accepts(bool)
@description("Applies cached updates")
class UpdateApplyTask(ProgressTask):
    def describe(self):
        return "Applies cached updates to the system and reboots if necessary"

    def verify(self, reboot_post_install=False):
        return ['root']

    def update_progress(self, progress, message):
        if message:
            self.message = message
        self.set_progress(progress)

    def run(self, reboot_post_install=False):
        self.message = 'Applying Updates...'
        self.set_progress(0)
        handler = UpdateHandler(self.dispatcher, update_progress=self.update_progress)
        cache_dir = self.dispatcher.call_sync('update.update_cache_getter', 'cache_dir')
        if cache_dir is None:
            try:
                cache_dir = self.dispatcher.call_sync(
                    'system_dataset.request_directory', 'update'
                )
            except RpcException:
                cache_dir = '/var/tmp/update'
        # Note: for now we force reboots always, TODO: Fix in M3-M4
        try:
            result = ApplyUpdate(
                cache_dir, install_handler=handler.install_handler, force_reboot=True
                )
        except ManifestInvalidSignature as e:
            logger.debug('UpdateApplyTask Error: Cached manifest has invalid signature: %s', e)
            raise TaskException(errno.EINVAL, 'Cached manifest has invalid signature: {0}'.format(str(e)))
        except UpdateBootEnvironmentException as e:
            logger.debug('UpdateApplyTask Boot Environment Error: {0}'.format(str(e)))
            raise TaskException(errno.EAGAIN, str(e))
        except UpdatePackageException as e:
            logger.debug('UpdateApplyTask Package Error: {0}'.format(str(e)))
            raise TaskException(errno.EAGAIN, str(e))
        except Exception as e:
            raise TaskException(
                errno.EAGAIN, 'Got exception {0} while trying to Apply Updates'.format(str(e))
            )
        if result is None:
            raise TaskException(errno.ENOENT, 'No downloaded Updates available to apply.')
        handler.finished = True
        handler.emit_update_details()
        self.message = "Updates Finished Installing Successfully"
        if reboot_post_install:
            self.message = "Scheduling user specified reboot post succesfull update"
            # Note not using subtasks on purpose as they do not have queuing logic
            self.dispatcher.submit_task('system.reboot')
        self.set_progress(100)


@description("Verify installation integrity")
@accepts()
class UpdateVerifyTask(ProgressTask):
    def describe(self):
        return "Verify installation integrity"

    def verify(self):
        return [update_resource_string]

    def verify_handler(self, index, total, fname):
        self.message = 'Verifying {0}'.format(fname)
        self.set_progress(int((float(index) / float(total)) * 100.0))

    def run(self):
        try:
            error_flag, ed, warn_flag, wl = Configuration.do_verify(self.verify_handler)
        except Exception as e:
            raise TaskException(
                errno.EAGAIN, 'Got exception while verifying install: {0}'.format(str(e))
            )
        return {
            'checksum': ed['checksum'],
            'notfound': ed['notfound'],
            'wrongtype': ed['wrongtype'],
            'perm': wl,
            'error': error_flag,
            'warn': warn_flag,
        }


@description("Checks for updates from the update server and downloads them if available")
@accepts(h.any_of(
    bool,
    None,
))
@returns(bool)
class CheckFectchUpdateTask(ProgressTask):
    def describe(self):
        return "Checks for updates from the update server and downloads them if available. " +\
               "Returns Ture if updates were found and applied else False"

    def verify(self, mail=False):
        block = self.dispatcher.resource_graph.get_resource(update_resource_string)
        if block is not None and block.busy:
            raise VerifyException(errno.EBUSY, (
                'An Update Operation (Configuration/ Download/ Applying'
                'the Updates) is already in the queue, please retry later'
            ))

        return []

    def run(self, mail=False):
        self.set_progress(0, 'Checking for new updates from update server...')
        self.join_subtasks(self.run_subtask('update.check'))
        if self.dispatcher.call_sync('update.is_update_available'):
            self.set_progress(20, 'New updates found. Downloading them now...')
            self.join_subtasks(self.run_subtask('update.download'))

            if mail:
                changelog = self.dispatcher.call_sync('update.obtain_changelog')
                train = self.dispatcher.call_sync('update.get_config').get('train')

                self.dispatcher.call_sync('mail.send', {
                    'subject': 'Update Available',
                    'message': 'A new update is available for the {0} train.\n\nChangelog:\n{1}'.format(
                        train,
                        '\n'.join(changelog),
                    ),
                })

            self.set_progress(100, 'Updates successfully Downloaded')

            return True
        return False


def _depends():
    return ['CalendarTasksPlugin', 'MailPlugin', 'SystemDatasetPlugin']


def _init(dispatcher, plugin):

    def nightly_update_check(args):
        if args.get('name') != 'schedulerd':
            return

        logger.debug('Scheduling a nightly update check task')
        caltask = dispatcher.call_sync(
            'calendar_tasks.query', [('name', '=', 'update.checkfetch')], {'single': True}
        ) or {'schedule': {}}

        caltask.update({
            'name': 'update.checkfetch',
            'args': [True],
            'hidden': True,
            'description': 'Nightly update check',
        })
        caltask['schedule'].update({
            'hour': str(random.randint(1, 6)),
            'minute': str(random.randint(0, 59)),
        })

        if caltask.get('id'):
            dispatcher.call_task_sync('calendar_tasks.update', caltask['id'], caltask)
        else:
            dispatcher.call_task_sync('calendar_tasks.create', caltask)

    # Register Schemas
    plugin.register_schema_definition('update', {
        'type': 'object',
        'properties': {
            'train': {'type': 'string'},
            'check_auto': {'type': 'boolean'},
            'update_server': {'type': 'string', 'readOnly': True},
        },
    })

    plugin.register_schema_definition('update-progress', h.object(properties={
        'operation': h.enum(str, ['DOWNLOADING', 'INSTALLING']),
        'details': str,
        'indeterminate': bool,
        'percent': int,
        'reboot': bool,
        'pkg_name': str,
        'pkg_version': str,
        'filesize': int,
        'num_files_done': int,
        'num_files_total': int,
        'error': bool,
        'finished': bool,
    }))

    plugin.register_schema_definition('update-ops', {
        'type': 'object',
        'properties': {
            'operation': {
                'type': 'string',
                'enum': ['delete', 'install', 'upgrade']
            },
            'new_name': {'type': ['string', 'null']},
            'new_version': {'type': ['string', 'null']},
            'previous_name': {'type': ['string', 'null']},
            'previous_version': {'type': ['string', 'null']},
        }
    })

    plugin.register_schema_definition('update-info', {
        'type': 'object',
        'properties': {
            'notes': {'type': 'object'},
            'notice': {'type': 'string'},
            'changelog': {
                'type': 'array',
                'items': {'type': 'string'},
            },
            'operations': {'$ref': 'update-ops'},
            'downloaded': {'type': 'boolean'},
        }
    })

    plugin.register_schema_definition('update-train', {
        'type': 'object',
        'properties': {
            'name': {'type': 'string'},
            'description': {'type': 'string'},
            'sequence': {'type': 'string'},
            'current': {'type': 'boolean'},
        }
    })

    # Register providers
    plugin.register_provider("update", UpdateProvider)

    # Register task handlers
    plugin.register_task_handler("update.configure", UpdateConfigureTask)
    plugin.register_task_handler("update.check", CheckUpdateTask)
    plugin.register_task_handler("update.download", DownloadUpdateTask)
    plugin.register_task_handler("update.manual", UpdateManualTask)
    plugin.register_task_handler("update.update", UpdateApplyTask)
    plugin.register_task_handler("update.verify", UpdateVerifyTask)
    plugin.register_task_handler("update.checkfetch", CheckFectchUpdateTask)

    # Register Event Types
    plugin.register_event_type('update.in_progress', schema=h.ref('update-progress'))
    plugin.register_event_type('update.changed')

    # Register reources
    plugin.register_resource(Resource(update_resource_string), ['system'])

    # Get the Update Cache (if any) at system boot (and hence in init here)
    generate_update_cache(dispatcher)

    # Schedule a task to check/dowload for updates
    plugin.register_event_handler('server.service_login', nightly_update_check)
