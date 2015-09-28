<%
    ssh_config = dispatcher.call_sync('service.ssh.get_config')
%>\
Subsystem sftp /usr/libexec/sftp-server -l ${ssh_config['sftp_log_level']} -f ${ssh_config['sftp_log_facility']}
Protocol 2
UseDNS no
ChallengeResponseAuthentication no
ClientAliveCountMax 3
ClientAliveInterval 15
NoneEnabled yes
Port ${ssh_config['port']}
PermitRootLogin ${"yes" if ssh_config['permit_root_login'] else "without-password"}
AllowTcpForwarding ${"yes" if ssh_config['allow_port_forwarding'] else "no"}
Compression ${"delayed" if ssh_config['compression'] else "no"}
PasswordAuthentication ${"yes" if ssh_config['allow_password_auth'] else "no"}
PubkeyAuthentication ${"yes" if ssh_config['allow_pubkey_auth'] else "no"}
% if ssh_config['auxiliary']:
${ssh_config['auxiliary']}
% endif
