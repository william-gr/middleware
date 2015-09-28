#
# $FreeBSD$
# $Id$
#

PORTNAME=       freenas-dispatcher
PORTVERSION=    ${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=	${REVISION}

CATEGORIES=     freenas
VALID_CATEGORIES+= freenas

MAINTAINER=     dev@ixsystems.com
COMMENT=        FreeNAS middleware daemon

USES=		python

RUN_DEPENDS=	${PYTHON_PKGNAMEPREFIX}jsonschema>0:${PORTSDIR}/devel/py-jsonschema \
		${PYTHON_PKGNAMEPREFIX}enum34>0:${PORTSDIR}/devel/py-enum34 \
		${PYTHON_PKGNAMEPREFIX}ws4py>0:${PORTSDIR}/www/py-ws4py \
		${PYTHON_PKGNAMEPREFIX}fnutils>0:${PORTSDIR}/freenas/py-fnutils

EXTRACT_ONLY=

NO_BUILD= 	yes
MAKE_JOBS_UNSAFE= yes
ALL_TARGET=	obj all
WRKSRC=		/usr/middleware_src/dispatcher

checksum fetch:
	echo ${.TARGET} not needed because building direct

do-install:
	${MAKE} -C ${WRKSRC} install STAGEDIR=${STAGEDIR} PREFIX=${PREFIX} PYTHON=${PYTHON_CMD}

.include <bsd.port.mk>
