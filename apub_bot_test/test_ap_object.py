from apub_bot import ap_object, mongodb
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


def test_get_person():
    person = ap_object.get_person()
    assert isinstance(person, dict)


def test_get_notes(db):
    for i in range(15):
        ap_object.insert_note(db, str(i))
    notes = ap_object.get_notes(db, limit=5, skip=5)
    print(notes)
    assert "5" == notes[0]["content"]
    assert 5 == len(notes)


def test_insert_note(db):
    note0 = ap_object.insert_note(db, "hoge")
    print(note0)
    note_id = note0["id"].split("/")[-1]
    result = ap_object.get_note(db, note_id)
    print(result)
    assert "hoge" == result["content"]
    assert note0 == result


def test_insert_follower(db):
    id_ = ap_object.insert_follower(db, {"actor": "actor"})
    res = db["follower"].find_one({"actor": "actor"})
    assert "actor" == res["actor"]
    ap_object.remove_follower(db, {"actor": "actor"})
    assert db["follower"].find_one({"actor": "actor"}) is None
