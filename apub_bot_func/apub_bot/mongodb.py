from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from apub_bot import config, gcp


uri = "mongodb+srv://ap_bot:{password}@serverlessinstance0.fzzbd4i.mongodb.net/?retryWrites=true&w=majority"
client = None


def init_client() -> MongoClient:    
    global client
    if client is not None:
        return client
    password = gcp.fetch_secret_version("mongodb_password")
    client = MongoClient(uri.format(password=password), server_api=ServerApi('1'))
    try:
        client.admin.command('ping')
        print("Pinged your deployment. You successfully connected to MongoDB!")
    except Exception as e:
        print(e)
    return client


def get_client() -> MongoClient:
    return client


def get_database():
    conf = config.get_config()
    return client.get_database(conf.mongodb.database)
