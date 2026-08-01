"""Password hashing for EC authentication (``jamule/auth/PasswordHasher.kt``).

aMule's algorithm combines two MD5 hashes:

1. ``salt_hash``     = MD5( hex(salt) in UPPERCASE )
2. ``password_hash`` = MD5( password in UTF-8 )
3. result            = MD5( hex(password_hash) in lowercase
                            + hex(salt_hash) in lowercase )

.. note:: **Nuance of the salt padding.**

   jaMule uses ``ULong.toHexString()``, which **zero-pads to 16 digits**.
   aMule's C client uses ``%lX``, which does **not** pad. For the known test
   vector (``salt=0x55099a4aea510c43``) both match because the salt
   already takes 16 digits. We reproduce jaMule's behavior
   (``format(salt, '016X')``) to keep bit-for-bit parity with the original
   library and its tests; if in some case the salt were < 2^60 the result
   could differ from aMule's, but jaMule (and therefore amarr) already assumed this
   behavior.
"""
from __future__ import annotations

import hashlib


def hash_password(password: str, salt: int) -> bytes:
    """Returns the 16-byte hash that aMule expects in EC_TAG_PASSWD_HASH."""
    salt_hex_upper = format(salt & 0xFFFFFFFFFFFFFFFF, "016X")
    salt_hash = hashlib.md5(salt_hex_upper.encode("ascii")).digest()

    password_hash = hashlib.md5(password.encode("utf-8")).digest()

    combined = (password_hash.hex().lower() + salt_hash.hex().lower()).encode("ascii")
    return hashlib.md5(combined).digest()
