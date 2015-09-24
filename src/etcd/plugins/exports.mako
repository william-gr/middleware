<%
    config = dispatcher.call_sync('service.nfs.get_config')

    def opts(share):
        if not 'properties' in share:
            return ''

        result = []
        properties = share['properties']

        if properties.get('alldirs'):
            result.append('-alldirs')

        if properties.get('read_only'):
            result.append('-ro')

        if properties.get('security'):
            result.append('-sec={0}'.format(':'.join(properties['security'])))

        if properties.get('mapall_user'):
            result.append('-mapall={0}'.format(properties['mapall_user']))

        elif properties.get('maproot_user'):
            result.append('-maproot={0}'.format(properties['maproot_user']))

        for host in properties.get('hosts', []):
            if '/' in host:
                result.append('-network={0}'.format(host))
                continue

            result.append(host)

        return ' '.join(result)
%>\
% if config.get('v4'):
% if confi.get('v4_kerberos'):
V4: / -sec=krb5:krb5i:krb5p
% else:
V4: / -sec=sys:krb5:krb5i:krb5p
% endif
% endif
% for share in dispatcher.call_sync("shares.query", [("type", "=", "nfs")]):
${share["target"]} ${opts(share)}
% endfor