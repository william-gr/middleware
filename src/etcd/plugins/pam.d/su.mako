#
# $FreeBSD$
#
# PAM configuration for the "su" service
#
<%
    ds_type = None

    directoryservices = dispatcher.call_sync('directoryservices.query')
    for ds in directoryservices:
        configure_pam = ds.get('configure_pam', False)
        if not configure_pam:
            continue

        ds_type = ds["type"]
%>

# auth
auth		sufficient	pam_rootok.so		no_warn
auth		sufficient	pam_self.so		no_warn
% if ds_type == "activedirectory":
auth		sufficient	/usr/local/lib/pam_winbind.so silent try_first_pass krb5_auth krb5_ccache_type=FILE
% elif ds_tyoe == "ldap":
auth		sufficient	/usr/local/lib/pam_sss.so 
% endif
auth		requisite	pam_group.so		no_warn group=wheel root_only fail_safe ruser
auth		include		system

# account
account		include		system

# session
session		required	pam_permit.so
% if ds_type == "activedirectory" or ds_type == "ldap":
session		required	/usr/local/lib/pam_mkhomedir.so
% endif
