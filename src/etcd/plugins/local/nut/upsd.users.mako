<%
    import re
    ups = dispatcher.call_sync('service.ups.get_config')
%>\
[${re.sub('([$#=])', r'\\\1', ups['monitor_user'])}]
	password = ${re.sub('([$#=])', r'\\\1', ups['monitor_password'])}
	upsmon master
${ups['auxiliary_users'] or ''}
