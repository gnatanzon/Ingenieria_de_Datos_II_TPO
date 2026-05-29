import redis
import csv

try:
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    if r.ping():
        print("\n¡SALIÓ PERFECTO! Python y Redis en Docker están conectados.")
        print("Tu entorno ya está listo para el TP de la tienda de música.\n")
        
except Exception as e:
    print(f"\n Algo falló. Error: {e}")
except NameError as b:
    print(f"\n El nombre de la musica no esta Error: {b}")

archivos_csv = [
    "playlist_anto.csv",
    "playlist_cami.csv",
    "playlist_chen.csv",
    "playlist_guillermina.csv",
    "playlist_julib.csv",
    "playlist_julis.csv"
]
print("Iniciando la carga automática de las 6 playlists...\n")


#bucle for
for nombre_archivo in archivos_csv:
    try:
        
        with open(nombre_archivo, mode='r', encoding='utf-8') as archivo:
            lector = csv.DictReader(archivo)
            
            for fila in lector:
                # 3. Buscamos el nombre probando las variantes
                nombre_cancion = (
                    fila.get('Track Name') or 
                    fila.get('Title') or 
                    fila.get('TrackName') or 
                    fila.get('Nombre')
                )
                
                # 4. Si lo encuentra, lo guarda una sola vez en Redis
                if nombre_cancion:
                    r.zincrby("ranking:global", 1, nombre_cancion)
                    
        print(f" Archivo '{nombre_archivo}' procesado con éxito.")
        
    except FileNotFoundError:
        print(f" Alerta: No encontré el archivo '{nombre_archivo}' en la carpeta.")

print("\n ¡Terminado! Todos los datos se inyectaron automáticamente en la memoria RAM de Redis.")