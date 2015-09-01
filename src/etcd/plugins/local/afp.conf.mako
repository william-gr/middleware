<%
    import os
    import sys
    if '/usr/local/www' not in sys.path:
        sys.path.append('/usr/local/www')

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freenasUI.settings')
    if 'DJANGO_LOGGING_DISABLE' not in os.environ:
        os.environ['DJANGO_LOGGING_DISABLE'] = 'true'

    # Make sure to load all modules
    from django.db.models.loading import cache
    cache.get_apps()

    from freenasUI.sharing.models import AFP_Share

    afp = dispatcher.call_sync('service.afp.get_config')

    uam_list = ['uams_dhx.so', 'uams_dhx2.so']
    if afp['guest_enable']:
        uam_list.append('uams_guest.so')

%>\
<%def name="opt(name, val)">\
% if val:
% if type(val) is list:
    ${name} = ${", ".join(val)}
% else:
    ${name} = ${val}
% endif
% endif
</%def>\
\
[Global]
    uam list = ${' '.join(uam_list)}
% if afp['guest_user']:
    guest account = ${afp['guest_user']}
% endif
% if not afp['bind_addresses']:
    afp listen = 0.0.0.0
% else:
    afp listen = ${' '.join(afp['bind_addresses'])}
% endif
    max connections = ${afp['connections_limit']}
    mimic model = RackMac
% if afp['dbpath']:
    vol dbnest = no
    vol dbpath = ${afp['dbpath']}
% else:
    vol dbnest = yes
% endif
% if afp['auxiliary']:
    ${afp['auxiliary']}
% endif

% if afp['homedir_enable']:
[Homes]
    basedir regex = ${afp['homedir_path']}
%   if afp['homedir_name']:
    home name = ${afp['homedir_name']}
%   endif
% endif

## Comment out this while this is handled by old GUI
##% for share in dispatcher.call_sync("shares.query", [("type", "=", "afp")]):
##[${share["id"]}]
##${opt("path", share["target"])}\
##${opt("invalid users", share["properties"].get("users-allow"))}\
##${opt("hosts allow", share["properties"].get("users-deny"))}\
##${opt("hosts deny", share["properties"].get("hosts-allow"))}\
##${opt("rolist", share["properties"].get("ro-list"))}\
##${opt("rwlist", share["properties"].get("rw-list"))}\
##${opt("time machine", "yes" if share["properties"].get("time-machine") else "no")}\
##${opt("read only", "yes" if share["properties"].get("read-only") else "no")}\
##% endfor
% for share in AFP_Share.objects.all():
[${share.afp_name}]
    path = ${share.afp_path}
% if share.afp_allow:
    valid users = ${share.afp_allow}
% endif
% if share.afp_deny:
    invalid users = ${share.afp_deny}
% endif
% if share.afp_hostsallow:
    hosts allow = ${share.afp_hostsallow}
% endif
% if share.afp_hostsdeny:
    hosts deny = ${share.afp_hostsdeny}
% endif
% if share.afp_ro:
    rolist = ${share.afp_ro}
% endif
% if share.afp_rw:
    rwlist = ${share.afp_rw}
% endif
% if share.afp_timemachine:
    time machine = yes
% endif
% if not share.afp_nodev:
    cnid dev = no
% endif
% if share.afp_nostat:
    stat vol = no
% endif
% if not share.afp_upriv:
    unix priv = no
% else:
%   if share.afp_fperm:
    file perm = ${share.afp_fperm}
%   endif
%   if share.afp_dperm:
    directory perm = ${share.afp_dperm}
%   endif
%   if share.afp_umask:
    umask = ${share.afp_umask}
%   endif
% endif
    veto files = .windows/.mac/
% endfor
