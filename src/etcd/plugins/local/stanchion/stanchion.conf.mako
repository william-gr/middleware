<%
    cfg = dispatcher.call_sync('service.stanchion.get_config')
%>\
## listen port and IP address
## 
## Default: 192.168.1.37:8085
## 
## Acceptable values:
##   - an IP/port pair, e.g. 192.168.1.37:10011
% if cfg['listener_ip'] and cfg['listener_port']:
listener =  ${cfg['listener_ip'].lower()}:${cfg['listener_port']}
% endif

## Default cert location for https can be overridden
## with the ssl config variable, for example:
## 
## Acceptable values:
##   - the path to a file
## ssl.certfile = /usr/local/etc/stanchion/cert.pem

## Default key location for https can be overridden with the ssl
## config variable, for example:
## 
## Acceptable values:
##   - the path to a file
## ssl.keyfile = usr/local/etc/stanchion/key.pem

## Riak IP address and port number where Stanchion connects
## 
## Default: 192.168.1.37:8087
## 
## Acceptable values:
##   - an IP/port pair, e.g. 192.168.1.37:10011
% if cfg['riak_host_ip'] and cfg['riak_host_ip_port']:
riak_host = ${cfg['riak_host_ip']}:${cfg['riak_host_ip_port']}
% endif

## Admin user credentials. The credentials specified here must
## match the admin credentials specified in the riak-cs app.config
## for the system to function properly.
## 
## Default: admin-key
## 
## Acceptable values:
##   - text
admin.key = ${cfg['admin_key']}

##
## Default: admin-secret
##
## Acceptable values:
##   - text
admin.secret = ${cfg['admin_secret']}

## Platform-specific installation paths
## 
## Default: /usr/local/sbin
## 
## Acceptable values:
##   - the path to a directory
platform_bin_dir = /usr/local/sbin

## 
## Default: /var/db/stanchion
## 
## Acceptable values:
##   - the path to a directory
platform_data_dir = /var/db/stanchion

## 
## Default: /usr/local/etc/stanchion
## 
## Acceptable values:
##   - the path to a directory
platform_etc_dir = /usr/local/etc/stanchion

## 
## Default: /usr/local/lib/stanchion/lib
## 
## Acceptable values:
##   - the path to a directory
platform_lib_dir = /usr/local/lib/stanchion/lib

## 
## Default: /var/log/stanchion
## 
## Acceptable values:
##   - the path to a directory
platform_log_dir = /var/log/stanchion

## Where to emit the default log messages (typically at 'info'
## severity):
## off: disabled
## file: the file specified by log.console.file
## console: to standard output (seen when using `riak attach-direct`)
## both: log.console.file and standard out.
## 
## Default: file
## 
## Acceptable values:
##   - one of: off, file, console, both
log.console = file

## The severity level of the console log, default is 'info'.
## 
## Default: info
## 
## Acceptable values:
##   - one of: debug, info, notice, warning, error, critical, alert, emergency, none
log.console.level = ${cfg['log_console_level'].lower()}

## When 'log.console' is set to 'file' or 'both', the file where
## console messages will be logged.
## 
## Default: $(platform_log_dir)/console.log
## 
## Acceptable values:
##   - the path to a file
log.console.file = $(platform_log_dir)/console.log

## The file where error messages will be logged.
## 
## Default: $(platform_log_dir)/error.log
## 
## Acceptable values:
##   - the path to a file
log.error.file = $(platform_log_dir)/error.log

## When set to 'on', enables log output to syslog.
## 
## Default: off
## 
## Acceptable values:
##   - on or off
log.syslog = off

## Whether to enable the crash log.
## 
## Default: on
## 
## Acceptable values:
##   - on or off
log.crash = on

## If the crash log is enabled, the file where its messages will
## be written.
## 
## Default: $(platform_log_dir)/crash.log
## 
## Acceptable values:
##   - the path to a file
log.crash.file = $(platform_log_dir)/crash.log

## Maximum size in bytes of individual messages in the crash log
## 
## Default: 64KB
## 
## Acceptable values:
##   - a byte size with units, e.g. 10GB
log.crash.maximum_message_size = 64KB

## Maximum size of the crash log in bytes, before it is rotated
## 
## Default: 10MB
## 
## Acceptable values:
##   - a byte size with units, e.g. 10GB
log.crash.size = 10MB

## The schedule on which to rotate the crash log.  For more
## information see:
## https://github.com/basho/lager/blob/master/README.md#internal-log-rotation
## 
## Default: $D0
## 
## Acceptable values:
##   - text
log.crash.rotation = $D0

## The number of rotated crash logs to keep. When set to
## 'current', only the current open log file is kept.
## 
## Default: 5
## 
## Acceptable values:
##   - an integer
##   - the text "current"
log.crash.rotation.keep = 5

## Name of the Erlang node
## 
## Default: stanchion@192.168.1.37
## 
## Acceptable values:
##   - text
% if cfg['nodename'] and cfg['node_ip']:
nodename = ${cfg['nodename'].lower()}@${cfg['node_ip'].lower()}
% endif

## Cookie for distributed node communication.  All nodes in the
## same cluster should use the same cookie or they will not be able to
## communicate.
## 
## Default: riak
## 
## Acceptable values:
##   - text
distributed_cookie = riak

## Sets the number of threads in async thread pool, valid range
## is 0-1024. If thread support is available, the default is 64.
## More information at: http://erlang.org/doc/man/erl.html
## 
## Default: 64
## 
## Acceptable values:
##   - an integer
erlang.async_threads = 64

## The number of concurrent ports/sockets
## Valid range is 1024-134217727
## 
## Default: 65536
## 
## Acceptable values:
##   - an integer
erlang.max_ports = 65536

## Set scheduler forced wakeup interval. All run queues will be
## scanned each Interval milliseconds. While there are sleeping
## schedulers in the system, one scheduler will be woken for each
## non-empty run queue found. An Interval of zero disables this
## feature, which also is the default.
## This feature is a workaround for lengthy executing native code, and
## native code that do not bump reductions properly.
## More information: http://www.erlang.org/doc/man/erl.html#+sfwi
## 
## Default: 500
## 
## Acceptable values:
##   - an integer
## erlang.schedulers.force_wakeup_interval = 500

## Enable or disable scheduler compaction of load. By default
## scheduler compaction of load is enabled. When enabled, load
## balancing will strive for a load distribution which causes as many
## scheduler threads as possible to be fully loaded (i.e., not run out
## of work). This is accomplished by migrating load (e.g. runnable
## processes) into a smaller set of schedulers when schedulers
## frequently run out of work. When disabled, the frequency with which
## schedulers run out of work will not be taken into account by the
## load balancing logic.
## More information: http://www.erlang.org/doc/man/erl.html#+scl
## 
## Default: false
## 
## Acceptable values:
##   - one of: true, false
## erlang.schedulers.compaction_of_load = false

## Enable or disable scheduler utilization balancing of load. By
## default scheduler utilization balancing is disabled and instead
## scheduler compaction of load is enabled which will strive for a
## load distribution which causes as many scheduler threads as
## possible to be fully loaded (i.e., not run out of work). When
## scheduler utilization balancing is enabled the system will instead
## try to balance scheduler utilization between schedulers. That is,
## strive for equal scheduler utilization on all schedulers.
## More information: http://www.erlang.org/doc/man/erl.html#+sub
## 
## Acceptable values:
##   - one of: true, false
## erlang.schedulers.utilization_balancing = true

