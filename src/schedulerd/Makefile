PREFIX ?= /usr/local
PYTHON ?= python

install:
	install etc/schedulerd ${PREFIX}/etc/rc.d/
	install sbin/schedulerd ${PREFIX}/sbin/
	install -d ${PREFIX}/lib/schedulerd
	install -d ${PREFIX}/lib/schedulerd/src
	cp -a src/ ${PREFIX}/lib/schedulerd/src/