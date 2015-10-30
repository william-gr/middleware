#!/usr/local/bin/python2.7
#+
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
import argparse
import logging
import json
import subprocess
import errno
import threading
import setproctitle
import socket
import netif
import time
import ipaddress
from datastore import get_datastore, DatastoreException
from datastore.config import ConfigStore
from dispatcher.client import Client, ClientError
from dispatcher.rpc import RpcService, RpcException, private
from fnutils.query import wrap
from fnutils.debug import DebugService
from fnutils import configure_logging


DEFAULT_CONFIGFILE = '/usr/local/etc/middleware.conf'


def cidr_to_netmask(cidr):
    iface = ipaddress.ip_interface(u'0.0.0.0/{0}'.format(cidr))
    return unicode(str(iface.netmask))


def convert_aliases(entity):
    for i in entity.get('aliases', []):
        addr = netif.InterfaceAddress()
        iface = ipaddress.ip_interface(u'{0}/{1}'.format(i['address'], i['netmask']))
        addr.af = getattr(netif.AddressFamily, i.get('type', 'INET'))
        addr.address = ipaddress.ip_address(i['address'])
        addr.netmask = iface.netmask
        addr.broadcast = iface.network.broadcast_address

        if i.get('broadcast'):
            addr.broadcast = ipaddress.ip_address(i['broadcast'])

        if i.get('dest-address'):
            addr.dest_address = ipaddress.ip_address(i['dest-address'])

        yield addr


def convert_route(entity):
    if not entity:
        return None

    if entity['network'] == 'default':
        entity['network'] = '0.0.0.0'
        entity['netmask'] = '0.0.0.0'

    netmask = cidr_to_netmask(entity['netmask'])
    r = netif.Route(
        entity['network'],
        netmask,
        entity.get('gateway'),
        entity.get('interface')
    )

    r.flags.add(netif.RouteFlags.STATIC)

    if not r.netmask:
        r.flags.add(netif.RouteFlags.HOST)

    if r.gateway:
        r.flags.add(netif.RouteFlags.GATEWAY)

    return r


def default_route(gateway):
    if not gateway:
        return None

    r = netif.Route(u'0.0.0.0', u'0.0.0.0', gateway)
    r.flags.add(netif.RouteFlags.STATIC)
    r.flags.add(netif.RouteFlags.GATEWAY)
    return r


def describe_route(route):
    bits = bin(int(route.netmask)).count('1') if route.netmask else 0
    return '{0}/{1} via {2}'.format(route.network, bits, route.gateway)


def filter_routes(routes):
    """
    Filter out routes for loopback addresses and local subnets
    :param routes: routes list
    :return: filtered routes list
    """

    aliases = [i.addresses for i in netif.list_interfaces().values()]
    aliases = reduce(lambda x, y: x+y, aliases)
    aliases = filter(lambda a: a.af == netif.AddressFamily.INET, aliases)
    aliases = [ipaddress.ip_interface(u'{0}/{1}'.format(a.address, a.netmask)) for a in aliases]

    for i in routes:
        if type(i.gateway) is str:
            continue

        if i.af != netif.AddressFamily.INET:
            continue

        found = True
        for a in aliases:
            if i.network in a.network:
                found = False
                break

        if found:
            yield i


def get_addresses(entity):
    return [ipaddress.ip_address(i['address']) for i in entity.get('aliases', [])]


