from dataclasses import dataclass
from typing import Dict


@dataclass
class MongoDbConfig:
    url: str
    password_secret_key: str
    database: str


@dataclass
class KMSConfig:
    key_ring_id: str = "ap_key_ring"
    key_id: str = "apbot_key"


@dataclass
class Config:
    bot_name: str = "test"
    bot_preferred_username: str = "test"
    mongodb: MongoDbConfig = MongoDbConfig(
        url="mongodb+srv://ap_bot:{password}@serverlessinstance0.fzzbd4i.mongodb.net/?retryWrites=true&w=majority",
        password_secret_key="mongodb_password",
        database="ap_bot_test"
    )
    base_url: str = "https://example.com/"
    kms: KMSConfig = KMSConfig(
        key_ring_id="ap_key_ring",
        key_id="apbot_key"
    )

    def get_link(self, path: str):
        return self.base_url + path

    @property
    def bot_id(self):
        return self.get_link("user")


config = Config()


def get_config():
    return config
