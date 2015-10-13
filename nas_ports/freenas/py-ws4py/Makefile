#
# $FreeBSD$
# $Id$
#


PORTNAME=	ws4py
PORTVERSION=	${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=	${REVISION}
PKGNAMEPREFIX=	${PYTHON_PKGNAMEPREFIX}

CATEGORIES=     freenas
VALID_CATEGORIES+= freenas

MAINTAINER=	suraj@ixsystems.com
COMMENT=	WebSocket package for Python

LICENSE=	BSD3CLAUSE

WRKSRC=		/usr/middleware_src/py-ws4py

USES=		python
USE_PYTHON=	distutils autoplist
EXTRACT_ONLY=

NO_ARCH=	yes

OPTIONS_DEFINE=	CHERRYPY GEVENT TORNADO
OPTIONS_DEFAULT=	CHERRYPY GEVENT
CHERRYPY_DESC=	CherryPy server support
GEVENT_DESC=	gevent-based client/server support
TORNADO_DESC=	Tornado client support

CHERRYPY_RUN_DEPENDS+=	${PYTHON_PKGNAMEPREFIX}cherrypy>=3.2.2:${PORTSDIR}/www/py-cherrypy
GEVENT_RUN_DEPENDS+=	${PYTHON_PKGNAMEPREFIX}gevent>=0.13.8:${PORTSDIR}/devel/py-gevent
TORNADO_RUN_DEPENDS+=	${PYTHON_PKGNAMEPREFIX}tornado>=3.1:${PORTSDIR}/www/py-tornado

checksum fetch:
	echo ${.TARGET} not needed because building direct

.include <bsd.port.options.mk>

# Do not install files which will not work
post-patch:
.if ! ${PORT_OPTIONS:MCHERRYPY}
.for f in test/test_cherrypy.py ws4py/server/cherrypyserver.py
	${RM} ${WRKSRC}/${f}
.endfor
.endif
.if ! ${PORT_OPTIONS:MGEVENT}
.for f in ws4py/client/geventclient.py ws4py/server/geventserver.py
	${RM} ${WRKSRC}/${f}
.endfor
.endif
.if ! ${PORT_OPTIONS:MTORNADO}
.for f in ws4py/client/tornadoclient.py
	${RM} ${WRKSRC}/${f}
.endfor
.endif

.include <bsd.port.mk>
