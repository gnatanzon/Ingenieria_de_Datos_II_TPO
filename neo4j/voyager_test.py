import numpy as np
import pandas as pd
from neo4j import GraphDatabase
from voyager import Index, Space

# 1. Configuración de conexiones (Coincidiendo exactamente con tu carga)
URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "guillermina"

# Podés cambiar este nombre por cualquiera que esté en las playlists (ej: 'Antonella', 'Chen', etc.)
USUARIO_OBJETIVO = "Guillermina"

# 2. Query adaptada a tus etiquetas y propiedades en español
query = """
MATCH (t:Track)<-[:AGREGO]-(anyUser:User)
WITH DISTINCT t
OPTIONAL MATCH (u:User {nombre: $target_user})-[:AGREGO]->(t)
WITH t, u IS NOT NULL AS le_gusta
RETURN t.uri AS uri, 
       t.nombre AS nombre, 
       t.bailabilidad AS bailabilidad, 
       t.energia AS energia,
       t.valencia AS valencia,
       t.tempo AS tempo,
       le_gusta
"""

print(f"Conectando a Neo4j para analizar las playlists del grupo...")
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
with driver.session() as session:
    result = session.run(query, target_user=USUARIO_OBJETIVO)
    records = [r.data() for r in result]
driver.close()

# Convertimos el resultado a un DataFrame de Pandas
df = pd.DataFrame(records)

if df.empty:
    print("La base de datos está vacía. Asegurate de haber corrido primero tu script de carga.")
    exit()

# 3. Definimos las características que guardaste en tu Neo4j
features = ['bailabilidad', 'energia', 'valencia', 'tempo']
df_norm = df.copy()

# Normalización Min-Max para asegurar que ambas métricas tengan el mismo peso matemático (rango 0 a 1)
for col in features:
    min_val = df_norm[col].min()
    max_val = df_norm[col].max()
    if max_val != min_val:
        df_norm[col] = (df_norm[col] - min_val) / (max_val - min_val)
    else:
        df_norm[col] = 0.0

# 4. Separación por lógica de Grafos (Filtro Colaborativo)
# Canciones que al usuario objetivo YA le gustan (para armar su perfil sónico)
df_liked = df_norm[df_norm['le_gusta'] == True]
# Canciones candidatas (temas agregados por amigos que el usuario objetivo NO tiene)
df_candidates = df_norm[df_norm['le_gusta'] == False]

if df_liked.empty:
    print(f"El usuario '{USUARIO_OBJETIVO}' no tiene canciones cargadas para calcular sus gustos.")
    exit()

if df_candidates.empty:
    print(f"¡Oops! '{USUARIO_OBJETIVO}' ya tiene agregadas absolutamente todas las canciones de sus amigos.")
    exit()

# 5. Cálculo del "Vector de Gusto" promedio del usuario objetivo
user_taste_vector = df_liked[features].mean().to_numpy().astype('float32')

print(f"\n--- Perfil Musical Calculado para {USUARIO_OBJETIVO} ---")
print(f" * Bailabilidad promedio: {user_taste_vector[0]:.2f}")
print(f" * Energía promedio: {user_taste_vector[1]:.2f}")

# 6. Indexar los vectores candidatos en Voyager (Espacio Euclideo bidimensional)
candidate_vectors = df_candidates[features].to_numpy().astype('float32')

index = Index(Space.Euclidean, num_dimensions=len(features))
index.add_items(candidate_vectors)

# Listas auxiliares para mapear los resultados de Voyager con los nombres reales
id_to_name = df_candidates['nombre'].tolist()

# 7. Consultar a Voyager cuáles canciones candidatas se acercan más al perfil del usuario
top_k = min(5, len(df_candidates))
neighbors, distances = index.query(user_taste_vector, k=top_k)

# 8. Desplegar los resultados del Recomendador Híbrido
print(f"\n=======================================================")
print(f"   TOP {top_k} RECOMENDACIONES HÍBRIDAS PARA {USUARIO_OBJETIVO.upper()} ")
print(f"=======================================================")
print("Filtrado por Grafo Social (Playlists de amigos) y ordenado por Spotify Voyager:\n")

for rank, (neighbor_id, distance) in enumerate(zip(neighbors, distances), 1):
    nombre_cancion = id_to_name[neighbor_id]
    print(f"{rank}. 🎵 '{nombre_cancion}'")
    print(f"   • Distancia Euclidiana a su perfil de gusto: {distance:.4f}")