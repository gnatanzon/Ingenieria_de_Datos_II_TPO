import numpy as np
import pandas as pd
from neo4j import GraphDatabase
from voyager import Index, Space

URI              = "bolt://localhost:7687"
USER             = "neo4j"
PASSWORD         = "guillermina"
USUARIO_OBJETIVO = ("Guillermina")
TOP_AMIGAS       = 2
TOP_RECOMENDADAS = 10
FEATURES         = ['bailabilidad', 'energia', 'valencia', 'tempo',
                    'volumen', 'vivacidad', 'instrumentalidad', 'acustica', 'dialogado']

query_afinidad = """
MATCH (yo:User {nombre: $target_user}), (amiga:User)
WHERE yo <> amiga

// Canciones en común
OPTIONAL MATCH (yo)-[:AGREGO]->(t:Track)<-[:AGREGO]-(amiga)
WITH yo, amiga, count(DISTINCT t) AS canciones_en_comun

// Artistas en común
OPTIONAL MATCH (yo)-[:AGREGO]->(:Track)<-[:INTERPRETA]-(a:Artista)-[:INTERPRETA]->(:Track)<-[:AGREGO]-(amiga)
WITH yo, amiga, canciones_en_comun, count(DISTINCT a) AS artistas_en_comun

// Géneros en común
OPTIONAL MATCH (yo)-[:AGREGO]->(:Track)-[:GENERO]->(g:Genero)<-[:GENERO]-(:Track)<-[:AGREGO]-(amiga)
WITH yo, amiga, canciones_en_comun, artistas_en_comun, count(DISTINCT g) AS generos_en_comun

WHERE canciones_en_comun > 0 OR artistas_en_comun > 0 OR generos_en_comun > 0

RETURN amiga.nombre AS amiga,
       canciones_en_comun,
       artistas_en_comun,
       generos_en_comun,
       (canciones_en_comun * 3 + artistas_en_comun * 2 + generos_en_comun * 1) AS puntaje_afinidad
ORDER BY puntaje_afinidad DESC
"""

print(f"Procesando, target: '{USUARIO_OBJETIVO}'...")
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
with driver.session() as session:
    records = [r.data() for r in session.run(query_afinidad, target_user=USUARIO_OBJETIVO)]
driver.close()

df_afinidad = pd.DataFrame(records)

if df_afinidad.empty:
    print("No se encontraron relaciones.")
    exit()

top_amigas = df_afinidad.head(TOP_AMIGAS)['amiga'].tolist()

print(f"\nTop {TOP_AMIGAS} amigas más afines:")
for _, row in df_afinidad.head(TOP_AMIGAS).iterrows():
    print(f"  • {row['amiga']} → {int(row['puntaje_afinidad'])} pts ")

query_candidatas = """
MATCH (yo:User {nombre: $target_user}), (amiga:User)
WHERE amiga.nombre IN $top_amigas

MATCH (amiga)-[:AGREGO]->(candidata:Track)
WHERE NOT (yo)-[:AGREGO]->(candidata)

RETURN DISTINCT
    candidata.uri          AS uri,
    candidata.nombre       AS nombre,
    candidata.bailabilidad AS bailabilidad,
    candidata.energia      AS energia,
    candidata.valencia     AS valencia,
    candidata.tempo        AS tempo,
    candidata.volumen      AS volumen,
    candidata.vivacidad    AS vivacidad,
    candidata.instrumentalidad AS instrumentalidad,
    candidata.acustica     AS acustica,
    candidata.dialogado    AS dialogado
"""

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
with driver.session() as session:
    candidatas = [r.data() for r in session.run(query_candidatas,
                                                  target_user=USUARIO_OBJETIVO,
                                                  top_amigas=top_amigas)]
driver.close()

df_candidatas = pd.DataFrame(candidatas)

if df_candidatas.empty:
    print("No se encontraron canciones nuevas.")
    exit()

print(f"Se encontraron {len(df_candidatas)} canciones candidatas.")

query_perfil = """
MATCH (u:User {nombre: $target_user})-[:AGREGO]->(t:Track)
RETURN t.bailabilidad      AS bailabilidad,
       t.energia          AS energia,
       t.valencia         AS valencia,
       t.tempo            AS tempo,
       t.volumen          AS volumen,
       t.vivacidad        AS vivacidad,
       t.instrumentalidad AS instrumentalidad,
       t.acustica         AS acustica,
       t.dialogado        AS dialogado
"""

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
with driver.session() as session:
    perfil_records = [r.data() for r in session.run(query_perfil, target_user=USUARIO_OBJETIVO)]
driver.close()

df_perfil = pd.DataFrame(perfil_records).dropna()

if df_perfil.empty:
    print("El usuario no tiene canciones.")
    exit()

#VOYAGER
vector_usuario = df_perfil[FEATURES].mean().to_numpy().astype('float32')

df_candidatas = df_candidatas.dropna(subset=FEATURES).reset_index(drop=True)
candidate_vectors = df_candidatas[FEATURES].to_numpy().astype('float32')

index = Index(Space.Euclidean, num_dimensions=len(FEATURES))
index.add_items(candidate_vectors)

k = min(TOP_RECOMENDADAS, len(df_candidatas))
neighbors, distances = index.query(vector_usuario, k=k)

print(f"RECOMENDACIONES PARA {USUARIO_OBJETIVO.upper()}")
print(f"Seleccionadas entre canciones de las amigas más afines,")
print(f"ordenadas por similitud acústica con tu perfil musical:\n")

for rank, (idx, dist) in enumerate(zip(neighbors, distances), 1):
    nombre = df_candidatas.loc[idx, 'nombre']
    print(f"{rank:>2}. '{nombre}'")