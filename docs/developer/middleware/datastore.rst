Database abstraction layer
==========================

Basic information
-----------------

FreeNAS 10 introduces database abstraction layer called "datastore".
datastore is a Python module, installed globally (so it's possible to do
``import datastore`` anywhere inside FN10 system).

Data is stored as JSON object in "schemaless" manner. "object" is a
python dict() instance, with at least "id" key with primary key value.

Module contents
---------------

.. py:function:: get_datastore(driver_name, dsn)

    Returns object implementing datastore interface (see below). Supported
    values of ``driver_name`` are ``mongodb`` and ``postgresql``. ``dsn`` is
    driver-specific database server URI, eg. ``mongodb://localhost``.

.. py:exception:: DatastoreException

    Generic exception class used by datastore interface.

.. py:exception:: DuplicateKeyException

    Exception raised when trying to insert or upsert object with key already
    present in collection.

datastore interface
-------------------

.. py:function:: datastore.query(collection, *filter, **params)

    Performs a query over collection of specified name. Optional positional
    arguments should be a 3-tuples consisting of: field name, operator,
    desired value. For example ``("name", "=", "foo")`` or
    ``("id", ">", 4)``. All filter arguments are joined using AND logic.
    There are following keyword arguments currently supported:

    -  ``offset`` - skips first ``n`` found objects
    -  ``limit`` - limits query to ``n`` objects
    -  ``sort`` - name of field used to sort results
    -  ``dir`` - sort order, either ``"asc"`` or ``"desc"``
    -  ``single`` - returns single object instead of array. If multiple
       objects were matched in the query, returns first one (in random order
       if ``sort`` was not specified).

    Following operators are supported:

    -  ``=``
    -  ``!=``
    -  ``>``
    -  ``<``
    -  ``>=``
    -  ``<=``
    -  ``in`` - value in set
    -  ``nin`` - value not in set
    -  ``~`` - regex match

.. py:function:: datastore.get_one(collection, *filter, *params)

    Same as ``query`` with keyword argument ``single`` set to ``True``.

.. py:function:: datastore.get_by_id(collection, pkey)

    Returns single object by its primary key or ``None``.

.. py:function:: datastore.insert(collection, obj, pkey=None)

    Inserts object to database. Object should be python ``dict``. If it has
    ``id`` key, it will be used as primary key. Primary key can be also
    supplied through optional ``pkey`` argument. If both ``pkey`` argument
    is ``None`` and there's no ``id`` property in object, primary key is
    automatically generated.

.. py:function:: datastore.update(collection, pkey, obj, upsert=False)

.. py:function:: datastore.delete(collection, pkey)

.. py:class:: ConfigStore

A convenience class for accessing key-value store used for various
global configuration settings.

.. py:function:: configstore.get(key)

    Returns value of specified key or ``None`` if it doesn't exist.

.. py:function:: configstore.set(key, value)

    Sets value of ``key`` to ``value``. If key was already present, old
    value is overwritten.

.. py:function:: configstore.list_children(root=None)

    Returns list of key-value pairs with path beginning with ``root``.

.. py:class:: ConfigNode

Examples
--------
