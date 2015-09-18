<%
    import socket
    import os

    config = dispatcher.call_sync('service.ftp.get_config')

    if not os.path.exists('/var/run/proftpd'):
        os.mkdir('/var/run/proftpd')
    if not os.path.exists('/var/log/proftpd'):
        os.mkdir('/var/log/proftpd')
    for f in (
        '/var/run/proftpd/proftpd.delay',
	'/etc/hosts.allow',
	'/etc/hosts.deny',
    ):
        if not os.path.exists(f):
            open(f, 'w').close()

    with open('/var/run/proftpd/proftpd.motd', 'w+') as f:
        if config['display_login']:
	    f.write(config['display_login'] + '\n')
        else:
	    f.write('Welcome to FreeNAS FTP Server\n')

    hostname = socket.gethostname()

    tls_options = []
    if config['tls_options']:
        if 'ALLOW_CLIENT_RENEGOTIATIONS' in config['tls_options']:
	    tls_options.append('AllowClientRenegotiations')
        if 'ALLOW_DOT_LOGIN' in config['tls_options']:
	    tls_options.append('AllowDotLogin')
        if 'ALLOW_PER_USER' in config['tls_options']:
	    tls_options.append('AllowPerUser')
        if 'COMMON_NAME_REQUIRED' in config['tls_options']:
	    tls_options.append('CommonNameRequired')
        if 'ENABLE_DIAGNOSTICS' in config['tls_options']:
	    tls_options.append('EnableDiags')
        if 'EXPORT_CERTIFICATE_DATA' in config['tls_options']:
	    tls_options.append('ExportCertData')
        if 'NO_CERTIFICATE_REQUEST' in config['tls_options']:
	    tls_options.append('NoCertRequest')
        if 'NO_EMPTY_FRAGMENTS' in config['tls_options']:
	    tls_options.append('NoEmptyFragments')
        if 'NO_SESSION_REUSE_REQUIRED' in config['tls_options']:
	    tls_options.append('NoSessionReuseRequired')
        if 'STANDARD_ENV_VARS' in config['tls_options']:
	    tls_options.append('StdEnvVars')
        if 'DNS_NAME_REQUIRED' in config['tls_options']:
	    tls_options.append('dNSNameRequired')
        if 'IP_ADDRESS_REQUIRED' in config['tls_options']:
	    tls_options.append('iPAddressRequired')
    else:
        tls_options.append('NoCertRequest')

    certificate = None
    if config['tls_ssl_certificate']:
        certificate = dispatcher.call_sync('crypto.certificates.query', [('id', '=', config['tls_ssl_certificate'])], {'single': True})

%>\
<%def name="on_off(val)">\
% if val:
on
% else:
off
% endif
</%def>\

ServerName "${hostname} FTP Server"
ServerType standalone
DefaultServer on
DefaultAddress localhost
UseIPv6 on
Port ${config['port']}
User nobody
Group nogroup
Umask ${config['filemask']} ${config['dirmask']}
SyslogFacility ftp
MultilineRFC2228 off
DisplayLogin /var/run/proftpd/proftpd.motd
DeferWelcome off
TimeoutIdle ${config['timeout']}
TimeoutLogin 300
TimeoutNoTransfer 300
TimeoutStalled 3600
MaxInstances none
% if config['max_clients']:
MaxClients ${config['max_clients']}
% endif
% if config['ip_connections']:
MaxConnectionsPerHost ${config['ip_connections']}
% endif
% if config['login_attempt']:
MaxLoginAttempts ${config['login_attempt']}
% endif
DefaultTransferMode ascii
AllowForeignAddress ${on_off(config['fxp'])}
% if config['masquerade_address']:
MasqueradeAddress ${config['masquerade_address']}
% endif
IdentLookups ${on_off(config['ident'])}
UseReverseDNS ${on_off(config['reverse_dns'])}
% if config['passive_ports_min'] and config['passive_ports_max']:
PassivePorts ${config['passive_ports_min']} ${config['passive_ports_max']}
% endif

% if config['only_anonymous'] and os.path.exists(config['anonymous_path'] or ''):
<Anonymous ${config['anonymous_path']}>
  User ftp
  Group ftp
  UserAlias anonymous ftp
% if config['anon_up_bandwidth']:
  TransferRate STOR ${config['anon_up_bandwidth']}
% endif
% if config['anon_down_bandwidth']:
  TransferRate RETR ${config['anon_down_bandwidth']}
% endif
  <Limit LOGIN>
    AllowAll
  </Limit>
</Anonymous>
% endif

% if config['only_local']:
<Limit LOGIN>
  AllowAll
</Limit>
% endif

% if not config['only_anonymous'] and not config['only_local']:
<Limit LOGIN>
  AllowGroup ftp
% if config['root_login']:
  AllowGroup wheel
% endif
  DenyAll
</Limit>
% endif

<Global>
  RequireValidShell off
% if config['chroot']:
  DefaultRoot ~ !wheel
% endif
% if config['root_login']:
  RootLogin on
% endif
  AllowOverwrite on
% if config['resume']:
  AllowRetrieveRestart on
  AllowStoreRestart on
% endif
  DeleteAbortedStores off
% if config['local_up_bandwidth']:
  TransferRate STOR ${config['local_up_bandwidth']}
% endif
% if config['local_down_bandwidth']:
  TransferRate RETR ${config['local_down_bandwidth']}
% endif
  TimesGMT off
</Global>


LoadModule mod_tls.c
<IfModule mod_tls.c>
  TLSEngine on
  TLSProtocol SSLv23
  TLSOptions ${' '.join(tls_options)}
% if certificate:
  TLSRSACertificateFile "${certificate['certificate_path']}"
  TLSRSACertificateKeyFile "${certificate['privatekey_path']}"
% endif
  TLSVerifyClient off
  TLSRequired ${config['tls_policy'].lower()}
</IfModule>

<IfModule mod_ban.c>
  BanEngine off
  BanControlsACLs all allow group wheel
  BanLog /var/log/proftpd/ban.log
  BanMessage Host %a has been banned
# -m "mod_ban/rule"
# -v "concat('  BanOnEvent ',event,' ',occurrence,'/',timeinterval,' ',expire)" -n
# -b
  BanTable /var/run/proftpd/ban.tab
</IfModule>


<IfModule mod_delay.c>
  DelayEngine on
  DelayTable /var/run/proftpd/proftpd.delay
</IfModule>

<IfModule mod_wrap.c>
  TCPAccessFiles /etc/hosts.allow /etc/hosts.deny
  TCPAccessSyslogLevels info warn
  TCPServiceName ftpd
</ifModule>

% if config['auxiliary']:
${config['auxiliary']}
% endif
