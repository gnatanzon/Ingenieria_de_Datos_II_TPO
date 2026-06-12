import json
import re
import glob
from datetime import datetime
from pathlib import Path
from cassandra.cluster import Cluster
from collections import defaultdict

# ─────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────
CASSANDRA_HOST = "127.0.0.1"
CASSANDRA_PORT = 9042
KEYSPACE = "sonicmesh"

# Carpeta donde están todos los archivos de historial.
# El script detecta automáticamente el usuario a partir del nombre:
#   historial_spotify_[usuario].json   → historial de Spotify
#   historial_youtube_[usuario].json   → historial de YouTube Music
DATA_DIR = "."


def detectar_usuarios(data_dir):
    """
    Detecta usuarios y agrupa sus archivos a partir de los nombres.
    Formatos soportados:
      historial_<usuario>_<año>.json     → Spotify (uno o más archivos por año)
      historial_youtube_<usuario>.json   → YouTube Music

    Devuelve un dict: { "usuario": {"spotify": [...paths], "youtube": path|None} }
    """
    usuarios = defaultdict(lambda: {"spotify": [], "youtube": None})

    for path in Path(data_dir).glob("historial_*.json"):
        name = path.stem  # sin .json

        # YouTube Music: historial_youtube_<usuario>
        yt_match = re.match(r"historial_youtube_(.+)", name)
        if yt_match:
            user = yt_match.group(1)
            usuarios[user]["youtube"] = str(path)
            continue

        # Spotify con año: historial_<usuario>_<año> (año = 4 dígitos)
        sp_match = re.match(r"historial_(.+)_(\d{4})$", name)
        if sp_match:
            user = sp_match.group(1)
            usuarios[user]["spotify"].append(str(path))
            continue

    # Ordenar los archivos de Spotify por año para consistencia
    for user in usuarios:
        usuarios[user]["spotify"].sort()

    return dict(usuarios)

# ─────────────────────────────────────────
# CONEXIÓN
# ─────────────────────────────────────────
def connect():
    cluster = Cluster([CASSANDRA_HOST], port=CASSANDRA_PORT)
    session = cluster.connect()
    return cluster, session


# ─────────────────────────────────────────
# CREACIÓN DEL KEYSPACE Y TABLAS
# ─────────────────────────────────────────
def create_schema(session):
    session.execute(f"""
        CREATE KEYSPACE IF NOT EXISTS {KEYSPACE}
        WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 1}}
    """)
    session.set_keyspace(KEYSPACE)

    # Q1 — historial completo del usuario, ordenado por timestamp desc
    session.execute("""
        CREATE TABLE IF NOT EXISTS tracks_by_user (
            user_id        TEXT,
            ts             TIMESTAMP,
            spotify_track_uri TEXT,
            track_name     TEXT,
            artist_name    TEXT,
            album_name     TEXT,
            ms_played      INT,
            platform       TEXT,
            skipped        BOOLEAN,
            source         TEXT,
            PRIMARY KEY (user_id, ts, spotify_track_uri)
        ) WITH CLUSTERING ORDER BY (ts DESC, spotify_track_uri ASC)
    """)

    # Q2 — top artistas por tiempo total escuchado
    session.execute("""
        CREATE TABLE IF NOT EXISTS top_artists_by_user (
            user_id         TEXT,
            total_ms_played BIGINT,
            artist_name     TEXT,
            play_count      INT,
            last_played     TIMESTAMP,
            PRIMARY KEY (user_id, total_ms_played, artist_name)
        ) WITH CLUSTERING ORDER BY (total_ms_played DESC, artist_name ASC)
    """)

    # Q3 — canciones de un artista específico escuchadas por el usuario
    session.execute("""
        CREATE TABLE IF NOT EXISTS tracks_by_user_artist (
            user_id           TEXT,
            artist_name       TEXT,
            ms_played         INT,
            spotify_track_uri TEXT,
            track_name        TEXT,
            album_name        TEXT,
            play_count        INT,
            PRIMARY KEY (user_id, artist_name, ms_played, spotify_track_uri)
        ) WITH CLUSTERING ORDER BY (artist_name ASC, ms_played DESC, spotify_track_uri ASC)
    """)

    # Q4 / Q4b — historial filtrado por año-mes
    session.execute("""
        CREATE TABLE IF NOT EXISTS history_by_user_year_month (
            user_id       TEXT,
            year_month    TEXT,
            ts            TIMESTAMP,
            track_name    TEXT,
            artist_name   TEXT,
            platform      TEXT,
            ms_played     INT,
            skipped       BOOLEAN,
            spotify_track_uri TEXT,
            PRIMARY KEY (user_id, year_month, ts)
        ) WITH CLUSTERING ORDER BY (year_month DESC, ts DESC)
    """)

    # Q5 — canciones por plataforma
    session.execute("""
        CREATE TABLE IF NOT EXISTS tracks_by_user_platform (
            user_id       TEXT,
            platform      TEXT,
            year_month    TEXT,
            ts            TIMESTAMP,
            track_name    TEXT,
            artist_name   TEXT,
            ms_played     INT,
            skipped       BOOLEAN,
            spotify_track_uri TEXT,
            PRIMARY KEY (user_id, platform, year_month, ts)
        ) WITH CLUSTERING ORDER BY (platform ASC, year_month DESC, ts DESC)
    """)

    # Q6 — canciones más salteadas
    session.execute("""
        CREATE TABLE IF NOT EXISTS skipped_tracks_by_user (
            user_id           TEXT,
            skip_count        INT,
            spotify_track_uri TEXT,
            track_name        TEXT,
            artist_name       TEXT,
            avg_ms_before_skip FLOAT,
            platform          TEXT,
            year_month        TEXT,
            PRIMARY KEY (user_id, skip_count, spotify_track_uri)
        ) WITH CLUSTERING ORDER BY (skip_count DESC, spotify_track_uri ASC)
    """)

    print("✅ Keyspace y tablas creadas.")


