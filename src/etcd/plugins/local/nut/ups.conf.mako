<%
    ups = dispatcher.call_sync('service.ups.get_config')
%>\
[${ups['identifier']}]
	driver = ${ups['driver']}
	port = ${ups['driver_port']}
	desc = "${ups['description'] or ''}"
% for line in (ups['auxiliary'] or '').split('\n'):
	${line}
% endfor
