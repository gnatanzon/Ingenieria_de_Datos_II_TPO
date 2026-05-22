import os
import pandas as pd
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = ""


class Neo4jPlaylistInserter:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def insert_playlist_file(self, file_path):
        print(f"procesando: {file_path}...")
        df = pd.read_csv(file_path)

        if 'Added At' in df.columns:
            df = df.drop(columns=['Added At'])

        with self.driver.session() as session:
            for index, row in df.iterrows():
                params = row.to_dict()

                artists = [a.strip() for a in str(params['Artist Name(s)']).split(';')]

                query = """
                MERGE (u:User {name: $user_name})

                MERGE (al:Album {name: $album_name})
                ON CREATE SET al.release_date = $release_date, al.label = $record_label

                MERGE (t:Track {uri: $track_uri})
                ON CREATE SET t.name = $track_name,
                              t.duration_ms = $duration,
                              t.explicit = $explicit,
                              t.danceability = $danceability,
                              t.energy = $energy
                ON MATCH SET t.popularity = $popularity // Actualiza popularidad si cambió

                MERGE (t)-[:PERTENECE_A]->(al)
                MERGE (u)-[:AGREGO]->(t)

                WITH t
                UNWIND $artist_list AS artist_name
                MERGE (a:Artist {name: artist_name})
                MERGE (a)-[:INTERPRETA]->(t)
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
                            energy=params['Energy'],
                            artist_list=artists)


def main():
    # Lista con todos los archivos de las playlists que quieres procesar
    playlist_files = [
        'playlist_anto.csv',
        'playlist_chen.csv',
        'playlist_cami.csv',
        'playlist_julis.csv',
        'playlist_julib.csv',
        'playlist_guillermina.csv',
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
    main()