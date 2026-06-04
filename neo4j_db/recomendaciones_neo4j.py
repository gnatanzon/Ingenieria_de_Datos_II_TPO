import numpy as np
import pandas as pd
from neo4j import GraphDatabase
from voyager import Index, Space

URI              = "bolt://localhost:7687"
USER             = "neo4j"
PASSWORD         = "guillermina"
USUARIO_OBJETIVO = "Carla"
TOP_AMIGAS       = 2
TOP_RECOMENDADAS = 10
FEATURES         = ['bailabilidad', 'energia', 'valencia', 'tempo',
                    'sonoridad', 'vivacidad', 'instrumentalidad', 'acustica', 'discursividad']

query_afinidad = """
MATCH (yo:User {nombre: $target_user}), (amiga:User)
WHERE yo <> amiga

OPTIONAL MATCH (yo)-[:AGREGO]->(t:Track)<-[:AGREGO]-(amiga)
WITH yo, amiga, count(DISTINCT t) AS canciones_en_comun

OPTIONAL MATCH (yo)-[:AGREGO]->(:Track)-[:PERTENECE_A]->(al:Album)<-[:PERTENECE_A]-(:Track)<-[:AGREGO]-(amiga)
WITH yo, amiga, canciones_en_comun, count(DISTINCT al) AS albumes_en_comun

OPTIONAL MATCH (yo)-[:AGREGO]->(:Track)<-[:INTERPRETA]-(a:Artista)-[:INTERPRETA]->(:Track)<-[:AGREGO]-(amiga)
WITH yo, amiga, canciones_en_comun, albumes_en_comun, count(DISTINCT a) AS artistas_en_comun

OPTIONAL MATCH (yo)-[:AGREGO]->(:Track)-[:GENERO]->(g:Genero)<-[:GENERO]-(:Track)<-[:AGREGO]-(amiga)
WITH yo, amiga, canciones_en_comun, albumes_en_comun, artistas_en_comun, count(DISTINCT g) AS generos_en_comun

WHERE canciones_en_comun > 0 OR albumes_en_comun > 0 OR artistas_en_comun > 0 OR generos_en_comun > 0

RETURN amiga.nombre AS amiga,
       canciones_en_comun,
       albumes_en_comun,
       artistas_en_comun,
       generos_en_comun,
       (canciones_en_comun * 4 + albumes_en_comun * 3 + artistas_en_comun * 2 + generos_en_comun * 1) AS puntaje_afinidad
ORDER BY puntaje_afinidad DESC
"""

print(f"Calculando afinidad social para '{USUARIO_OBJETIVO}'...")
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
with driver.session() as session:
    records = [r.data() for r in session.run(query_afinidad, target_user=USUARIO_OBJETIVO)]
driver.close()

df_afinidad = pd.DataFrame(records)

if df_afinidad.empty:
    print("No se encontró afinidad.")
    exit()

top_amigas = df_afinidad.head(TOP_AMIGAS)['amiga'].tolist()

print(f"\nTop {TOP_AMIGAS} amigas más afines:")
for _, row in df_afinidad.head(TOP_AMIGAS).iterrows():
    print(f"  • {row['amiga']} → {int(row['puntaje_afinidad'])} pts "
          f"({int(row['canciones_en_comun'])} canciones, "
          f"{int(row['albumes_en_comun'])} álbumes, "
          f"{int(row['artistas_en_comun'])} artistas, "
          f"{int(row['generos_en_comun'])} géneros en común)")

query_artistas_comun = """
MATCH (yo:User {nombre: $target_user})-[:AGREGO]->(:Track)<-[:INTERPRETA]-(a:Artista)
WITH yo, collect(DISTINCT a.nombre) AS mis_artistas

MATCH (amiga:User)-[:AGREGO]->(candidata:Track)<-[:INTERPRETA]-(a2:Artista)
WHERE amiga.nombre IN $top_amigas
  AND NOT (yo)-[:AGREGO]->(candidata)
  AND a2.nombre IN mis_artistas

RETURN DISTINCT
    candidata.uri              AS uri,
    candidata.nombre           AS nombre,
    candidata.bailabilidad     AS bailabilidad,
    candidata.energia          AS energia,
    candidata.valencia         AS valencia,
    candidata.tempo            AS tempo,
    candidata.sonoridad        AS sonoridad,
    candidata.vivacidad        AS vivacidad,
    candidata.instrumentalidad AS instrumentalidad,
    candidata.acustica         AS acustica,
    candidata.discursividad    AS discursividad
"""

