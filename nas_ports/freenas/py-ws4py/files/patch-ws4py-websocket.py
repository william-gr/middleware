diff --git ws4py/websocket.py ws4py/websocket.py
index 2c9c6ef..d441c34 100644
--- ws4py/websocket.py
+++ ws4py/websocket.py
@@ -6,12 +6,6 @@ import threading
 import types
 import errno
 
-try:
-    from OpenSSL.SSL import Error as pyOpenSSLError
-except ImportError:
-    class pyOpenSSLError(Exception):
-        pass
-
 from ws4py.streaming import Stream
 from ws4py.messaging import (
     Message, PingControlMessage, PongControlMessage
@@ -25,6 +19,11 @@ logger = logging.getLogger('ws4py')
 __all__ = ['WebSocket', 'EchoWebSocket', 'Heartbeat']
 
 
+# Only define and not import this for freenas
+class pyOpenSSLError(Exception):
+    pass
+
+
 class Heartbeat(threading.Thread):
     def __init__(self, websocket, frequency=2.0):
         """
