def probe(obj, datastore):
    return datastore.collection_has_migration("users", "0002-lastname")

def apply(obj, datastore):
    obj["title"] = "Mr"
    return obj
