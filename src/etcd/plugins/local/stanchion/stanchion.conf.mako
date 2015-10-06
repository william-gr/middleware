<%
    cfg = dispatcher.call_sync('service.stanchion.get_config')
%>\
% if cfg['listener_ip'] and cfg['listener_port']:
listener =  ${cfg['listener_ip'].lower()}:${cfg['listener_port']}
% endif
% if cfg['riak_host_ip'] and cfg['riak_host_port']:
riak_host = ${cfg['riak_host_ip']}:${cfg['riak_host_port']}
% endif
admin.key = ${cfg['admin_key']}
admin.secret = ${cfg['admin_secret']}
platform_bin_dir = /usr/local/sbin
platform_data_dir = /var/db/stanchion
platform_etc_dir = /usr/local/etc/stanchion
platform_lib_dir = /usr/local/lib/stanchion/lib
platform_log_dir = /var/log/stanchion
log.console = file
log.console.level = ${cfg['log_console_level'].lower()}
log.console.file = $(platform_log_dir)/console.log
log.error.file = $(platform_log_dir)/error.log
log.syslog = off
log.crash = on
log.crash.file = $(platform_log_dir)/crash.log
log.crash.maximum_message_size = 64KB
log.crash.size = 10MB
log.crash.rotation = $D0
log.crash.rotation.keep = 5
% if cfg['nodename'] and cfg['node_ip']:
nodename = ${cfg['nodename'].lower()}@${cfg['node_ip'].lower()}
% endif
distributed_cookie = riak
erlang.async_threads = 64
erlang.max_ports = 65536
