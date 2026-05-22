import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # ── NUEVA: empresas ──────────────────────────────────────────
        # Si alguien usa el sistema sin web, igual se crea una empresa
        # por defecto en el seed (ver abajo). El reloj siempre manda
        # empresa_id=1 si no está configurado de otra forma.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS empresas (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                rut_empresa VARCHAR(20),
                email_contacto VARCHAR(100),
                telefono VARCHAR(20),
                direccion VARCHAR(200),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ── NUEVA: dispositivos ──────────────────────────────────────
        # Cada reloj se registra aquí. Sin esto no sabes qué reloj
        # sincronizó qué registros ni si está caído.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dispositivos (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id) DEFAULT 1,
                nombre VARCHAR(100) DEFAULT 'Reloj Principal',
                mac_address VARCHAR(20),
                ip_local VARCHAR(20),
                estado VARCHAR(20) DEFAULT 'activo',
                ultimo_heartbeat TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ── NUEVA: usuarios_web ──────────────────────────────────────
        # Solo para quien use el panel web. No afecta al reloj.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios_web (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id) DEFAULT 1,
                nombre VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(200) NOT NULL,
                rol VARCHAR(20) DEFAULT 'admin',
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ── MODIFICADA: personas ─────────────────────────────────────
        # Se agrega empresa_id y activo. El resto igual que antes.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS personas (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id) DEFAULT 1,
                nombre VARCHAR(100) NOT NULL,
                rut VARCHAR(20) UNIQUE NOT NULL,
                email VARCHAR(100),
                huella_id INTEGER,
                encoding_facial TEXT,
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("ALTER TABLE personas ADD COLUMN IF NOT EXISTS empresa_id INTEGER REFERENCES empresas(id) DEFAULT 1")
        cur.execute("ALTER TABLE personas ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE")

        # ── MODIFICADA: turnos ───────────────────────────────────────
        # Se agrega empresa_id y activo.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS turnos (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id) DEFAULT 1,
                nombre VARCHAR(100) NOT NULL,
                hora_inicio TIME NOT NULL,
                hora_fin TIME NOT NULL,
                dias VARCHAR(50),
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("ALTER TABLE turnos ADD COLUMN IF NOT EXISTS empresa_id INTEGER REFERENCES empresas(id) DEFAULT 1")
        cur.execute("ALTER TABLE turnos ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE")

        # ── SIN CAMBIOS: asignaciones ────────────────────────────────
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

        # ── MODIFICADA: asistencias ──────────────────────────────────
        # Se agrega dispositivo_id y sincronizado_at para trazabilidad
        # completa (necesario para Resolución Exenta N°38).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS asistencias (
                id SERIAL PRIMARY KEY,
                persona_id INTEGER REFERENCES personas(id),
                dispositivo_id INTEGER REFERENCES dispositivos(id) DEFAULT 1,
                nombre VARCHAR(100),
                tipo VARCHAR(20),
                metodo VARCHAR(50) DEFAULT 'huella',
                fecha_hora TIMESTAMP DEFAULT NOW(),
                timestamp_local VARCHAR(50),
                origen VARCHAR(20) DEFAULT 'dispositivo',
                imagen_path TEXT,
                sincronizado BOOLEAN DEFAULT TRUE,
                sincronizado_at TIMESTAMP
            )
        """)
        cur.execute("ALTER TABLE asistencias ADD COLUMN IF NOT EXISTS dispositivo_id INTEGER REFERENCES dispositivos(id) DEFAULT 1")
        cur.execute("ALTER TABLE asistencias ADD COLUMN IF NOT EXISTS timestamp_local VARCHAR(50)")
        cur.execute("ALTER TABLE asistencias ADD COLUMN IF NOT EXISTS sincronizado_at TIMESTAMP")

        # ── NUEVA: sincronizacion_log ────────────────────────────────
        # Registra cada vez que el reloj sincroniza datos offline.
        # Es la tabla que vas a usar en tus pruebas de confiabilidad.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sincronizacion_log (
                id SERIAL PRIMARY KEY,
                dispositivo_id INTEGER REFERENCES dispositivos(id) DEFAULT 1,
                registros_enviados INTEGER DEFAULT 0,
                registros_ok INTEGER DEFAULT 0,
                estado VARCHAR(20) DEFAULT 'ok',
                detalle TEXT,
                fecha TIMESTAMP DEFAULT NOW()
            )
        """)

        # ── NUEVA: integraciones ERP ────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS integraciones_erp (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(120) NOT NULL,
                tipo VARCHAR(40) NOT NULL,
                webhook_url TEXT NOT NULL,
                headers TEXT DEFAULT '{}',
                field_map TEXT DEFAULT '{}',
                envio_auto BOOLEAN DEFAULT TRUE,
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ── ÍNDICES ──────────────────────────────────────────────────
        cur.execute("CREATE INDEX IF NOT EXISTS idx_asistencias_persona ON asistencias(persona_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_asistencias_dispositivo ON asistencias(dispositivo_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_asistencias_fecha ON asistencias(fecha_hora)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_personas_empresa ON personas(empresa_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_erp_activo ON integraciones_erp(activo)")

        # ── SEED: empresa y dispositivo por defecto ──────────────────
        # Esto es lo que hace que el sistema funcione SIN página web.
        # El reloj siempre puede usar empresa_id=1 y dispositivo_id=1
        # sin necesitar configuración adicional.
        cur.execute("""
            INSERT INTO empresas (id, nombre, rut_empresa)
            VALUES (1, 'Empresa por defecto', '00000000-0')
            ON CONFLICT (id) DO NOTHING
        """)
        cur.execute("""
            INSERT INTO dispositivos (id, empresa_id, nombre)
            VALUES (1, 1, 'Reloj Principal')
            ON CONFLICT (id) DO NOTHING
        """)

        conn.commit()
        print("Base de datos inicializada correctamente")
    except Exception as e:
        print(f"Error al inicializar BD: {e}")
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    init_db()