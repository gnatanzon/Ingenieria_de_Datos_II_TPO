import pandas as pd
from pymongo import MongoClient, ASCENDING, DESCENDING

MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "sonicmesh_db"
COLLECTION_NAME = "canciones"

client = MongoClient(MONGO_URI)
col    = client[DATABASE_NAME][COLLECTION_NAME]

class MongoAnalytics:
    def __init__(self, uri, db_name, collection_name):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def crear_indices(self):
        #1. INDEXACIÓN: creo un índice compuesto por 'artistas' y 'popularidad' para acelerar los rankings.
        
        print("Creando índices...")
        self.collection.create_index([("artistas", ASCENDING), ("popularidad", DESCENDING)])
        # índice único para la URI de la canción (evita duplicados si corro la carga dos veces)
        self.collection.create_index([("uri", ASCENDING)], unique=True)

    def top_artistas_mas_populares(self):
        #2. PIPELINE DE AGREGACIÓN: ranking de artistas basado en el promedio de popularidad de sus canciones individuales.
        
        print("\n--- TOP 5 ARTISTAS MÁS POPULARES EN EL CATÁLOGO ---")
        pipeline = [
            # desestructuro el array de artistas para analizar cada uno por separado
            {"$unwind": "$artistas"},
            # agrupo por nombre de artista y calculo el promedio de popularidad
            {
                "$group": {
                    "_id": "$artistas",
                    "popularidad_promedio": {"$avg": "$popularidad"},
                    "total_canciones": {"$sum": 1}
                }
            },
            # Filtro artistas que tengan más de una canción para que sea representativo
            {"$match": {"total_canciones": {"$gt": 1}}},
            # Ordeno de mayor a menor popularidad
            {"$sort": {"popularidad_promedio": DESCENDING}},
            # Limito a los 5 mejores
            {"$limit": 5}
        ]
        
        resultados = self.collection.aggregate(pipeline)
        for i, res in enumerate(resultados, 1):
            print(f"{i}. 🎤 {res['_id']} - Promedio: {res['popularidad_promedio']:.1f} (Basado en {res['total_canciones']} temas)")

    def buscar_por_mood(self, danceability_min, energy_min):
        
        #3. CONSULTA CON FILTROS AVANZADOS: Buscar canciones para "fiesta" (alta bailabilidad y energía) que no sean explícitas.
        
        print(f"\n--- RECOMENDACIÓN POR 'MOOD' (Bailabilidad > {danceability_min} y Energía > {energy_min}) ---")
        
        query = {
            "bailabilidad": {"$gt": danceability_min},
            "energia": {"$gt": energy_min},
            "explicito": {"$ne": True}  # Que no sea explícito (apto todo público)
        }
        
        proyeccion = {
            "nombre": 1, 
            "artistas": 1, 
            "bailabilidad": 1, 
            "energia": 1, 
            "_id": 0
        }
        
        # busca, ordena por popularidad y trae las 5 mejores
        resultados = self.collection.find(query, proyeccion).sort("popularidad", DESCENDING).limit(5)
        
        for i, track in enumerate(resultados, 1):
            artistas = ", ".join(track.get("artistas", []))
            print(f"{i}. '{track['nombre']}' de {artistas} [Bailabilidad: {track['bailabilidad']}, Energía: {track['energia']}]")

    def resumen_por_decada(self):
        """
        ANALÍTICA AVANZADA: Agrupación y cálculo de duración promedio 
        utilizando la clave exacta en español guardada en la carga.
        """
        print("\n--- DURACIÓN PROMEDIO DE LAS CANCIONES POR DÉCADA ---")
        pipeline = [
            # 1. Filtramos las canciones que tengan cargada la fecha de lanzamiento en español
            {
                "$match": {
                    "album.fecha_de_lanzamiento": {"$exists": True, "$ne": None}
                }
            },
            # 2. Tomamos los primeros 3 caracteres del año (ej: "202" de "2023") y le concatenamos "0s"
            {
                "$project": {
                    "duracion_ms": 1,
                    "decada": {
                        "$concat": [
                            {"$substr": ["$album.fecha_de_lanzamiento", 0, 3]},
                            "0s"
                        ]
                    }
                }
            },
            # 3. Agrupamos por década y convertimos los milisegundos a minutos promedio
            {
                "$group": {
                    "_id": "$decada",
                    "duracion_promedio_min": {"$avg": {"$divide": ["$duracion_ms", 60000]}},
                    "cantidad_temas": {"$sum": 1}
                }
            },
            # 4. Ordenamos cronológicamente de menor a mayor
            {"$sort": {"_id": 1}}
        ]
        
        resultados = self.collection.aggregate(pipeline)
        
        conteo = 0
        for res in resultados:
            # Validamos que el ID de la década sea coherente (ej: "2020s" tiene 5 caracteres)
            if res['_id'] and len(res['_id']) == 5 and res['_id'][0].isdigit():
                print(f" * Década {res['_id']}: {res['duracion_promedio_min']:.2f} minutos promedio ({res['cantidad_temas']} canciones)")
                conteo += 1
                
        if conteo == 0:
            print("⚠️ No se encontraron décadas para agrupar. Verificá que los documentos en la base de datos tengan el campo 'album.fecha_de_lanzamiento'.")

    def close(self):
        self.client.close()


