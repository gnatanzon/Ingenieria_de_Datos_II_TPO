import os
import pandas as pd
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "sonicmesh_db"
COLLECTION_NAME = "canciones"


def val(v):
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def build_doc(params):
    album = {}
    for key, csv_col in [("nombre", "Album Name"), ("fecha_de_lanzamiento", "Release Date"),
                         ("discografica", "Record Label")]:
        v = val(params.get(csv_col))
        if v is not None:
            album[key] = v

    artists = []
    if val(params.get("Artist Name(s)")):
        artists = [a.strip() for a in str(params["Artist Name(s)"]).split(";")]

    flat_fields = [
        ("uri", "Track URI"),
        ("nombre", "Track Name"),
        ("duracion_ms", "Duration (ms)"),
        ("popularidad", "Popularity"),
        ("explicito", "Explicit"),
        ("bailabilidad", "Danceability"),
        ("energia", "Energy"),
        ("clave", "Key"),
        ("sonoridad", "Loudness"),
        ("modo", "Mode"),
        ("discursividad", "Speechiness"),
        ("acustica", "Acousticness"),
        ("instrumentalidad", "Instrumentalness"),
        ("vivacidad", "Liveness"),
        ("valencia", "Valence"),
        ("tempo", "Tempo"),
        ("compas", "Time Signature"),
        ("generos", "Genres"),
    ]

    doc = {}
    for doc_key, csv_col in flat_fields:
        v = val(params.get(csv_col))
        if v is not None:
            doc[doc_key] = v

    if artists:
        doc["artistas"] = artists
    if album:
        doc["album"] = album

    return doc


class MongoPlaylistInserter:
    def __init__(self, uri, db_name, collection_name):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def close(self):
        self.client.close()

    def insert_playlist_file(self, file_path):
        print(f"procesando: {file_path}...")
        df = pd.read_csv(file_path)
        df = df.where(pd.notnull(df), None)

        documents = [build_doc(row.to_dict()) for _, row in df.iterrows()]

        if documents:
            resultado = self.collection.insert_many(documents)
            print(f"{len(resultado.inserted_ids)} canciones insertadas")


def carga_mongodb():
    playlist_files = ["canciones.csv"]

    inserter = MongoPlaylistInserter(MONGO_URI, DATABASE_NAME, COLLECTION_NAME)
    try:
        for file in playlist_files:
            if os.path.exists(file):
                inserter.insert_playlist_file(file)
            else:
                print(f"{file} no existe")
        print("\ncarga exitosa")
    except Exception as e:
        print(f"ERROR! {e}")
    finally:
        inserter.close()


if __name__ == "__main__":
    carga_mongodb()