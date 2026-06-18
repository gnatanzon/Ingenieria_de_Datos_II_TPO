import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient

st.set_page_config(
    page_title="SonicMesh Dashboard",
    layout="wide"
)

MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "sonicmesh_db"
COLLECTION_NAME = "canciones"

@st.cache_resource
def init_connection():
    return MongoClient(MONGO_URI)

client = init_connection()
db = client[DATABASE_NAME]
col = db[COLLECTION_NAME]

st.title("Dashboard SonicMesh")

#corte
st.markdown("---")

total_tracks = col.count_documents({})
artistas_unicos = len(col.distinct("artistas"))
avg_pop = list(col.aggregate([{"$group": {"_id": None, "avg": {"$avg": "$popularidad"}}}]))
popularidad_promedio = round(avg_pop[0]["avg"], 1) if avg_pop else 0

kpi1, kpi2, kpi3 = st.columns(3)

with kpi1:
    st.metric(label="Total de Canciones en Catálogo", value=f"{total_tracks:,}")
with kpi2:
    st.metric(label="Artistas Únicos", value=artistas_unicos)
with kpi3:
    st.metric(label="Popularidad Promedio", value=f"{popularidad_promedio} pts")

#corte
st.markdown("---")

st.subheader("Análisis del Catálogo")
col_graf1, col_graf2 = st.columns(2)

with col_graf1:
    st.markdown("### **Top 5 Artistas Más Populares**")
    pipeline_artistas = [
        {"$unwind": "$artistas"},
        {
            "$group": {
                "_id": "$artistas",
                "popularidad_promedio": {"$avg": "$popularidad"},
                "total_canciones": {"$sum": 1}
            }
        },
        {"$match": {"total_canciones": {"$gt": 1}}},
        {"$sort": {"popularidad_promedio": -1}},
        {"$limit": 5}
    ]

    resultados_artistas = list(col.aggregate(pipeline_artistas))
    if resultados_artistas:
        df_artistas = pd.DataFrame(resultados_artistas)
        df_artistas.rename(columns={"_id": "Artista", "popularidad_promedio": "Popularidad Promedio"}, inplace=True)
        fig_bar = px.bar(df_artistas, x="Popularidad Promedio", y="Artista",
                         orientation='h', text_auto='.1f',
                         color="Popularidad Promedio", color_continuous_scale="agsunset")
        fig_bar.update_layout(yaxis={'categoryorder': 'total ascending'}, showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No hay suficientes datos para el ranking.")

with col_graf2:
    st.markdown("### **Géneros del Catálogo**")
    cursor_generos = col.find({}, {"generos": 1, "_id": 0})

    lista_generos = []
    for doc in cursor_generos:
        gen_str = doc.get("generos")
        if gen_str and isinstance(gen_str, str):
            sub_generos = [g.strip().lower() for g in gen_str.split(",")]
            lista_generos.extend(sub_generos)

    if lista_generos:
        df_gen = pd.DataFrame(lista_generos, columns=["Género"])
        top_generos = df_gen["Género"].value_counts().reset_index()
        top_generos.columns = ["Género", "Cantidad"]

        fig_pie = px.pie(top_generos.head(7), values="Cantidad", names="Género",
                         hole=0.4, color_discrete_sequence=px.colors.sequential.Plasma_r)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("No se encontraron datos de géneros para graficar.")

st.markdown("---")

st.subheader("Tendencias Históricas")

pipeline_decadas = [
    {"$match": {"album.fecha_de_lanzamiento": {"$exists": True, "$ne": None}}},
    {
        "$project": {
            "duracion_ms": 1,
            "decada": {
                "$concat": [{"$substr": ["$album.fecha_de_lanzamiento", 0, 3]}, "0s"]
            }
        }
    },
    {
        "$group": {
            "_id": "$decada",
            "duracion_promedio_min": {"$avg": {"$divide": ["$duracion_ms", 60000]}},
            "cantidad_temas": {"$sum": 1}
        }
    },
    {"$sort": {"_id": 1}}
]
resultados_decadas = list(col.aggregate(pipeline_decadas))
datos_limpios = [
    {
        "Década": r["_id"],
        "Duración Promedio": round(r["duracion_promedio_min"], 2),
        "Canciones Lanzadas": r["cantidad_temas"]
    }
    for r in resultados_decadas
    if r["_id"] and len(r["_id"]) == 5 and r["_id"][0].isdigit()
]

if datos_limpios:
    df_decadas = pd.DataFrame(datos_limpios)
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        fig_linea = px.line(df_decadas, x="Década", y="Duración Promedio", markers=True,
                            title="Evolución de la Duración Promedio por Década",
                            color_discrete_sequence=["#9b5de5"])
        st.plotly_chart(fig_linea, use_container_width=True)
    with col_t2:
        fig_vol = px.bar(df_decadas, x="Década", y="Canciones Lanzadas",
                         title="Volumen de Lanzamientos por Década",
                         color_discrete_sequence=["#00bbf9"])
        st.plotly_chart(fig_vol, use_container_width=True)
else:
    st.warning("No se encontraron fechas de lanzamiento válidas para analizar tendencias.")
st.markdown("---")
st.subheader("Atributos de Audio")

col_bi1, col_bi2 = st.columns(2)

with col_bi1:
    st.markdown("### **Energía vs. Bailabilidad**")
    st.caption("El tamaño de las burbujas representa la popularidad de la canción.")

    cursor_audio = col.find({},
                            {"nombre": 1, "artistas": 1, "energia": 1, "bailabilidad": 1, "popularidad": 1, "_id": 0})
    df_audio = pd.DataFrame(list(cursor_audio))

    if not df_audio.empty:
        df_audio["artistas"] = df_audio["artistas"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)

        fig_scatter = px.scatter(
            df_audio,
            x="bailabilidad",
            y="energia",
            size="popularidad",
            color="popularidad",
            hover_name="nombre",
            hover_data=["artistas"],
            color_continuous_scale="Viridis",
            labels={"bailabilidad": "Bailabilidad (Danceability)", "energia": "Energía (Energy)"}
        )
        st.plotly_chart(fig_scatter, use_container_width=True)
    else:
        st.info("No hay datos suficientes para la matriz de audio.")

with col_bi2:
    st.markdown("### **Artistas del Catálogo**")
    st.caption("Distribución del volumen total de canciones por artista (Top 10 + Otros).")

    # Agregación directa: contamos cuántas canciones tiene cada artista
    pipeline_artistas_directo = [
        {"$unwind": "$artistas"},
        {
            "$group": {
                "_id": "$artistas",
                "cantidad": {"$sum": 1}
            }
        },
        {"$sort": {"cantidad": -1}}
    ]

    resultados_artistas_vol = list(col.aggregate(pipeline_artistas_directo))

    if resultados_artistas_vol:
        df_art = pd.DataFrame(resultados_artistas_vol)
        df_art.rename(columns={"_id": "Artista", "cantidad": "Cantidad de Canciones"}, inplace=True)

        if len(df_art) > 10:
            top_10 = df_art.head(10).copy()
            otros_cant = df_art.iloc[10:]["Cantidad de Canciones"].sum()

            fila_otros = pd.DataFrame([{"Artista": "Otros Artistas", "Cantidad de Canciones": otros_cant}])
            df_chart = pd.concat([top_10, fila_otros], ignore_index=True)
        else:
            df_chart = df_art

        fig_pie_artistas_directo = px.pie(
            df_chart,
            values="Cantidad de Canciones",
            names="Artista",
            hole=0.4,
            color_discrete_sequence=px.colors.sequential.Plotly3_r
        )

        fig_pie_artistas_directo.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_pie_artistas_directo, use_container_width=True)
    else:
        st.info("No se encontraron datos de artistas para graficar.")

