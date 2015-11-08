[appdefaults]
	pam = {
		forwardable = true   
		ticket_lifetime = 86400
		renew_lifetime = 86400
	}
            
[libdefaults]
	dns_lookup_realm = true
	dns_lookup_kdc = true
	ticket_lifetime = 24h
	clockskew = 300
	forwardable = yes 

<%
    realms = {}
    directoryservices = dispatcher.call_sync('directoryservices.query')
    for ds in directoryservices:
        ds_id = ds['id']
        res = dispatcher.call_task_sync('directoryservice.get', [ ds_id, 'kdcs' ])
        if res and 'result' in res and res['result']:
            realm = ds['domain'].upper()

            # XXX need to handle multiple records and best host
            first_srv_record = res['result'][0]
            parts = first_srv_record.split()
            if len(parts) >= 3:
                kdc = parts[3]
                parts = kdc.split('.')
                kdc = ".".join(parts[0:len(parts)-1])
                realms[realm] = kdc
%>
[domain_realm]
% for realm in realms:
<%
    upper = realm.upper()
    lower = realm.lower()
%>
	${lower} = ${upper}
	.${lower} = ${upper}
	${upper} = ${upper}
	.${upper} = ${upper}
% endfor

[realms]
% for realm in realms:
<%
	kdc = realms[realm]
%>
	${realm} = {
		kdc = ${kdc}
	}
% endfor

[logging]
	default = SYSLOG:INFO:LOCAL7

