<%
    cfg = dispatcher.call_sync('service.haproxy.get_config')
%>\
global
    log 127.0.0.1     local0
    log 127.0.0.1     local1 notice
% if cfg['global_maxconn']:
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
% if cfg['defaults_maxconn']:
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
#    server riak1 r1s01.example.com:8081 weight 1 maxconn 1024 check
#    server riak2 r1s02.example.com:8081 weight 1 maxconn 1024 check
#    server riak3 r1s03.example.com:8081 weight 1 maxconn 1024 check
#    server riak4 r1s04.example.com:8081 weight 1 maxconn 1024 check
#    server riak5 r1s05.example.com:8081 weight 1 maxconn 1024 check
