# $FreeBSD$

PORTNAME=	freenas-fnstatd
PORTVERSION=	${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=	${REVISION}
CATEGORIES=	freenas
VALID_CATEGORIES+=	freenas

MAINTAINER=	dev@ixsystems.com
COMMENT=	FreeNAS stats collecting daemon

RUN_DEPENDS=	\
		${PYTHON_PKGNAMEPREFIX}dateutil>0:${PORTSDIR}/devel/py-dateutil \
		${PYTHON_PKGNAMEPREFIX}gevent>0:${PORTSDIR}/devel/py-gevent \
		${PYTHON_PKGNAMEPREFIX}numpy>0:${PORTSDIR}/math/py-numpy \
		${PYTHON_PKGNAMEPREFIX}pandas>0:${PORTSDIR}/math/py-pandas \
		${PYTHON_PKGNAMEPREFIX}setproctitle>0:${PORTSDIR}/devel/py-setproctitle \
		${PYTHON_PKGNAMEPREFIX}tables>0:${PORTSDIR}/devel/py-tables

USES=		python
EXTRACT_ONLY=

NO_BUILD=	yes
MAKE_JOBS_UNSAFE= yes
ALL_TARGET=	obj all
WRKSRC=		/usr/middleware_src/fnstatd

checksum fetch:
	${ECHO_CMD} ${.TARGET} not needed because building direct

do-install:
	${MAKE} -C ${WRKSRC} install PREFIX=${STAGEDIR}${PREFIX} PYTHON=${PYTHON_CMD}

post-install:
	${PYTHON_CMD} -m compileall ${STAGEDIR}${PREFIX}/lib/fnstatd
	(cd ${STAGEDIR}${PREFIX}/lib/fnstatd; ${FIND} -E . -type f -regex ".*.pyc?" \
		| ${SED} -e 's,^\./,,g' \
		| ${AWK} '{print length, $$0}' | ${SORT} -rn \
		| ${AWK} '{print "lib/fnstatd/"$$2 }' >> ${TMPPLIST})

.include <bsd.port.mk>
