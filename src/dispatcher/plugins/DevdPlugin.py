#+
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

import os
import re
import netif
import time
import io
from xml.etree import ElementTree
from bsd import geom
from event import EventSource
from task import Provider
from dispatcher.rpc import accepts, returns, description
from dispatcher.rpc import SchemaHelper as h
from gevent import socket
from lib.freebsd import get_sysctl
from fnutils import exclude


@description("Provides information about devices installed in the system")
class DeviceInfoPlugin(Provider):
    @description("Returns list of available device classes")
    @returns(h.array(str))
    def get_classes(self):
        return [
            "disk",
            "network",
            "cpu"
        ]

    @description("Returns list of devices from given class")
    @accepts(str)
    @returns(h.any_of(
        h.ref('disk-device'),
        h.ref('network-device'),
        h.ref('cpu-device')
    ))
    def get_devices(self, dev_class):
        method = "_get_class_{0}".format(dev_class)
        if hasattr(self, method):
            return getattr(self, method)()

        return None

    def _get_class_disk(self):
        result = []
        geom.scan()
        for child in geom.class_by_name('DISK').geoms:
            result.append({
                "path": os.path.join("/dev", child.name),
                "name": child.name,
                "mediasize": child.provider.mediasize,
                "description": child.provider.config['descr']
            })

        return result

    def _get_class_multipath(self):
        result = []
        geom.scan()
        cls = geom.class_by_name('MULTIPATH')
        if not cls:
            return []

        for child in cls.geoms:
            result.append({
                "path": os.path.join("/dev", child.name),
                "name": child.name,
                "mediasize": child.provider.mediasize,
                "members": [c.provider.name for c in child.consumers]
            })

        return result

    def _get_class_network(self):
        result = []
        for i in list(netif.list_interfaces().keys()):
            if i.startswith('lo'):
                continue

            desc = get_sysctl(re.sub('(\w+)([0-9]+)', 'dev.\\1.\\2.%desc', i))
            result.append({
                'name': i,
                'description': desc
            })

        return result

    def _get_class_cpu(self):
        pass


