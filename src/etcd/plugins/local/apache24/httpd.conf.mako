<%
    import os
    import pwd

    cfg = dispatcher.call_sync('service.webdav.get_config')

    certificate = None
    if cfg['certificate']:
        certificate = dispatcher.call_sync('crypto.certificates.query', [('id', '=', cfg['certificate'])], {'single': True})

    auth_file = '/usr/local/etc/apache24/webdavauth'

    if cfg['authentication'] == 'BASIC':
        import imp
	htpasswd = imp.load_source('htpasswd', '/usr/local/bin/htpasswd.py')
	passwdfile = htpasswd.HtpasswdFile(auth_file, create=True)
	passwdfile.update('webdav', cfg['password'])
    else:
        import hashlib
	hexdigest = hashlib.md5('webdav:webdav:{0}'.format(cfg['password'])).hexdigest()
	with open(auth_file, 'w') as f:
	    f.write('webdav:webdav:{0}\n'.format(hexdigest))

    user = pwd.getpwnam('webdav')
    os.chown(auth_file, user.pw_uid, user.pw_gid)
    os.chmod(auth_file, 0640)

%>\
# Generating apache general httpd.conf
# The absolutely necessary modules
LoadModule authn_file_module libexec/apache24/mod_authn_file.so
LoadModule authn_core_module libexec/apache24/mod_authn_core.so
LoadModule authz_user_module libexec/apache24/mod_authz_user.so
LoadModule authz_core_module libexec/apache24/mod_authz_core.so
LoadModule alias_module libexec/apache24/mod_alias.so
LoadModule mpm_itk_module libexec/apache24/mod_mpm_itk.so
LoadModule unixd_module libexec/apache24/mod_unixd.so
LoadModule auth_basic_module libexec/apache24/mod_auth_basic.so
LoadModule auth_digest_module libexec/apache24/mod_auth_digest.so
LoadModule setenvif_module libexec/apache24/mod_setenvif.so
LoadModule dav_module libexec/apache24/mod_dav.so
LoadModule dav_fs_module libexec/apache24/mod_dav_fs.so
LoadModule allowmethods_module libexec/apache24/mod_allowmethods.so
LoadModule ssl_module libexec/apache24/mod_ssl.so
LoadModule socache_shmcb_module libexec/apache24/mod_socache_shmcb.so

# The still deciding whether or not to keep thse modules or not
LoadModule authz_host_module libexec/apache24/mod_authz_host.so
LoadModule authz_groupfile_module libexec/apache24/mod_authz_groupfile.so
LoadModule access_compat_module libexec/apache24/mod_access_compat.so
LoadModule reqtimeout_module libexec/apache24/mod_reqtimeout.so
LoadModule filter_module libexec/apache24/mod_filter.so
LoadModule mime_module libexec/apache24/mod_mime.so
LoadModule log_config_module libexec/apache24/mod_log_config.so
LoadModule env_module libexec/apache24/mod_env.so
LoadModule headers_module libexec/apache24/mod_headers.so
#LoadModule version_module libexec/apache24/mod_version.so
LoadModule status_module libexec/apache24/mod_status.so
LoadModule autoindex_module libexec/apache24/mod_autoindex.so
LoadModule dir_module libexec/apache24/mod_dir.so

# Third party modules
IncludeOptional etc/apache24/modules.d/[0-9][0-9][0-9]_*.conf
ServerName localhost

# Limiting the number of idle threads
# see: http://httpd.apache.org/docs/current/mod/prefork.html#MinSpareServers
<IfModule mpm_itk_module>
        StartServers 1
        MinSpareServers 1
</IfModule>

<IfModule unixd_module>
User www
Group www
</IfModule>

<IfModule dir_module>
    DirectoryIndex index.html
</IfModule>

<Files ".ht*">
    Require all denied
</Files>

ErrorLog "/var/log/httpd-error.log"
LogLevel warn

<IfModule log_config_module>
    LogFormat "%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-Agent}i\"" combined
    LogFormat "%h %l %u %t \"%r\" %>s %b" common
    <IfModule logio_module>
      LogFormat "%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-Agent}i\" %I %O" combinedio
    </IfModule>
    CustomLog "/var/log/httpd-access.log" common

</IfModule>

<IfModule alias_module>
    ScriptAlias /cgi-bin/ "/usr/local/www/apache24/cgi-bin/"
</IfModule>

