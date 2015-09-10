<%
    dyndns = dispatcher.call_sync('service.dyndns.get_config')
%>\
% if dyndns.get('provider'):
--dyndns_system ${dyndns['provider']} 
% endif\
% if dyndns.get('ipserver'):
--ip_server_name ${dyndns['ipserver']} 
% endif\
% if dyndns.get('update_period'):
--update_period_sec ${dyndns['update_period']} 
% endif\
% if dyndns.get('force_update_period'):
--forced_update_period ${dyndns['force_update_period']} 
% endif\
% if dyndns.get('auxiliary'):
${dyndns['auxiliary']} 
% endif\
--background --syslog --username ${dyndns['username']} --password ${dyndns['password']} --alias ${dyndns['domain']}
