import numpy as np
import pandas as pd
from neo4j import GraphDatabase
from voyager import Index, Space
from sklearn.preprocessing import MinMaxScaler

URI              = "bolt://localhost:7687"
USER             = "neo4j"
PASSWORD         = "guillermina"
USUARIO_OBJETIVO = None
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


def recomendar(usuario_objetivo=USUARIO_OBJETIVO, top_amigas_n=TOP_AMIGAS, top_recomendadas_n=TOP_RECOMENDADAS):
    print(f"Calculando afinidad social para '{usuario_objetivo}'...")
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session() as session:
        records = [r.data() for r in session.run(query_afinidad, target_user=usuario_objetivo)]
    driver.close()

    df_afinidad = pd.DataFrame(records)

    if df_afinidad.empty:
        return {"error": f"No se encontró afinidad para '{usuario_objetivo}'."}

    top_amigas = df_afinidad.head(top_amigas_n)['amiga'].tolist()

    print(f"\nTop {top_amigas_n} amigas más afines:")
    for _, row in df_afinidad.head(top_amigas_n).iterrows():
        print(f"  • {row['amiga']} → {int(row['puntaje_afinidad'])} pts "
              f"({int(row['canciones_en_comun'])} canciones, "
              f"{int(row['albumes_en_comun'])} álbumes, "
              f"{int(row['artistas_en_comun'])} artistas, "
              f"{int(row['generos_en_comun'])} géneros en común)")

    print(f"\nBuscando canciones candidatas de {top_amigas}...")
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session() as session:
        artistas_records = [r.data() for r in session.run(query_artistas_comun,
                                                           target_user=usuario_objetivo,
                                                           top_amigas=top_amigas)]
        generos_records  = [r.data() for r in session.run(query_generos_comun,
                                                           target_user=usuario_objetivo,
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
        return {"error": "No se encontraron recomendaciones.",
                "afinidad": df_afinidad.head(top_amigas_n).to_dict(orient="records")}

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session() as session:
        perfil_records = [r.data() for r in session.run(query_perfil, target_user=usuario_objetivo)]
    driver.close()

    df_perfil = pd.DataFrame(perfil_records)
    df_perfil[FEATURES] = df_perfil[FEATURES].apply(pd.to_numeric, errors='coerce')
    df_perfil = df_perfil.dropna(subset=FEATURES).reset_index(drop=True)

    if df_perfil.empty:
        return {"error": "No se pudo encontrar canciones.",
                "afinidad": df_afinidad.head(top_amigas_n).to_dict(orient="records")}

    vector_usuario = df_perfil[FEATURES].mean().to_numpy().astype('float32')

    df_pool = pd.concat([df_artistas, df_generos], ignore_index=True)

    scaler = MinMaxScaler()
    pool_vectors_norm = scaler.fit_transform(df_pool[FEATURES].to_numpy().astype('float32'))
    vector_usuario_norm = scaler.transform(vector_usuario.reshape(1, -1))[0].astype('float32')

    index = Index(Space.Euclidean, num_dimensions=len(FEATURES))
    index.add_items(pool_vectors_norm)

    k = min(len(df_pool), top_recomendadas_n + len(df_artistas))
    neighbors, distances = index.query(vector_usuario_norm, k=k)

    uris_resultado = []
    resultado_filas = []

    #artistas en común entran siempre
    for idx, row in df_artistas.iterrows():
        uri = row['uri']
        if uri not in uris_resultado:
            uris_resultado.append(uri)
            resultado_filas.append({
                "nombre": row['nombre'],
                "uri": uri,
                "tipo": "artista"
            })

    if len(resultado_filas) < top_recomendadas_n and not df_generos.empty:
        candidatas_genero = [
            {"nombre": df_pool.loc[idx, 'nombre'], "uri": df_pool.loc[idx, 'uri'], "tipo": "genero"}
            for idx, dist in zip(neighbors, distances)
            if df_pool.loc[idx, 'uri'] not in uris_artistas
               and df_pool.loc[idx, 'uri'] not in uris_resultado
        ]
        faltantes = top_recomendadas_n - len(resultado_filas)
        for cancion in candidatas_genero[:faltantes]:
            uris_resultado.append(cancion['uri'])
            resultado_filas.append(cancion)

    print(f"\nRECOMENDACIONES PARA {usuario_objetivo.upper()}")
    print(f"De las playlists de: {', '.join(top_amigas)}\n")
    for rank, r in enumerate(resultado_filas, 1):
        print(f"{rank:>2}. '{r['nombre']}'")


    return {
        "afinidad":        df_afinidad.head(top_amigas_n).to_dict(orient="records"),
        "recomendaciones": resultado_filas,
    }


if __name__ == "__main__":
    usuario = input("Usuario: ").strip()
    recomendar(usuario)