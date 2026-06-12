# SonicMesh

Sistema que permite analizar la música, los historiales y generar recomendaciones,  desarrollado en el marco de la materia **Ingeniería de Datos II**.

SonicMesh integra cuatro bases de datos NoSQL para poder realizar consultas sobre el catálogo de canciones disponibles, sobre los historiales y sobre las recomendaciones de música. 

---

## Arquitectura

 **MongoDB:** Documental, catálogo de canciones (update, query)

 **Neo4j:** Grafos, relaciones entre usuarios, canciones, artistas, álbumes y géneros. (update, query)

 **Redis:** Clave-valor, carrito de canciones (update, query, delete) 

 **Apache Cassandra:** Columnar, historial de reproducciones de los usuarios (update, query, delete) 

---

## Fuentes de datos

- **Spotify**: historial extendido de reproducciones y playlists exportadas con [Exportify](https://exportify.net/)

- **YouTube Music**: historial de reproducciones exportado desde Google Takeout

---
