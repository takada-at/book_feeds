from bson.objectid import ObjectId
from datetime import datetime, timezone
from typing import Dict

from apub_bot import config, gcp


def get_public_key():
    conf = config.get_config()
    bot_id = conf.bot_id
    pubkey = gcp.get_public_key(conf.kms["key_ring_id"], conf.kms["key_id"], "1")
    return {
        'id': bot_id,
        'type': 'Key',
        'owner': bot_id,
        'publicKeyPem': pubkey
    }


def get_accept(object_: Dict):
    conf = config.get_config()
    bot_id = conf.bot_id
    return {
        '@context': 'https://www.w3.org/ns/activitystreams',
        'type': 'Accept',
        'actor': bot_id,
        'object': object_,
    }


def get_person():
    conf = config.get_config()
    bot_id = conf.bot_id
    return {
        '@context': 'https://www.w3.org/ns/activitystreams',
        'type': 'Person',
        'id': bot_id,
        'name': conf.bot_name,
        'preferredUsername': conf.bot_preferred_username,
        'inbox': conf.get_link('inbox'),
        'outbox': conf.get_link('outbox'),
        'url': bot_id,
        'publicKey': get_public_key(),
        'icon': {
            'type': 'Image',
            'mediaType': 'image/png',
            'url': bot_id
        }
    }


def insert_note(db, content: str):
    now = datetime.now(tz=timezone.utc)
    collection = db["note"]
    result = collection.insert_one({
        "content": content,
        "published": now
    })
    return result.inserted_id


def convert_note(dic):
    conf = config.get_config()
    bot_id = conf.bot_id
    id_ = dic["_id"]
    return {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": "Note",
        "id": conf.get_link(f"note/{id_}"),
        "attributedTo": bot_id,
        "content": dic["content"],
        "published": dic["published"].isoformat(),
        "to": [
            "https://www.w3.org/ns/activitystreams#Public",
            "https://example.com/test/follower",
        ]        
    }


def get_note(db, id_):
    note = db.note.find_one({'_id': ObjectId(id_)})
    if note is None:
        return None
    return convert_note(note)


def insert_follower(db, actor_data):
    collection = db["follower"]
    result = collection.insert_one(actor_data)
    return result.inserted_id


def remove_follower(db, actor_data):
    collection = db["follower"]
    result = collection.delete_one({"actor": actor_data["actor"]})
    return result.deleted_count
