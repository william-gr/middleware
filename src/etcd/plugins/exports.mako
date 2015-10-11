<%
    config = dispatcher.call_sync('service.nfs.get_config')
%>\
% if config.get('v4'):
% if config.get('v4_kerberos'):
V4: / -sec=krb5:krb5i:krb5p
% else:
V4: / -sec=sys:krb5:krb5i:krb5p
% endif
% endif
