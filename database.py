import psycopg2
import os
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")
def get_connection():
    # Neon requiere sslmode=require para conexiones externas
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Tabla de Personas (Iteración 1 y 2)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS personas (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                rut VARCHAR(20) UNIQUE NOT NULL,
                email VARCHAR(100),
                huella_id INTEGER,
                encoding_facial TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Tabla de Turnos (Iteración 2)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS turnos (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                hora_inicio TIME NOT NULL,
                hora_fin TIME NOT NULL,
                dias VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Tabla de Asignaciones (Iteración 2)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS asignaciones (
                id SERIAL PRIMARY KEY,
                persona_id INTEGER REFERENCES personas(id),
                turno_id INTEGER REFERENCES turnos(id),
                fecha_asignacion TIMESTAMP DEFAULT NOW(),
                vigente BOOLEAN DEFAULT TRUE,
                UNIQUE(persona_id, turno_id, vigente)
            )
        """)

        # Tabla de Asistencias (Iteración 3: Sincronización)
        # Se añade 'metodo' para diferenciar entre rostro y dactilar [cite: 39]
        cur.execute("""
            CREATE TABLE IF NOT EXISTS asistencias (
                id SERIAL PRIMARY KEY,
                persona_id INTEGER REFERENCES personas(id),
                nombre VARCHAR(100),
                tipo VARCHAR(20),
                metodo VARCHAR(50) DEFAULT 'huella',
                fecha_hora TIMESTAMP DEFAULT NOW(),
                origen VARCHAR(20) DEFAULT 'dispositivo',
                id_dispositivo INTEGER,
                imagen_path TEXT,
                sincronizado BOOLEAN DEFAULT TRUE
            )
        """)

        # Índice para optimizar consultas de la API [cite: 1182]
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_asistencias_persona 
            ON asistencias(persona_id)
        """)

        conn.commit()
        print("Base de datos en Neon inicializada correctamente")
    except Exception as e:
        print(f"Error al conectar a Neon: {e}")
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    init_db()