<IfModule mime_module>
    #
    # TypesConfig points to the file containing the list of mappings from
    # filename extension to MIME-type.
    #
    TypesConfig etc/apache24/mime.types

    #
    # AddType allows you to add to or override the MIME configuration
    # file specified in TypesConfig for specific file types.
    #
    #AddType application/x-gzip .tgz
    #
    # AddEncoding allows you to have certain browsers uncompress
    # information on the fly. Note: Not all browsers support this.
    #
    #AddEncoding x-compress .Z
    #AddEncoding x-gzip .gz .tgz
    #
    # If the AddEncoding directives above are commented-out, then you
    # probably should define those extensions to indicate media types:
    #
    AddType application/x-compress .Z
    AddType application/x-gzip .gz .tgz

    #
    # AddHandler allows you to map certain file extensions to "handlers":
    # actions unrelated to filetype. These can be either built into the server
    # or added with the Action directive (see below)
    #
    # To use CGI scripts outside of ScriptAliased directories:
    # (You will also need to add "ExecCGI" to the "Options" directive.)
    #
    #AddHandler cgi-script .cgi

    # For type maps (negotiated resources):
    #AddHandler type-map var

    #
    # Filters allow you to process content before it is sent to the client.
    #
    # To parse .shtml files for server-side includes (SSI):
    # (You will also need to add "Includes" to the "Options" directive.)
    #
    #AddType text/html .shtml
    #AddOutputFilter INCLUDES .shtml
</IfModule>

# Secure (SSL/TLS) connections
#Include etc/apache24/extra/httpd-ssl.conf
#
# Note: The following must must be present to support
#       starting without SSL on platforms with no /dev/random equivalent
#       but a statically compiled-in mod_ssl.
#
<IfModule ssl_module>
SSLRandomSeed startup builtin
SSLRandomSeed connect builtin
SSLProtocol +TLSv1 +TLSv1.1 +TLSv1.2
</IfModule>

<%def name="webdav_block(cfg, field, certificate=None)">
Listen ${cfg[field]}

% if certificate:
  SSLEngine on
  SSLCertificateFile "${certificate['certificate_path']}"
  SSLCertificateKeyFile "${certificate['privatekey_path']}"
  SSLProtocol +TLSv1 +TLSv1.1 +TLSv1.2
  SSLCipherSuite HIGH:MEDIUM
% endif

<VirtualHost *:${cfg[field]}>
  DavLockDB "/etc/local/apache24/var/DavLock"
  AssignUserId webdav webdav

  <Directory />
    AuthType ${cfg['authentication'].lower()}
    AuthName webdav
    AuthUserFile "/usr/local/etc/apache24/webdavauth"
% if cfg['authentication'] == 'DIGEST':
    AuthDigestProvider file
% endif
    Require valid-user

    Dav On
    IndexOptions Charset=utf-8
    AddDefaultCharset UTF-8
    AllowOverride None
    Order allow,deny
    Allow from all
    Options Indexes FollowSymLinks
  </Directory>

## Shares go here
##for share in webshares:
##    temp_path = """ "%s" """ % share.webdav_path
##    f.write("\t   Alias /"+share.webdav_name+temp_path+"\n")
##    f.write("\t   <Directory "+temp_path+">\n")
##    f.write("\t   </Directory>\n")
##    if share.webdav_ro == 1:
##            f.write("\t   <Location /" +
##                    share.webdav_name +
##                    ">\n\t\t AllowMethods GET OPTIONS PROPFIND\n\t   </Locati
##
##    if share.webdav_perm:
##        _pipeopen("chown -R webdav:webdav %s" % share.webdav_path)

  # The following directives disable redirects on non-GET requests for
  # a directory that does not include the trailing slash.  This fixes a
  # problem with several clients that do not appropriately handle
  # redirects for folders with DAV methods.
  BrowserMatch "Microsoft Data Access Internet Publishing Provider" redirect-carefully
  BrowserMatch "MS FrontPage" redirect-carefully
  BrowserMatch "^WebDrive" redirect-carefully
  BrowserMatch "^WebDAVFS/1.[01234]" redirect-carefully
  BrowserMatch "^gnome-vfs/1.0" redirect-carefully
  BrowserMatch "^XML Spy" redirect-carefully
  BrowserMatch "^Dreamweaver-WebDAV-SCM1" redirect-carefully
  BrowserMatch " Konqueror/4" redirect-carefully
</VirtualHost>
</%def>

% if 'HTTP' in cfg['protocol']:
${webdav_block(cfg, 'http_port')}
% endif

% if 'HTTPS' in cfg['protocol']:
${webdav_block(cfg, 'https_port', certificate)}
% endif
