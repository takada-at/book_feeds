import requests
from datetime import datetime
from typing import Dict
from urllib.parse import urlparse
import base64
import concurrent.futures
import hashlib
import json

from apub_bot import ap_object, config, gcp, mongodb
from apub_bot.sig import InjectableSigner


def get_notes(page: int = 1):
    db = mongodb.get_database()
    limit = 100
    skip = limit * (page - 1)
    return ap_object.get_notes(db, limit=limit, skip=skip)


def create_note(content: str):
    db = mongodb.get_database()
    note = ap_object.insert_note(content)
    create_activity = ap_object.get_note_create_activity(note)
    futures = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        for follower in db["follower"].find():
            future = executor.submit(send_note_wraper, (follower, create_activity))
            futures.append(future)
        for future in concurrent.futures.as_completed(futures):
            result = future.result()


def send_note_wraper(args):
    try:
        send_note(args[0], args[1])
    except:
        pass


def send_note(follower, create_activity):
    actor = follower["actor"]
    actor_data = get_actor_data(actor)
    netloc = urlparse(actor_data["inbox"])
    headers = {
        "Date": datetime.now().isoformat()
    }
    headers = sign_header("POST", netloc.path, headers)
    response = requests.post(actor_data["inbox"], json=create_activity, headers=headers)
    print(response, response.content)


def handle_follow(request_data: Dict):
    actor = request_data["actor"]
    actor_data = get_actor_data(actor)
    db = mongodb.get_database()
    ap_object.insert_follower(db, actor_data)
    accept_follow(actor_data, request_data)


def handle_unfollow(request_data: Dict):
    actor = request_data["object"]["actor"]
    actor_data = get_actor_data(actor)
    db = mongodb.get_database()
    ap_object.remove_follower(db, actor_data)
    accept_follow(actor_data, request_data)


def get_actor_data(actor: str):
    response = requests.get(actor, headers={
        "Accept": "application/activity+json"
    })
    print(response)
    actor_data = response.json()
    for key in ["id", "preferredUsername", "inbox"]:
        assert key in actor_data
    return actor_data


def accept_follow(actor_data: Dict, request_data: Dict):
    request_json = ap_object.get_accept(request_data)
    # sign header
    netloc = urlparse(actor_data["inbox"])
    digest = hashlib.sha256(json.dumps(request_json).encode("utf-8")).digest()
    headers = {
        "Host": netloc.hostname,
        "Date": ap_object.format_datetime(datetime.now()),
        "Digest": digest
    }
    headers = sign_header("POST", netloc.path, headers, ['(request-target)', 'host', 'date', 'digest'])
    headers["Content-Type"] = "application/activity+json"
    headers["Accept"] = "application/activity+json"
    response = requests.post(actor_data["inbox"], json=request_json, headers=headers)
    print(response, response.content)


def sign_header(method: str, path: str, headers: Dict, required_headers):
    conf = config.get_config()
    bot_id = conf.bot_id
    public_key = gcp.get_public_key(conf.kms.key_ring_id, conf.kms.key_id, "1")
    signer = InjectableSigner(bot_id, public_key.pem.encode("utf-8"),
                              algorithm="rsa-sha256",
                              headers=required_headers,
                              sign_header="signature",
                              sign_func=sign_func)
    return signer.sign(headers=headers, method=method, path=path)


def sign_func(message: bytes):
    conf = config.get_config()
    sig = gcp.sign_asymmetric(conf.kms.key_ring_id, conf.kms.key_id, conf.kms.version, message)
    return base64.b64encode(sig.signature).decode("ascii")


def find_note(uuid: str):
    db = mongodb.get_database()
    return ap_object.get_note(db, uuid)
