import json
import tempfile

import gnupg


class GPGEncryptionError(Exception):
    pass


def gpg_encrypt(data, public_key):
    """
    Encrypts data to public_key using a throwaway keyring.

    Raises GPGEncryptionError instead of returning empty output, so a
    failed import or encryption can never result in sending a blank file.
    """
    with tempfile.TemporaryDirectory() as gnupghome:
        gpg = gnupg.GPG(gnupghome=gnupghome)
        imported_keys = gpg.import_keys(public_key)
        if not imported_keys.fingerprints:
            raise GPGEncryptionError("no usable public key could be imported")
        encrypted = gpg.encrypt(
            data, imported_keys.fingerprints[0], armor=True, always_trust=True
        )
        if not encrypted.ok:
            raise GPGEncryptionError(f"gpg encryption failed: {encrypted.status}")
        return encrypted.data


def gpg_encrypt_data(data, key):
    return gpg_encrypt(json.dumps(data), key)
