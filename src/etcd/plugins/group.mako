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

    from freenasUI.directoryservice.models import NIS
    try:
        nis = NIS.objects.order_by('-id')[0]
    except:
        nis = NIS.objects.create()

    def get_name(id):
        user = dispatcher.call_sync('users.query', [('id', '=', id)], {'single': True})
        return user['username']

    def members(group):
        return ','.join([get_name(i) for i in group['members']])
%>\
% for group in dispatcher.call_sync("groups.query"):
${group['name']}:*:${group['id']}:${members(group)}
% endfor
% if nis.nis_enable:
+:*::
% endif