class RoutingSocketEventSource(threading.Thread):
    def __init__(self, context):
        super(RoutingSocketEventSource, self).__init__()
        self.context = context
        self.client = context.client
        self.mtu_cache = {}
        self.flags_cache = {}
        self.link_state_cache = {}

    def build_cache(self):
        # Build a cache of certain interface states so we'll later know what has changed
        for i in netif.list_interfaces().values():
            self.mtu_cache[i.name] = i.mtu
            self.flags_cache[i.name] = i.flags
            self.link_state_cache[i.name] = i.link_state

    def alias_added(self, message):
        pass

    def alias_removed(self, message):
        pass

    def run(self):
        rtsock = netif.RoutingSocket()
        rtsock.open()

        self.build_cache()

        while True:
            message = rtsock.read_message()

            if type(message) is netif.InterfaceAnnounceMessage:
                args = {'name': message.interface}

                if message.type == netif.InterfaceAnnounceType.ARRIVAL:
                    self.context.interface_attached(message.interface)
                    self.client.emit_event('network.interface.attached', args)

                if message.type == netif.InterfaceAnnounceType.DEPARTURE:
                    self.context.interface_detached(message.interface)
                    self.client.emit_event('network.interface.detached', args)

                self.build_cache()

            if type(message) is netif.InterfaceInfoMessage:
                ifname = message.interface
                if self.mtu_cache[ifname] != message.mtu:
                    self.client.emit_event('network.interface.mtu_changed', {
                        'interface': ifname,
                        'old-mtu': self.mtu_cache[ifname],
                        'new-mtu': message.mtu
                    })

                if self.link_state_cache[ifname] != message.link_state:
                    if message.link_state == netif.InterfaceLinkState.LINK_STATE_DOWN:
                        self.context.logger.warn('Link down on interface {0}'.format(ifname))
                        self.client.emit_event('network.interface.link_down', {
                            'interface': ifname,
                        })

                    if message.link_state == netif.InterfaceLinkState.LINK_STATE_UP:
                        self.context.logger.warn('Link up on interface {0}'.format(ifname))
                        self.client.emit_event('network.interface.link_up', {
                            'interface': ifname,
                        })

                if self.flags_cache[ifname] != message.flags:
                    if (netif.InterfaceFlags.UP in self.flags_cache) and (netif.InterfaceFlags.UP not in message.flags):
                        self.client.emit_event('network.interface.down', {
                            'interface': ifname,
                        })

                    if (netif.InterfaceFlags.UP not in self.flags_cache) and (netif.InterfaceFlags.UP in message.flags):
                        self.client.emit_event('network.interface.up', {
                            'interface': ifname,
                        })

                    self.client.emit_event('network.interface.flags_changed', {
                        'interface': ifname,
                        'old-flags': [f.name for f in self.flags_cache[ifname]],
                        'new-flags': [f.name for f in message.flags]
                    })

                self.build_cache()

            if type(message) is netif.InterfaceAddrMessage:
                entity = self.context.datastore.get_by_id('network.interfaces', message.interface)
                if entity is None:
                    continue

                # Skip messagess with empty address
                if not message.address:
                    continue

                # Skip 0.0.0.0 aliases
                if message.address == ipaddress.IPv4Address('0.0.0.0'):
                    continue

                addr = netif.InterfaceAddress()
                addr.af = netif.AddressFamily.INET
                addr.address = message.address
                addr.netmask = message.netmask
                addr.broadcast = message.dest_address

                if message.type == netif.RoutingMessageType.NEWADDR:
                    self.context.logger.warn('New alias added to interface {0} externally: {1}/{2}'.format(
                        message.interface,
                        message.address,
                        message.netmask
                    ))

                if message.type == netif.RoutingMessageType.DELADDR:
                    self.context.logger.warn('Alias removed from interface {0} externally: {1}/{2}'.format(
                        message.interface,
                        message.address,
                        message.netmask
                    ))

                self.client.emit_event('network.interface.changed', {
                    'operation': 'update',
                    'ids': [entity['id']]
                })

            if type(message) is netif.RoutingMessage:
                if message.errno != 0:
                    continue

                if message.type == netif.RoutingMessageType.ADD:
                    self.context.logger.info('Route to {0} added'.format(describe_route(message.route)))
                    self.client.emit_event('network.route.added', message.__getstate__())

                if message.type == netif.RoutingMessageType.DELETE:
                    self.context.logger.info('Route to {0} deleted'.format(describe_route(message.route)))
                    self.client.emit_event('network.route.deleted', message.__getstate__())

        rtsock.close()


