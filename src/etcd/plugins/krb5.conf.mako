<%
    realms = {}
    directoryservices = dispatcher.call_sync('directoryservices.query')
    for ds in directoryservices:
        configure_kerberos = ds.get('configure_kerberos', False)
        if not configure_kerberos:
            continue

            kdcs = dispatcher.call_sync('directoryservices.get', ds['id'], 'kdcs')
            if not kdcs:
                continue

            # XXX need to handle multiple records and best host
            first_srv_record = kdcs[0]
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

