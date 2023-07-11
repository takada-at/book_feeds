from google.cloud import kms
from google.cloud import secretmanager
import base64
import hashlib
import os


PROJECT_NAME = os.environ["PROJECT_NAME"]
kms_client = kms.KeyManagementServiceClient()
secret_manager_client = secretmanager.SecretManagerServiceClient()


def fetch_secret_version(key: str):
    name = f"projects/{PROJECT_NAME}/secrets/{key}/versions/latest"
    response = secret_manager_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def get_public_key(key_ring_id: str, key_id: str, version_id: str) -> kms.PublicKey:
    """
    Get the public key for an asymmetric key.

    Args:
        key_ring_id (string): ID of the Cloud KMS key ring (e.g. 'my-key-ring').
        key_id (string): ID of the key to use (e.g. 'my-key').
        version_id (string): ID of the key to use (e.g. '1').

    Returns:
        PublicKey: Cloud KMS public key response.

    """

    # Create the client.

    # Build the key version name.
    key_version_name = kms_client.crypto_key_version_path(
        PROJECT_NAME, "global", key_ring_id, key_id, version_id
    )

    # Call the API.
    public_key = kms_client.get_public_key(request={"name": key_version_name})

    # Optional, but recommended: perform integrity verification on public_key.
    # For more details on ensuring E2E in-transit integrity to and from Cloud KMS visit:
    # https://cloud.google.com/kms/docs/data-integrity-guidelines
    if not public_key.name == key_version_name:
        raise Exception("The request sent to the server was corrupted in-transit.")
    # See crc32c() function defined below.
    if not public_key.pem_crc32c == crc32c(public_key.pem):
        raise Exception(
            "The response received from the server was corrupted in-transit."
        )
    # End integrity verification
    return public_key


def sign_asymmetric(
    key_ring_id: str,
    key_id: str,
    version_id: str,
    message: bytes,
) -> kms.AsymmetricSignResponse:
    """
    Sign a message using the public key part of an asymmetric key.

    Args:
        key_ring_id (string): ID of the Cloud KMS key ring (e.g. 'my-key-ring').
        key_id (string): ID of the key to use (e.g. 'my-key').
        version_id (string): Version to use (e.g. '1').
        message (bytes): Message to sign.

    Returns:
        AsymmetricSignResponse: Signature.
    """

    # Create the client.
    client = kms.KeyManagementServiceClient()

    # Build the key version name.
    key_version_name = kms_client.crypto_key_version_path(
        PROJECT_NAME, "global", key_ring_id, key_id, version_id
    )

    # Calculate the hash.
    hash_ = hashlib.sha256(message).digest()
    print("digest", hash_)

    # Build the digest.
    #
    # Note: Key algorithms will require a varying hash function. For
    # example, EC_SIGN_P384_SHA384 requires SHA-384.
    digest = {"sha256": hash_}

    # Optional, but recommended: compute digest's CRC32C.
    # See crc32c() function defined below.
    digest_crc32c = crc32c(hash_)

    # Call the API
    sign_response = client.asymmetric_sign(
        request={
            "name": key_version_name,
            "digest": digest,
            "digest_crc32c": digest_crc32c,
        }
    )

    # Optional, but recommended: perform integrity verification on sign_response.
    # For more details on ensuring E2E in-transit integrity to and from Cloud KMS visit:
    # https://cloud.google.com/kms/docs/data-integrity-guidelines
    if not sign_response.verified_digest_crc32c:
        raise Exception("The request sent to the server was corrupted in-transit.")
    if not sign_response.name == key_version_name:
        raise Exception("The request sent to the server was corrupted in-transit.")
    if not sign_response.signature_crc32c == crc32c(sign_response.signature):
        raise Exception(
            "The response received from the server was corrupted in-transit."
        )
    return sign_response


def crc32c(data: bytes) -> int:
    """
    Calculates the CRC32C checksum of the provided data.
    Args:
        data: the bytes over which the checksum should be calculated.
    Returns:
        An int representing the CRC32C checksum of the provided bytes.
    """
    import crcmod  # type: ignore
    import six  # type: ignore

    crc32c_fun = crcmod.predefined.mkPredefinedCrcFun("crc-32c")
    return crc32c_fun(six.ensure_binary(data))
