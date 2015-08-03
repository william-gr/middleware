<%
    import os
    import sys
    if '/usr/local/www' not in sys.path:
        sys.path.append('/usr/local/www')

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freenasUI.settings')

    # Make sure to load all modules
    from django.db.models.loading import cache
    cache.get_apps()

    from freenasUI.directoryservice.models import NIS
    try:
        nis = NIS.objects.order_by('-id')[0]
    except:
        nis = NIS.objects.create()
%>\
% for group in ds.query("groups"):
${group['name']}:*:${group['id']}:${",".join(group['members']) if 'members' in group else ""}
% endfor
% if nis.nis_enable:
+:*::
% endif
