Defaults syslog_goodpri = debug
Defaults secure_path = /sbin:/bin:/usr/sbin:/usr/bin:/usr/local/sbin:/usr/local/bin

# Let find_alias_for_smtplib.py runs as root (it needs database access)
ALL ALL=(ALL) NOPASSWD: /etc/find_alias_for_smtplib.py

% for user in ds.query("users"):
    ${user['username']} ALL=(ALL) ALL
% endfor
% for group in ds.query("groups"):
    %${group['name']} ALL=(ALL) ALL
% endfor
