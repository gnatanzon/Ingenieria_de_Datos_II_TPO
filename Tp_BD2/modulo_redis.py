import redis
import time
import json

try:
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    print("[INFRAESTRUCTURA] Conexión establecida con Redis de forma exitosa.\n")
except Exception as e:
    print(f" Error de conexión: {e}")

