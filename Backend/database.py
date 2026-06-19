import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def resolver_rut_a_id(rut):
    if not rut:
        return None
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM personas WHERE rut = %s", (rut,))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        cur.close()
        conn.close()

def init_db():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS dispositivos (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id) DEFAULT 1,
                nombre VARCHAR(100) DEFAULT 'Reloj Principal',
                mac_address VARCHAR(20),
                ip_local VARCHAR(20),
                estado VARCHAR(20) DEFAULT 'activo',
                ultimo_heartbeat TIMESTAMP,
                codigo_enrol VARCHAR(8),
                enrolado BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS codigo_enrol VARCHAR(8)")
        cur.execute("ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS enrolado BOOLEAN DEFAULT TRUE")
        cur.execute("ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS password_hash VARCHAR(64)")
        cur.execute("ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS password_plain VARCHAR(20)")
        cur.execute("ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS password_pendiente BOOLEAN DEFAULT FALSE")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios_web (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(200) NOT NULL,
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("ALTER TABLE usuarios_web ALTER COLUMN empresa_id DROP NOT NULL")
        cur.execute("ALTER TABLE usuarios_web DROP COLUMN IF EXISTS rol")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuario_empresa (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER NOT NULL REFERENCES usuarios_web(id) ON DELETE CASCADE,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
                rol VARCHAR(20) NOT NULL DEFAULT 'trabajador',
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(usuario_id, empresa_id)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ue_usuario ON usuario_empresa(usuario_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ue_empresa ON usuario_empresa(empresa_id)")
        cur.execute("ALTER TABLE usuario_empresa DROP CONSTRAINT IF EXISTS usuario_empresa_usuario_id_key")
        cur.execute("ALTER TABLE usuario_empresa DROP CONSTRAINT IF EXISTS usuario_empresa_empresa_id_key")

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
        cur.execute("ALTER TABLE asignaciones DROP CONSTRAINT IF EXISTS asignaciones_persona_id_key")
        cur.execute("ALTER TABLE asignaciones DROP CONSTRAINT IF EXISTS asignaciones_turno_id_key")
        cur.execute("ALTER TABLE asignaciones DROP CONSTRAINT IF EXISTS asignaciones_vigente_key")

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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS integraciones_erp (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER REFERENCES empresas(id) DEFAULT 1,
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
        cur.execute("ALTER TABLE integraciones_erp ADD COLUMN IF NOT EXISTS empresa_id INTEGER REFERENCES empresas(id) DEFAULT 1")
        cur.execute("ALTER TABLE integraciones_erp ADD COLUMN IF NOT EXISTS ultimo_envio TIMESTAMP")
        cur.execute("ALTER TABLE integraciones_erp ADD COLUMN IF NOT EXISTS ultimo_estado VARCHAR(200)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS consentimientos (
                id SERIAL PRIMARY KEY,
                persona_id INTEGER NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
                fecha_aceptacion TIMESTAMP DEFAULT NOW(),
                version_politica VARCHAR(20) DEFAULT '1.0',
                ip_dispositivo VARCHAR(45),
                metodo_aceptacion VARCHAR(30) DEFAULT 'web',
                UNIQUE(persona_id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS logs_biometricos (
                id SERIAL PRIMARY KEY,
                persona_id INTEGER REFERENCES personas(id) ON DELETE SET NULL,
                dispositivo_id INTEGER REFERENCES dispositivos(id) ON DELETE SET NULL,
                timestamp TIMESTAMP DEFAULT NOW(),
                tipo_operacion VARCHAR(30) NOT NULL,
                resultado VARCHAR(20) NOT NULL,
                ip_origen VARCHAR(45)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS eliminaciones_biometricas (
                id SERIAL PRIMARY KEY,
                persona_id INTEGER NOT NULL,
                embedding_anterior TEXT,
                foto_path VARCHAR(500),
                usuario_solicitante VARCHAR(100),
                timestamp TIMESTAMP DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS encodings_faciales (
                id SERIAL PRIMARY KEY,
                persona_id INTEGER NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
                encoding TEXT NOT NULL,
                foto_path VARCHAR(500),
                quality_score FLOAT DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ef_persona ON encodings_faciales(persona_id)")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_consentimientos_persona ON consentimientos(persona_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_biometricos_persona ON logs_biometricos(persona_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_biometricos_timestamp ON logs_biometricos(timestamp)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_eliminaciones_biometricas_persona ON eliminaciones_biometricas(persona_id)")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_asistencias_persona ON asistencias(persona_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_asistencias_dispositivo ON asistencias(dispositivo_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_asistencias_fecha ON asistencias(fecha_hora)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_personas_empresa ON personas(empresa_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_personas_rut ON personas(rut)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_erp_activo ON integraciones_erp(activo)")

        cur.execute("""
            INSERT INTO encodings_faciales (persona_id, encoding, foto_path)
            SELECT p.id, p.encoding_facial, 'static/previews/' || p.id || '.jpg'
            FROM personas p
            WHERE p.encoding_facial IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM encodings_faciales ef WHERE ef.persona_id = p.id
              )
        """)

        # ── SEED ─────────────────────────────────────────────────────
        cur.execute("""
            INSERT INTO empresas (id, nombre, rut_empresa)
            VALUES (1, 'Empresa por defecto', '00000000-0')
            ON CONFLICT (id) DO NOTHING
        """)

        cur.execute("SELECT id FROM usuarios_web WHERE email = 'admin@empresa.cl'")
        admin_row = cur.fetchone()
        if admin_row:
            admin_id = admin_row[0]
        else:
            import bcrypt
            admin_hash = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cur.execute(
                "INSERT INTO usuarios_web (nombre, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
                ('Administrador', 'admin@empresa.cl', admin_hash)
            )
            admin_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO usuario_empresa (usuario_id, empresa_id, rol)
            VALUES (%s, 1, 'admin')
            ON CONFLICT (usuario_id, empresa_id) DO NOTHING
        """, (admin_id,))

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
