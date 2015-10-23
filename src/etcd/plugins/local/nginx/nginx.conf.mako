user www;
pid /var/run/nginx.pid;
error_log /var/log/nginx-error.log warn;

events {
    worker_connections 1024;
}

http {
    include mime.types;
    default_type application/octet-stream;

    # reserve 1MB under the name 'proxied' to track uploads
    upload_progress proxied 1m;

    sendfile on;
    client_max_body_size 500m;
    keepalive_timeout 65;

    client_body_temp_path /var/tmp/firmware;

    server {
% if config.get("service.nginx.http.enable"):
    % for addr in config.get("service.nginx.listen"):
        listen ${addr}:${config.get("service.nginx.http.port")};
    % endfor
% endif
<%

    cert_id = config.get('service.nginx.https.certificate')
    certificate = dispatcher.call_sync(
        'crypto.certificates.query', [('id', '=', cert_id)], {'single': True})

%>\
% if config.get("service.nginx.https.enable") and certificate:
    % for addr in config.get("service.nginx.listen"):
        listen ${addr}:${config.get("service.nginx.https.port")} default_server ssl spdy;
    % endfor

        ssl_session_timeout	120m;
        ssl_session_cache	shared:ssl:16m;

        ssl_certificate ${certificate.get("certificate_path")};
        ssl_certificate_key ${certificate.get("privatekey_path")};
        ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
        ssl_prefer_server_ciphers on;
        ssl_ciphers EECDH+ECDSA+AESGCM:EECDH+aRSA+AESGCM:EECDH+ECDSA+SHA256:EECDH+aRSA+RC4:EDH+aRSA:EECDH:RC4:!aNULL:!eNULL:!LOW:!3DES:!MD5:!EXP:!PSK:!SRP:!DSS;
        add_header Strict-Transport-Security max-age=31536000;
% endif
        server_name localhost;

        location / {
            proxy_pass http://127.0.0.1:8888;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_cache_bypass $http_upgrade;
        }

        location /socket {
            proxy_pass http://127.0.0.1:5000/socket;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

    }
% if config.get("service.nginx.https.enable") and config.get("service.nginx.http.redirect_https"):
    server {
    % for addr in config.get("service.nginx.listen"):
        listen ${addr}:80;
    % endfor
        server_name localhost;
        return 307 https://$host:${config.get("service.nginx.https.port")}$request_uri;
    }
% endif
}
