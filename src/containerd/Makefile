PREFIX ?= /usr/local
PYTHON ?= python

install:
	install etc/containerd ${PREFIX}/etc/rc.d/
	install sbin/containerd ${PREFIX}/sbin/
	install -d ${PREFIX}/lib/containerd
	install -d ${PREFIX}/lib/containerd/src
	install -d ${PREFIX}/lib/containerd/plugins
	cp -a src/ ${PREFIX}/lib/containerd/src/
