import json
import os
from urllib.parse import urlparse
from flask import Flask, Response, request
from apub_bot import ap_logic, ap_object, config, mongodb


app = Flask(__name__)


@app.route("/")
@app.route('/user')
@app.route('/user/<name>')
def person(name: str = ""):
    response = ap_object.get_person()
    return Response(json.dumps(response), headers={'Content-Type': 'application/activity+json'})


@app.route('/note/<uuid>')
def note(uuid: str):
    response = ap_logic.find_note(uuid)
    return Response(json.dumps(response), headers={'Content-Type': 'application/activity+json'})


@app.route("/inbox", methods=["GET", "POST"])
def inbox():
    if request.headers.get("Content-Type") != "application/activity+json":
        return Response(status=400)
    data = request.json
    print(data)
    print(data)
    if type(data) != dict or "type" not in data:
        return Response(status=400)
    elif data["type"] == "Follow":
        try:
            ap_logic.handle_follow(data)
        except Exception as e:
            print(e)
            return Response(status=500)
        return Response(status=200)
    elif data["type"] == "Undo":
        try:
            if data["object"]["type"] == "Follow":
                ap_logic.handle_unfollow(data)
        except:
            return Response(status=500)
        return Response(status=200)


@app.route("/outbox/")
@app.route("/outbox/<int:page>")
def outbox(page: int = 1):
    response = ap_logic.get_notes(page)
    return Response(json.dumps(response), headers={'Content-Type': 'application/activity+json'})


@app.route('/.well-known/host-meta')
def webfinger_host_meta():
    conf = config.get_config()
    link = conf.get_link(".well-known/webfinger")
    xml_str = f"""<?xml version="1.0"?>
    <XRD xmlns="http://docs.oasis-open.org/ns/xri/xrd-1.0">
    <Link rel="lrdd" type="application/xrd+xml" template="{link}?resource={{uri}}"/>
</XRD>"""
    return Response(xml_str, headers={'Content-Type': 'application/xml'})


@app.route('/.well-known/webfinger')
def webfinger_resource():
    conf = config.get_config()
    bot_id = conf.bot_id
    netloc = urlparse(conf.base_url)
    response = {
        'subject': f"acct:{conf.bot_preferred_username}@{netloc.hostname}",
        'links': [
            {
                'rel':  'self',
                'type': 'application/activity+json',
                'href': bot_id
            },
        ]
    }
    return Response(json.dumps(response), headers={'Content-Type': 'jrd+json'})


mongodb.init_client()
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
