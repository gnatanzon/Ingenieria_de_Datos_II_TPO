import csv
import io
import os
import sys

from flask import Flask, jsonify, render_template, request

BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)

from mongodb_db import mongo_analytics as mongo_db
from redis_db import carrito_redis   as redis_db
from neo4j_db.carga_neo4j import carga_neo4j
from neo4j_db import recomendaciones_neo4j as rec


CSV_COLUMNAS = [
    "Track URI", "Track Name", "Artist Name(s)", "Album Name",
    "Release Date", "Record Label", "Duration (ms)", "Popularity",
    "Explicit", "Danceability", "Energy", "Loudness", "Speechiness",
    "Acousticness", "Instrumentalness", "Liveness", "Valence",
    "Tempo", "Genres", "Added By"
]

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


def doc_a_fila_csv(doc: dict, usuario: str) -> dict:
    fila = {col: "" for col in CSV_COLUMNAS}
    for mongo_key, csv_col in MONGO_A_CSV.items():
        val = doc.get(mongo_key, "")
        if isinstance(val, list):
            val = "; ".join(val)
        fila[csv_col] = val if val is not None else ""

    album = doc.get("album", {})
    fila["Album Name"]     = album.get("nombre", "")
    fila["Release Date"]   = album.get("fecha_de_lanzamiento", "")
    fila["Record Label"]   = album.get("discografica", "")

    artistas = doc.get("artistas", [])
    fila["Artist Name(s)"] = "; ".join(artistas) if artistas else ""
    fila["Added By"]       = usuario
    return fila


app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/recomendaciones")
def recomendaciones_page():
    return render_template("recomendaciones.html")


@app.route("/api/canciones")
def get_canciones():
    busqueda = request.args.get("q", "").strip()
    genero   = request.args.get("genero", "").strip()
    canciones = mongo_db.buscar_canciones(busqueda, genero)
    return jsonify(canciones)


@app.route("/api/generos")
def get_generos():
    return jsonify(mongo_db.obtener_generos())


@app.route("/api/carrito/<usuario>")
def get_carrito(usuario):
    uris      = redis_db.obtener_uris_carrito(usuario)
    canciones = mongo_db.buscar_canciones_por_uris(list(uris))
    return jsonify(canciones)


@app.route("/api/carrito/<usuario>/agregar", methods=["POST"])
def agregar_al_carrito(usuario):
    uri = request.json.get("uri")
    if not uri:
        return jsonify({"error": "URI requerido"}), 400
    total = redis_db.agregar_uri(usuario, uri)
    return jsonify({"ok": True, "total": total})


@app.route("/api/carrito/<usuario>/quitar", methods=["POST"])
def quitar_del_carrito(usuario):
    uri = request.json.get("uri")
    if not uri:
        return jsonify({"error": "URI requerido"}), 400
    total = redis_db.quitar_uri(usuario, uri)
    return jsonify({"ok": True, "total": total})


@app.route("/api/carrito/<usuario>/confirmar", methods=["POST"])
def confirmar(usuario):
    uris = redis_db.obtener_uris_carrito(usuario)
    if not uris:
        return jsonify({"error": "El carrito está vacío"}), 400

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNAS)
    writer.writeheader()
    for uri in uris:
        doc = mongo_db.buscar_cancion_por_uri(uri)
        if doc:
            writer.writerow(doc_a_fila_csv(doc, usuario))

    csv_content = output.getvalue()

    csv_path = os.path.join(BASE_DIR, "neo4j_db", "playlist_nueva.csv")
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        f.write(csv_content)

    try:
        carga_neo4j(csv_path)
    except Exception as e:
        return jsonify({"error": f"Neo4j: {str(e)}"}), 500

    redis_db.vaciar_carrito(usuario)
    return jsonify({"ok": True, "insertadas": len(uris)})


@app.route("/api/recomendaciones/<usuario>")
def get_recomendaciones(usuario):
    top_amigas_n = int(request.args.get("top_amigas", 2))
    top_rec_n    = int(request.args.get("top_rec", 10))

    resultado = rec.recomendar(usuario, top_amigas_n, top_rec_n)
    return jsonify(resultado)


if __name__ == "__main__":
    app.run(debug=True, port=5000)