<%
    config = dispatcher.call_sync('service.rsyncd.get_config')
%>\
use chroot = yes
max connections = 4
pid file = /var/run/rsyncd.pid
port = ${config['port']}
% if config['auxiliary']:
${config['auxiliary']}
% endif
