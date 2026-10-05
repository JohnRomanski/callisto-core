import base64

import argon2

from django.conf import settings
from django.contrib.auth.hashers import BasePasswordHasher, PBKDF2PasswordHasher
from django.core.exceptions import ImproperlyConfigured
from django.utils.encoding import force_bytes
from django.utils.module_loading import import_string


# Portions of the below implementation are copyright the Django Software Foundation and individual contributors, and
# are under the BSD-3 Clause License:
# https://github.com/django/django/blob/master/LICENSE
def get_hashers():
    hashers = []
    for hasher_path in settings.KEY_HASHERS:
        hasher_cls = import_string(hasher_path)
        hasher = hasher_cls()
        if not getattr(hasher, "algorithm"):
            raise ImproperlyConfigured(
                f"hasher doesn't specify an algorithm name: {hasher_path}"
            )
        hashers.append(hasher)
    return hashers


def get_hashers_by_algorithm():
    hashers = get_hashers()
    return {hasher.algorithm: hasher for hasher in hashers}


def get_hasher(algorithm="default"):
    if algorithm == "default":
        return get_hashers()[0]
    else:
        hashers = get_hashers_by_algorithm()
        try:
            return hashers[algorithm]
        except KeyError:
            raise ValueError(
                f"Unknown key hashing algorithm {algorithm}."
                "Did you specify it in the KEY_HASHERS setting?"
            )


def identify_hasher(encoded):
    """
    Returns a hasher based on either a fully encoded key or just the encode
    prefix. If the encoded prefix is empty, assume the previous default hasher.
    """
    # assume all previous entries before this scheme is implemented use PBKDF2
    # + SHA256
    if not encoded:
        algorithm = "pbkdf2_sha256"
    else:
        algorithm = encoded.split("$", 1)[0]
    return get_hasher(algorithm)


def make_key(encode_prefix, key, salt):
    iterations = None
    hasher = identify_hasher(encode_prefix)

    if not encode_prefix:
        assert salt is not None
        iterations = settings.ORIGINAL_KEY_ITERATIONS
    else:
        salt = encode_prefix.rsplit("$", 1)[1]

    if encode_prefix and hasher.algorithm == "pbkdf2_sha256":
        iterations = encode_prefix.split("$")[1]

    params = None
    if encode_prefix and hasattr(hasher, "params_from_prefix"):
        # re-derive with the parameters the record was created with; the
        # current settings only apply to newly encrypted records
        params = hasher.params_from_prefix(encode_prefix)

    extra = {"params": params} if params else {}
    encoded = hasher.encode(key, salt, iterations=iterations, **extra)
    if hasher.algorithm == "pbkdf2_sha256" and hasher.must_update(encode_prefix):
        hasher.harden_runtime(key, encoded)

    prefix, key = hasher.split_encoded(encoded)
    return prefix, key


class PBKDF2KeyHasher(PBKDF2PasswordHasher):
    """
    Key stretching using Django's PBKDF2 + SHA256 implementation.

    Iterations may be changed safely in settings.
    """

    iterations = settings.KEY_ITERATIONS

    def must_update(self, encode_prefix):
        if not encode_prefix:
            iterations = settings.ORIGINAL_KEY_ITERATIONS
        else:
            algorithm, iterations, salt = encode_prefix.split("$", 2)
        return int(iterations) != self.iterations

    def split_encoded(self, encoded):
        """
        Splits the encoded string into a separate prefix and stretched key.

        Returns a prefix and a stretched key.
        """
        prefix, b64stretched = encoded.rsplit("$", 1)
        stretched_key = base64.b64decode(b64stretched)
        return prefix, force_bytes(stretched_key)


