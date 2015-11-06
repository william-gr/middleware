#!/usr/local/bin/python
#
# Copyright (c) 2010-2011 iXsystems, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
#

""" Helper for FreeNAS to execute command line tools

This helper class abstracts operating system operations like starting,
stopping, restarting services out from the normal Django stuff and makes
future extensions/changes to the command system easier.  When used as a
command line utility, this helper class can also be used to do these
actions.
"""

from collections import defaultdict
from bsd import sysctl
import base64
from Crypto.Cipher import AES
import ctypes
import logging
import os
import re
import signal
import sqlite3
from subprocess import Popen, PIPE
import sys
import threading
import time

WWW_PATH = "/usr/local/www"
FREENAS_PATH = os.path.join(WWW_PATH, "freenasUI")
NEED_UPDATE_SENTINEL = '/data/need-update'
VERSION_FILE = '/etc/version'
GELI_KEYPATH = '/data/geli'
GELI_KEY_SLOT = 0
GELI_RECOVERY_SLOT = 1
SYSTEMPATH = '/var/db/system'
PWENC_BLOCK_SIZE = 32
PWENC_PADDING = b'{'
PWENC_CHECK = 'Donuts!'
BACKUP_SOCK = '/var/run/backupd.sock'

sys.path.append(WWW_PATH)
sys.path.append(FREENAS_PATH)

os.environ["DJANGO_SETTINGS_MODULE"] = "freenasUI.settings"

# Make sure to load all modules
from django.db.models.loading import cache
cache.get_apps()

RE_DSKNAME = re.compile(r'^([a-z]+)([0-9]+)$')
log = logging.getLogger('middleware.notifier')


class StartNotify(threading.Thread):

    def __init__(self, pidfile, verb, *args, **kwargs):
        self._pidfile = pidfile
        self._verb = verb
        super(StartNotify, self).__init__(*args, **kwargs)

    def run(self):
        """
        If we are using start or restart we expect that a .pid file will
        exists at the end of the process, so we wait for said pid file to
        be created and check if its contents are non-zero.
        Otherwise we will be stopping and expect the .pid to be deleted,
        so wait for it to be removed
        """
        if not self._pidfile:
            return None

        tries = 1
        while tries < 6:
            time.sleep(1)
            if self._verb in ('start', 'restart'):
                if os.path.exists(self._pidfile):
                    # The file might have been created but it may take a
                    # little bit for the daemon to write the PID
                    time.sleep(0.1)
                if (os.path.exists(self._pidfile)
                    and os.stat(self._pidfile).st_size > 0):
                    break
            elif self._verb == "stop" and not os.path.exists(self._pidfile):
                break
            tries += 1


