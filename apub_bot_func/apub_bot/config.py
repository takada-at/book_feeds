from dataclasses import dataclass
from typing import Dict
import os


@dataclass
class MongoDbConfig:
    url: str
    password_secret_key: str
    database: str


@dataclass
class KMSConfig:
    key_ring_id: str = "ap_key_ring"
    key_id: str = "apbot_key_rsa_pkcs15_sha256"
    version: str = "1"


@dataclass
class Config:
    bot_name: str = os.environ["BOT_NAME"]
    bot_preferred_username: str = os.environ["BOT_ID"]
    mongodb: MongoDbConfig = MongoDbConfig(
        url="mongodb+srv://ap_bot:{password}@serverlessinstance0.fzzbd4i.mongodb.net/?retryWrites=true&w=majority",
        password_secret_key="mongodb_password",
        database="ap_bot_test"
    )
    base_url: str = os.environ["BASE_URL"]
    kms: KMSConfig = KMSConfig(
        key_ring_id="ap_key_ring",
        key_id="apbot_key_rsa_pkcs15_sha256",
        version="1"
    )

    def get_link(self, path: str):
        return self.base_url + path

    @property
    def bot_id(self):
        return self.get_link("user")


config = Config()


def get_config():
    return config
