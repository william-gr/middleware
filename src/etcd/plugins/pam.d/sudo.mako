#
# $FreeBSD: src/etc/pam.d/sudo,v 1.18 2009/10/05 09:28:54 des Exp $
#
# PAM configuration for the "sudo" service
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
% if ds_tyoe == "ldap":
auth		sufficient	/usr/local/lib/pam_sss.so 
% endif
auth		required	pam_unix.so		no_warn try_first_pass

# account
account		required	pam_nologin.so
account		required	pam_login_access.so
% if ds_tyoe == "ldap":
account		sufficient	/usr/local/lib/pam_sss.so 
% endif
account		required	pam_unix.so

# session
session		required	pam_permit.so
% if ds_type == "ldap":
session		required	/usr/local/lib/pam_mkhomedir.so
% endif

# password
% if ds_tyoe == "ldap":
password	sufficient	/usr/local/lib/pam_sss.so use_authtok
% endif
password	required	pam_unix.so		no_warn try_first_pass
