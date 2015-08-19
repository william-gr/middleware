daily_status_zfs_enable="YES"
daily_status_ata_raid_enable="YES"
daily_status_gmirror_enable="YES"
daily_status_graid3_enable="YES"
daily_status_gstripe_enable="YES"
daily_clean_hoststat_enable="NO"
daily_status_mail_rejects_enable="NO"
daily_status_include_submit_mailq="NO"
daily_submit_queuerun="NO"
daily_status_3ware_raid_enable="YES"
daily_status_security_neggrpperm_enable="NO"
daily_status_security_chksetuid_enable="NO"
daily_status_disks_enable="NO"
daily_backup_passwd_enable="NO"
daily_backup_pkgdb_enable="NO"
daily_status_security_diff_no_today_info="NO"
daily_status_security_chkmounts_ignore="(.+)@(.+)[[:space:]]+/mnt/\1/\.zfs/snapshot/\2"
daily_show_success="NO"
security_show_success="NO"
weekly_locate_enable="NO"
monthly_show_success="NO"
<%
    userid = dispatcher.call_sync('system.advanced.get_config')['periodic_notify_user']
    if userid is not None:
        user = dispatcher.call_sync('users.query', [('id', '=', userid)], {'single': True})
    else:
        user = None
%>\
% if user:
daily_output="${user['username']}"
daily_status_security_output="${user['username']}"
weekly_output="${user['username']}"
weekly_status_security_output="${user['username']}"
monthly_output="${user['username']}"
monthly_status_security_output="${user['username']}"
% endif