class Argon2KeyHasher(BasePasswordHasher):
    """
    Key stretching using Argon2i.

    Requires argon2_cffi which may cause portability issues due to it vendoring its own C code. See:
    https://argon2-cffi.readthedocs.io/en/stable/installation.html for more information.
    """

    algorithm = "argon2"
    library = "argon2"

    type = argon2.low_level.Type.I

    time_cost = settings.ARGON2_TIME_COST
    memory_cost = settings.ARGON2_MEM_COST
    parallelism = settings.ARGON2_PARALLELISM

    def current_params(self):
        return {
            "time_cost": self.time_cost,
            "memory_cost": self.memory_cost,
            "parallelism": self.parallelism,
        }

    def params_from_prefix(self, encode_prefix):
        """Reads m/t/p from a prefix like argon2$argon2i$v=19$m=512,t=2,p=2$salt"""
        raw = next(bit for bit in encode_prefix.split("$") if bit.startswith("m="))
        values = dict(item.split("=", 1) for item in raw.split(","))
        return {
            "memory_cost": int(values["m"]),
            "time_cost": int(values["t"]),
            "parallelism": int(values["p"]),
        }

    # accept **kwargs to allow a single encode statement across different
    # hashers
    def encode(self, key, salt, params=None, **kwargs):
        assert key is not None
        assert salt and "$" not in salt
        data = argon2.low_level.hash_secret(
            force_bytes(key),
            force_bytes(salt),
            hash_len=32,
            type=self.type,
            **(params or self.current_params()),
        )
        return self.algorithm + data.decode("utf-8")

    def verify(self, key, encoded):
        algorithm, rest = encoded.split("$", 1)
        assert algorithm == self.algorithm
        try:
            return argon2.low_level.verify_secret(
                force_bytes("$" + rest), force_bytes(key), type=self.type
            )
        except argon2.exceptions.VerificationError:
            return False

    def must_update(self, encoded):
        (
            algorithm,
            variety,
            version,
            time_cost,
            memory_cost,
            parallelism,
            salt,
            data,
        ) = self._decode(encoded)
        assert algorithm == self.algorithm
        return (
            argon2.low_level.ARGON2_VERSION != version
            or self.time_cost != time_cost
            or self.memory_cost != memory_cost
            or self.parallelism != parallelism
        )

    def harden_runtime(self, key, encoded):
        # The runtime for Argon2 is too complicated to implement a sensible
        # hardening algorithm.
        pass

    def split_encoded(self, encoded):
        """
        Splits the encoded string into a separate prefix and stretched key.
        Also decodes the salt and key from base64 encoding automatically done by argon2.low_level.secret_hash().

        Returns a prefix and a stretched key.
        """
        prefix_minus_salt, b64salt, b64stretched = encoded.rsplit("$", 2)
        missing_padding_salt = 4 - len(b64salt) % 4
        missing_padding_hash = 4 - len(b64stretched) % 4

        # argon2's secret_hash() output doesn't include padding so to decode it
        # we have to add it back in
        if missing_padding_hash:
            b64stretched += "=" * missing_padding_hash
        if missing_padding_salt:
            b64salt += "=" * missing_padding_salt

        stretched_key = base64.b64decode(b64stretched)

        salt = base64.b64decode(b64salt).decode("utf-8").rstrip("=")
        prefix = "$".join((prefix_minus_salt, salt))
        return prefix, stretched_key

    def _decode(self, encoded):
        """
        Split an encoded hash and return: (
            algorithm, variety, version, time_cost, memory_cost,
            parallelism, salt, data,
        ).
        """
        bits = encoded.split("$")
        if len(bits) == 5:
            # Argon2 < 1.3
            algorithm, variety, raw_params, salt, data = bits
            version = 0x10
        else:
            assert len(bits) == 6
            algorithm, variety, raw_version, raw_params, salt, data = bits
            assert raw_version.startswith("v=")
            version = int(raw_version[len("v=") :])
        params = dict(bit.split("=", 1) for bit in raw_params.split(","))
        assert len(params) == 3 and all(x in params for x in ("t", "m", "p"))
        time_cost = int(params["t"])
        memory_cost = int(params["m"])
        parallelism = int(params["p"])
        return (
            algorithm,
            variety,
            version,
            time_cost,
            memory_cost,
            parallelism,
            salt,
            data,
        )


class Argon2idKeyHasher(Argon2KeyHasher):
    """
    Key stretching using Argon2id, the variant recommended for new hashes.

    Parameters come from ARGON2ID_TIME_COST, ARGON2ID_MEMORY_COST (KiB) and
    ARGON2ID_PARALLELISM, read when a key is created. The defaults are the
    OWASP minimum. Matching derives a key for every stored match report on
    each submission, so higher costs make matching proportionally slower.
    """

    algorithm = "argon2id"
    type = argon2.low_level.Type.ID

    @property
    def time_cost(self):
        return getattr(settings, "ARGON2ID_TIME_COST", 2)

    @property
    def memory_cost(self):
        return getattr(settings, "ARGON2ID_MEMORY_COST", 19 * 1024)

    @property
    def parallelism(self):
        return getattr(settings, "ARGON2ID_PARALLELISM", 1)
