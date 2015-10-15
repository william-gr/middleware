#
# $FreeBSD$
# $Id$
#

PORTNAME=       freenas-fnstatd
PORTVERSION=    ${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=	${REVISION}

CATEGORIES=     freenas
VALID_CATEGORIES+= freenas

MAINTAINER=     dev@ixsystems.com
COMMENT=        FreeNAS stats collecting daemon

RUN_DEPENDS=	${PYTHON_PKGNAMEPREFIX}numpy>0:${PORTSDIR}/math/py-numpy \
		${PYTHON_PKGNAMEPREFIX}pandas>0:${PORTSDIR}/math/py-pandas \
		${PYTHON_PKGNAMEPREFIX}tables>0:${PORTSDIR}/devel/py-tables

USES=		python
EXTRACT_ONLY=

NO_BUILD= 	yes
MAKE_JOBS_UNSAFE= yes
ALL_TARGET=	obj all
WRKSRC=		/usr/middleware_src/fnstatd

USES=		python

checksum fetch:
	echo ${.TARGET} not needed because building direct

do-install:
	${MAKE} -C ${WRKSRC} install PREFIX=${STAGEDIR}${PREFIX} PYTHON=${PYTHON_CMD}

.include <bsd.port.mk>
