import redis_db

try:
    db = redis_db.Redis(host='localhost', port=6379, decode_responses=True)

    db.ping()
    print("Conexión exitosa")

except redis_db.exceptions.ConnectionError as e:
    print(f"Error de conexión con Redis: {e}")

except Exception as e:
    print(f"Error: {e}")