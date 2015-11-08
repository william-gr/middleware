#
# $FreeBSD$
#
# PAM configuration for the "login" service
#
<%
    ds_type = None

    directoryservices = dispatcher.call_sync('directoryservices.query')
    for ds in directoryservices:
        if ds["configure_pam"] == True:
            ds_type = ds["type"]
            break

%>
# auth
auth		sufficient	pam_self.so		no_warn
% if ds_type == "activedirectory":
auth		sufficient	/usr/local/lib/pam_winbind.so silent try_first_pass krb5_auth krb5_ccache_type=FILE
% elif ds_tyoe == "ldap":
auth		sufficient	/usr/local/lib/pam_sss.so 
% endif
auth		include		system

# account
account		requisite	pam_securetty.so
account		required	pam_nologin.so
% if ds_type == "activedirectory":
account		sufficient	/usr/local/lib/pam_winbind.so krb5_auth krb5_ccache_type=FILE
% elif ds_tyoe == "ldap":
account		sufficient	/usr/local/lib/pam_sss.so 
% endif
account		include		system

# session
session		include		system

# password
password	include		system