# ─────────────────────────────────────────
# PARSEO DE REGISTROS
# ─────────────────────────────────────────
def parse_spotify(record, user_id):
    """Normaliza un registro del historial de Spotify."""
    track_name = record.get("master_metadata_track_name")
    artist_name = record.get("master_metadata_album_artist_name")
    album_name = record.get("master_metadata_album_album_name")

    # Ignorar podcasts, audiolibros y reproducciones sin nombre de canción
    if not track_name or not artist_name:
        return None

    ts_str = record.get("ts")
    if not ts_str:
        return None

    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

    platform_raw = record.get("platform", "")
    # Simplificamos el nombre de plataforma
    platform = simplify_platform(platform_raw)

    return {
        "user_id": user_id,
        "ts": ts,
        "spotify_track_uri": record.get("spotify_track_uri", ""),
        "track_name": track_name,
        "artist_name": artist_name,
        "album_name": album_name or "",
        "ms_played": record.get("ms_played", 0),
        "platform": platform,
        "skipped": record.get("skipped", False),
        "source": "spotify",
    }


def parse_youtube(record, user_id):
    """Normaliza un registro del historial de YouTube Music."""
    # Solo nos interesan reproducciones de YouTube Music
    if record.get("header") != "YouTube Music":
        return None

    title_raw = record.get("title", "")
    # El título viene como "Watched <nombre de la canción>"
    track_name = title_raw.removeprefix("Watched ")
    if not track_name:
        return None

    subtitles = record.get("subtitles", [])
    artist_name = subtitles[0].get("name", "Desconocido") if subtitles else "Desconocido"
    # YouTube Music a veces agrega " - Topic" al nombre del canal
    artist_name = artist_name.removesuffix(" - Topic")

    url = record.get("titleUrl", "")
    video_id = url.split("v=")[-1] if "v=" in url else url

    ts_str = record.get("time", "")
    if not ts_str:
        return None
    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

    return {
        "user_id": user_id,
        "ts": ts,
        "spotify_track_uri": f"youtube:{video_id}",  # usamos el video_id como URI
        "track_name": track_name,
        "artist_name": artist_name,
        "album_name": "",
        "ms_played": 0,  # YouTube Music no provee ms reproducidos
        "platform": "youtube_music",
        "skipped": False,
        "source": "youtube",
    }


def simplify_platform(platform_raw):
    """Mapea el string de plataforma de Spotify a un nombre corto."""
    p = platform_raw.lower()
    if "android" in p:
        return "android"
    if "ios" in p or "iphone" in p or "ipad" in p:
        return "ios"
    if "windows" in p or "osx" in p or "macos" in p or "linux" in p:
        return "desktop"
    if "web" in p or "browser" in p:
        return "web"
    if "cast" in p or "chromecast" in p:
        return "cast"
    return platform_raw[:50] if platform_raw else "unknown"


