import requests
from datetime import datetime
from typing import Dict
from urllib.parse import urlparse

from apub_bot import ap_object, config, gcp, mongodb


def handle_follow(request_data: Dict):
    actor = request_data["actor"]
    actor_data = get_actor_data(actor)
    db = mongodb.get_database()
    follow_id = ap_object.insert_follower(db, actor_data)
    accept_follow(actor_data, request_data)


def get_actor_data(actor: str):
    response = requests.get(actor, headers={
        "Accept": "application/activity+json"
    })
    actor_data = response.json()
    for key in ["id", "preferredUsername", "inbox"]:
        assert key in actor_data
    return actor_data


def accept_follow(actor_data: Dict, request_data: Dict):
    request_json = ap_object.get_accept(request_data)
    # sign header
    netloc = urlparse(actor_data["inbox"])
    headers = {
        "Date": datetime.now().isoformat(),
        "Host": netloc.host,
    }
    headers = sign_header("POST", netloc.path, headers)
    response = requests.post(actor_data["inbox"], json=request_json, headers=headers)


def sign_header(method: str, path: str, headers: Dict):
    conf = config.get_config()
    bot_id = conf.bot_id
    message = sign_header_message(method, path, headers)
    sig = gcp.sign_asymmetric(conf.kms.key_ring_id, conf.kms.key_id, "1", message)
    keys = [
        ('keyId', bot_id),
        ('algorithm', 'rsa-sha256'),
        ('headers', "(request-target) host date"),
        ('signature', sig)
    ]
    signature = ",".join(f'{k}="{v}"' for k, v in keys)
    new_headers = {k: v for k, v in headers.items()}
    new_headers["Signature"] = signature
    return new_headers


def sign_header_message(method: str, path: str, headers: Dict) -> str:
    lines = [
        "(request-target): {method} {path}".format(method=method.lower(), path=path)
    ]
    for key, value in headers.items():
        lines.append("{key}: {value}".format(key=key.lower(), value=value))
    message = "\n".join(lines).encode("ascii")
    return message