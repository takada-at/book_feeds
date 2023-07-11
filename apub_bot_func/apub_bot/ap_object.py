from bson.objectid import ObjectId
from datetime import datetime, timezone
from typing import Dict

from apub_bot import config, gcp


def get_now():
    return format_datetime(datetime.now(tz=timezone.utc))


def format_datetime(datetime_obj: datetime) -> str:
    # return datetime_obj.isoformat()[:19] + "Z"
    return datetime_obj.strftime("%a, %d %b %Y %H:%M:%S %Z").replace("UTC", "GMT")


def get_public_key():
    conf = config.get_config()
    bot_id = conf.bot_id
    pubkey = gcp.get_public_key(conf.kms.key_ring_id, conf.kms.key_id, conf.kms.version)
    return {
        'id': bot_id,
        'type': 'Key',
        'owner': bot_id,
        'publicKeyPem': pubkey.pem
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
        'url': get_link("static/index.html"),
        'publicKey': get_public_key(),
        'icon': {
            'type': 'Image',
            'mediaType': 'image/png',
            'url': conf.get_link("static/icon.png")
        }
    }


def insert_note(db, content: str):
    now = datetime.now(tz=timezone.utc)
    collection = db["note"]
    base_dict = {
        "content": content,
        "published": now
    }
    result = collection.insert_one(base_dict)
    base_dict["_id"] = result.inserted_id
    return convert_note(base_dict)


def convert_note(dic):
    conf = config.get_config()
    bot_id = conf.bot_id
    id_ = dic["_id"]
    url = conf.get_link(f"note/{id_}")

    return {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": "Note",
        "id": url,
        "attributedTo": bot_id,
        "content": dic["content"],
        "published": format_datetime(dic["published"]),
        "to": [
            "https://www.w3.org/ns/activitystreams#Public"
        ]        
    }

def get_note_create_activity(note):
    conf = config.get_config()
    bot_id = conf.bot_id
    note_id = note["id"].split('/')[-1]
    note_sub = {key: value for key, value in note.items() if key != "@context"}
    url = conf.get_link(f"note{note_id}/activity")
    return {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": url,
        "type": "Create",
        "actor": bot_id,
        "published": note_sub["published"],
        "to": note_sub["to"],
        "note": note_sub,
    }


def get_note(db, id_):
    collection = db["note"]
    note = collection.find_one({'_id': ObjectId(id_)})
    if note is None:
        return None
    return convert_note(note)


def get_notes(db, limit: int = 100, skip: int = 0):
    return [convert_note(note) for note in db["note"].find(limit=limit, skip=skip)]


def insert_follower(db, actor_data):
    collection = db["follower"]
    result = collection.insert_one(actor_data)
    return result.inserted_id


def remove_follower(db, actor_data):
    collection = db["follower"]
    result = collection.delete_one({"actor": actor_data["actor"]})
    return result.deleted_count
