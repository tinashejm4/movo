import base64
import hashlib
import secrets


ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000


def new_salt_hex():
    return secrets.token_hex(16)


def make_offline_verifier(code, *, salt=None):
    """Return a versioned verifier that Dart can reproduce byte for byte."""
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode("ascii"), salt, ITERATIONS)
    return {
        "version": 1,
        "algorithm": ALGORITHM,
        "iterations": ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "digest": base64.b64encode(digest).decode("ascii"),
    }
