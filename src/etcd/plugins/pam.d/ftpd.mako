#
# $FreeBSD$
#
# PAM configuration for the "ftpd" service
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
auth		sufficient	pam_opie.so		no_warn no_fake_prompts
auth		requisite	pam_opieaccess.so	no_warn allow_local
% if ds_type == "activedirectory":
auth		sufficient	/usr/local/lib/pam_winbind.so silent try_first_pass krb5_auth krb5_ccache_type=FILE
% elif ds_tyoe == "ldap":
auth		sufficient	/usr/local/lib/pam_sss.so ignore_authinfo_unavail
% endif
#auth		sufficient	pam_krb5.so		no_warn
#auth		sufficient	pam_ssh.so		no_warn try_first_pass
auth		required	pam_unix.so		no_warn try_first_pass

# account
account		required	pam_nologin.so
% if ds_type == "activedirectory":
account		sufficient	/usr/local/lib/pam_winbind.so silent krb5_auth krb5_ccache_type=FILE
% elif ds_tyoe == "ldap":
account		sufficient	/usr/local/lib/pam_sss.so ignore_authinfo_unavail
% endif
#account	required	pam_krb5.so
account		required	pam_unix.so

# session
session		required	pam_permit.so
% if ds_type == "activedirectory" or ds_type == "ldap":
session		required	/usr/local/lib/pam_mkhomedir.so
% endif
