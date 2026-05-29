import os
import pandas as pd
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "guillermina"


class Neo4jPlaylistInserter:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def insert_playlist_file(self, file_path):
        print(f"procesando: {file_path}...")

        df = pd.read_csv(file_path)
        df = df.fillna("")

        if 'Added At' in df.columns:
            df = df.drop(columns=['Added At'])

        with self.driver.session() as session:
            for index, row in df.iterrows():
                params = row.to_dict()

                artists = [a.strip() for a in str(params['Artist Name(s)']).split(';')]

                genres = [g.strip().lower() for g in str(params.get('Genres', '')).split(',') if g.strip()]

                query = """
                MERGE (u:User {nombre: $user_name})

                MERGE (al:Album {nombre: $album_name})
                ON CREATE SET al.fecha_de_lanzamiento = $release_date, al.discografica = $record_label

                MERGE (t:Track {uri: $track_uri})
                ON CREATE SET t.nombre = $track_name,
                              t.duracion_ms = $duration,
                              t.explicito = $explicit,
                              t.bailabilidad = $danceability,
                              t.energia = $energy,
                              t.valencia = $valence,
                              t.tempo = $tempo,
                              t.volumen = $loudness,
                              t.vivacidad = $liveness,
                              t.instrumentalidad = $instrumentalness,
                              t.acustica = $acousticness,
                              t.dialogado = $speechiness
                ON MATCH SET t.popularidad = $popularity 

                MERGE (t)-[:PERTENECE_A]->(al)
                MERGE (u)-[:AGREGO]->(t)

                WITH t
                UNWIND $artist_list AS artist_name
                MERGE (a:Artista {nombre: artist_name})
                MERGE (a)-[:INTERPRETA]->(t)

                WITH DISTINCT t
                UNWIND $genre_list AS genre_name
                WITH t, genre_name WHERE genre_name <> ""
                MERGE (g:Genero {nombre: genre_name})
                MERGE (t)-[:GENERO]->(g)
                """

                session.run(query,
                            user_name=params['Added By'],
                            album_name=params['Album Name'],
                            release_date=params['Release Date'],
                            record_label=params['Record Label'],
                            track_uri=params['Track URI'],
                            track_name=params['Track Name'],
                            duration=params['Duration (ms)'],
                            explicit=params['Explicit'],
                            popularity=params['Popularity'],
                            danceability=params['Danceability'],
                            valence=params['Valence'],
                            tempo=params['Tempo'],
                            energy=params['Energy'],
                            loudness=params['Loudness'],
                            acousticness=params['Acousticness'],
                            liveness=params['Liveness'],
                            speechiness=params['Speechiness'],
                            instrumentalness=params['Instrumentalness'],
                            artist_list=artists,
                            genre_list=genres)


def carga_neo4j():
    playlist_files = [
        'neo4j/playlists.csv',
    ]

    inserter = Neo4jPlaylistInserter(URI, USER, PASSWORD)
    try:
        for file in playlist_files:
            if os.path.exists(file):
                inserter.insert_playlist_file(file)
            else:
                print(f"{file} no existe")
        print("\narchivos insertados con éxito")
    except Exception as e:
        print(f"ERROR! {e}")
    finally:
        inserter.close()


if __name__ == "__main__":
    carga_neo4j()