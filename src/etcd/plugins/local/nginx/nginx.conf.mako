<%

    import sys
    if '/usr/local/www' not in sys.path:
        sys.path.append('/usr/local/www')
    from freenasUI import settings

    dojo_version = settings.DOJANGO_DOJO_VERSION

%>\
user www;
pid /var/run/nginx.pid;
error_log /var/log/nginx-error.log debug;

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
% if config.get("service.nginx.https.enable"):
    % for addr in config.get("service.nginx.listen"):
        listen ${addr}:${config.get("service.nginx.https.port")} default_server ssl spdy;
    % endfor

        ssl_session_timeout	120m;
	    ssl_session_cache	shared:ssl:16m;

        ssl_certificate ${config.get("service.nginx.https.ssl_cert")};
        ssl_certificate_key ${config.get("service.nginx.https.ssl_key")}
        ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
        ssl_prefer_server_ciphers on;
        ssl_ciphers EECDH+ECDSA+AESGCM:EECDH+aRSA+AESGCM:EECDH+ECDSA+SHA256:EECDH+aRSA+RC4:EDH+aRSA:EECDH:RC4:!aNULL:!eNULL:!LOW:!3DES:!MD5:!EXP:!PSK:!SRP:!DSS;
        add_header Strict-Transport-Security max-age=31536000;
% endif
        server_name localhost;

        location / {
            include fastcgi_params;
            fastcgi_pass 127.0.0.1:9042;
            fastcgi_pass_header Authorization;
            fastcgi_intercept_errors off;
            fastcgi_read_timeout 600m;
            #fastcgi_temp_path /var/tmp/firmware;
            fastcgi_param HTTPS $https;

            # track uploads in the 'proxied' zone
            # remember connections for 30s after they finished
            track_uploads proxied 30s;
        }

        location /progress {
            # report uploads tracked in the 'proxied' zone
            report_uploads proxied;
        }

        location /dojango {
            alias /usr/local/www/freenasUI/dojango;
        }

        location /static {
            alias /usr/local/www/freenasUI/static;
        }

        location /reporting/graphs {
            alias /var/db/graphs;
        }

        location /dojango/dojo-media/release/${dojo_version} {
            alias /usr/local/www/dojo;
        }

        location /docs {
                alias /usr/local/www/data/docs;
        }

    }
}
