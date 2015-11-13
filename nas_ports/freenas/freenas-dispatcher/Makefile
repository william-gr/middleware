# $FreeBSD$

PORTNAME=	freenas-dispatcher
PORTVERSION=	${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=	${REVISION}
CATEGORIES=	freenas
VALID_CATEGORIES+= freenas

MAINTAINER=	dev@ixsystems.com
COMMENT=	FreeNAS middleware daemon

FETCH_DEPENDS=	npm012>0:${PORTSDIR}/www/npm012

BUILD_DEPENDS=	cython>0:${PORTSDIR}/lang/cython \
		npm012>0:${PORTSDIR}/www/npm012

RUN_DEPENDS=	${PYTHON_PKGNAMEPREFIX}argh>0:${PORTSDIR}/devel/py-argh \
		${PYTHON_PKGNAMEPREFIX}dateutil>0:${PORTSDIR}/devel/py-dateutil \
		${PYTHON_PKGNAMEPREFIX}Flask>0:${PORTSDIR}/www/py-flask \
		${PYTHON_PKGNAMEPREFIX}Flask-Bootstrap>0:${PORTSDIR}/www/py-flask-bootstrap \
		${PYTHON_PKGNAMEPREFIX}fnutils>0:${PORTSDIR}/freenas/py-fnutils \
		${PYTHON_PKGNAMEPREFIX}gevent>0:${PORTSDIR}/devel/py-gevent \
		${PYTHON_PKGNAMEPREFIX}gevent-websocket>0:${PORTSDIR}/www/py-gevent-websocket \
		${PYTHON_PKGNAMEPREFIX}jsonschema>0:${PORTSDIR}/devel/py-jsonschema \
		${PYTHON_PKGNAMEPREFIX}lxml>0:${PORTSDIR}/devel/py-lxml \
		${PYTHON_PKGNAMEPREFIX}openssl>0:${PORTSDIR}/security/py-openssl \
		${PYTHON_PKGNAMEPREFIX}psutil>0:${PORTSDIR}/sysutils/py-psutil \
		${PYTHON_PKGNAMEPREFIX}pyee>0:${PORTSDIR}/devel/py-pyee \
		${PYTHON_PKGNAMEPREFIX}requests>0:${PORTSDIR}/www/py-requests \
		${PYTHON_PKGNAMEPREFIX}setproctitle>0:${PORTSDIR}/devel/py-setproctitle \
		${PYTHON_PKGNAMEPREFIX}simplejson>0:${PORTSDIR}/devel/py-simplejson \
		${PYTHON_PKGNAMEPREFIX}texttable>0:${PORTSDIR}/textproc/py-texttable \
		${PYTHON_PKGNAMEPREFIX}ws4py>0:${PORTSDIR}/freenas/py-ws4py

USES=		python
USE_PYTHON=	py3kplist

EXTRACT_ONLY=

NO_BUILD=	yes
MAKE_JOBS_UNSAFE= yes
ALL_TARGET=	obj all
WRKSRC=		/usr/middleware_src/dispatcher

checksum:
	${ECHO_CMD} ${.TARGET} not needed because building direct

fetch:
	${MAKE} -C ${WRKSRC}/client/javascript fetch

extract:
	:

do-install:
	${MAKE} -C ${WRKSRC} install STAGEDIR=${STAGEDIR} PREFIX=${PREFIX} PYTHON=${PYTHON_CMD}

post-install:
	${PYTHON_CMD} -m compileall ${STAGEDIR}${PREFIX}/lib/dispatcher
	#cd ${STAGEDIR}${PREFIX}/lib/dispatcher && ${FIND} -E . -regex ".*.pyc?" | ${SED} 's,^./,lib/dispatcher/,g' >> ${TMPPLIST}
	(cd ${STAGEDIR}${PREFIX}/lib/dispatcher; ${FIND} -E . -type f -regex ".*.pyc?" \
		| ${SED} -e 's,^\./,,g' \
		| ${AWK} '{print length, $$0}' | ${SORT} -rn \
		| ${AWK} '{print "lib/dispatcher/"$$2 }' >> ${TMPPLIST})


.include <bsd.port.mk>
