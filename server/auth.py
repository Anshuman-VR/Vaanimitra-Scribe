"""
Admin authentication dependency.

The ADMIN_KEY_HASH environment variable must be the SHA-256 hex digest of
the admin password. If not set, defaults to sha256("test123").

To generate a hash for a new password:
    python -c "import hashlib; print(hashlib.sha256(b'yourpassword').hexdigest())"

Or in bash:
    echo -n "yourpassword" | sha256sum | cut -d' ' -f1
"""
import os
import hmac
import hashlib

from fastapi import Header, HTTPException


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# Default hash is sha256("test123"). Override via env var in production.
_DEFAULT_HASH = _sha256("test123")
ADMIN_KEY_HASH: str = os.environ.get("ADMIN_KEY_HASH", _DEFAULT_HASH)


async def verify_admin(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    """
    FastAPI dependency that verifies the X-Admin-Key header using constant-time
    comparison against a stored SHA-256 hash. Raises 401 on mismatch.
    """
    if not hmac.compare_digest(_sha256(x_admin_key), ADMIN_KEY_HASH):
        raise HTTPException(status_code=401, detail="Unauthorized")
