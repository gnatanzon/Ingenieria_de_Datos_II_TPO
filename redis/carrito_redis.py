import redis

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB   = 0

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)


def _key(usuario: str) -> str:
    return f"carrito:{usuario}"


def obtener_uris_carrito(usuario: str) -> list:
    """
    LRANGE carrito:<usuario> 0 -1
    """
    return r.lrange(_key(usuario), 0, -1)


def contar_carrito(usuario: str) -> int:
    """
    LLEN carrito:<usuario>
    """
    return r.llen(_key(usuario))


def agregar_uri(usuario: str, uri: str) -> int:
    """
    RPUSH carrito:<usuario> <uri>
    """
    key = _key(usuario)

    # Verificar si ya está (LRANGE + búsqueda en lista)
    if uri not in r.lrange(key, 0, -1):
        r.rpush(key, uri)

    return r.llen(key)

def quitar_uri(usuario: str, uri: str) -> int:
    """
    LREM carrito:<usuario> 0 <uri>
    """
    r.lrem(_key(usuario), 0, uri)
    return r.llen(_key(usuario))

def vaciar_carrito(usuario: str) -> None:
    """
    DEL carrito:<usuario>
    """
    r.delete(_key(usuario))