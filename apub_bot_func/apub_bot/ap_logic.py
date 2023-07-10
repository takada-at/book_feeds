import requests
from datetime import datetime
from typing import Dict
from urllib.parse import urlparse
import base64

from apub_bot import ap_object, config, gcp, mongodb
from apub_bot.sig import InjectionableSigner


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
        "Date": datetime.now().isoformat()
    }
    headers = sign_header("POST", netloc.path, headers)
    response = requests.post(actor_data["inbox"], json=request_json, headers=headers)


def sign_header(method: str, path: str, headers: Dict):
    conf = config.get_config()
    bot_id = conf.bot_id
    public_key = gcp.get_public_key(conf.kms.key_ring_id, conf.kms.key_id, "1")
    signer = InjectionableSigner(bot_id, public_key.pem.encode("utf-8"),
                                 algorithm="rsa-sha256",
                                 headers=['(request-target)', 'date'],
                                 sign_header="signature",
                                 sign_func=sign_func)
    return signer.sign(headers=headers, method=method, path=path)


def sign_func(message: bytes):
    conf = config.get_config()
    sig = gcp.sign_asymmetric(conf.kms.key_ring_id, conf.kms.key_id, conf.kms.version, message)
    print(sig)
    return base64.b64encode(sig.signature).decode("ascii")
