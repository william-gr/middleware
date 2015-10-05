127.0.0.1   localhost localhost.localdomain
::1         localhost localhost.localdomain
127.0.0.1   ${config.get("system.hostname").split(".")[0]} ${config.get("system.hostname")}
::1         ${config.get("system.hostname").split(".")[0]} ${config.get("system.hostname")}

% for host in dispatcher.call_sync("network.hosts.query"):
${host["address"]} ${host["id"]}
% endfor
