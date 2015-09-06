# FreeNAS 10 Middleware

The FreeNAS 10 middleware is a separate process which controls all aspects
of a FreeNAS 10 instance's configuration and management.  It can be talked
to using the CLI (also part of this project) or a web application
(see http://github.com/freenas/gui).

For documentation of the tools and processes for hacking on FreeNAS 10
overall, visit http://doc.freenas.org/10/devdocs.

You should not, however, be working directly in this repo if you simply wish
to build and/or test the middleware.  You should, instead, check out the
http://github.com/freenas/freenas-build project which will automatically
check out all sub-repositories (including this one) and do the right
things to create / update a FreeNAS 10 development instance.
