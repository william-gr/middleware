#
# $FreeBSD$
# $Id$
#

PORTNAME=       freenas-middleware-files
PORTVERSION=	${PRODUCT_VERSION:C/\-.*//:C/\_.*//}
PORTREVISION=	${REVISION}

CATEGORIES=     freenas
VALID_CATEGORIES+=	freenas

MAINTAINER=     dev@ixsystems.com
COMMENT=        miscellaneous files for FreeNAS middleware

USE_XZ=		yes

PREFIX=/

# explicitly set this for the port build
FREEBSD_SRCTOP=/usr/src
PLIST_SUB=	MACHINE_ARCH=${MACHINE_ARCH}

EXTRACT_ONLY=
WRKSRC=/usr/middleware_src

# no checksum, we just used git!
 #extract:
checksum fetch:
	echo ${.TARGET} not needed because building direct

pre-clean:
	@

ALL_TARGET=obj all

MAKE_JOBS_UNSAFE=yes

do-build:
	${MAKE} -C ${WRKSRC}/extract-tarball   obj
	${MAKE} -C ${WRKSRC}/extract-tarball  all

do-install:
	cp -a ${WRKSRC}/middleware-files/ ${STAGEDIR}${PREFIX}/

post-install:
	cd ${WRKSRC}/middleware-files && ${FIND} . \( -type f -o -type l \) | \
		${SED} -e 's|^\./||' | ${SORT} >> ${TMPPLIST}


.include <bsd.port.mk>
