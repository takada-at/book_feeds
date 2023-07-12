import requests
from datetime import datetime
from typing import Dict
from urllib.parse import urlparse
import base64
import concurrent.futures
import hashlib
import json
import logging

from apub_bot import ap_object, config, gcp, mongodb
from apub_bot.sig import InjectableSigner


logger = logging.getLogger(__name__)


def get_notes(page: int = 1):
    db = mongodb.get_database()
    limit = 100
    skip = limit * (page - 1)
    return ap_object.get_notes(db, limit=limit, skip=skip)


def create_note(content: str):
    db = mongodb.get_database()
    note = ap_object.insert_note(db, content)
    create_activity = ap_object.get_note_create_activity(note)
    futures = []
    for follower in db["follower"].find():
        send_note_wraper((follower, create_activity))
    # with concurrent.futures.ThreadPoolExecutor() as executor:
    #    for follower in db["follower"].find():
    #        future = executor.submit(send_note_wraper, (follower, create_activity))
    #        futures.append(future)
    #    for future in concurrent.futures.as_completed(futures):
    #        result = future.result()
    #        print(result)


def send_note_wraper(args):
    try:
        return send_note(args[0], args[1])
    except:
        logging.info('General exception noted.', exc_info=True)


def send_note(follower, create_activity):
    actor = follower["actor"]
    actor_data = get_actor_data(actor)
    response = send_request(actor_data["inbox"], create_activity)
    return response


def handle_follow(request_data: Dict):
    actor = request_data["actor"]
    actor_data = get_actor_data(actor)
    db = mongodb.get_database()
    ap_object.insert_follower(db, {"actor": actor})
    accept_follow(actor_data, request_data)


def handle_unfollow(request_data: Dict):
    actor = request_data["object"]["actor"]
    actor_data = get_actor_data(actor)
    db = mongodb.get_database()
    ap_object.remove_follower(db, request_data["object"])
    accept_follow(actor_data, request_data)


def get_actor_data(actor: str):
    response = requests.get(actor, headers={
        "Accept": "application/activity+json"
    })
    actor_data = response.json()
    print("actor_data", actor_data)
    for key in ["id", "preferredUsername", "inbox"]:
        assert key in actor_data
    return actor_data


def check_token(token: str) -> bool:
    expected = gcp.fetch_secret_version("apub_bot_secret_token")
    return expected == token


def get_digest(data: Dict):
    input_data = json.dumps(data)
    digest = hashlib.sha256(input_data.encode("utf-8")).digest()
    encoded_value = base64.b64encode(digest).decode("utf-8")
    print("digest", input_data, encoded_value)
    return encoded_value


def accept_follow(actor_data: Dict, request_data: Dict):
    request_json = ap_object.get_accept(request_data)
    print(request_json)
    send_request(actor_data["inbox"], request_json)


def send_request(url: str, data: Dict):
    netloc = urlparse(url)
    digest = get_digest(data)
    headers = {
        "Host": netloc.hostname,
        "Date": ap_object.get_now(),
        "Digest": f"sha-256={digest}"
    }
    headers = sign_header("POST", netloc.path, headers, ['(request-target)', 'host', 'date', 'digest'])
    headers["Content-Type"] = "application/activity+json"
    headers["Accept"] = "application/activity+json"
    print(headers)
    response = requests.post(url, json=data, headers=headers)
    print(response, response.content)
    return response


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
