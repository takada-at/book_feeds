from apub_bot import ap_object, gcp, mongodb
import pytest


@pytest.fixture
def db(request):
    def teardown():
        client.drop_database("test_db")
    mongodb.init_client()
    client = mongodb.get_client()
    database = client.get_database("test_db")
    request.addfinalizer(teardown)
    return database


def test_insert_note(db):
    id_ = ap_object.insert_note(db, "hoge")
    result = ap_object.get_note(db, str(id_))
    assert "hoge" == result["content"]


def test_insert_follower(db):
    id_ = ap_object.insert_follower(db, {"actor": "actor"})
    res = db["follower"].find_one({"actor": "actor"})
    assert "actor" == res["actor"]
