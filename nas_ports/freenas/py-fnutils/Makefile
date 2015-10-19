# $FreeBSD$

PORTNAME=	fnutils
PORTVERSION=	${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=	${REVISION}
PKGNAMEPREFIX=	${PYTHON_PKGNAMEPREFIX}

CATEGORIES=	freenas
VALID_CATEGORIES+= freenas

MAINTAINER=	dev@ixsystems.com
COMMENT=	FreeNAS common Python modules

RUN_DEPENDS=	\
		${PYTHON_PKGNAMEPREFIX}dateutil>0:${PORTSDIR}/devel/py-dateutil

USES=		python
USE_PYTHON=	autoplist distutils
EXTRACT_ONLY=

WRKSRC=		/usr/middleware_src/py-fnutils

checksum fetch:
	${ECHO_CMD} ${.TARGET} not needed because building direct

.include <bsd.port.mk>
