#+
# Copyright 2014 iXsystems, Inc.
# All rights reserved
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted providing that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
# IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
#####################################################################


import time
import copy
import uuid
import dateutil.parser
from datetime import datetime
from pymongo import MongoClient
import pymongo
import pymongo.errors
from six import string_types
from datastore import DuplicateKeyException
from freenas.utils.query import wrap


class MongodbDatastore(object):
    def __init__(self):
        self.conn = None
        self.db = None
        self.log_db = None
        self.operators_table = {
            '>': '$gt',
            '<': '$lt',
            '>=': '$gte',
            '<=': '$lte',
            '!=': '$ne',
            'in': '$in',
            'nin': '$nin',
            '~': '$regex',
        }

        self.clauses_table = {
            'or': lambda v: {'$or': [self._predicate(*t) for t in v]},
            'nor': lambda v: {'$nor': [self._predicate(*t) for t in v]},
            'and': lambda v: {'$and': [self._predicate(*t) for t in v]},
            'where': lambda v: {'$where': v},
            'text': lambda v: {'$text': {'$search': v, '$language': 'none'}}
        }

        self.conversions_table = {
            'timestamp': lambda v: dateutil.parser.parse(v)
        }

    @property
    def client(self):
        return self.conn

    def _predicate(self, *args):
        if len(args) == 2:
            return self._joint_predicate(*args)

        if len(args) in (3, 4):
            return self._operator_predicate(*args)

    def _operator_predicate(self, name, op, value, conversion=None):
        if name == 'id':
            name = '_id'

        if conversion:
            value = self.conversions_table[conversion](value)

        if op == '=':
            return {name: value}

        if op in self.operators_table:
            if op in ('in', 'nin'):
                if isinstance(value, (list, tuple)):
                    return {name: {self.operators_table[op]: value}}
                else:
                    return {name: {self.operators_table[op]: [value]}}

            return {name: {self.operators_table[op]: value}}

    def _joint_predicate(self, op, value):
        if op in self.clauses_table:
            return self.clauses_table[op](value)

    def _build_query(self, params):
        result = []
        for item in params:
            r = self._predicate(*item)
            if r:
                result.append(r)

        return {'$and': result} if len(result) > 0 else {}

    def _get_db(self, collection):
        c = self.db['collections'].find_one({"_id": collection})
        typ = c['attributes'].get('type', 'config')

        if typ == 'log':
            return self.log_db[collection]

        return self.db[collection]

    def connect(self, dsn, database='freenas'):
        self.conn = MongoClient(dsn)
        self.db = self.conn[database]
        self.log_db = self.conn[database + '-log']

    def collection_create(self, name, pkey_type='uuid', attributes=None):
        attributes = attributes or {}
        ttl_index = attributes.get('ttl_index')
        unique_indexes = attributes.get('unique_indexes', [])

        if not self.db['collections'].find_one(name):
            self.db['collections'].insert({
                '_id': name,
                'pkey-type': pkey_type,
                'last-id': 0,
                'attributes': attributes
            })

        if ttl_index:
            self.db[name].create_index(ttl_index, expireAfterSeconds=0)

        for idx in unique_indexes:
            if isinstance(idx, str):
                idx = [idx]

            self.db[name].create_index([(i, pymongo.ASCENDING) for i in idx], unique_indexes=True)

        self.db[name].create_index([('$**', pymongo.TEXT)])

    def collection_exists(self, name):
        return self.db['collections'].find_one({"_id": name}) is not None

    def collection_get_attrs(self, name):
        item = self.db['collections'].find_one({"_id": name})
        return item['attributes']

    def collection_set_attrs(self, name):
        item = self.db['collections'].find_one({"_id": name})
        return item['attributes']

    def collection_get_max_id(self, name):
        item = self.db['collections'].find_one({"_id": name})
        return item['last-id']

    def collection_get_migrations(self, name):
        item = self.db['collections'].find_one({"_id": name})
        return item.get('migrations', [])

    def collection_has_migration(self, name, migration_name):
        item = self.db['collections'].find_one({"_id": name})
        return migration_name in item.get('migrations', [])

    def collection_record_migration(self, name, migration_name):
        item = self.db['collections'].find_one({"_id": name})
        migs = item.setdefault('migrations', [])
        migs.append(migration_name)
        self.db['collections'].update({'_id': name}, item)

    def collection_list(self):
        return [x['_id'] for x in self.db['collections'].find()]

    def collection_delete(self, name):
        if not self.db['collections'].find_one({"_id": name}):
            return

        self._get_db(name).drop()
        self.db['collections'].remove({'_id': name})

    def collection_get_pkey_type(self, name):
        item = self.db['collections'].find_one({"_id": name})
        return item['pkey-type']

    def collection_get_next_pkey(self, name, prefix):
        counter = 0
        while True:
            pkey = prefix + str(counter)
            if not self.exists(name, ('id', '=', pkey)):
                return pkey

            counter += 1

    def query(self, collection, *args, **kwargs):
        sort = kwargs.pop('sort', None)
        limit = kwargs.pop('limit', None)
        offset = kwargs.pop('offset', None)
        single = kwargs.pop('single', False)
        count = kwargs.pop('count', False)
        postprocess = kwargs.pop('callback', None)
        select = kwargs.pop('select', None)
        result = []

        db = self._get_db(collection)
        cur = db.find(self._build_query(args))
        if count:
            return cur.count()

        if select:
            def select_fn(fn, obj):
                obj = fn(obj) if fn else obj
                obj = wrap(obj)

                if isinstance(select, (list, tuple)):
                    return [obj.get(i) for i in select]

                if isinstance(select, str):
                    return obj.get(select)

            old = postprocess
            postprocess = lambda o: select_fn(old, o)

        if sort:
            def sort_transform(result, key):
                direction = pymongo.ASCENDING
                if key.startswith('-'):
                    key = key[1:]
                    direction = pymongo.DESCENDING
                key = '_id' if key == 'id' else key
                _sort.append((key, direction))

            _sort = []
            if isinstance(sort, string_types):
                sort_transform(_sort, sort)
            elif isinstance(sort, (tuple, list)):
                for s in sort:
                    sort_transform(_sort, s)
            if _sort:
                cur = cur.sort(_sort)

        if offset:
            cur = cur.skip(offset)

        if limit:
            cur = cur.limit(limit)

        if single:
            i = next(cur, None)
            if i is None:
                return i

            i['id'] = i.pop('_id')
            return postprocess(i) if postprocess else i

        for i in cur:
            i['id'] = i.pop('_id')
            r = postprocess(i) if postprocess else i
            if r is not None:
                result.append(r)

        return result

    def listen(self, collection, *args, **kwargs):
        cur = self._get_db(collection).find(self._build_query(args), tailable=True, await_data=True)
        for i in cur:
            i['id'] = i.pop('_id')
            yield i

    def get_one(self, collection, *args, **kwargs):
        db = self._get_db(collection)
        obj = db.find_one(self._build_query(args))
        if obj is None:
            return None

        obj['id'] = obj.pop('_id')
        return obj

    def get_by_id(self, collection, pkey):
        db = self._get_db(collection)
        obj = db.find_one({'_id': pkey})
        if obj is None:
            return None

        obj['id'] = obj.pop('_id')
        return obj

    def exists(self, collection, *args, **kwargs):
        return self.get_one(collection, *args, **kwargs) is not None

    def insert(self, collection, obj, pkey=None, timestamp=True, config=False):
        if hasattr(obj, '__getstate__'):
            obj = obj.__getstate__()
        elif type(obj) is not dict or config:
            obj = {'value': obj}
        else:
            obj = copy.copy(obj)

        if 'id' in obj:
            pkey = obj.pop('id')

        if pkey is None:
            pkey_type = self.collection_get_pkey_type(collection)
            if pkey_type in ('serial', 'integer'):
                ret = self.db['collections'].find_and_modify({'_id': collection}, {'$inc': {'last-id': 1}})
                pkey = ret['last-id']
            elif pkey_type == 'uuid':
                pkey = str(uuid.uuid4())

        obj['_id'] = pkey

        if timestamp:
            t = datetime.now()
            obj['updated_at'] = t
            obj['created_at'] = t

        try:
            db = self._get_db(collection)
            db.insert(obj)
        except pymongo.errors.DuplicateKeyError:
            raise DuplicateKeyException('Document with given key already exists')

        return pkey

    def update(self, collection, pkey, obj, upsert=False, timestamp=True, config=False):
        if hasattr(obj, '__getstate__'):
            obj = obj.__getstate__()
        elif type(obj) is not dict or config:
            obj = {'value': obj}
        else:
            obj = copy.deepcopy(obj)

        if 'id' in obj:
            # We gonna remove the document and reinsert it to change the id...
            full_obj = self.get_by_id(collection, pkey)
            full_obj.update(obj)
            self.delete(collection, pkey)
            self.insert(collection, full_obj, timestamp=False)
            return

        if timestamp:
            t = datetime.now()
            obj['updated_at'] = t

            if not self.get_by_id(collection, pkey):
                obj['created_at'] = t

        db = self._get_db(collection)
        db.update({'_id': pkey}, obj, upsert=upsert)

    def upsert(self, collection, pkey, obj, config=False):
        return self.update(collection, pkey, obj, upsert=True, config=config)

    def delete(self, collection, pkey):
        db = self._get_db(collection)
        db.remove(pkey)
