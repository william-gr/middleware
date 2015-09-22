<%
    config = dispatcher.call_sync('service.rsyncd.get_config')
    modules = dispatcher.call_sync('service.rsyncd.module.query')
%>\
use chroot = yes
max connections = 4
pid file = /var/run/rsyncd.pid
port = ${config['port']}
% if config['auxiliary']:
${config['auxiliary']}
% endif

% for module in modules:
[${module['name']}]
	path = ${module['path']}
% if module.get('max_connections'):
	max connections = ${module.get('max_connections')}
% endif
% if module.get('user'):
	uid = ${module.get('user')}
% endif
% if module.get('group'):
	gid = ${module.get('group')}
% endif
% if module.get('description'):
	comment = ${module.get('description')}
% endif
% if module.get('mode') == 'READONLY':
	write only = false
	read only = true
% elif module.get('mode') == 'WRITEONLY':
	write only = true
	read only = false
% elif module.get('mode') == 'READWRITE':
	write only = false
	read only = false
% endif
% if module.get('hosts_allow'):
	hosts allow = ${module.get('hosts_allow')}
% endif
% if module.get('hosts_deny'):
	hosts deny = ${module.get('hosts_deny')}
% endif
% if module.get('auxiliary'):
${module.get('auxiliary')}
% endif
% endfor
