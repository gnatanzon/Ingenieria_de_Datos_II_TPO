import redis

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB   = 0

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

TTL_CARRITO = 900

def _key(usuario: str):
    return f"carrito:{usuario}"


def obtener_uris_carrito(usuario: str):
    return r.execute_command("SMEMBERS", _key(usuario))


def contar_carrito(usuario: str):
    return r.execute_command("SCARD", _key(usuario))


def agregar_uri(usuario: str, uri: str):
    key = _key(usuario)
    r.execute_command("SADD", _key(usuario), uri)
    r.execute_command("EXPIRE", key, TTL_CARRITO)
    return r.execute_command("SCARD", _key(usuario))


def quitar_uri(usuario: str, uri: str):
    key = _key(usuario)
    r.execute_command("SREM", _key(usuario), uri)
    r.execute_command("EXPIRE", key, TTL_CARRITO)
    return r.execute_command("SCARD", _key(usuario))


def vaciar_carrito(usuario: str):
    r.execute_command("DEL", _key(usuario))