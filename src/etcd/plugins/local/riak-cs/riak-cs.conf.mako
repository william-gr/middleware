<%
    cfg = dispatcher.call_sync('service.riak_cs.get_config')
%>\
% if cfg['listener_ip'] and cfg['listener_ip_port']:
listener = ${cfg['listener_ip'].lower()}:${cfg['listener_ip_port'].lower()}
% endif 
% if cfg['riak_host_ip'] and cfg['riak_host_ip_port']:
riak_host = ${cfg['riak_host_ip'].lower()}:${cfg['riak_host_ip_port'].lower()}
% endif 
% if cfg['stanchion_host_ip'] and cfg['stanchion_host_ip_port']:
stanchion_host = ${cfg['stanchion_host_ip'].lower()}:${cfg['stanchion_host_ip_port'].lower()}
% endif 
stanchion.ssl = off
anonymous_user_creation =  ${"on" if cfg['anonymous_user_creation'] else "off"}
admin.key = ${cfg['admin_key']}
admin.secret = ${cfg['admin_secret']}
root_host = s3.amazonaws.com
pool.request.size = 128
pool.list.size = 5
max_buckets_per_user = ${cfg['max_buckets_per_user']}
trust_x_forwarded_for = off
gc.leeway_period = 24h
gc.interval = 15m
gc.retry_interval = 6h
stats.access.flush_factor = 1
stats.access.flush_size = 1000000
stats.access.archive_period = 1h
stats.access.archiver.max_backlog = 2
stats.access.archiver.max_workers = 2
stats.storage.archive_period = 1d
stats.usage_request_limit = 744
server.name = Riak CS
log.access = on
log.access.dir = $(platform_log_dir)
cs_version = 10300
dtrace = off
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
platform_log_dir = /var/log/riak-cs
% if cfg['nodename'] and cfg['node_ip']:
nodename = ${cfg['nodename'].lower()}@${cfg['node_ip'].lower()}
% endif
distributed_cookie = riak
erlang.async_threads = 64
erlang.max_ports = 65536
