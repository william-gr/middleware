# $FreeBSD$

PORTNAME=       freenas-networkd
PORTVERSION=    ${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=	${REVISION}
CATEGORIES=     freenas
VALID_CATEGORIES+= freenas

MAINTAINER=     dev@ixsystems.com
COMMENT=        FreeNAS network configuration daemon

RUN_DEPENDS=	\
		${PYTHON_PKGNAMEPREFIX}ipaddress>0:${PORTSDIR}/net/py-ipaddress

USES=		python
EXTRACT_ONLY=

NO_BUILD=	yes
MAKE_JOBS_UNSAFE= yes
ALL_TARGET=	obj all
WRKSRC=		/usr/middleware_src/networkd

checksum fetch:
	${ECHO_CMD} ${.TARGET} not needed because building direct

do-install:
	${MAKE} -C ${WRKSRC} install PREFIX=${STAGEDIR}${PREFIX} PYTHON=${PYTHON_CMD}

post-install:
	${PYTHON_CMD} -m compileall ${STAGEDIR}${PREFIX}/lib/networkd

.include <bsd.port.mk>
