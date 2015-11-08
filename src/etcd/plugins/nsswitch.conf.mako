#
# nsswitch.conf(5) - name service switch configuration file
# $FreeBSD$
#
<%
    passwd_source = "files"
    group_source = "files"

    directoryservices = dispatcher.call_sync('directoryservices.query')
    for ds in directoryservices:
        if ds["configure_nsswitch"] == False:
            continue

        if ds["type"] == "activedirectory":
            passwd_source += " winbind"
            group_source += " winbind"

        if ds["type"] == "ldap":
            passwd_source += " ldap"
            group_source += " ldap"
%>
passwd: ${passwd_source}
group: ${group_source}
hosts: files mdns dns
shells: files
services: compat
services_compat: nis
protocols: files
rpc: files