query_generos_comun = """
MATCH (yo:User {nombre: $target_user})-[:AGREGO]->(:Track)-[:GENERO]->(g:Genero)
WITH yo, collect(DISTINCT g.nombre) AS mis_generos

MATCH (amiga:User)-[:AGREGO]->(candidata:Track)-[:GENERO]->(g2:Genero)
WHERE amiga.nombre IN $top_amigas
  AND NOT (yo)-[:AGREGO]->(candidata)
  AND g2.nombre IN mis_generos

RETURN DISTINCT
    candidata.uri              AS uri,
    candidata.nombre           AS nombre,
    candidata.bailabilidad     AS bailabilidad,
    candidata.energia          AS energia,
    candidata.valencia         AS valencia,
    candidata.tempo            AS tempo,
    candidata.sonoridad        AS sonoridad,
    candidata.vivacidad        AS vivacidad,
    candidata.instrumentalidad AS instrumentalidad,
    candidata.acustica         AS acustica,
    candidata.discursividad    AS discursividad
"""

print(f"\nBuscando canciones candidatas de {top_amigas}...")
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
with driver.session() as session:
    artistas_records = [r.data() for r in session.run(query_artistas_comun,
                                                       target_user=USUARIO_OBJETIVO,
                                                       top_amigas=top_amigas)]
    generos_records  = [r.data() for r in session.run(query_generos_comun,
                                                       target_user=USUARIO_OBJETIVO,
                                                       top_amigas=top_amigas)]
driver.close()

df_artistas = pd.DataFrame(artistas_records)
df_artistas[FEATURES] = df_artistas[FEATURES].apply(pd.to_numeric, errors='coerce')
df_artistas = df_artistas.dropna(subset=FEATURES).reset_index(drop=True)

df_generos = pd.DataFrame(generos_records)
df_generos[FEATURES] = df_generos[FEATURES].apply(pd.to_numeric, errors='coerce')
df_generos = df_generos.dropna(subset=FEATURES).reset_index(drop=True)

uris_artistas = set(df_artistas['uri'].tolist()) if not df_artistas.empty else set()
df_generos = df_generos[~df_generos['uri'].isin(uris_artistas)].reset_index(drop=True)

if df_artistas.empty and df_generos.empty:
    print("No se encontraron recomendaciones.")
    exit()

query_perfil = """
MATCH (u:User {nombre: $target_user})-[:AGREGO]->(t:Track)
RETURN t.bailabilidad      AS bailabilidad,
       t.energia           AS energia,
       t.valencia          AS valencia,
       t.tempo             AS tempo,
       t.sonoridad         AS sonoridad,
       t.vivacidad         AS vivacidad,
       t.instrumentalidad  AS instrumentalidad,
       t.acustica          AS acustica,
       t.discursividad     AS discursividad
"""

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
with driver.session() as session:
    perfil_records = [r.data() for r in session.run(query_perfil, target_user=USUARIO_OBJETIVO)]
driver.close()

df_perfil = pd.DataFrame(perfil_records)
df_perfil[FEATURES] = df_perfil[FEATURES].apply(pd.to_numeric, errors='coerce')
df_perfil = df_perfil.dropna(subset=FEATURES).reset_index(drop=True)

if df_perfil.empty:
    print("No se pudo encontrar canciones.")
    exit()

vector_usuario = df_perfil[FEATURES].mean().to_numpy().astype('float32')

df_pool = pd.concat([df_artistas, df_generos], ignore_index=True)
pool_vectors = df_pool[FEATURES].to_numpy().astype('float32')

index = Index(Space.Euclidean, num_dimensions=len(FEATURES))
index.add_items(pool_vectors)

k = min(len(df_pool), TOP_RECOMENDADAS + len(df_artistas))
neighbors, distances = index.query(vector_usuario, k=k)

uris_resultado   = []
resultado_filas  = []

for idx, dist in zip(neighbors, distances):
    uri = df_pool.loc[idx, 'uri']
    if uri in uris_artistas and uri not in uris_resultado:
        uris_resultado.append(uri)
        resultado_filas.append((df_pool.loc[idx, 'nombre']))

elementos_faltantes = TOP_RECOMENDADAS - len(resultado_filas)

for idx, dist in list(zip(neighbors, distances))[:elementos_faltantes]:
    uri = df_pool.loc[idx, 'uri']
    if uri not in uris_artistas and uri not in uris_resultado:
        uris_resultado.append(uri)
        resultado_filas.append(df_pool.loc[idx, 'nombre'])

print(f"RECOMENDACIONES PARA {USUARIO_OBJETIVO.upper()}")
print(f"De las playlists de: {', '.join(top_amigas)}\n")

for rank, (nombre) in enumerate(resultado_filas, 1):
    print(f"{rank:>2}. '{nombre}'")