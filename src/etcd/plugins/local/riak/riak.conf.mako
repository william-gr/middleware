<%
    cfg = dispatcher.call_sync('service.riak.get_config')
%>\
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
nodename = ${cfg['nodename']}@${cfg['node_ip']}
% endif
distributed_cookie = riak
erlang.async_threads = 64
erlang.max_ports = 65536
dtrace = off
platform_bin_dir = /usr/local/sbin
platform_data_dir = /var/db/riak
platform_etc_dir = /usr/local/etc/riak
platform_lib_dir = /usr/local/lib/riak/lib
platform_log_dir = /var/log/riak
% if cfg['listener_http_internal'] and cfg['listener_http_internal_port']:
listener.http.internal = ${cfg['listener_http_internal']}:${cfg['listener_http_internal_port']}
% endif
% if cfg['listener_protobuf_internal'] and cfg['listener_protobuf_internal_port']:
listener.protobuf.internal = ${cfg['listener_protobuf_internal']}:${cfg['listener_protobuf_internal_port']}
% endif
% if cfg['listener_https_internal'] and cfg['listener_https_internal_port']:
listener.https.internal = ${cfg['listener_https_internal']}:${cfg['listener_https_internal_port']}
% endif
anti_entropy = active
storage_backend = ${cfg['storage_backend'].lower()}
buckets.default.allow_mult = ${"true" if cfg['buckets_default_allow_multi'] else "false"}
object.format = 1
object.size.warning_threshold = ${cfg['object_size_warning_threshold']}
object.size.maximum = ${cfg['object_size_maximum']}
object.siblings.warning_threshold = 25
object.siblings.maximum = 100
bitcask.data_root = $(platform_data_dir)/bitcask
bitcask.io_mode = erlang
riak_control = ${"on" if cfg['riak_control'] else "off"}
riak_control.auth.mode = off
riak_control.auth.user.admin.password = pass
leveldb.maximum_memory.percent = 70
search = off
search.solr.start_timeout = 30s
search.solr.port = 8093
search.solr.jmx_port = 8985
search.solr.jvm_options = -d64 -Xms1g -Xmx1g -XX:+UseStringCache -XX:+UseCompressedOops
ssl.keyfile = $(platform_etc_dir)/key.pem
ssl.certfile = $(platform_etc_dir)/cert.pem
ssl.cacertfile = $(platform_etc_dir)/cacertfile.pem
dtrace = off