class DevdEventSource(EventSource):
    class DevdEvent(dict):
        def __init__(self, kind):
            self.kind = kind
            super(DevdEventSource.DevdEvent, self).__init__()

    def __init__(self, dispatcher):
        super(DevdEventSource, self).__init__(dispatcher)
        self.register_event_type("system.device.attached")
        self.register_event_type("system.device.detached")
        self.register_event_type("system.device.changed")
        self.register_event_type("system.network.interface.attached")
        self.register_event_type("system.network.interface.detached")
        self.register_event_type("system.network.interface.link_up")
        self.register_event_type("system.network.interface.link_down")
        self.register_event_type("fs.zfs.scrub.start")
        self.register_event_type("fs.zfs.scrub.finish")
        self.register_event_type("fs.zfs.scrub.aborted")
        self.register_event_type("fs.zfs.resilver.started")
        self.register_event_type("fs.zfs.resilver.finished")
        self.register_event_type("fs.zfs.pool.created")
        self.register_event_type("fs.zfs.pool.destroyed")
        self.register_event_type("fs.zfs.pool.updated")
        self.register_event_type("fs.zfs.pool.changed")
        self.register_event_type("fs.zfs.dataset.created")
        self.register_event_type("fs.zfs.dataset.deleted")
        self.register_event_type("fs.zfs.dataset.renamed")

    def __tokenize(self, buffer):
        try:
            tree = ElementTree.fromstring(buffer)
        except ElementTree.ParseError:
            return None

        ret = self.DevdEvent(tree.tag)
        for i in tree:
            ret[i.tag] = i.text

        return ret

    def __process_devfs(self, args):
        if args["subsystem"] == "CDEV":
            params = {
                "name": args["cdev"],
                "path": os.path.join("/dev", args["cdev"])
            }

            if args["type"] == "CREATE":
                params["description"] = "Device {0} attached".format(args["cdev"])
                self.emit_event("system.device.attached", **params)

            if args["type"] == "DESTROY":
                params["description"] = "Device {0} detached".format(args["cdev"])
                self.emit_event("system.device.detached", **params)

            if args["type"] == "MEDIACHANGE":
                params["description"] = "Device {0} media changed".format(args["cdev"])
                self.emit_event("system.device.mediachange", **params)

    def __process_ifnet(self, args):
        params = {
            "interface": args["subsystem"]
        }

    def __process_system(self, args):
        if args["subsystem"] == "HOSTNAME":
            if args["type"] == "CHANGE":
                params = exclude(args, "system", "subsystem", "type")
                params["description"] = "System hostname changed"
                self.emit_event("system.hostname.change", **params)

    def __process_zfs(self, args):
        event_mapping = {
            "misc.fs.zfs.scrub_start": ("fs.zfs.scrub.started", "Scrub on volume {0} started"),
            "misc.fs.zfs.scrub_finish": ("fs.zfs.scrub.finished", "Scrub on volume {0} finished"),
            "misc.fs.zfs.scrub_abort": ("fs.zfs.scrub.aborted", "Scrub on volume {0} aborted"),
            "misc.fs.zfs.resilver_start": ("fs.zfs.resilver.started", "Resilver on volume {0} started"),
            "misc.fs.zfs.resilver_finish": ("fs.zfs.resilver.finished", "Resilver on volume {0} finished"),
            "misc.fs.zfs.pool_create": ("fs.zfs.pool.created", "Pool {0} created"),
            "misc.fs.zfs.pool_destroy": ("fs.zfs.pool.destroyed", "Pool {0} destroyed"),
            "misc.fs.zfs.dataset_create": ("fs.zfs.dataset.created", "Dataset on pool {0} created"),
            "misc.fs.zfs.dataset_delete": ("fs.zfs.dataset.deleted", "Dataset on pool {0} deleted"),
            "misc.fs.zfs.dataset_rename": ("fs.zfs.dataset.renamed", "Dataset on pool {0} renamed"),
            "misc.fs.zfs.config_sync": ("fs.zfs.pool.updated", "Pool {0} configuration updated"),
            "misc.fs.zfs.vdev_statechange": ("fs.zfs.pool.changed", "Pool {0} status changed"),
        }

        if args["type"] not in event_mapping:
            return

        ev_type = args.pop("type")
        pool_name = args.pop("pool_name", None)

        params = {
            "pool": pool_name,
            "guid": args.pop("pool_guid", None),
            "description": event_mapping[ev_type][1].format(pool_name)
        }

        if "ds" in args:
            params["ds"] = args.pop("ds")

        if "new_ds" in args:
            params["new_ds"] = args.pop("new_ds")

        if args:
            params["extra"] = args

        self.emit_event(event_mapping[ev_type][0], **params)

    def read_until_nul(self, sock):
        buf = io.BytesIO()
        while True:
            byte = sock.read(1)
            if byte == b'':
                return None

            if byte == b'\x00':
                return buf.getvalue()

            buf.write(byte)

    def run(self):
        while True:
            try:
                self.socket = socket.socket(family=socket.AF_UNIX)
                self.socket.connect("/var/run/devd.pipe")
                f = self.socket.makefile("rb", 0)
                
                while True:
                    line = self.read_until_nul(f)
                    if line is None:
                        # Connection closed - we need to reconnect
                        # return
                        raise OSError('Connection closed')

                    event = self.__tokenize(line.decode('utf-8', 'replace'))
                    if not event:
                        # WTF
                        continue
                        
                    if "system" not in event:
                        # WTF
                        continue

                    if event["system"] == "DEVFS":
                        self.__process_devfs(event)

                    if event["system"] == "IFNET":
                        self.__process_ifnet(event)

                    if event["system"] == "ZFS":
                        self.__process_zfs(event)

                    if event["system"] == "SYSTEM":
                        self.__process_system(event)

            except OSError:
                # sleep for a half a second and retry
                self.dispatcher.logger.debug(
                    '/var/run/devd.pipe timedout/was not available, retrying in 0.5 seconds')
                time.sleep(0.5)


def _depends():
    return ['ServiceManagePlugin']


def _init(dispatcher, plugin):
    def on_service_started(args):
        if args['name'] == 'devd':
            # devd is running, kick in DevdEventSource
            plugin.register_event_source('system.device', DevdEventSource)
            plugin.unregister_event_handler(
                'service.started', on_service_started)

    plugin.register_schema_definition('disk-device', {
        'type': 'object',
        'properties': {
            'name': {'type': 'string'},
            'mediasize': {'type': 'integer'},
            'description': {'type': 'string'}
        }
    })

    plugin.register_schema_definition('network-device', {
        'type': 'object',
        'properties': {
            'name': {'type': 'string'},
            'description': {'type': 'string'}
        }
    })

    plugin.register_schema_definition('cpu-device', {
        'type': 'object',
        'properties': {
            'name': {'type': 'string'},
            'description': {'type': 'string'}
        }
    })

    if os.path.exists('/var/run/devd.pipe'):
        plugin.register_event_source('system.device', DevdEventSource)
    else:
        plugin.register_event_handler(
            'service.started', on_service_started)

    plugin.register_provider('system.device', DeviceInfoPlugin)
