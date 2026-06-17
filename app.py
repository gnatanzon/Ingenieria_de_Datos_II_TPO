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
from cassandra.cluster import Cluster as CassandraCluster

CASSANDRA_HOST = "127.0.0.1"
CASSANDRA_PORT = 9042
CASSANDRA_KEYSPACE = "sonicmesh"

def get_cassandra():
    cluster = CassandraCluster([CASSANDRA_HOST], port=CASSANDRA_PORT)
    session = cluster.connect(CASSANDRA_KEYSPACE)
    return cluster, session


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


@app.route("/historial")
def historial():
    return render_template("historial.html")


@app.route("/api/historial/<usuario>/canciones")
def historial_canciones(usuario):
    year_month = request.args.get("year_month", "").strip()
    platform   = request.args.get("platform", "").strip()

    cluster, session = get_cassandra()
    try:
        if platform and year_month:
            # Q5: filtra por plataforma Y mes
            rows = session.execute(
                """SELECT ts, track_name, artist_name, ms_played,
                          skipped, spotify_track_uri, platform
                   FROM tracks_by_user_platform
                   WHERE user_id = %s AND platform = %s AND year_month = %s""",
                (usuario, platform, year_month)
            )
        elif year_month:
            # Q4: filtra solo por mes
            rows = session.execute(
                """SELECT ts, track_name, artist_name, platform,
                          ms_played, skipped, spotify_track_uri
                   FROM history_by_user_year_month
                   WHERE user_id = %s AND year_month = %s""",
                (usuario, year_month)
            )
        elif platform:
            # Sin mes: traemos todos los períodos disponibles y filtramos en memoria
            periodos = session.execute(
                """SELECT DISTINCT year_month
                   FROM history_by_user_year_month
                   WHERE user_id = %s""",
                (usuario,)
            )
            todas = []
            for p in periodos:
                r = session.execute(
                    """SELECT ts, track_name, artist_name, ms_played,
                              skipped, spotify_track_uri, platform
                       FROM tracks_by_user_platform
                       WHERE user_id = %s AND platform = %s AND year_month = %s""",
                    (usuario, platform, p.year_month)
                )
                todas.extend(r)
            rows = sorted(todas, key=lambda x: x.ts, reverse=True)[:200]
        else:
            # Q1: historial completo
            rows = session.execute(
                """SELECT ts, track_name, artist_name, album_name,
                          platform, ms_played, skipped, source,
                          spotify_track_uri
                   FROM tracks_by_user
                   WHERE user_id = %s
                   LIMIT 200""",
                (usuario,)
            )

        resultado = []
        for r in rows:
            resultado.append({
                "ts":          r.ts.isoformat() if r.ts else None,
                "track_name":  r.track_name,
                "artist_name": r.artist_name,
                "album_name":  getattr(r, "album_name", None),
                "platform":    getattr(r, "platform", None),
                "ms_played":   r.ms_played,
                "skipped":     r.skipped,
                "uri":         r.spotify_track_uri,
            })
        return jsonify(resultado)
    finally:
        cluster.shutdown()


@app.route("/api/historial/<usuario>/top-artistas")
def historial_top_artistas(usuario):
    """Q2 — top artistas por tiempo total escuchado."""
    cluster, session = get_cassandra()
    try:
        rows = session.execute(
            """SELECT artist_name, total_ms_played, play_count, last_played
               FROM top_artists_by_user
               WHERE user_id = %s
               LIMIT 50""",
            (usuario,)
        )
        resultado = [
            {
                "artist_name":     r.artist_name,
                "total_ms_played": r.total_ms_played,
                "play_count":      r.play_count,
                "last_played":     r.last_played.isoformat() if r.last_played else None,
            }
            for r in rows
        ]
        return jsonify(resultado)
    finally:
        cluster.shutdown()


@app.route("/api/historial/<usuario>/artista/<artista>")
def historial_canciones_artista(usuario, artista):
    """Q3 — canciones de un artista específico escuchadas por el usuario."""
    cluster, session = get_cassandra()
    try:
        rows = session.execute(
            """SELECT track_name, album_name, ms_played, play_count, spotify_track_uri
               FROM tracks_by_user_artist
               WHERE user_id = %s AND artist_name = %s
               LIMIT 100""",
            (usuario, artista)
        )
        resultado = [
            {
                "track_name": r.track_name,
                "album_name": r.album_name,
                "ms_played":  r.ms_played,
                "play_count": r.play_count,
                "uri":        r.spotify_track_uri,
            }
            for r in rows
        ]
        return jsonify(resultado)
    finally:
        cluster.shutdown()


@app.route("/api/historial/<usuario>/salteadas")
def historial_salteadas(usuario):
    """Q6 — canciones más salteadas."""
    cluster, session = get_cassandra()
    try:
        rows = session.execute(
            """SELECT track_name, artist_name, skip_count, avg_ms_before_skip,
                      platform, year_month, spotify_track_uri
               FROM skipped_tracks_by_user
               WHERE user_id = %s
               LIMIT 50""",
            (usuario,)
        )
        resultado = [
            {
                "track_name":        r.track_name,
                "artist_name":       r.artist_name,
                "skip_count":        r.skip_count,
                "avg_ms_before_skip": r.avg_ms_before_skip,
                "platform":          r.platform,
                "year_month":        r.year_month,
                "uri":               r.spotify_track_uri,
            }
            for r in rows
        ]
        return jsonify(resultado)
    finally:
        cluster.shutdown()

@app.route("/api/historial/usuarios")
def historial_usuarios():
    cluster, session = get_cassandra()
    try:
        rows = session.execute("SELECT DISTINCT user_id FROM tracks_by_user")
        usuarios = sorted([r.user_id for r in rows if r.user_id])
        return jsonify(usuarios)
    finally:
        cluster.shutdown()

@app.route("/api/historial/<usuario>/periodos")
def historial_periodos(usuario):
    cluster, session = get_cassandra()
    try:
        rows = session.execute(
            """SELECT year_month
               FROM history_by_user_year_month
               WHERE user_id = %s""",
            (usuario,)
        )
        periodos = sorted({r.year_month for r in rows if r.year_month}, reverse=True)
        return jsonify(periodos)
    finally:
        cluster.shutdown()


@app.route("/api/historial/<usuario>/plataformas")
def historial_plataformas(usuario):
    cluster, session = get_cassandra()
    try:
        rows = session.execute(
            """SELECT platform
               FROM tracks_by_user
               WHERE user_id = %s""",
            (usuario,)
        )
        plataformas = sorted({r.platform for r in rows if r.platform})
        return jsonify(plataformas)
    finally:
        cluster.shutdown()


if __name__ == "__main__":
    app.run(debug=True, port=5000)