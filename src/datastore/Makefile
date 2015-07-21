PREFIX ?= /usr/local
PYTHON ?= python

install:
	install -d ${PREFIX}/lib/datastore
	install -d ${PREFIX}/lib/datastore/drivers
	install -d ${PREFIX}/share/datastore
	install sbin/dsutil ${PREFIX}/sbin/
	install sbin/dsdump ${PREFIX}/sbin/
	install sbin/dsrestore ${PREFIX}/sbin/
	install sbin/dsmigrate ${PREFIX}/sbin/
	install sbin/dspasswd ${PREFIX}/sbin/
	install sbin/dsinit ${PREFIX}/sbin/
	install etc/datastore ${PREFIX}/etc/rc.d/
	install share/factory.json ${PREFIX}/share/datastore/
	cp -R test ${PREFIX}/share/datastore/
	cp -R drivers/ ${PREFIX}/lib/datastore/drivers/
	${PYTHON} setup.py install --prefix=${PREFIX}
