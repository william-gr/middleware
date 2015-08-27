Defaults syslog_goodpri = debug
Defaults secure_path = /sbin:/bin:/usr/sbin:/usr/bin:/usr/local/sbin:/usr/local/bin

# Let find_alias_for_smtplib.py runs as root (it needs database access)
ALL ALL=(ALL) NOPASSWD: /etc/find_alias_for_smtplib.py

#includedir /usr/local/etc/sudoers.d

% for user in ds.query("users", ("sudo", "=", True)):
    ${user['username']} ALL=(ALL) ALL
% endfor
% for group in ds.query("groups", ("sudo", "=", True)):
    %%${group['name']} ALL=(ALL) ALL
% endfor
