# $FreeBSD$

PORTNAME=	freenas.cli
PORTVERSION=	${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=	${REVISION}
PORTREVISION=   ${REVISION}
PKGNAMEPREFIX=	${PYTHON_PKGNAMEPREFIX}

CATEGORIES=	freenas
VALID_CATEGORIES+= freenas

MAINTAINER=	dev@ixsystems.com
COMMENT=	FreeNAS Command Line Iterface

RUN_DEPENDS=	${PYTHON_PKGNAMEPREFIX}columnize>0:${PORTSDIR}/devel/py-columnize \
		${PYTHON_PKGNAMEPREFIX}icu>0:${PORTSDIR}/devel/py-icu \
		${PYTHON_PKGNAMEPREFIX}natural>0:${PORTSDIR}/devel/py-natural \
		${PYTHON_PKGNAMEPREFIX}ply>0:${PORTSDIR}/devel/py-ply \
		${PYTHON_PKGNAMEPREFIX}tables>0:${PORTSDIR}/devel/py-tables \
		${PYTHON_PKGNAMEPREFIX}termcolor>0:${PORTSDIR}/devel/py-termcolor \
		${PYTHON_PKGNAMEPREFIX}texttable>0:${PORTSDIR}/textproc/py-texttable

USES=		python
USE_PYTHON=	autoplist distutils
EXTRACT_ONLY=

WRKSRC=		/usr/middleware_src/cli

PLIST_FILES=	bin/cli bin/logincli

checksum fetch:
	${ECHO_CMD} ${.TARGET} not needed because building direct

post-install:
	${INSTALL_SCRIPT} ${WRKSRC}/tools/cli ${STAGEDIR}${PREFIX}/bin/
	${INSTALL_SCRIPT} ${WRKSRC}/tools/logincli ${STAGEDIR}${PREFIX}/bin/

.include <bsd.port.mk>
