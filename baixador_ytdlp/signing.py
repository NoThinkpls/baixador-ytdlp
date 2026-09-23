"""Assinatura Ed25519 (RFC 8032) do ``SHA256SUMS.txt`` das releases.

Implementação direta da referência da RFC 8032, seção 6, sem dependências
nativas: só é usada para verificar UMA assinatura por atualização, então o
custo (dezenas de ms em Python puro) é irrelevante e o instalador não ganha
outra biblioteca binária. A validação cruzada com ``cryptography`` e os vetores
oficiais da RFC ficam em ``tests/test_signing.py``.

Por que existe: o atualizador conferia o instalador contra o SHA256SUMS da
MESMA release. Quem controlasse a conta ou o token do Actions publicaria os
dois juntos. Com a chave pública embutida no app, o hash só é aceito se tiver
sido assinado pela chave privada, que fica fora do repositório.
"""
from __future__ import annotations

import base64
import hashlib

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _sha512_modq(data: bytes) -> int:
    return int.from_bytes(_sha512(data), "little") % _L


# Pontos em coordenadas estendidas (X, Y, Z, T).
def _point_add(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % _P
    b = (p[1] + p[0]) * (q[1] + q[0]) % _P
    c = 2 * p[3] * q[3] * _D % _P
    d = 2 * p[2] * q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _point_mul(scalar: int, point):
    result = (0, 1, 1, 0)
    while scalar > 0:
        if scalar & 1:
            result = _point_add(result, point)
        point = _point_add(point, point)
        scalar >>= 1
    return result


def _point_equal(p, q) -> bool:
    if (p[0] * q[2] - q[0] * p[2]) % _P != 0:
        return False
    return (p[1] * q[2] - q[1] * p[2]) % _P == 0


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compress(point) -> bytes:
    zinv = pow(point[2], _P - 2, _P)
    x = point[0] * zinv % _P
    y = point[1] * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(data: bytes):
    if len(data) != 32:
        return None
    y = int.from_bytes(data, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _secret_expand(secret: bytes) -> tuple[int, bytes]:
    if len(secret) != 32:
        raise ValueError("A chave privada Ed25519 tem 32 bytes.")
    digest = _sha512(secret)
    a = int.from_bytes(digest[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, digest[32:]


def public_key(secret: bytes) -> bytes:
    a, _prefix = _secret_expand(secret)
    return _compress(_point_mul(a, _G))


def sign(secret: bytes, message: bytes) -> bytes:
    a, prefix = _secret_expand(secret)
    public = _compress(_point_mul(a, _G))
    r = _sha512_modq(prefix + message)
    rs = _compress(_point_mul(r, _G))
    h = _sha512_modq(rs + public + message)
    s = (r + h * a) % _L
    return rs + int.to_bytes(s, 32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    a_point = _decompress(public)
    if a_point is None:
        return False
    rs = signature[:32]
    r_point = _decompress(rs)
    if r_point is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = _sha512_modq(rs + public + message)
    return _point_equal(_point_mul(s, _G), _point_add(r_point, _point_mul(h, a_point)))


def verify_detached(public_keys_b64: tuple[str, ...], message: bytes, signature_text: str) -> bool:
    """Aceita a assinatura se qualquer chave publicada no app a validar (rotação)."""
    try:
        signature = base64.b64decode(signature_text.strip(), validate=True)
    except ValueError:
        return False
    for encoded in public_keys_b64:
        try:
            key = base64.b64decode(encoded, validate=True)
        except ValueError:
            continue
        if verify(key, message, signature):
            return True
    return False
