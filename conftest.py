import os

import nacl.signing

# Test-only defaults. Production deployments must set these explicitly.
os.environ.setdefault("INDEXING_KEY", "thisisatest")

if "PASETO_PRIVATE_KEY" not in os.environ:
    _signing_key = nacl.signing.SigningKey.generate()
    os.environ["PASETO_PRIVATE_KEY"] = (
        bytes(_signing_key) + bytes(_signing_key.verify_key)
    ).hex()
