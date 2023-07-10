from datetime import datetime
# from httpsig.verify import HeaderVerifier
from apub_bot.sig import HeaderVerifier
import requests

from apub_bot import ap_logic, config, gcp
# Import hashlib.
import hashlib

# Import cryptographic helpers from the cryptography package.
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import utils
# Import the client library.
from google.cloud import kms


def verify_asymmetric_rsa(
    project_id: str,
    location_id: str,
    key_ring_id: str,
    key_id: str,
    version_id: str,
    message: str,
    signature: str,
) -> bool:
    """
    Verify the signature of an message signed with an asymmetric RSA key.

    Args:
        project_id (string): Google Cloud project ID (e.g. 'my-project').
        location_id (string): Cloud KMS location (e.g. 'us-east1').
        key_ring_id (string): ID of the Cloud KMS key ring (e.g. 'my-key-ring').
        key_id (string): ID of the key to use (e.g. 'my-key').
        version_id (string): ID of the version to use (e.g. '1').
        message (string): Original message (e.g. 'my message')
        signature (bytes): Signature from a sign request.

    Returns:
        bool: True if verified, False otherwise

    """

    # Convert the message to bytes.
    message_bytes = message.encode("utf-8")

    # Create the client.
    client = kms.KeyManagementServiceClient()

    # Build the key version name.
    key_version_name = client.crypto_key_version_path(
        project_id, location_id, key_ring_id, key_id, version_id
    )

    # Get the public key.
    public_key = client.get_public_key(request={"name": key_version_name})

    # Extract and parse the public key as a PEM-encoded RSA key.
    pem = public_key.pem.encode("utf-8")
    rsa_key = serialization.load_pem_public_key(pem, default_backend())
    hash_ = hashlib.sha256(message_bytes).digest()

    # Attempt to verify.
    try:
        sha256 = hashes.SHA256()
        pad = padding.PKCS1v15()
        rsa_key.verify(signature, hash_, pad, utils.Prehashed(sha256))
        print("Signature verified")
        return True
    except InvalidSignature:
        print("Signature failed to verify")
        return False


def test_sign_header():
    conf = config.get_config()
    headers = {
        "Date": datetime.now().isoformat()
    }
    headers2 = ap_logic.sign_header("POST", "/", headers)
    print(headers2)
    assert "Signature" in headers2
    public_key = gcp.get_public_key(conf.kms.key_ring_id, conf.kms.key_id, "1")

    
    result = HeaderVerifier(headers2, public_key.pem.encode("utf-8"),
                            method="POST", path="/",
                            sign_header="signature").verify()
    assert True == result
