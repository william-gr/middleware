<%
    ups = dispatcher.call_sync('service.ups.get_config')
    if ups['mode'] == 'MASTER':
        identifier = ups['identifier']
    else:
        identifier = '{0}@{1}:{2}'.format(ups['identifier'], ups['remote_host'], ups['remote_port'])
%>\
FINALDELAY ${ups['shutdown_timer']}
MONITOR ${identifier} 1 ${ups['monitor_user'].replace('#', '\#').replace('$', '\$')} ${ups['monitor_password'].replace('#', '\#').replace('$', '\$')} ${ups['mode'].lower()}
NOTIFYCMD "/usr/local/sbin/upssched"
NOTIFYFLAG ONBATT SYSLOG+WALL+EXEC
NOTIFYFLAG LOWBATT SYSLOG+WALL+EXEC
NOTIFYFLAG ONLINE SYSLOG+WALL+EXEC
NOTIFYFLAG COMMBAD SYSLOG+WALL+EXEC
NOTIFYFLAG COMMOK SYSLOG+WALL+EXEC
NOTIFYFLAG REPLBATT SYSLOG+WALL+EXEC
NOTIFYFLAG NOCOMM SYSLOG+EXEC
NOTIFYFLAG FSD SYSLOG+EXEC
NOTIFYFLAG SHUTDOWN SYSLOG+EXEC
SHUTDOWNCMD "/sbin/shutdown -p now"
POWERDOWNFLAG ${'/etc/killpower' if ups['powerdown'] else '/etc/nokillpower'}