@private
class ConfigurationService(RpcService):
    def __init__(self, context):
        self.context = context
        self.logger = context.logger
        self.config = context.configstore
        self.datastore = context.datastore
        self.client = context.client

    def get_next_name(self, type):
        type_map = {
            'VLAN': 'vlan',
            'LAGG': 'lagg',
            'BRIDGE': 'bridge'
        }

        if type not in type_map.keys():
            raise RpcException(errno.EINVAL, 'Invalid type: {0}'.format(type))

        ifaces = netif.list_interfaces()
        for i in range(0, 999):
            name = '{0}{1}'.format(type_map[type], i)
            if name not in ifaces.keys() and not self.datastore.exists('network.interfaces', ('id', '=', name)):
                return name

        raise RpcException(errno.EBUSY, 'No free interfaces left')

    def query_interfaces(self):
        return netif.list_interfaces()

    def query_routes(self):
        rtable = netif.RoutingTable()
        return wrap(rtable.static_routes)

    def configure_network(self):
        if self.config.get('network.autoconfigure'):
            # Try DHCP on each interface until we find lease. Mark failed ones as disabled.
            self.logger.warn('Network in autoconfiguration mode')
            for i in netif.list_interfaces().values():
                entity = self.datastore.get_by_id('network.interfaces', i.name)
                if i.type == netif.InterfaceType.LOOP:
                    continue

                self.logger.info('Trying to acquire DHCP lease on interface {0}...'.format(i.name))
                if self.context.configure_dhcp(i.name):
                    entity.update({
                        'enabled': True,
                        'dhcp': True
                    })

                    self.datastore.update('network.interfaces', entity['id'], entity)
                    self.config.set('network.autoconfigure', False)
                    self.logger.info('Successfully configured interface {0}'.format(i.name))
                    return

            self.logger.warn('Failed to configure any network interface')
            return

        for i in self.datastore.query('network.interfaces'):
            self.logger.info('Configuring interface {0}...'.format(i['id']))
            try:
                self.configure_interface(i['id'])
            except BaseException, e:
                self.logger.warning('Cannot configure {0}: {1}'.format(i['id'], str(e)))

        # Are there any orphaned interfaces?
        for name, iface in netif.list_interfaces().items():
            if not name.startswith(('vlan', 'lagg', 'bridge')):
                continue

            if not self.datastore.exists('network.interfaces', ('id', '=', name)):
                netif.destroy_interface(name)

        self.configure_routes()
        self.client.emit_event('network.changed', {
            'operation': 'update'
        })

    def configure_routes(self):
        rtable = netif.RoutingTable()
        static_routes = filter_routes(rtable.static_routes)
        default_route_ipv4 = default_route(self.config.get('network.gateway.ipv4'))

        if not self.context.using_dhcp_for_gateway():
            # Default route was deleted
            if not default_route_ipv4 and rtable.default_route_ipv4:
                self.logger.info('Removing default route')
                try:
                    rtable.delete(rtable.default_route_ipv4)
                except OSError, e:
                    self.logger.error('Cannot remove default route: {0}'.format(str(e)))

            # Default route was added
            elif not rtable.default_route_ipv4 and default_route_ipv4:
                self.logger.info('Adding default route via {0}'.format(default_route_ipv4.gateway))
                try:
                    rtable.add(default_route_ipv4)
                except OSError, e:
                    self.logger.error('Cannot add default route: {0}'.format(str(e)))

            # Default route was changed
            elif rtable.default_route_ipv4 != default_route_ipv4:
                self.logger.info('Changing default route from {0} to {1}'.format(
                    rtable.default_route.gateway,
                    default_route_ipv4.gateway))

                try:
                    rtable.change(default_route_ipv4)
                except OSError, e:
                    self.logger.error('Cannot add default route: {0}'.format(str(e)))

        else:
            self.logger.info('Not configuring default route as using DHCP')

        # Same thing for IPv6
        default_route_ipv6 = default_route(self.config.get('network.gateway.ipv6'))

        # Now the static routes...
        old_routes = set(static_routes)
        new_routes = set([convert_route(e) for e in self.datastore.query('network.routes')])

        for i in old_routes - new_routes:
            self.logger.info('Removing static route to {0}'.format(describe_route(i)))
            try:
                rtable.delete(i)
            except OSError, e:
                self.logger.error('Cannot remove static route to {0}: {1}'.format(describe_route(i), str(e)))

        for i in new_routes - old_routes:
            self.logger.info('Adding static route to {0}'.format(describe_route(i)))
            try:
                rtable.add(i)
            except OSError, e:
                self.logger.error('Cannot add static route to {0}: {1}'.format(describe_route(i), str(e)))

    def configure_interface(self, name):
        entity = self.datastore.get_one('network.interfaces', ('id', '=', name))
        if not entity:
            raise RpcException(errno.ENXIO, "Configuration for interface {0} not found".format(name))

        if not entity.get('enabled'):
            self.logger.info('Interface {0} is disabled'.format(name))
            return

        try:
            iface = netif.get_interface(name)
        except KeyError:
            if entity.get('cloned'):
                netif.create_interface(entity['id'])
                iface = netif.get_interface(name)
            else:
                raise RpcException(errno.ENOENT, "Interface {0} not found".format(name))

        # If it's VLAN, configure parent and tag
        if entity.get('type') == 'VLAN':
            vlan = entity.get('vlan')
            if vlan:
                parent = vlan.get('parent')
                tag = vlan.get('tag')

                if parent and tag:
                    try:
                        tag = int(tag)
                        iface.unconfigure()
                        iface.configure(parent, tag)
                    except Exception, e:
                        self.logger.warn('Failed to configure VLAN interface {0}: {1}'.format(name, str(e)))

        # Configure protocol and member ports for a LAGG
        if entity.get('type') == 'LAGG':
            lagg = entity.get('lagg')
            if lagg:
                iface.protocol = getattr(netif.AggregationProtocol, lagg.get('protocol', 'FAILOVER'))

                for i in lagg['ports']:
                    iface.add_port(i)

        if entity.get('dhcp'):
            self.logger.info('Trying to acquire DHCP lease on interface {0}...'.format(name))
            if not self.context.configure_dhcp(name):
                self.logger.warn('Failed to configure interface {0} using DHCP'.format(name))
        else:
            addresses = set(convert_aliases(entity))
            existing_addresses = set(filter(lambda a: a.af != netif.AddressFamily.LINK, iface.addresses))

            # Remove orphaned addresses
            for i in existing_addresses - addresses:
                self.logger.info('Removing address from interface {0}: {1}'.format(name, i))
                iface.remove_address(i)

            # Add new or changed addresses
            for i in addresses - existing_addresses:
                self.logger.info('Adding new address to interface {0}: {1}'.format(name, i))
                iface.add_address(i)

        # nd6 stuff
        if entity.get('rtadv', False):
            iface.nd6_flags = iface.nd6_flags | {netif.NeighborDiscoveryFlags.ACCEPT_RTADV}
        else:
            iface.nd6_flags = iface.nd6_flags - {netif.NeighborDiscoveryFlags.ACCEPT_RTADV}

        if entity.get('noipv6', False):
            iface.nd6_flags = iface.nd6_flags | {netif.NeighborDiscoveryFlags.IFDISABLED}
        else:
            iface.nd6_flags = iface.nd6_flags - {netif.NeighborDiscoveryFlags.IFDISABLED}

        if entity.get('mtu'):
            iface.mtu = entity['mtu']

        if entity.get('media'):
            iface.media_subtype = entity['media']

        if entity.get('capabilities'):
            caps = iface.capabilities
            for c in entity['capabilities'].get('add'):
                caps.add(getattr(netif.InterfaceCapability, c))

            for c in entity['capabilities'].get('del'):
                caps.remove(getattr(netif.InterfaceCapability, c))

            iface.capabilities = caps

        if netif.InterfaceFlags.UP not in iface.flags:
            self.logger.info('Bringing interface {0} up'.format(name))
            iface.up()

        self.client.emit_event('network.interface.configured', {
            'interface': name,
        })

    def up_interface(self, name):
        try:
            iface = netif.get_interface(name)
        except NameError:
            raise RpcException(errno.ENOENT, "Interface {0} not found".format(name))

        iface.up()

    def down_interface(self, name):
        try:
            iface = netif.get_interface(name)
        except NameError:
            raise RpcException(errno.ENOENT, "Interface {0} not found".format(name))

        # Remove all IP addresses from interface
        for addr in iface.addresses:
            if addr.af == netif.AddressFamily.LINK:
                continue

            try:
                iface.remove_address(addr)
            except:
                # Continue anyway
                pass

        iface.down()


