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
            if 'mapall_group' in properties:
                result.append('-mapall={mapall_user}:{mapall_group}'.format(**properties))
            else:
                result.append('-mapall={mapall_user}'.format(**properties))

        elif properties.get('maproot_user'):
            if 'maproot_group' in properties:
                result.append('-maproot={maroot_user}:{maproot_group}'.format(**properties))
            else:
                result.append('-maproot={maroot_user}'.format(**properties))

        for host in properties.get('hosts', []):
            if '/' in host:
                result.append('-network={0}'.format(host))
                continue

            result.append(host)

        return ' '.join(result)
%>\
% if config.get('v4'):
% if config.get('v4_kerberos'):
V4: / -sec=krb5:krb5i:krb5p
% else:
V4: / -sec=sys:krb5:krb5i:krb5p
% endif
% endif
% for share in dispatcher.call_sync("shares.query", [("type", "=", "nfs")]):
${share["target"]} ${opts(share)}
% endfor