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

var diff = require('deep-diff').diff;


var operatorsTable = {
    '=': (x, y) => x == y,
    '!=': (x, y) => x != y,
    '>': (x, y) => x > y,
    '<': (x, y) => x < y,
    '>=': (x, y) => x >= y,
    '<=': (x, y) => x <= y,
    '~': (x, y) => x.match(y),
    'in': (x, y) => y.indexOf(x) > -1,
    'nin': (x, y) => y.indexOf(x) == -1
};


var conversions_table = {
    'timestamp': v => Date.parse(v)/1000
};


function eval_logic_and(item, lst){
    for (let i of lst){
        if (!evalTuple(item, i)){
            return false;
        }
    }

    return true;
}

function eval_logic_or(item, lst){
    for (let i of lst){
        if (evalTuple(item, i)){
            return true;
        }
    }

    return false;
}

function eval_logic_nor(item, lst){
    for (let i of lst){
        if (evalTuple(item, i)){
            return false;
        }
    }

    return true;
}

function evalLogicOperator(item, t){
    let op = t[0];
    let lst = t[1];
    let functName = 'eval_logic_';
    functName.concat(op);
    return window[functName](item, lst);
}

function evalFieldOperator(item, t){
    let left = t[0];
    let op = t[1];
    let right = t[2];

    if (t.length == 4){
        right = conversions_table[t[3]](right);
    }

    return operatorsTable[op](item[left], right);
}

function evalTuple(item, t){
    if (t.length == 2){
        return evalLogicOperator(item, t);
    }
    if ((t.length == 3)||(t.length == 4)){
        return evalFieldOperator(item, t);
    }
}

function matches(obj, rules){
    let fail = false;
    for (let r of rules){
        if (!evalTuple(obj, r)){
            fail = true;
            break;
        }
    }

    return !fail;
}

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

    deleteKey(key)
    {
        this.map.delete(key);
    }

    entries()
    {
        return this.map.entries();
    }

}

export class EntitySubscriber
{
    constructor(client, name, maxsize=2000)
    {
        this.name = name;
        this.client = client;
        this.maxsize = maxsize;
        this.objects = new CappedMap(maxsize);
        this.handlerCookie = null;

        /* Callbacks */
        this.onCreate = () => {};
        this.onUpdate = () => {};
        this.onDelete = () => {};
    }

    start()
    {
        this.handlerCookie = this.client.registerEventHandler(
            `entity-subscriber.${this.name}.changed`,
            this.__onChanged
        );
    }

    stop()
    {
        this.client.unregisterEventHandler(
            `entity-subscriber.${this.name}.changed`,
            this.handlerCookie
        );
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
                    this.objects.deleteKey(entity.id);
        }
    }

    query(rules, params, callback){
        if (this.objects.getSize() == this.maxsize){
            DispatcherClient.call(`${this.name}.query`, rules.concat(params), callback);
        } else {
            let single = params["single"];
            let count = params["count"];
            let offset = params["offset"];
            let limit = params["limit"];
            let sort = params["sort"];
            let result = new Array();

            if (rules.length == 0){
                result = this.objects.entries();
            } else {
                for (let i of this.objects.entries()){
                    if(matches(i, rules)){
                       result.push(i);
                    }
                }
            }

            if (sort){
                let sortKeys = [];
                let direction = [];
                for (let i of sort){
                    if (i.charAt(0) == '-'){
                        sortKeys.push(i.slice(1));
                        direction.push('desc');
                    } else {
                        sortKeys.push(i);
                        direction.push('asc');
                    }
                }
                _.map(_.sortByOrder(result, sortKeys, direction), _.values);
            }

            if (offset){
                callback(result.slice(offset));
            }

            if (limit) {
                callback(result.slice(0,limit));
            }

            if ((!result.length) && (single)){
                callback(null);
            }

            if (single) {
                callback(result[0]);
            }

            if (count) {
                callback(result.length);
            }

            callback(result);
        }
    }
}