# ─────────────────────────────────────────
# INSERCIÓN EN CASSANDRA
# ─────────────────────────────────────────
def insert_record(session, r):
    year_month = r["ts"].strftime("%Y-%m")

    # Q1 — tracks_by_user
    session.execute("""
        INSERT INTO tracks_by_user
        (user_id, ts, spotify_track_uri, track_name, artist_name, album_name,
         ms_played, platform, skipped, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        r["user_id"], r["ts"], r["spotify_track_uri"],
        r["track_name"], r["artist_name"], r["album_name"],
        r["ms_played"], r["platform"], r["skipped"], r["source"]
    ))

    # Q4 — history_by_user_year_month
    session.execute("""
        INSERT INTO history_by_user_year_month
        (user_id, year_month, ts, track_name, artist_name,
         platform, ms_played, skipped, spotify_track_uri)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        r["user_id"], year_month, r["ts"],
        r["track_name"], r["artist_name"],
        r["platform"], r["ms_played"], r["skipped"], r["spotify_track_uri"]
    ))

    # Q5 — tracks_by_user_platform
    session.execute("""
        INSERT INTO tracks_by_user_platform
        (user_id, platform, year_month, ts, track_name, artist_name,
         ms_played, skipped, spotify_track_uri)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        r["user_id"], r["platform"], year_month, r["ts"],
        r["track_name"], r["artist_name"],
        r["ms_played"], r["skipped"], r["spotify_track_uri"]
    ))


def insert_aggregates(session, user_id, records):
    """Calcula e inserta los agregados para Q2, Q3 y Q6."""

    # Agrupamos en memoria
    artist_stats = defaultdict(lambda: {"total_ms": 0, "count": 0, "last": None})
    track_by_artist = defaultdict(lambda: defaultdict(lambda: {"ms": 0, "count": 0, "album": ""}))
    skip_stats = defaultdict(lambda: {"count": 0, "ms_list": [], "platform": "", "year_month": ""})

    for r in records:
        a = r["artist_name"]
        uri = r["spotify_track_uri"]
        ym = r["ts"].strftime("%Y-%m")

        # Q2
        artist_stats[a]["total_ms"] += r["ms_played"]
        artist_stats[a]["count"] += 1
        if artist_stats[a]["last"] is None or r["ts"] > artist_stats[a]["last"]:
            artist_stats[a]["last"] = r["ts"]

        # Q3
        track_by_artist[a][uri]["ms"] = max(track_by_artist[a][uri]["ms"], r["ms_played"])
        track_by_artist[a][uri]["count"] += 1
        track_by_artist[a][uri]["track_name"] = r["track_name"]
        track_by_artist[a][uri]["album"] = r["album_name"]

        # Q6
        if r["skipped"]:
            skip_stats[uri]["count"] += 1
            skip_stats[uri]["ms_list"].append(r["ms_played"])
            skip_stats[uri]["track_name"] = r["track_name"]
            skip_stats[uri]["artist_name"] = a
            skip_stats[uri]["platform"] = r["platform"]
            skip_stats[uri]["year_month"] = ym

    # Q2 — top_artists_by_user
    for artist, stats in artist_stats.items():
        session.execute("""
            INSERT INTO top_artists_by_user
            (user_id, total_ms_played, artist_name, play_count, last_played)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, stats["total_ms"], artist, stats["count"], stats["last"]))

    # Q3 — tracks_by_user_artist
    for artist, tracks in track_by_artist.items():
        for uri, info in tracks.items():
            session.execute("""
                INSERT INTO tracks_by_user_artist
                (user_id, artist_name, ms_played, spotify_track_uri,
                 track_name, album_name, play_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id, artist, info["ms"], uri,
                info["track_name"], info["album"], info["count"]
            ))

    # Q6 — skipped_tracks_by_user
    for uri, info in skip_stats.items():
        avg_ms = sum(info["ms_list"]) / len(info["ms_list"])
        session.execute("""
            INSERT INTO skipped_tracks_by_user
            (user_id, skip_count, spotify_track_uri, track_name,
             artist_name, avg_ms_before_skip, platform, year_month)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id, info["count"], uri, info["track_name"],
            info["artist_name"], avg_ms, info["platform"], info["year_month"]
        ))

    print(f"  ↳ Agregados: {len(artist_stats)} artistas, {sum(len(t) for t in track_by_artist.values())} tracks únicos, {len(skip_stats)} canciones salteadas")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def cargar_usuario(session, user_id, spotify_files, youtube_file):
    print(f"\n📥 Cargando historial de: {user_id}")
    records = []

    # Spotify
    for path in spotify_files:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        for entry in raw:
            r = parse_spotify(entry, user_id)
            if r:
                records.append(r)
        print(f"  ✅ Spotify ({path}): {len(raw)} registros leídos")

    # YouTube Music
    if youtube_file:
        with open(youtube_file, encoding="utf-8") as f:
            raw_yt = json.load(f)
        yt_count = 0
        for entry in raw_yt:
            r = parse_youtube(entry, user_id)
            if r:
                records.append(r)
                yt_count += 1
        print(f"  ✅ YouTube Music ({youtube_file}): {yt_count} reproducciones de música")

    print(f"  → Total registros válidos: {len(records)}")

    # Insertar fila por fila (Q1, Q4, Q5)
    for i, r in enumerate(records):
        insert_record(session, r)
        if (i + 1) % 500 == 0:
            print(f"    {i + 1}/{len(records)} insertados...")

    # Insertar agregados (Q2, Q3, Q6)
    insert_aggregates(session, user_id, records)
    print(f"  ✅ Carga completa para {user_id}")


if __name__ == "__main__":
    usuarios = detectar_usuarios(DATA_DIR)

    if not usuarios:
        print("❌ No se encontraron archivos con el formato historial_spotify_<usuario>.json")
        print("   Asegurate de que los archivos estén en:", DATA_DIR)
        exit(1)

    print(f"👥 Usuarios detectados: {', '.join(usuarios.keys())}")

    cluster, session = connect()
    try:
        create_schema(session)
        for user_id, archivos in usuarios.items():
            cargar_usuario(
                session,
                user_id=user_id,
                spotify_files=archivos["spotify"],
                youtube_file=archivos["youtube"],
            )
    finally:
        cluster.shutdown()
        print("\n🔒 Conexión cerrada.")