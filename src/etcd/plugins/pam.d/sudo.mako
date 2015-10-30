#
# $FreeBSD: src/etc/pam.d/sudo,v 1.18 2009/10/05 09:28:54 des Exp $
#
# PAM configuration for the "sudo" service
#

# auth
auth		sufficient	pam_opie.so		no_warn no_fake_prompts
auth		requisite	pam_opieaccess.so	no_warn allow_local
auth		required	pam_unix.so		no_warn try_first_pass

# account
account		required	pam_nologin.so
account		required	pam_login_access.so
account		required	pam_unix.so

# session
session		required	pam_permit.so

# password
password	required	pam_unix.so		no_warn try_first_pass
