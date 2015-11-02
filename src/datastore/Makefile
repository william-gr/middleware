PREFIX ?= /usr/local
PYTHON ?= python

install:
	install -d ${STAGEDIR}${PREFIX}/lib/datastore
	install -d ${STAGEDIR}${PREFIX}/lib/datastore/drivers
	install -d ${STAGEDIR}${PREFIX}/share/datastore
	install sbin/dsutil ${STAGEDIR}${PREFIX}/sbin/
	install sbin/dsdump ${STAGEDIR}${PREFIX}/sbin/
	install sbin/dsrestore ${STAGEDIR}${PREFIX}/sbin/
	install sbin/dsmigrate ${STAGEDIR}${PREFIX}/sbin/
	install sbin/dspasswd ${STAGEDIR}${PREFIX}/sbin/
	install sbin/dsinit ${STAGEDIR}${PREFIX}/sbin/
	install etc/datastore ${STAGEDIR}${PREFIX}/etc/rc.d/
	install share/factory.json ${STAGEDIR}${PREFIX}/share/datastore/
	cp -R share/migrations ${STAGEDIR}${PREFIX}/share/datastore/
	cp -R test ${STAGEDIR}${PREFIX}/share/datastore/
	cp -R drivers/ ${STAGEDIR}${PREFIX}/lib/datastore/drivers/
	${PYTHON} setup.py install --root=${STAGEDIR} --prefix=${PREFIX}
