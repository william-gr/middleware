fetch:
	npm install
	npm install -g browserify

install:
	npm config set prefix ${STAGEDIR}${PREFIX}
	npm install --unsafe-perm -g .
	NODE_PATH=${STAGEDIR}${PREFIX}/lib/node_modules browserify --standalone middleware -r dispatcher-client -o ${BROWSERIFY_BUNDLE}

clean:
	rm -rf lib node_modules
