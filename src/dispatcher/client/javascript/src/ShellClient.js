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

export class ShellClient
{
    constructor(client)
    {
        this.client = client;
        this.socket = null;
        this.token = null;
        this.authenticated = false;

        /* Callbacks */
        this.onConnect = () => {};
        this.onClose = () => {};
        this.onData = () => {}
    }

    __onopen()
    {
        this.socket.send(JSON.stringify({
            "token": this.token
        }));
    }


    __onclose()
    {

    }

    __onmessage(msg)
    {
        if (!this.authenticated) {
            let payload = JSON.parse(msg.data);
            if (payload.status == "ok") {
                this.authenticated = true;
            } else {
                /* XXX error */
            }

            return;
        }

        var reader = new FileReader();
        reader.onload = () => { this.onData(reader.result); };
        reader.readAsBinaryString(msg.data);
    }

    connect(command)
    {
        /* Request shell connection */
        self.client.call("shell.spawn", [command], result => {
            this.token = result;
            this.socket = new WebSocket(`http://${this.client.hostname}:5000/shell`);
            this.socket.onopen = this.__onopen.bind(this);
            this.socket.onmessage = this.__onmessage.bind(this);
            this.socket.onclose = this.__onclose.bind(this)
        });
    }

    disconnect()
    {
        if (this.socket === null) {

        }

        this.socket.close();
    }
}