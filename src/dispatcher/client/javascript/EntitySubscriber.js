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

class CappedMap
{
    constructor(maxsize)
    {
        this.map = new Map();
        this.maxsize = maxsize;
    }

    get(key)
    {
        return this.map.get(key);
    }

    set(key, value)
    {
        this.map.set(key, value);
        if (this.map.size() > this.maxsize) {
            let mapIter = this.map.entries();
            this.map.delete(mapIter.next().key);
        }
    }

    has(key)
    {
        return this.map.has(key);
    }

    getSize()
    {
        return this.map.size();
    }

    setMaxSize(maxsize)
    {
        if (maxsize < this.maxsize){
            let mapIter = this.map.entries();
            let deleteSize = this.map.size() - maxsize;
            for (i = 0; i < deleteSize; i++){
                this.map.delete(mapIter.next().key);
            }
        }
        this.maxsize = maxsize;
    }

}

class EntitySubscriber
{
    constructor(client, name, maxsize=2000)
    {
        this.name = name;
        this.client = client;
        this.maxsize = maxsize;
        this.objects = new CappedMap(maxsize);
        this.handlerCookie = null;

        /* Callbacks */
        this.onCreate = null;
        this.onUpdate = null;
        this.onDelete = null;
    }

    start()
    {
        this.handlerCookie = this.client.registerEventHandler(`entity-subscriber.${this.name}.changed`);
    }

    stop()
    {
        this.client.unregisterEventHandler(this.handlerCookie);
    }

    __onChanged(event)
    {
        if (event.action == "create") {
            for (let entity of event.entities)
                this.objects.set(entity.id, entity);
        }

        if (event.action == "update") {
            for (let entity of event.entities)
                this.objects.set(entity.id, entity);
        }

        if (event.action == "delete") {
            for (let entity of event.entities)
                if (this.objects.has(entity.id))
                    this.objects.delete(entity.id);
        }
    }
}
