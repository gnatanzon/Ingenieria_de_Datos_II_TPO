import redis

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB   = 0

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)


def _key(usuario: str):
    return f"carrito:{usuario}"


def obtener_uris_carrito(usuario: str):
    return r.execute_command("LRANGE", _key(usuario), 0, -1)


def contar_carrito(usuario: str):
    return r.execute_command("LLEN", _key(usuario))


def agregar_uri(usuario: str, uri: str):
    key = _key(usuario)
    existentes = r.execute_command("LRANGE", key, 0, -1)
    if uri not in existentes:
        r.execute_command("RPUSH", key, uri)
    return r.execute_command("LLEN", key)


def quitar_uri(usuario: str, uri: str):
    key = _key(usuario)
    r.execute_command("LREM", key, 0, uri)
    return r.execute_command("LLEN", key)


def vaciar_carrito(usuario: str):
    r.execute_command("DEL", _key(usuario))