<%
    config = dispatcher.call_sync('service.smartd.get_config')
%>\
DEVICESCAN -m root
