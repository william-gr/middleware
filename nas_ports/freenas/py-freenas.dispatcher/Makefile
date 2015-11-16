# $FreeBSD$

PORTNAME=	freenas.dispatcher
PORTVERSION=	${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=	${REVISION}
PKGNAMEPREFIX=	${PYTHON_PKGNAMEPREFIX}

CATEGORIES=	freenas
VALID_CATEGORIES+= freenas

MAINTAINER=	dev@ixsystems.com
COMMENT=	FreeNAS Command Line Iterface

RUN_DEPENDS=	${PYTHON_PKGNAMEPREFIX}ws4py>0:${PORTSDIR}/freenas/py-ws4py \
		${PYTHON_PKGNAMEPREFIX}jsonschema>0:${PORTSDIR}/devel/py-jsonschema \
		${PYTHON_PKGNAMEPREFIX}gevent>0:${PORTSDIR}/devel/py-gevent \
		${PYTHON_PKGNAMEPREFIX}paramiko>0:${PORTSDIR}/security/py-paramiko \
		${PYTHON_PKGNAMEPREFIX}six>0:${PORTSDIR}/devel/py-six \
		${PYTHON_PKGNAMEPREFIX}freenas.utils>0:${PORTSDIR}/freenas/py-freenas.utils

USES=		python
USE_PYTHON=	autoplist distutils
EXTRACT_ONLY=

WRKSRC=		/usr/middleware_src/dispatcher/client/python

checksum fetch:
	${ECHO_CMD} ${.TARGET} not needed because building direct

.include <bsd.port.mk>
