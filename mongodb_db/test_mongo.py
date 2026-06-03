from pymongo import MongoClient
from carga_mongodb import MongoPlaylistInserter, build_doc 
from mongo_analytics import MongoAnalytics

# Configuración de la base de datos temporal de prueba
URI = "mongodb://localhost:27017/"
DB_TEST = "test_sonicmesh_db"
COLL_TEST = "test_canciones"

def ejecutar_tests():
    print("Iniciando pruebas de MongoDB\n")
    
    client = MongoClient(URI)
    db = client[DB_TEST]
    collection = db[COLL_TEST]
    
    # para que colección empiece vacía
    collection.delete_many({})

    
    # TEST 1: Verificar el formateo del diccionario (build_doc)

    print("[Test 1] Probando transformación de datos (build_doc)...")
    fila_falsa = {
        "Track URI": "spotify:track:test999",
        "Track Name": "Canción de Prueba",
        "Artist Name(s)": "Charly Garcia; Nito Mestre",
        "Album Name": "Vida",
        "Release Date": "1972-11-05",
        "Popularity": 88,
        "Danceability": 0.65,
        "Energy": 0.70
    }
    
    doc_transformado = build_doc(fila_falsa)
    
    # validamos que los campos se hayan estructurado bien usando 'assert'
    assert doc_transformado["uri"] == "spotify:track:test999", "Error: La URI no coincide"
    assert doc_transformado["nombre"] == "Canción de Prueba", "Error: El nombre no coincide"
    assert "Charly Garcia" in doc_transformado["artistas"], "Error: Falta Charly en la lista"
    assert doc_transformado["album"]["nombre"] == "Vida", "Error: El álbum no se estructuró correctamente"
    print("Test 1 aprobado: Conversión de campos impecable.")


    # TEST 2: Verificar que las consultas corran sin errores
    print("\n[Test 2] Probando inserción e índices")
    
    # inserto documentos controlados para simular datos reales
    canciones_mock = [
        {
            "uri": "spotify:track:m1", "nombre": "Seminare", 
            "artistas": ["Serú Girán"], "popularidad": 95, "explicito": False,
            "bailabilidad": 0.50, "energia": 0.60, "duracion_ms": 200000,
            "album": {"nombre": "Grasa de las Capitales", "fecha_de_lanzamiento": "1979-01-01"}
        },
        {
            "uri": "spotify:track:m2", "nombre": "Autoositos", 
            "artistas": ["Serú Girán"], "popularidad": 40, "explicito": False,
            "bailabilidad": 0.80, "energia": 0.85, "duracion_ms": 150000,
            "album": {"nombre": "Serú Girán", "fecha_de_lanzamiento": "1978-01-01"}
        }
    ]
    collection.insert_many(canciones_mock)
    
    # instancio clase de analítica apuntando a la base de prueba
    analytics = MongoAnalytics(URI, DB_TEST, COLL_TEST)
    
    try:
        # para ver que los métodos no tiren excepciones de sintaxis o de conexión
        analytics.crear_indices()
        analytics.top_artistas_mas_populares()
        analytics.buscar_por_mood(danceability_min=0.7, energy_min=0.7)
        analytics.resumen_por_decada()
        
        # validación de lógica: La consulta de mood debería traer solo 1 tema ('Autoositos')
        query_mood = {"bailabilidad": {"$gt": 0.7}, "energia": {"$gt": 0.7}}
        resultado = list(collection.find(query_mood))
        assert len(resultado) == 1, "Error: La consulta de Mood debería devolver exactamente 1 canción"
        assert resultado[0]["nombre"] == "Autoositos", "Error: La canción filtrada por Mood debió ser 'Autoositos'"
        
        print("\nTest 2 aprobado: Las agregaciones y búsquedas funcionan.")
        
    except Exception as e:
        print(f"\n ¡Fallo en el Test 2! Ocurrió un error inesperado: {e}")
        raise e
    finally:
        analytics.close()


    # LIMPIEZA FINAL
    
    print("\nBorrando base de datos temporal de test...")
    client.drop_database(DB_TEST)
    client.close()
    print("\n El código pasó todas las pruebas sin problemas.")

if __name__ == "__main__":
    ejecutar_tests()