# -*- coding: utf-8 -*-
"""MD4 para Kad. Muchas instalaciones de Python (OpenSSL 3) traen md4 deshabilitado
en hashlib, asi que se incluye una implementacion en Python puro como respaldo."""
import struct


def _md4_py(message):
    def lrot(x, n):
        return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF

    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476]
    msg = bytearray(message)
    ml = (8 * len(message)) & 0xFFFFFFFFFFFFFFFF
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += struct.pack("<Q", ml)
    for off in range(0, len(msg), 64):
        X = struct.unpack("<16I", bytes(msg[off:off + 64]))
        a, b, c, d = h
        # Ronda 1
        for k in (0, 4, 8, 12):
            a = lrot((a + (((b & c) | (~b & d)) & 0xFFFFFFFF) + X[k]) & 0xFFFFFFFF, 3)
            d = lrot((d + (((a & b) | (~a & c)) & 0xFFFFFFFF) + X[k + 1]) & 0xFFFFFFFF, 7)
            c = lrot((c + (((d & a) | (~d & b)) & 0xFFFFFFFF) + X[k + 2]) & 0xFFFFFFFF, 11)
            b = lrot((b + (((c & d) | (~c & a)) & 0xFFFFFFFF) + X[k + 3]) & 0xFFFFFFFF, 19)
        # Ronda 2
        for k in (0, 1, 2, 3):
            a = lrot((a + (((b & c) | (b & d) | (c & d)) & 0xFFFFFFFF) + X[k] + 0x5A827999) & 0xFFFFFFFF, 3)
            d = lrot((d + (((a & b) | (a & c) | (b & c)) & 0xFFFFFFFF) + X[k + 4] + 0x5A827999) & 0xFFFFFFFF, 5)
            c = lrot((c + (((d & a) | (d & b) | (a & b)) & 0xFFFFFFFF) + X[k + 8] + 0x5A827999) & 0xFFFFFFFF, 9)
            b = lrot((b + (((c & d) | (c & a) | (d & a)) & 0xFFFFFFFF) + X[k + 12] + 0x5A827999) & 0xFFFFFFFF, 13)
        # Ronda 3
        for k in (0, 2, 1, 3):
            a = lrot((a + ((b ^ c ^ d) & 0xFFFFFFFF) + X[k] + 0x6ED9EBA1) & 0xFFFFFFFF, 3)
            d = lrot((d + ((a ^ b ^ c) & 0xFFFFFFFF) + X[k + 8] + 0x6ED9EBA1) & 0xFFFFFFFF, 9)
            c = lrot((c + ((d ^ a ^ b) & 0xFFFFFFFF) + X[k + 4] + 0x6ED9EBA1) & 0xFFFFFFFF, 11)
            b = lrot((b + ((c ^ d ^ a) & 0xFFFFFFFF) + X[k + 12] + 0x6ED9EBA1) & 0xFFFFFFFF, 15)
        h = [(h[0] + a) & 0xFFFFFFFF, (h[1] + b) & 0xFFFFFFFF,
             (h[2] + c) & 0xFFFFFFFF, (h[3] + d) & 0xFFFFFFFF]
    return struct.pack("<4I", *h)


def md4(data):
    """Devuelve el digest MD4 (16 bytes) de 'data'. Usa hashlib si lo soporta."""
    try:
        import hashlib
        h = hashlib.new("md4")
        h.update(data)
        return h.digest()
    except (ValueError, TypeError):
        return _md4_py(data)
