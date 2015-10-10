<%
    cfg = dispatcher.call_sync('service.haproxy.get_config')
%>\
global
    log 127.0.0.1     local0
    log 127.0.0.1     local1 notice
% if cfg['global_maxconn'] 
    maxconn           ${cfg['global_maxconn']}
% endif
    spread-checks     5
    daemon

defaults
    log               global
    option            dontlognull
    option            redispatch
    option            allbackups
    no option         httpclose
    retries           3
% if cfg['defaults_maxconn'] 
    maxconn           ${cfg['defaults_maxconn']}
% endif
    timeout connect   5000
    timeout client    5000
    timeout server    5000

frontend riak_cs
% if cfg['http_ip'] and cfg['http_port']:
    bind              ${cfg['http_ip'].lower()}:${cfg['http_port']}
% endif
    # Example bind for SSL termination
% if cfg['https_ip'] and cfg['https_port']:
    # bind            ${cfg['https_ip'].lower()}:${cfg['https_port']} ssl crt /usr/local/etc/data.pem
% endif
% if cfg['frontend_mode']:
    mode              ${cfg['frontend_mode'].lower()}
% endif
    option            httplog
    capture           request header Host len 64
#    acl good_ips      src -f /usr/local/etc/gip.lst
#    block if          !good_ips
#    use_backend       riak_cs_backend if good_ips

backend riak_cs_backend
% if cfg['backend_mode']:
    mode              ${cfg['backend_mode'].lower()}
% endif
    balance           roundrobin
    # Ping Riak CS to determine health
    option            httpchk GET /riak-cs/ping
    timeout connect 60s
    timeout http-request 60s
% if cfg['backend_server_one_name'] and cfg['backend_server_one_host']:
    server ${cfg['backend_server_one_name'].lower()} ${cfg['backend_server_one_host'].lower()}:${cfg['backend_server_one_port']} weight ${cfg['backend_server_one_weight']} maxconn 1024 check
% endif
% if cfg['backend_server_two_name'] and cfg['backend_server_two_host']:
    server ${cfg['backend_server_two_name'].lower()} ${cfg['backend_server_two_host'].lower()}:${cfg['backend_server_two_port']} weight ${cfg['backend_server_two_weight']} maxconn 1024 check
% endif
% if cfg['backend_server_three_name'] and cfg['backend_server_three_host']:
    server ${cfg['backend_server_three_name'].lower()} ${cfg['backend_server_three_host'].lower()}:${cfg['backend_server_three_port']} weight ${cfg['backend_server_three_weight']} maxconn 1024 check
% endif
% if cfg['backend_server_four_name'] and cfg['backend_server_four_host']:
    server ${cfg['backend_server_four_name'].lower()} ${cfg['backend_server_four_host'].lower()}:${cfg['backend_server_four_port']} weight ${cfg['backend_server_four_weight']} maxconn 1024 check
% endif
% if cfg['backend_server_five_name'] and cfg['backend_server_five_host']:
    server ${cfg['backend_server_five_name'].lower()} ${cfg['backend_server_five_host'].lower()}:${cfg['backend_server_five_port']} weight ${cfg['backend_server_five_weight']} maxconn 1024 check
% endif
#   server riak5 r1s05.example.com:8081 weight 1 maxconn 1024 check
