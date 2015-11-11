<%
    realms = {}
    directoryservices = dispatcher.call_sync('directoryservices.query')
    for ds in directoryservices:
        if 'configure_kerberos' in ds and ds['configure_kerberos'] == True:
            res = dispatcher.call_task_sync('directoryservice.get', [ ds['id'], 'kdcs' ])
            result = res.get('result', None)
            if not result:
                continue

            # XXX need to handle multiple records and best host
            first_srv_record = result[0]
            parts = first_srv_record.split()
            if len(parts) >= 3:
                kdc = parts[3]
                parts = kdc.split('.')
                kdc = ".".join(parts[0:len(parts)-1])
                realms[ds['domain'].upper()] = kdc
%>

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

