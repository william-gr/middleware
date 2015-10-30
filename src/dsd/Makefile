PREFIX ?= /usr/local
PYTHON ?= python

install:
	install etc/dsd ${PREFIX}/etc/rc.d/
	install tools/dsd ${PREFIX}/sbin/
	install -d ${PREFIX}/lib/dsd
	install -d ${PREFIX}/lib/dsd/src
	cp -a src/ ${PREFIX}/lib/dsd/src/
