"""MongoDB history. All functions fail soft if MongoDB is down."""
import datetime
from bson import ObjectId
from pymongo import MongoClient
import config
_c = None

def _col():
    global _c
    if _c is None:
        _c = MongoClient(
            config.MONGO_URI,
            serverSelectionTimeoutMS=5000
        )
    return _c[config.MONGO_DB]["submissions"]

def _clean(d):
    d["_id"] = str(d["_id"])
    if isinstance(d.get("created_at"), datetime.datetime):
        d["created_at"] = d["created_at"].isoformat()
    return d

def save(doc):
    try:
        doc = {
            **doc,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
        result = _col().insert_one(doc)
        print("MONGODB: Submission saved successfully.")
        return str(result.inserted_id)
    except Exception as e:
        print("MONGODB SAVE ERROR:", repr(e))
        return None

def list_all(limit=50):
    try:
        records = _col().find(
            {},
            {
                "code": 1,
                "language": 1,
                "created_at": 1,
                "error.name": 1,
                "quality.score": 1
            }
        ).sort("created_at", -1).limit(limit)
        result = [_clean(d) for d in records]
        print("MONGODB: History loaded successfully.")
        return result, True
    except Exception as e:
        print("MONGODB HISTORY ERROR:", repr(e))
        return [], False

def get(i):
    try:
        d = _col().find_one({
            "_id": ObjectId(i)
        })
        return _clean(d) if d else None
    except Exception as e:
        print("MONGODB GET ERROR:", repr(e))
        return None

def delete(i):
    try:
        result = _col().delete_one({
            "_id": ObjectId(i)
        })
        return result.deleted_count == 1
    except Exception as e:
        print("MONGODB DELETE ERROR:", repr(e))
        return False

def ping():
    try:
        _col().database.client.admin.command("ping")
        print("MONGODB CONNECTION SUCCESSFUL")
        return True
    except Exception as e:
        print("MONGODB CONNECTION ERROR:", repr(e))
        return False
