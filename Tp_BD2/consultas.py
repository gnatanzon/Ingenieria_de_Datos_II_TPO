import redis

# 1. Conexión a Docker
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# 2. Función de Inicio de Sesión
def iniciar_sesion(id_usuario, nombre_alumno, plataforma):
    clave_sesion = f"sesion:{id_usuario}"
    r.hset(clave_sesion, mapping={
        "nombre": nombre_alumno,
        "plataforma_origen": plataforma,
        "estado": "activo"
    })
    # Cambiamos el candadito por texto normal para que Windows no se trabe
    print(f"LOGIN EXITO: Sesion iniciada para {nombre_alumno} ({plataforma}).")

# 3. Prueba de funcion de inicio de sesion
print("--- PROBANDO INICIOS DE SESIÓN ---")
iniciar_sesion("anto_playlist", "Anto", "Spotify")
iniciar_sesion("cami_playlist", "Cami", "Spotify")
iniciar_sesion("chen_playlist", "Chen", "Spotify")
iniciar_sesion("guillermina_playlist", "Guille", "Spotify")
iniciar_sesion("julib_playlist", "Juli B", "Spotify")
iniciar_sesion("julis_playlist", "Juli S", "Spotify")

# funcion Guardar canciones favoritas (Sin que se dupliquen)
def agregar_favorita(id_usuario, nombre_cancion):
    r.sadd(f"favoritas:{id_usuario}", nombre_cancion)
    print(f" FAVORITOS -> '{nombre_cancion}' ha sido agregada a favoritos de {id_usuario}.")

#Pruebas de como guardaron las funciones favoritas


print("--- TESTEANDO CANCIONES FAVORITAS PARA LAS 6 INTEGRANTES ---")

#Favoritos de Antonella
agregar_favorita("anto_playlist", "SWIM")             
agregar_favorita("anto_playlist", "Style")            
agregar_favorita("anto_playlist", "Lover")            
agregar_favorita ("anto_playlist", "Black Space")

#Favoritos de Camila Nieba
agregar_favorita("cami_playlist", "CORAZÓN VACÍO")      
agregar_favorita("cami_playlist", "SWIM")              
agregar_favorita("cami_playlist", "Perfecta")          
agregar_favorita("cami_playlist", "CORAZÓN VACÍO")

# Favoritos de Chen
agregar_favorita("chen_playlist", "Perfecta")        
agregar_favorita("chen_playlist", "Ella Dice")         
agregar_favorita("chen_playlist", "Let It Happen")     
agregar_favorita("chen_playlist", " New Rules")


#Favoritos de Guillermina
agregar_favorita("guillermina_playlist", "MEJOR QUE VOS")  
agregar_favorita("guillermina_playlist", "Perfecta")       
agregar_favorita("guillermina_playlist", "CORAZÓN VACÍO")  
agregar_favorita("guillermina_playlist", "Perfecta!")


# Favoritos de Julieta B
agregar_favorita("julib_playlist", "Walking On A Dream") 
agregar_favorita("julib_playlist", "SWIM")               
agregar_favorita("julib_playlist", "Please Please Please") 
agregar_favorita("julib_playlist", "MEJOR QUE VOS")


# Favoritos de Julieta S
agregar_favorita("julis_playlist", "Cabildo y Juramento") 
agregar_favorita("julis_playlist", "A la Vez")           
agregar_favorita("julis_playlist", "Nonsense")           
agregar_favorita("julis_playlist", "Cupido" )



##Función para VER qué hay adentro de los favoritos de un usuario
def mostrar_favoritas(id_usuario):
    clave = f"favoritas:{id_usuario}"
    canciones = r.smembers(clave) # smembers le pide a Redis todos los elementos del Set
    print(f" Lista en Redis para {id_usuario}: {canciones}")

