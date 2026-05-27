"""Hash de contraseña para autenticación EC (``jamule/auth/PasswordHasher.kt``).

El algoritmo de aMule combina dos hashes MD5:

1. ``salt_hash``     = MD5( hex(salt) en MAYÚSCULAS )
2. ``password_hash`` = MD5( password en UTF-8 )
3. resultado         = MD5( hex(password_hash) en minúsculas
                            + hex(salt_hash) en minúsculas )

.. note:: **Matiz del relleno del salt.**

   jaMule usa ``ULong.toHexString()``, que **rellena con ceros a 16 dígitos**.
   El cliente C de aMule usa ``%lX``, que **no rellena**. Para el vector de
   prueba conocido (``salt=0x55099a4aea510c43``) ambos coinciden porque el salt
   ya ocupa 16 dígitos. Reproducimos el comportamiento de jaMule
   (``format(salt, '016X')``) para mantener paridad bit a bit con la librería
   original y con sus tests; si en algún caso el salt fuese < 2^60 el resultado
   podría diferir del de aMule, pero jaMule (y por tanto amarr) ya asumían este
   comportamiento.
"""
from __future__ import annotations

import hashlib


def hash_password(password: str, salt: int) -> bytes:
    """Devuelve el hash de 16 bytes que aMule espera en EC_TAG_PASSWD_HASH."""
    salt_hex_upper = format(salt & 0xFFFFFFFFFFFFFFFF, "016X")
    salt_hash = hashlib.md5(salt_hex_upper.encode("ascii")).digest()

    password_hash = hashlib.md5(password.encode("utf-8")).digest()

    combined = (password_hash.hex().lower() + salt_hash.hex().lower()).encode("ascii")
    return hashlib.md5(combined).digest()
