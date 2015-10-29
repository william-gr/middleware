

function Middleware ( ) {
  this.socket = null;
  this.rpcTimeout = 10000;
  this.pendingCalls = {};
}

function uuid ( ) {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace( /[xy]/g, function ( c ) {
    var r = Math.random() * 16 | 0, v = c == "x" ? r : ( r & 0x3 | 0x8 );
    return v.toString( 16 );
  });
}

Middleware.prototype.connect = function ( url ) {
  var self = this;
  this.socket = new WebSocket( url );
  this.socket.onmessage = function ( msg ) { self.onMessage( msg.data ); };
  this.socket.onopen = function ( ) { self.emit( "connected" ); };
};

Middleware.prototype.login = function ( username, password ) {
  var self = this;
  var id = uuid();
  var payload = {
    "username": username,
    "password": password
  };

  this.pendingCalls[id] = {
    "callback": function () { self.emit( "login" ); },
    "timeout": setTimeout( function () {
      self.onRpcTimeout( id );
    }, this.rpcTimeout )
  };

  this.socket.send( this.pack( "rpc", "auth", payload, id ) );
};

Middleware.prototype.subscribe = function ( eventMasks ) {
  this.socket.send( this.pack( "events", "subscribe", eventMasks ) );
};

Middleware.prototype.unsubscribe = function ( eventMasks ) {
  this.socket.send( this.pack( "events", "unsubscribe", eventMasks ) );
};

Middleware.prototype.call = function ( method, args, callback ) {
  var self = this;
  var id = uuid();
  var payload = {
    "method": method,
    "args": args
  };

  this.pendingCalls[id] = {
    "method": method,
    "args": args,
    "callback": callback,
    "timeout": setTimeout( function ( ) {
      self.onRpcTimeout( id );
    }, this.rpcTimeout )
  };

  this.socket.send( this.pack( "rpc", "call", payload, id ) );
};

Middleware.prototype.onRpcTimeout = function ( data ) { };

Middleware.prototype.onMessage = function ( msg ) {
  var reader = new FileReader();
  reader.onload = function ( evt ) {
    var data = JSON.parse( reader.result );
    if ( data.namespace == "events" && data.name == "event" ) {
      this.emit( "event", data.args );
    }

    if ( data.namespace == "rpc" ) {
      if ( data.name == "response" ) {
        if ( !( data.id in this.pendingCalls ) ) {
          /* Spurious reply, just ignore it */
          return;
        }
        call = this.pendingCalls[data.id];
        call.callback( data.args );
        clearTimeout( call.timeout );
        delete this.pendingCalls[data.id];
      }

      if ( data.name == "error" ) {
        this.emit( "error", data.args );
      }
    };
  }.bind( this );
  reader.readAsText( msg );
};

Middleware.prototype.pack = function ( namespace, name, args, id ) {
  return JSON.stringify({
    "namespace": namespace,
    "id": id || uuid(),
    "name": name,
    "args": args
  });
};

Emitter( Middleware.prototype );
