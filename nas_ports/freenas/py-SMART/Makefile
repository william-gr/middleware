# $FreeBSD$

PORTNAME=	SMART
PORTVERSION=	${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=	${REVISION}
PKGNAMEPREFIX=	${PYTHON_PKGNAMEPREFIX}

CATEGORIES=	freenas
VALID_CATEGORIES+= freenas

MAINTAINER=	dev@ixsystems.com
COMMENT=	Python wrapper for `smartctl` (smartmontools)

RUN_DEPENDS=	smartctl:${PORTSDIR}/sysutils/smartmontools

USES=		python
EXTRACT_ONLY=

WRKSRC=		/usr/middleware_src/py-SMART

USES=		python
USE_PYTHON=	autoplist distutils

checksum fetch:
	${ECHO_CMD} ${.TARGET} not needed because building direct

.include <bsd.port.mk>
