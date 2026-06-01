import os
import json
import numpy as np
import psycopg2
from datetime import datetime
from deepface import DeepFace
from dotenv import load_dotenv


load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
# =====================================================================
# 1. CONFIGURACIÓN DE BASE DE DATOS (Ajusta según tu entorno de Coolify)
# =====================================================================
def get_connection():
    return psycopg2.connect(DATABASE_URL)

# =====================================================================
# 2. FUNCIÓN PRINCIPAL DE PROCESAMIENTO
# =====================================================================
def simular_asistencia_por_foto(ruta_imagen):
    print(f"\n==================================================")
    print(f"📸 Procesando: {os.path.basename(ruta_imagen)}")
    print(f"==================================================")
    
    try:
        print("🔍 Analizando rostro y verificando seguridad (Anti-Spoofing)...")
        resultado = DeepFace.represent(
            img_path=ruta_imagen,
            model_name="Facenet",
            enforce_detection=True,
            detector_backend="retinaface", # o "opencv"
            anti_spoofing=True       
        )
        nuevo_embedding = np.array(resultado[0]['embedding'])
        print("✅ Rostro 3D válido detectado.")

    except ValueError as e:
        print(f"❌ Rechazado por DeepFace: {str(e)}")
        print("💡 Causa: No hay rostro, está borroso o es una foto/pantalla falsa.")
        return
    except Exception as e:
        print(f"❌ Error procesando la imagen: {str(e)}")
        return

    print("⏳ Buscando coincidencias en la base de datos...")
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT id, nombre, encoding_facial FROM personas WHERE encoding_facial IS NOT NULL")
        registros_existentes = cur.fetchall()
        
        UMBRAL_SIMILITUD = 10.0
        persona_encontrada = None
        distancia_minima = float('inf')

        for ex_id, ex_nombre, ex_encoding in registros_existentes:
            embedding_db = np.array(json.loads(ex_encoding))
            distancia = np.linalg.norm(embedding_db - nuevo_embedding)

            if distancia < UMBRAL_SIMILITUD and distancia < distancia_minima:
                distancia_minima = distancia
                persona_encontrada = {"id": ex_id, "nombre": ex_nombre}

        if persona_encontrada:
            print(f"✅ ¡Match encontrado! Persona: {persona_encontrada['nombre']} (ID: {persona_encontrada['id']})")
            print(f"📏 Distancia: {distancia_minima:.2f}")

            fecha_hoy = datetime.now().date()
            cur.execute("""
                SELECT tipo FROM asistencias 
                WHERE persona_id = %s AND DATE(timestamp) = %s 
                ORDER BY timestamp DESC LIMIT 1
            """, (persona_encontrada['id'], fecha_hoy))
            
            ultimo_registro = cur.fetchone()
            tipo_asistencia = "salida" if ultimo_registro and ultimo_registro[0] == "entrada" else "entrada"

            ahora = datetime.now()
            cur.execute("""
                INSERT INTO asistencias (persona_id, nombre, tipo, metodo, timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """, (persona_encontrada['id'], persona_encontrada['nombre'], tipo_asistencia, 'facial_test_manual', ahora))
            
            conn.commit()
            print(f"📥 Asistencia guardada: {tipo_asistencia.upper()} a las {ahora.strftime('%H:%M:%S')}")
        else:
            print("⚠️ El rostro es real, pero no coincide con nadie en la base de datos.")

    except Exception as e:
        print(f"❌ Error fatal de base de datos: {str(e)}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

# =====================================================================
# 3. MENÚ INTERACTIVO DE TERMINAL
# =====================================================================
def menu_interactivo():
    # Detecta dónde está este archivo (Backend/deteccion.py)
    directorio_actual = os.path.dirname(os.path.abspath(__file__))
    
    # Entra directo a static/capturas_prueba (misma carpeta Backend)
    directorio_fotos = os.path.abspath(os.path.join(directorio_actual, "static", "capturas_prueba"))
    
    while True:
        print("\n" + "="*50)
        print("🤖 SIMULADOR DE ASISTENCIA FACIAL")
        print("="*50)
        
        if not os.path.exists(directorio_fotos):
            print(f"❌ Error: No se encontró la carpeta de capturas en:\n{directorio_fotos}")
            print("Verifica que las carpetas existan.")
            break
            
        # Filtra solo imágenes
        archivos = [f for f in os.listdir(directorio_fotos) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        
        if not archivos:
            print(f"📂 El directorio {directorio_fotos} está vacío.")
            print("Coloca fotos en esa carpeta para probar.")
            break
            
        print(f"📂 Ruta activa: .../Backend/static/capturas_prueba/\n")
        print("Fotos disponibles:")
        for i, archivo in enumerate(archivos, 1):
            print(f"  [{i}] {archivo}")
            
        print("\nOpciones:")
        print(" - Escribe el NÚMERO de la foto")
        print(" - Escribe el NOMBRE de la foto (ej: intento_01.jpg)")
        print(" - Escribe 'q' para salir")
        
        opcion = input("\n👉 Selecciona tu opción: ").strip()
        
        if opcion.lower() in ['q', 'salir', 'exit', 'quit']:
            print("👋 Cerrando simulador...")
            break
            
        ruta_imagen = None
        
        # Lógica para entender si el usuario puso un número o texto
        if opcion.isdigit() and 1 <= int(opcion) <= len(archivos):
            nombre_archivo = archivos[int(opcion) - 1]
            ruta_imagen = os.path.join(directorio_fotos, nombre_archivo)
        else:
            # Buscar el nombre exacto
            ruta_tentativa = os.path.join(directorio_fotos, opcion)
            # Buscar el nombre asumiendo que no escribió el .jpg
            ruta_con_jpg = os.path.join(directorio_fotos, opcion + ".jpg")
            
            if os.path.exists(ruta_tentativa):
                ruta_imagen = ruta_tentativa
            elif os.path.exists(ruta_con_jpg):
                ruta_imagen = ruta_con_jpg
            else:
                print("❌ Entrada inválida o archivo no encontrado. Intenta de nuevo.")
                continue
        
        if ruta_imagen:
            simular_asistencia_por_foto(ruta_imagen)

if __name__ == "__main__":
    # Inicia el menú apenas se ejecuta el script
    menu_interactivo()