/*
 * Copyright 2015 iXsystems, Inc.
 * All rights reserved
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted providing that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
 * IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
 * DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
 * OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
 * STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
 * IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 *
 */

class DispatcherClient
{
    const INVALID_JSON_RESPONSE = 1;
    const CONNECTION_TIMEOUT = 2;
    const CONNECTION_CLOSED = 3;
    const RPC_CALL_TIMEOUT = 4;
    const RPC_CALL_ERROR = 5;
    const SPURIOUS_RPC_RESPONSE = 6;
    const LOGOUT = 7;
    const OTHER = 8;

    constructor(hostname)
    {
        this.defaultTimeout = 20;
        this.socket = new WebSocket(`ws://${hostname}:5000/socket`);
        this.socket.onmessage = this.__onmessage;
        this.socket.onopen = this.__onopen;
        this.socket.onclose = this.__onclose;
        this.pendingCalls = new Map();
        this.eventHandlers = new Map();

        /* Callbacks */
        this.onEvent = null;
        this.onLogin = null;
        this.onRPCResponse = null;
        this.onError = null;
    }

    __onmessage(msg)
    {
        try {
            let data = JSON.parse(msg);
        } catch (e) {
            return;
        }

        if (data.namespace == "events" && data.name == "event") {
            this.emit("event", data.args);
            return;
        }

        if (data.namespace == "events" && data.name == "logout") {
            this.onError(this.LOGOUT);
        }

        if (data.namespace == "rpc") {
            if (data.name == "call") {

            }

            if (data.name == "response") {
                if (!this.pendingCalls.has(data.id)) {

                }

                let call = this.pendingCalls.get(data.id);
                clearTimeout(call.timeout);
                call.callback(data.args);
                this.pendingCalls.delete(data.id);
            }
        }
    }

    __onopen()
    {

    }

    __onclose()
    {

    }

    __ontimeout()
    {

    }

    static __uuid() {
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace( /[xy]/g, c => {
            var r = Math.random() * 16 | 0, v = c == "x" ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    static __pack(namespace, name, args, id)
    {
        return JSON.stringify({
            "namespace": namespace,
            "id": id || this.__uuid(),
            "name": name,
            "args": args
        });
    }

    connect()
    {

    }

    login(username, password)
    {
        let id = this.__uuid();
        let payload = {
            "username": username,
            "password": password
        };

        this.pendingCalls[id] = {
            "callback": () => self.emit( "login" )
        };

        this.socket.send(this.pack("rpc", "auth", payload, id));
    }

    call(method, args, callback)
    {
        let id = uuid();
        let payload = {
            "method": method,
            "args": args
        };

        this.pendingCalls[id] = {
            "method": method,
            "args": args,
            "callback": callback
        };

        this.socket.send(this.pack("rpc", "call", payload, id));
    }

    emitEvent(name, args)
    {

    }

    registerEventHandler(name, callback)
    {

    }

    unregisterEventHandler(cookie)
    {

    }
}