def buscar_canciones(busqueda: str = "", genero: str = "") -> list:
    print(f"\n--- CONSULTA 1: BÚSQUEDA DE CANCIONES (q='{busqueda}', genero='{genero}') ---")

    query = {}

    if busqueda:
        query["$or"] = [
            {"nombre": {"$regex": busqueda, "$options": "i"}},
            {"artistas": {"$regex": busqueda, "$options": "i"}},
        ]

    if genero:
        query["generos"] = {"$regex": genero, "$options": "i"}

    canciones = list(col.find(query, {"_id": 0}).limit(100))
    print(f"   → {len(canciones)} canciones encontradas.")
    return canciones


def obtener_generos() -> list:
    print("\n--- CONSULTA 2: GÉNEROS ÚNICOS (distinct) ---")

    query = col.distinct("generos")

    generos = set()
    for g in query:
        if g:
            for item in str(g).split(","):
                item = item.strip()
                if item:
                    generos.add(item)

    resultado = sorted(generos)
    print(f"   → {len(resultado)} géneros distintos encontrados.")
    return resultado


def buscar_cancion_por_uri(uri: str) -> dict | None:
    print(f"\n--- CONSULTA 3: BUSCAR POR URI ---")
    print(f"   uri: {uri}")

    query = {"uri": uri}

    resultado = col.find_one(query, {"_id": 0})
    print(f"   → {'Encontrada' if resultado else 'No encontrada'}.")
    return resultado


def buscar_canciones_por_uris(uris: list) -> list:
    print(f"\n--- CONSULTA 4: BUSCAR POR LISTA DE URIs ($in) ---")
    print(f"   URIs solicitados: {len(uris)}")

    query = {"uri": {"$in": uris}}

    docs = {
        doc["uri"]: doc
        for doc in col.find(query, {"_id": 0})
    }


    resultado = [docs[uri] for uri in uris if uri in docs]
    print(f"   → {len(resultado)} documentos hidratados.")
    return resultado

if __name__ == "__main__":
    analytics = MongoAnalytics(MONGO_URI, DATABASE_NAME, COLLECTION_NAME)
    try:
        analytics.crear_indices()
        analytics.top_artistas_mas_populares()
        analytics.buscar_por_mood(danceability_min=0.7, energy_min=0.7)
        analytics.resumen_por_decada()
    except Exception as e:
        print(f"ERROR en analítica: {e}")
    finally:
        analytics.close()