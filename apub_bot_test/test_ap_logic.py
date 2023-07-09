from datetime import datetime
from httpsig.verify import HeaderVerifier
import requests

from apub_bot import ap_logic, config, gcp


def test_sign_header():
    conf = config.get_config()
    headers = {
        "Date": datetime.now().isoformat(),
        "Host": "example.com",
    }
    headers2 = ap_logic.sign_header("POST", "/", headers)
    assert "Signature" in headers2
    public_key = gcp.get_public_key(conf.kms.key_ring_id, conf.kms.key_id, "1")
    result = HeaderVerifier(headers2, public_key.pem,
                            method="POST", path="/",
                            sign_header="Signature").verify()
    assert True == result
