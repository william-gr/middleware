#
# PAM configuration for the "netatalk" service
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
auth		sufficient	pam_opie.so		no_warn no_fake_prompts
auth		requisite	pam_opieaccess.so	no_warn allow_local
% if ds_type == "activedirectory":
auth		sufficient	/usr/local/lib/pam_winbind.so silent try_first_pass krb5_auth krb5_ccache_type=FILE
% elif ds_tyoe == "ldap":
auth		sufficient	/usr/local/lib/pam_sss.so 
% endif
#auth		sufficient	pam_ssh.so		no_warn try_first_pass
auth		required	pam_unix.so		no_warn try_first_pass

# account
account		required	pam_nologin.so
% if ds_type == "activedirectory":
account		sufficient	/usr/local/lib/pam_winbind.so try_first_pass krb5_auth krb5_ccache_type=FILE
% elif ds_tyoe == "ldap":
account		sufficient	/usr/local/lib/pam_sss.so 
% endif
account		required	pam_unix.so

# session
session		required	pam_permit.so
% if ds_type == "activedirectory" or ds_type == "ldap":
session		required	/usr/local/lib/pam_mkhomedir.so
% endif

# password
% if ds_type == "activedirectory":
password	sufficient	/usr/local/lib/pam_winbind.so try_first_pass krb5_auth krb5_ccache_type=FILE
% elif ds_tyoe == "ldap":
password	sufficient	/usr/local/lib/pam_sss.so use_authtok
% endif
password	required	pam_unix.so		no_warn try_first_pass
