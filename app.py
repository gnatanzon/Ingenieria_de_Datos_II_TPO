import csv
import io
import os

from flask import Flask, jsonify, render_template, request, send_file
from pymongo import MongoClient
from neo4j import GraphDatabase
import redis

# ── Configuración ──────────────────────────────────────────────────────────────
MONGO_URI        = "mongodb://localhost:27017/"
DATABASE_NAME    = "sonicmesh_db"
COLLECTION_NAME  = "canciones"

REDIS_HOST       = "localhost"
REDIS_PORT       = 6379
REDIS_DB         = 0

NEO4J_URI        = "bolt://localhost:7687"
NEO4J_USER       = "neo4j"
NEO4J_PASSWORD   = "guillermina"

CSV_COLUMNAS = [
    "Track URI", "Track Name", "Artist Name(s)", "Album Name",
    "Release Date", "Record Label", "Duration (ms)", "Popularity",
    "Explicit", "Danceability", "Energy", "Loudness", "Speechiness",
    "Acousticness", "Instrumentalness", "Liveness", "Valence",
    "Tempo", "Genres", "Added By"
]

# Mapeo MongoDB → columna CSV
MONGO_A_CSV = {
    "uri":              "Track URI",
    "nombre":           "Track Name",
    "duracion_ms":      "Duration (ms)",
    "popularidad":      "Popularity",
    "explicito":        "Explicit",
    "bailabilidad":     "Danceability",
    "energia":          "Energy",
    "sonoridad":        "Loudness",
    "discursividad":    "Speechiness",
    "acustica":         "Acousticness",
    "instrumentalidad": "Instrumentalness",
    "vivacidad":        "Liveness",
    "valencia":         "Valence",
    "tempo":            "Tempo",
    "generos":          "Genres",
}

app = Flask(__name__)

mongo   = MongoClient(MONGO_URI)
col     = mongo[DATABASE_NAME][COLLECTION_NAME]
r       = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

# ── Helpers ────────────────────────────────────────────────────────────────────
def redis_key(usuario):
    return f"carrito:{usuario}"

def doc_a_fila_csv(doc, usuario):
    fila = {col: "" for col in CSV_COLUMNAS}
    for mongo_key, csv_col in MONGO_A_CSV.items():
        val = doc.get(mongo_key, "")
        if isinstance(val, list):
            val = "; ".join(val)
        fila[csv_col] = val if val is not None else ""
    album = doc.get("album", {})
    fila["Album Name"]    = album.get("nombre", "")
    fila["Release Date"]  = album.get("fecha_de_lanzamiento", "")
    fila["Record Label"]  = album.get("discografica", "")
    artistas = doc.get("artistas", [])
    fila["Artist Name(s)"] = "; ".join(artistas) if artistas else ""
    fila["Added By"] = usuario
    return fila

# ── Rutas API ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/canciones")
def get_canciones():
    busqueda = request.args.get("q", "").strip()
    genero   = request.args.get("genero", "").strip()

    filtro = {}
    if busqueda:
        filtro["$or"] = [
            {"nombre":   {"$regex": busqueda, "$options": "i"}},
            {"artistas": {"$regex": busqueda, "$options": "i"}},
        ]
    if genero:
        filtro["generos"] = {"$regex": genero, "$options": "i"}

    canciones = list(col.find(filtro, {"_id": 0}).limit(100))
    return jsonify(canciones)

@app.route("/api/generos")
def get_generos():
    """Devuelve la lista de géneros únicos para el filtro."""
    todos = col.distinct("generos")
    # Separar por coma y deduplicar
    generos = set()
    for g in todos:
        if g:
            for item in str(g).split(","):
                item = item.strip()
                if item:
                    generos.add(item)
    return jsonify(sorted(generos))

@app.route("/api/carrito/<usuario>")
def get_carrito(usuario):
    uris = r.lrange(redis_key(usuario), 0, -1)
    canciones = []
    for uri in uris:
        doc = col.find_one({"uri": uri}, {"_id": 0})
        if doc:
            canciones.append(doc)
    return jsonify(canciones)

@app.route("/api/carrito/<usuario>/agregar", methods=["POST"])
def agregar_al_carrito(usuario):
    uri = request.json.get("uri")
    if not uri:
        return jsonify({"error": "URI requerido"}), 400
    key = redis_key(usuario)
    if uri not in r.lrange(key, 0, -1):
        r.rpush(key, uri)
    return jsonify({"ok": True, "total": r.llen(key)})

@app.route("/api/carrito/<usuario>/quitar", methods=["POST"])
def quitar_del_carrito(usuario):
    uri = request.json.get("uri")
    if not uri:
        return jsonify({"error": "URI requerido"}), 400
    r.lrem(redis_key(usuario), 0, uri)
    return jsonify({"ok": True, "total": r.llen(redis_key(usuario))})

@app.route("/api/carrito/<usuario>/confirmar", methods=["POST"])
def confirmar(usuario):
    uris = r.lrange(redis_key(usuario), 0, -1)
    if not uris:
        return jsonify({"error": "El carrito está vacío"}), 400

    # 1. Armar CSV en memoria
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNAS)
    writer.writeheader()
    for uri in uris:
        doc = col.find_one({"uri": uri}, {"_id": 0})
        if doc:
            writer.writerow(doc_a_fila_csv(doc, usuario))
    csv_content = output.getvalue()

    # 2. Guardar CSV en disco (para que carga_neo4j lo lea)
    csv_path = os.path.join(os.path.dirname(__file__), "neo4j", "playlist_nueva.csv")
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        f.write(csv_content)

    # 3. Cargar a Neo4j
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        df = __import__("pandas").read_csv(io.StringIO(csv_content)).fillna("")
        with driver.session() as session:
            for _, row in df.iterrows():
                params = row.to_dict()
                artists = [a.strip() for a in str(params["Artist Name(s)"]).split(";")]
                genres  = [g.strip().lower() for g in str(params.get("Genres", "")).split(",") if g.strip()]
                session.run(NEO4J_QUERY,
                            user_name=usuario,
                            album_name=params["Album Name"],
                            release_date=params["Release Date"],
                            record_label=params["Record Label"],
                            track_uri=params["Track URI"],
                            track_name=params["Track Name"],
                            duration=params["Duration (ms)"],
                            explicit=params["Explicit"],
                            popularity=params["Popularity"],
                            danceability=params["Danceability"],
                            valence=params["Valence"],
                            tempo=params["Tempo"],
                            energy=params["Energy"],
                            loudness=params["Loudness"],
                            acousticness=params["Acousticness"],
                            liveness=params["Liveness"],
                            speechiness=params["Speechiness"],
                            instrumentalness=params["Instrumentalness"],
                            artist_list=artists,
                            genre_list=genres)
        driver.close()
    except Exception as e:
        return jsonify({"error": f"Neo4j: {str(e)}"}), 500

    # 4. Limpiar carrito
    r.delete(redis_key(usuario))

    return jsonify({"ok": True, "insertadas": len(uris)})

# ── Query Neo4j (igual a carga_neo4j.py) ──────────────────────────────────────
NEO4J_QUERY = """
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
              t.sonoridad = $loudness,
              t.vivacidad = $liveness,
              t.instrumentalidad = $instrumentalness,
              t.acustica = $acousticness,
              t.discursividad = $speechiness
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

if __name__ == "__main__":
    app.run(debug=True, port=5000)