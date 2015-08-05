#
# Copyright 2015 iXsystems, Inc.
# All rights reserved
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted providing that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
# IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
#####################################################################
import re

ALIASES = '''# $FreeBSD$
#	@(#)aliases	5.3 (Berkeley) 5/24/90
#
#  Aliases in this file will NOT be expanded in the header from
#  Mail, but WILL be visible over networks.
#
#	>>>>>>>>>>	The program "newaliases" must be run after
#	>> NOTE >>	this file is updated for any changes to
#	>>>>>>>>>>	show through to sendmail.
#
#
# See also RFC 2142, `MAILBOX NAMES FOR COMMON SERVICES, ROLES
# AND FUNCTIONS', May 1997
# 	http://tools.ietf.org/html/rfc2142

# Pretty much everything else in this file points to "root", so
# you would do well in either reading root's mailbox or forwarding
# root's email from here.

# root:	me@my.domain

# Basic system aliases -- these MUST be present
MAILER-DAEMON: postmaster
postmaster: root

# General redirections for pseudo accounts
_dhcp:	root
_pflogd: root
auditdistd:	root
bin:	root
bind:	root
daemon:	root
games:	root
hast:	root
kmem:	root
mailnull: postmaster
man:	root
news:	root
nobody:	root
operator: root
pop:	root
proxy:	root
smmsp:	postmaster
sshd:	root
system:	root
toor:	root
tty:	root
usenet: news
uucp:	root

# Well-known aliases -- these should be filled in!
# manager:
# dumper:

# BUSINESS-RELATED MAILBOX NAMES
# info:
# marketing:
# sales:
# support:

# NETWORK OPERATIONS MAILBOX NAMES
abuse:	root
# noc:		root
security:	root

# SUPPORT MAILBOX NAMES FOR SPECIFIC INTERNET SERVICES
ftp: 		root
ftp-bugs: 	ftp
# hostmaster: 	root
# webmaster: 	root
# www: 		webmaster

# NOTE: /var/msgs and /var/msgs/bounds must be owned by sendmail's
#	DefaultUser (defaults to mailnull) for the msgs alias to work.
#
# msgs: "| /usr/bin/msgs -s"

# bit-bucket: /dev/null
# dev-null: bit-bucket'''


def run(context):

    users = context.datastore.query('users', [('email', '!=', '')])
    aliases = ALIASES
    for user in users:
        if not user.get('email'):
            continue

        reg = re.search(r'^{0}:(.*)'.format(user['username']), aliases)
        if reg:
            new = '{0}: {1} {2}'.format(
                user['username'],
                reg.group(1),
                user['email'])
            aliases = aliases.replace(reg.group(0), new)
        else:
            aliases = '{0}\n{1}: {2}'.format(
                aliases,
                user['username'],
                user['email'])

    with open('/etc/mail/aliases', 'w') as f:
        f.write(aliases)

    context.emit_event('etcd.file_generated', {
        'filename': '/etc/mail/aliases'
    })