#pruebas de favoritos usuarios:
mostrar_favoritas("anto_playlist")
mostrar_favoritas("cami_playlist")
mostrar_favoritas("chen_playlist")
mostrar_favoritas("guillermina_playlist")
mostrar_favoritas("julib_playlist")
mostrar_favoritas("julis_playlist")

#registrar generos musicales (Estructura: Set)
def registrar_genero(nombre_genero):
    r.sadd("tienda:generos_disponibles", nombre_genero)
    print(f"GÉNERO '{nombre_genero}' está disponible en sonicmesh.")

# test de generos:
registrar_genero("pop latino")
registrar_genero("k-pop")
registrar_genero("pop latino") # se supone que aca redus ignora el duplicado por default
registrar_genero("trap")
registrar_genero("reggeton")


#funcion de canciones en comun entre dos integrantes
def canciones_en_comun(id_usuario1, id_usuario2):
    print(f" TEST: BUSCANDO COINCIDENCIAS ENTRE {id_usuario1} Y {id_usuario2}")
    # sinter calcula la intersección real entre dos Sets de Redis
    coincidencias = r.sinter(f"favoritas:{id_usuario1}", f"favoritas:{id_usuario2}")
    print(f"   A las dos les gusta: {coincidencias}")

# --- TEST ---
r.sadd("favoritas:cami_playlist", "CORAZÓN VACÍO", "SWIM", "Perfecta")
r.sadd("favoritas:guillermina_playlist", "SWIM", "Style", "Lover")
canciones_en_comun("cami_playlist", "guillermina_playlist")

#funcion de buscra por artistas (set)
def catalogar_cancion_por_artista(nombre_artista, nombre_cancion):
    clave = f"artista:{nombre_artista.lower().replace(' ', '_')}"
    r.sadd(clave, nombre_cancion)

def buscar_por_artista(nombre_artista):
    clave = f"artista:{nombre_artista.lower().replace(' ', '_')}"
    resultados = r.smembers(clave)
    print(f" Buscador de artista -> Canciones de '{nombre_artista}': {resultados}")

print("\n--- TESTEANDO BUSCADOR POR ARTISTA ---")

# Anto
catalogar_cancion_por_artista("BTS", "SWIM")
catalogar_cancion_por_artista("SANTOS BRAVOS", "VELOCIDADE")
catalogar_cancion_por_artista("DPR IAN", "The Show")
catalogar_cancion_por_artista("DPR IAN", "No Blueberries")

# Cami
catalogar_cancion_por_artista("Maria Becerra", "CORAZÓN VACÍO")
catalogar_cancion_por_artista("Nicki Nicole", "8 AM")
catalogar_cancion_por_artista("TINI", "Ella Dice")
catalogar_cancion_por_artista("Taylor Swift", "Style")

#Chen 
catalogar_cancion_por_artista("Laufey", "From The Start")
catalogar_cancion_por_artista("Miranda!", "Perfecta")
catalogar_cancion_por_artista("Sabrina Carpenter", "Nonsense")
catalogar_cancion_por_artista("NAFTA", "Potra")

# Guillermina 
catalogar_cancion_por_artista("Conociendo Rusia", "A la Vez")
catalogar_cancion_por_artista("Chappell Roan", "Red Wine Supernova")
catalogar_cancion_por_artista("Taylor Swift", "Opalite")

#Julieta b
catalogar_cancion_por_artista("Empire Of The Sun", "Walking On A Dream")
catalogar_cancion_por_artista("Tame Impala", "Let It Happen")
catalogar_cancion_por_artista("Taylor Swift", "Lover")

#Julieta s
catalogar_cancion_por_artista("Conociendo Rusia", "Cabildo y Juramento")
catalogar_cancion_por_artista("Bandalos Chinos", "Mi Fiesta")


# test de buscar por artista
buscar_por_artista("Taylor Swift")
buscar_por_artista("Miranda!")
buscar_por_artista("DPR IAN")
buscar_por_artista("TINI")