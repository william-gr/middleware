PREFIX ?= /usr/local
PYTHON ?= python

install:
	install etc/crashd ${PREFIX}/etc/rc.d/
	install sbin/crashd ${PREFIX}/sbin/
	install -d ${PREFIX}/lib/crashd
	install -d ${PREFIX}/lib/crashd/src
	cp -a src/ ${PREFIX}/lib/crashd/src/