#corte
st.markdown("---")

st.subheader("Filtros sobre canciones")

f1, f2, f3, f4 = st.columns(4)
with f1:
    search_query = st.text_input("Buscar por Canción/Artista", placeholder="Ej: Femininomenon")
with f2:
    genero_query = st.text_input("Filtrar Género texto", placeholder="Ej: pop")
with f3:
    dance_min = st.slider("Bailabilidad Mínima", 0.0, 1.0, 0.0, step=0.05)
with f4:
    energy_min = st.slider("Energía Mínima", 0.0, 1.0, 0.0, step=0.05)


incluir_explicito = st.checkbox("Incluir contenido explícito", value=True)

query = {"bailabilidad": {"$gte": dance_min}, "energia": {"$gte": energy_min}}
if not incluir_explicito:
    query["explicito"] = {"$nin": [True, "true", "True"]}
if search_query:
    query["$or"] = [{"nombre": {"$regex": search_query, "$options": "i"}},
                    {"artistas": {"$regex": search_query, "$options": "i"}}]
if genero_query:
    query["generos"] = {"$regex": genero_query, "$options": "i"}

proyeccion = {"nombre": 1, "artistas": 1, "generos": 1, "popularidad": 1, "bailabilidad": 1, "energia": 1, "_id": 0}
resultados = list(col.find(query, proyeccion).sort("popularidad", -1).limit(100))

if resultados:
    for doc in resultados:
        if isinstance(doc.get("artistas"), list):
            doc["artistas"] = ", ".join(doc["artistas"])

    df_canciones = pd.DataFrame(resultados)
    df_canciones = df_canciones.reindex(
        columns=["nombre", "artistas", "generos", "popularidad", "bailabilidad", "energia"])
    st.dataframe(df_canciones, use_container_width=True, hide_index=True)
else:
    st.info("No se encontraron registros que coincidan con la configuración de filtros.")