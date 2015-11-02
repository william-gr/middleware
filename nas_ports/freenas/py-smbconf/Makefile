#
# $FreeBSD$
# $Id$
#

PORTNAME=       smbconf
PORTVERSION=    ${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=   ${REVISION}
PKGNAMEPREFIX=  ${PYTHON_PKGNAMEPREFIX}

CATEGORIES=     freenas
VALID_CATEGORIES+= freenas

MAINTAINER=     dev@ixsystems.com
COMMENT=	Python wrapper around Samba libsmbconf.

BUILD_DEPENDS=	

USES=		python
EXTRACT_ONLY=
BUILD_DEPENDS=  ${LOCALBASE}/bin/cython:${PORTSDIR}/lang/cython \
		talloc>=2.1.2:${PORTSDIR}/devel/talloc \
		samba43>=0:${PORTSDIR}/net/samba43

WRKSRC=		/usr/middleware_src/py-smbconf

USES=		python:2
USE_PYTHON=	autoplist distutils

checksum fetch:
	echo ${.TARGET} not needed because building direct

.include <bsd.port.mk>
