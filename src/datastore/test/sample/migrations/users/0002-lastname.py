from freenas.utils import extend


def probe(obj, datastore):
    return obj.get("full_name") and "last_name" not in obj

def apply(obj, datastore):
    return extend(obj, {"last_name": obj["full_name"].split()[-1]})