class Main:
    def __init__(self):
        self.config = None
        self.client = None
        self.datastore = None
        self.configstore = None
        self.rtsock_thread = None
        self.logger = logging.getLogger('networkd')

    def configure_dhcp(self, interface):
        # Check if dhclient is running
        if os.path.exists(os.path.join('/var/run', 'dhclient.{0}.pid'.format(interface))):
            self.logger.info('Interface {0} already configured by DHCP'.format(interface))
            return True

        # XXX: start dhclient through launchd in the future
        ret = subprocess.call(['/sbin/dhclient', interface])
        return ret == 0

    def interface_detached(self, name):
        self.logger.warn('Interface {0} detached from the system'.format(name))

    def interface_attached(self, name):
        self.logger.warn('Interface {0} attached to the system'.format(name))

    def using_dhcp_for_gateway(self):
        for i in self.datastore.query('network.interfaces'):
            if i.get('dhcp') and self.configstore.get('network.dhcp.assign_gateway'):
                    return True

        return False

    def scan_interfaces(self):
        self.logger.info('Scanning available network interfaces...')
        existing = []

        # Add newly plugged NICs to DB
        for i in netif.list_interfaces().values():
            # We want only physical NICs
            if i.cloned:
                continue

            existing.append(i.name)
            if not self.datastore.exists('network.interfaces', ('id', '=', i.name)):
                self.logger.info('Found new interface {0} ({1})'.format(i.name, i.type.name))
                self.datastore.insert('network.interfaces', {
                    'enabled': False,
                    'id': i.name,
                    'type': i.type.name
                })

        # Remove unplugged NICs from DB
        for i in self.datastore.query('network.interfaces', ('id', 'nin', existing)):
            self.datastore.delete('network.interfaces', i['id'])

    def parse_config(self, filename):
        try:
            f = open(filename, 'r')
            self.config = json.load(f)
            f.close()
        except IOError, err:
            self.logger.error('Cannot read config file: %s', err.message)
            sys.exit(1)
        except ValueError, err:
            self.logger.error('Config file has unreadable format (not valid JSON)')
            sys.exit(1)

    def init_datastore(self):
        try:
            self.datastore = get_datastore(self.config['datastore']['driver'], self.config['datastore']['dsn'])
        except DatastoreException, err:
            self.logger.error('Cannot initialize datastore: %s', str(err))
            sys.exit(1)

        self.configstore = ConfigStore(self.datastore)

    def connect(self, resume=False):
        while True:
            try:
                self.client.connect('127.0.0.1')
                self.client.login_service('networkd')
                self.client.enable_server()
                self.register_schemas()
                self.client.register_service('networkd.configuration', ConfigurationService(self))
                self.client.register_service('networkd.debug', DebugService())
                if resume:
                    self.client.resume_service('networkd.configuration')
                    self.client.resume_service('networkd.debug')

                return
            except socket.error, err:
                self.logger.warning('Cannot connect to dispatcher: {0}, retrying in 1 second'.format(str(err)))
                time.sleep(1)

    def init_dispatcher(self):
        def on_error(reason, **kwargs):
            if reason in (ClientError.CONNECTION_CLOSED, ClientError.LOGOUT):
                self.logger.warning('Connection to dispatcher lost')
                self.connect(resume=True)

        self.client = Client()
        self.client.on_error(on_error)
        self.connect()

    def init_routing_socket(self):
        self.rtsock_thread = RoutingSocketEventSource(self)
        self.rtsock_thread.start()

    def register_schemas(self):
        self.client.register_schema('network-aggregation-protocols', {
            'type': 'string',
            'enum': netif.AggregationProtocol.__members__.keys()
        })

        self.client.register_schema('network-interface-flags', {
            'type': 'array',
            'items': {
                'type': 'string',
                'enum': netif.InterfaceFlags.__members__.keys()
            }
        })

        self.client.register_schema('network-interface-capabilities', {
            'type': 'array',
            'items': {
                'type': 'string',
                'enum': netif.InterfaceCapability.__members__.keys()
            }
        })

        self.client.register_schema('network-interface-mediaopts', {
            'type': 'array',
            'items': {
                'type': 'string',
                'enum': netif.InterfaceMediaOption.__members__.keys()
            }
        })

        self.client.register_schema('network-interface-type', {
            'type': 'string',
            'enum': [
                'LOOPBACK',
                'ETHER',
                'VLAN',
                'BRIDGE',
                'LAGG'
            ]
        })

        self.client.register_schema('network-interface-status', {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'link_state': {'type': 'string'},
                'link_address': {'type': 'string'},
                'mtu': {'type': 'integer'},
                'media_type': {'type': 'string'},
                'media_subtype': {'type': 'string'},
                'media_options': {'$ref': 'network-interface-media-options'},
                'capabilities': {'$ref': 'network-interface-capabilities'},
                'flags': {'$ref': 'network-interface-flags'},
                'aliases': {
                    'type': 'array',
                    'items': {'$ref': 'network-interface-alias'}
                }
            }
        })

    def main(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-c', metavar='CONFIG', default=DEFAULT_CONFIGFILE, help='Middleware config file')
        args = parser.parse_args()
        configure_logging('/var/log/networkd.log', 'DEBUG')
        setproctitle.setproctitle('networkd')
        self.parse_config(args.c)
        self.init_datastore()
        self.init_dispatcher()
        self.scan_interfaces()
        self.init_routing_socket()
        self.client.resume_service('networkd.configuration')
        self.logger.info('Started')
        self.client.wait_forever()

if __name__ == '__main__':
    m = Main()
    m.main()
