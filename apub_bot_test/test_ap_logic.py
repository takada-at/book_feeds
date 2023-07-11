from datetime import datetime
from httpsig.verify import HeaderVerifier
from apub_bot import ap_logic, ap_object, config, gcp


def test_sign_header():
    conf = config.get_config()
    request_json = {
        "hoge": 1
    }
    digest = ap_logic.get_digest(request_json)
    headers = {
        "Host": "example.com",
        "Date": ap_object.get_now(),
        "Digest": f"sha-256={digest}"
    }
    headers2 = ap_logic.sign_header("POST", "/", headers, ['(request-target)', 'host', 'date', 'digest'])

    assert "Signature" in headers2
    public_key = gcp.get_public_key(conf.kms.key_ring_id, conf.kms.key_id, conf.kms.version)
    result = HeaderVerifier(headers2, public_key.pem.encode("utf-8"),
                            method="POST", path="/",
                            sign_header="signature").verify()
    assert True is result
