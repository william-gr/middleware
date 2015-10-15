#
# $FreeBSD$
# $Id$
#

PORTNAME=       freenas-cli
PORTVERSION=    ${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=	${REVISION}

CATEGORIES=     freenas
VALID_CATEGORIES+= freenas

MAINTAINER=     dev@ixsystems.com
COMMENT=        FreeNAS Command Line Iterface

RUN_DEPENDS=	${PYTHON_PKGNAMEPREFIX}enum34>0:${PORTSDIR}/devel/py-enum34 \
		${PYTHON_PKGNAMEPREFIX}icu>0:${PORTSDIR}/devel/py-icu \
		${PYTHON_PKGNAMEPREFIX}natural>0:${PORTSDIR}/devel/py-natural \
		${PYTHON_PKGNAMEPREFIX}ply>0:${PORTSDIR}/devel/py-ply \
		${PYTHON_PKGNAMEPREFIX}tables>0:${PORTSDIR}/devel/py-tables

USES=		python
EXTRACT_ONLY=

NO_BUILD= 	yes
MAKE_JOBS_UNSAFE= yes
ALL_TARGET=	obj all
WRKSRC=		/usr/middleware_src/cli

USES=		python

checksum fetch:
	echo ${.TARGET} not needed because building direct

do-install:
	${MAKE} -C ${WRKSRC} install PREFIX=${STAGEDIR}${PREFIX} PYTHON=${PYTHON_CMD}

.include <bsd.port.mk>