class notifier:

    from os import system as __system
    from pwd import getpwnam as ___getpwnam
    from grp import getgrnam as ___getgrnam
    IDENTIFIER = 'notifier'

    def is_freenas(self):
        return True

    def _system(self, command):
        log.debug("Executing: %s", command)
        # TODO: python's signal class should be taught about sigprocmask(2)
        # This is hacky hack to work around this issue.
        libc = ctypes.cdll.LoadLibrary("libc.so.7")
        omask = (ctypes.c_uint32 * 4)(0, 0, 0, 0)
        mask = (ctypes.c_uint32 * 4)(0, 0, 0, 0)
        pmask = ctypes.pointer(mask)
        pomask = ctypes.pointer(omask)
        libc.sigprocmask(signal.SIGQUIT, pmask, pomask)
        try:
            ret = self.__system("(" + command + ") 2>&1 | logger -p daemon.notice -t %s"
                                % (self.IDENTIFIER, ))
        finally:
            libc.sigprocmask(signal.SIGQUIT, pomask, None)
        log.debug("Executed: %s -> %s", command, ret)
        return ret

    def _system_nolog(self, command):
        log.debug("Executing: %s", command)
        # TODO: python's signal class should be taught about sigprocmask(2)
        # This is hacky hack to work around this issue.
        libc = ctypes.cdll.LoadLibrary("libc.so.7")
        omask = (ctypes.c_uint32 * 4)(0, 0, 0, 0)
        mask = (ctypes.c_uint32 * 4)(0, 0, 0, 0)
        pmask = ctypes.pointer(mask)
        pomask = ctypes.pointer(omask)
        libc.sigprocmask(signal.SIGQUIT, pmask, pomask)
        try:
            retval = self.__system("(" + command + ") >/dev/null 2>&1")
        finally:
            libc.sigprocmask(signal.SIGQUIT, pomask, None)
        retval >>= 8
        log.debug("Executed: %s; returned %d", command, retval)
        return retval

    def _pipeopen(self, command, logger=log):
        if logger:
            logger.debug("Popen()ing: %s", command)
        return Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True, close_fds=False)

    def _pipeerr(self, command, good_status=0):
        proc = self._pipeopen(command)
        err = proc.communicate()[1]
        if proc.returncode != good_status:
            log.debug("%s -> %s (%s)", command, proc.returncode, err)
            return err
        log.debug("%s -> %s", command, proc.returncode)
        return None

    def _do_nada(self):
        pass

    def _simplecmd(self, action, what):
        log.debug("Calling: %s(%s) ", action, what)
        f = getattr(self, '_' + action + '_' + what, None)
        if f is None:
            # Provide generic start/stop/restart verbs for rc.d scripts
            if what in self.__service2daemon:
                procname, pidfile = self.__service2daemon[what]
                if procname:
                    what = procname
            if action in ("start", "stop", "restart", "reload"):
                if action == 'restart':
                    self._system("/usr/sbin/service " + what + " forcestop ")
                self._system("/usr/sbin/service " + what + " " + action)
                f = self._do_nada
            else:
                raise ValueError("Internal error: Unknown command")
        f()

    __service2daemon = {
        'ctld': ('ctld', '/var/run/ctld.pid'),
        'webshell': (None, '/var/run/webshell.pid'),
        'backup': (None, '/var/run/backup.pid')
    }

    def _started_notify(self, verb, what):
        """
        The check for started [or not] processes is currently done in 2 steps
        This is the first step which involves a thread StartNotify that watch for event
        before actually start/stop rc.d scripts

        Returns:
            StartNotify object if the service is known or None otherwise
        """

        # FIXME: Ugly workaround for one service and multiple backend
        if what == 'iscsitarget':
            what = 'ctld'

        if what in self.__service2daemon:
            procname, pidfile = self.__service2daemon[what]
            sn = StartNotify(verb=verb, pidfile=pidfile)
            sn.start()
            return sn
        else:
            return None

    def _started(self, what, notify=None):
        """
        This is the second step::
        Wait for the StartNotify thread to finish and then check for the
        status of pidfile/procname using pgrep

        Returns:
            True whether the service is alive, False otherwise
        """

        # FIXME: Ugly workaround for one service and multiple backend
        if what == 'iscsitarget':
            what = 'ctld'

        if what in self.__service2daemon:
            procname, pidfile = self.__service2daemon[what]
            if notify:
                notify.join()

            if pidfile:
                procname = " " + procname if procname else ""
                retval = self._pipeopen("/bin/pgrep -F %s%s" % (pidfile, procname)).wait()
            else:
                retval = self._pipeopen("/bin/pgrep %s" % (procname,)).wait()

            if retval == 0:
                return True
            else:
                return False
        else:
            return False

    def destroy(self, what, objectid=None):
        if objectid is None:
            raise ValueError("Calling destroy without id")
        else:
            f = getattr(self, '_destroy_' + what)
            f(objectid)

    def start(self, what):
        """ Start the service specified by "what".

        The helper will use method self._start_[what]() to start the service.
        If the method does not exist, it would fallback using service(8)."""
        sn = self._started_notify("start", what)
        self._simplecmd("start", what)
        return self.started(what, sn)

    def started(self, what, sn=None):
        """ Test if service specified by "what" has been started. """
        f = getattr(self, '_started_' + what, None)
        if callable(f):
            return f()
        else:
            return self._started(what, sn)

    def stop(self, what):
        """ Stop the service specified by "what".

        The helper will use method self._stop_[what]() to stop the service.
        If the method does not exist, it would fallback using service(8)."""
        sn = self._started_notify("stop", what)
        self._simplecmd("stop", what)
        return self.started(what, sn)

    def restart(self, what):
        """ Restart the service specified by "what".

        The helper will use method self._restart_[what]() to restart the service.
        If the method does not exist, it would fallback using service(8)."""
        sn = self._started_notify("restart", what)
        self._simplecmd("restart", what)
        return self.started(what, sn)

    def reload(self, what):
        """ Reload the service specified by "what".

        The helper will use method self._reload_[what]() to reload the service.
        If the method does not exist, the helper will try self.restart of the
        service instead."""
        try:
            self._simplecmd("reload", what)
        except:
            self.restart(what)
        return self.started(what)

    def change(self, what):
        """ Notify the service specified by "what" about a change.

        The helper will use method self.reload(what) to reload the service.
        If the method does not exist, the helper will try self.start the
        service instead."""
        try:
            self.reload(what)
        except:
            self.start(what)

    def _open_db(self, ret_conn=False):
        """Open and return a cursor object for database access."""
        try:
            from freenasUI.settings import DATABASES
            dbname = DATABASES['default']['NAME']
        except:
            dbname = '/data/freenas-v1.db'

        conn = sqlite3.connect(dbname)
        c = conn.cursor()
        if ret_conn:
            return c, conn
        return c

    def get_disks(self):
        """
        Grab usable disks and pertinent info about them
        This accounts for:
            - all the disks the OS found
                (except the ones that are providers for multipath)
            - multipath geoms providers

        Returns:
            Dict of disks
        """
        disksd = {}

        disks = self.__get_disks()

        """
        Replace devnames by its multipath equivalent
        """
        for mp in self.multipath_all():
            for dev in mp.devices:
                if dev in disks:
                    disks.remove(dev)
            disks.append(mp.devname)

        for disk in disks:
            info = self._pipeopen('/usr/sbin/diskinfo %s' % disk).communicate()[0].split('\t')
            if len(info) > 3:
                disksd.update({
                    disk: {
                        'devname': info[0],
                        'capacity': info[2],
                    },
                })

        for mp in self.multipath_all():
            for consumer in mp.consumers:
                if consumer.lunid and mp.devname in disksd:
                    disksd[mp.devname]['ident'] = consumer.lunid
                    break

        return disksd

    def __init__(self):
        self.__confxml = None
        self.__camcontrol = None
        self.__diskserial = {}
        self.__twcli = {}

    def __del__(self):
        self.__confxml = None

    def _geom_confxml(self):
        from lxml import etree
        if self.__confxml is None:
            self.__confxml = etree.fromstring(self.sysctl('kern.geom.confxml'))
        return self.__confxml

    def get_label_consumer(self, geom, name):
        """
        Get the label consumer of a given ``geom`` with name ``name``

        Returns:
            The provider xmlnode if found, None otherwise
        """
        doc = self._geom_confxml()
        xpath = doc.xpath("//class[name = 'LABEL']//provider[name = '%s']/../consumer/provider/@ref" % "%s/%s" % (geom, name))
        if not xpath:
            return None
        providerid = xpath[0]
        provider = doc.xpath("//provider[@id = '%s']" % providerid)[0]

        class_name = provider.xpath("../../name")[0].text

        # We've got a GPT over the softraid, not raw UFS filesystem
        # So we need to recurse one more time
        if class_name == 'PART':
            providerid = provider.xpath("../consumer/provider/@ref")[0]
            newprovider = doc.xpath("//provider[@id = '%s']" % providerid)[0]
            class_name = newprovider.xpath("../../name")[0].text
            # if this PART is really backed up by softraid the hypothesis was correct
            if class_name in ('STRIPE', 'MIRROR', 'RAID3'):
                return newprovider

        return provider

    def get_disks_from_provider(self, provider):
        disks = []
        geomname = provider.xpath("../../name")[0].text
        if geomname in ('DISK', 'PART'):
            disks.append(provider.xpath("../name")[0].text)
        elif geomname in ('STRIPE', 'MIRROR', 'RAID3'):
            doc = self._geom_confxml()
            for prov in provider.xpath("../consumer/provider/@ref"):
                prov2 = doc.xpath("//provider[@id = '%s']" % prov)[0]
                disks.append(prov2.xpath("../name")[0].text)
        else:
            # TODO log, could not get disks
            pass
        return disks

    def _find_root_devs(self):
        """Find the root device.

        Returns:
             The root device name in string format

        """

        try:
            zpool = self.zpool_parse('freenas-boot')
            return zpool.get_disks()
        except:
            log.warn("Root device not found!")
            return []

    def __get_disks(self):
        """Return a list of available storage disks.

        The list excludes all devices that cannot be reserved for storage,
        e.g. the root device, CD drives, etc.

        Returns:
            A list of available devices (ada0, da0, etc), or an empty list if
            no devices could be divined from the system.
        """

        disks = self.sysctl('kern.disks').split()
        disks.reverse()

        blacklist_devs = self._find_root_devs()
        device_blacklist_re = re.compile('a?cd[0-9]+')

        return filter(lambda x: not device_blacklist_re.match(x) and x not in blacklist_devs, disks)

    def sysctl(self, name):
        """
        Tiny wrapper for sysctl module for compatibility
        """
        sysc = sysctl.sysctlbyname(name)
        if sysc is not None:
            return sysc

        raise ValueError(name)

    def __get_geoms_recursive(self, prvid):
        """
        Get _ALL_ geom nodes that depends on a given provider
        """
        doc = self._geom_confxml()
        geoms = []
        for c in doc.xpath("//consumer/provider[@ref = '%s']" % (prvid, )):
            geom = c.getparent().getparent()
            if geom.tag != 'geom':
                continue
            geoms.append(geom)
            for prov in geom.xpath('./provider'):
                geoms.extend(self.__get_geoms_recursive(prov.attrib.get('id')))

        return geoms

    def disk_get_consumers(self, devname):
        doc = self._geom_confxml()
        geom = doc.xpath("//class[name = 'DISK']/geom[name = '%s']" % (
            devname,
        ))
        if geom:
            provid = geom[0].xpath("./provider/@id")[0]
        else:
            raise ValueError("Unknown disk %s" % (devname, ))
        return self.__get_geoms_recursive(provid)

    def get_smartctl_args(self, devname):
        args = ["/dev/%s" % devname]
        camcontrol = self._camcontrol_list()
        info = camcontrol.get(devname)
        if info is not None:
            if info.get("drv") == "rr274x_3x":
                channel = info["channel"] + 1
                if channel > 16:
                    channel -= 16
                elif channel > 8:
                    channel -= 8
                args = [
                    "/dev/%s" % info["drv"],
                    "-d",
                    "hpt,%d/%d" % (info["controller"] + 1, channel)
                    ]
            elif info.get("drv").startswith("arcmsr"):
                args = [
                    "/dev/%s%d" % (info["drv"], info["controller"]),
                    "-d",
                    "areca,%d" % (info["lun"] + 1 + (info["channel"] * 8), )
                    ]
            elif info.get("drv").startswith("hpt"):
                args = [
                    "/dev/%s" % info["drv"],
                    "-d",
                    "hpt,%d/%d" % (info["controller"] + 1, info["channel"] + 1)
                    ]
            elif info.get("drv") == "ciss":
                args = [
                    "/dev/%s%d" % (info["drv"], info["controller"]),
                    "-d",
                    "cciss,%d" % (info["channel"], )
                    ]
            elif info.get("drv") == "twa":
                twcli = self.__get_twcli(info["controller"])
                args = [
                    "/dev/%s%d" % (info["drv"], info["controller"]),
                    "-d",
                    "3ware,%d" % (twcli.get(info["channel"], -1), )
                    ]
        return args

    def serial_from_device(self, devname):
        if devname in self.__diskserial:
            return self.__diskserial.get(devname)

        args = self.get_smartctl_args(devname)

        p1 = Popen(["/usr/local/sbin/smartctl", "-i"] + args, stdout=PIPE)
        output = p1.communicate()[0]
        search = re.search(r'Serial Number:\s+(?P<serial>.+)', output, re.I)
        if search:
            serial = search.group("serial")
            self.__diskserial[devname] = serial
            return serial
        return None

    def _camcontrol_list(self):
        """
        Parse camcontrol devlist -v output to gather
        controller id, channel no and driver from a device

        Returns:
            dict(devname) = dict(drv, controller, channel)
        """
        if self.__camcontrol is not None:
            return self.__camcontrol

        self.__camcontrol = {}

        """
        Hacky workaround

        It is known that at least some HPT controller have a bug in the
        camcontrol devlist output with multiple controllers, all controllers
        will be presented with the same driver with index 0
        e.g. two hpt27xx0 instead of hpt27xx0 and hpt27xx1

        What we do here is increase the controller id by its order of
        appearance in the camcontrol output
        """
        hptctlr = defaultdict(int)

        re_drv_cid = re.compile(r'.* on (?P<drv>.*?)(?P<cid>[0-9]+) bus', re.S | re.M)
        re_tgt = re.compile(r'target (?P<tgt>[0-9]+) .*?lun (?P<lun>[0-9]+) .*\((?P<dv1>[a-z]+[0-9]+),(?P<dv2>[a-z]+[0-9]+)\)', re.S | re.M)
        drv, cid, tgt, lun, dev, devtmp = (None, ) * 6

        proc = self._pipeopen("/sbin/camcontrol devlist -v")
        for line in proc.communicate()[0].splitlines():
            if not line.startswith('<'):
                reg = re_drv_cid.search(line)
                if not reg:
                    continue
                drv = reg.group("drv")
                if drv.startswith("hpt"):
                    cid = hptctlr[drv]
                    hptctlr[drv] += 1
                else:
                    cid = reg.group("cid")
            else:
                reg = re_tgt.search(line)
                if not reg:
                    continue
                tgt = reg.group("tgt")
                lun = reg.group("lun")
                dev = reg.group("dv1")
                devtmp = reg.group("dv2")
                if dev.startswith("pass"):
                    dev = devtmp
                self.__camcontrol[dev] = {
                    'drv': drv,
                    'controller': int(cid),
                    'channel': int(tgt),
                    'lun': int(lun)
                    }
        return self.__camcontrol

    def pwenc_reset_model_passwd(self, model, field):
        for obj in model.objects.all():
            setattr(obj, field, '')
            obj.save()

    def pwenc_generate_secret(self, reset_passwords=True, _settings=None):
        from Crypto import Random
        from django.conf import settings as dsettings
        if _settings is None:
            from freenasUI.system.models import Settings
            _settings = Settings

        try:
            settings = _settings.objects.order_by('-id')[0]
        except IndexError:
            settings = _settings.objects.create()

        secret = Random.new().read(PWENC_BLOCK_SIZE)
        with open(dsettings.PWENC_FILE_SECRET, 'wb') as f:
            os.chmod(dsettings.PWENC_FILE_SECRET, 0o600)
            f.write(secret)

        settings.stg_pwenc_check = self.pwenc_encrypt(PWENC_CHECK)
        settings.save()

        if reset_passwords:
            from freenasUI.directoryservice.models import ActiveDirectory, LDAP, NT4
            self.pwenc_reset_model_passwd(ActiveDirectory, 'ad_bindpw')
            self.pwenc_reset_model_passwd(LDAP, 'ldap_bindpw')
            self.pwenc_reset_model_passwd(NT4, 'nt4_adminpw')

    def pwenc_check(self):
        from freenasUI.system.models import Settings
        try:
            settings = Settings.objects.order_by('-id')[0]
        except IndexError:
            settings = Settings.objects.create()
        try:
            return self.pwenc_decrypt(settings.stg_pwenc_check) == PWENC_CHECK
        except IOError:
            return False

    def pwenc_get_secret(self):
        from django.conf import settings
        with open(settings.PWENC_FILE_SECRET, 'rb') as f:
            secret = f.read()
        return secret

    def pwenc_encrypt(self, text):
        from Crypto.Random import get_random_bytes
        from Crypto.Util import Counter
        pad = lambda x: x + (PWENC_BLOCK_SIZE - len(x) % PWENC_BLOCK_SIZE) * PWENC_PADDING

        nonce = get_random_bytes(8)
        cipher = AES.new(
            self.pwenc_get_secret(),
            AES.MODE_CTR,
            counter=Counter.new(64, prefix=nonce),
        )
        encoded = base64.b64encode(nonce + cipher.encrypt(pad(text)))
        return encoded

    def pwenc_decrypt(self, encrypted=None):
        if not encrypted:
            return ""
        from Crypto.Util import Counter
        encrypted = base64.b64decode(encrypted)
        nonce = encrypted[:8]
        encrypted = encrypted[8:]
        cipher = AES.new(
            self.pwenc_get_secret(),
            AES.MODE_CTR,
            counter=Counter.new(64, prefix=nonce),
        )
        return cipher.decrypt(encrypted).rstrip(PWENC_PADDING).decode('utf8')


def usage():
    usage_str = """usage: %s action command
    Action is one of:
        start: start a command
        stop: stop a command
        restart: restart a command
        reload: reload a command (try reload; if unsuccessful do restart)
        change: notify change for a command (try self.reload; if unsuccessful do start)""" \
        % (os.path.basename(sys.argv[0]), )
    sys.exit(usage_str)

# When running as standard-alone script
if __name__ == '__main__':
    if len(sys.argv) < 2:
        usage()
    else:
        n = notifier()
        f = getattr(n, sys.argv[1], None)
        if f is None:
            sys.stderr.write("Unknown action: %s\n" % sys.argv[1])
            usage()
        print(f(*sys.argv[2:]))
