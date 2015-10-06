PORTNAME=	   iocage
PORTVERSION=       ${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=      ${REVISION}
PKGNAMESUFFIX=	   -devel
CATEGORIES=        freenas
VALID_CATEGORIES+= freenas

MAINTAINER=	   brandon@ixsystems.com
COMMENT=	   Full featured, no dependency Jail container manager - development build
EXTRACT_ONLY=

WRKSRC=            /usr/middleware_src/iocage-devel
LICENSE=	   BSD2CLAUSE
LICENSE_FILE=	   ${WRKSRC}/LICENSE

NO_BUILD=	   yes

checksum fetch:
	echo ${.TARGET} not needed because building direct

post-patch:
	@${REINPLACE_CMD} -e "s|/usr/local/lib/iocage|${PREFIX}/lib/iocage|g" ${WRKSRC}/iocage

pre-install:
	@${MKDIR} ${STAGEDIR}${PREFIX}/lib/iocage

do-install:
	${INSTALL_SCRIPT} ${WRKSRC}/rc.d/iocage ${STAGEDIR}${PREFIX}/etc/rc.d
	${INSTALL_SCRIPT} ${WRKSRC}/iocage ${STAGEDIR}${PREFIX}/sbin
	(cd ${WRKSRC}/lib/ && ${COPYTREE_SHARE} . ${STAGEDIR}${PREFIX}/lib/iocage)
	${INSTALL_MAN} ${WRKSRC}/iocage.8 ${STAGEDIR}${PREFIX}/man/man8

.include <bsd.port.mk>
