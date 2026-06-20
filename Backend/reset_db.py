from database import get_connection, init_db

TABLAS = [
    'encodings_faciales',
    'logs_biometricos',
    'eliminaciones_biometricas',
    'consentimientos',
    'asistencias',
    'asignaciones',
    'turnos',
    'integraciones_erp',
    'dispositivos',
    'personas',
    'sincronizacion_log',
    'usuario_empresa',
    'usuarios_web',
    'empresas',
]

def reset_db():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            TRUNCATE TABLE {', '.join(TABLAS)}
            RESTART IDENTITY CASCADE
        """)
        conn.commit()
        print("Tablas truncadas correctamente")
    except Exception as e:
        conn.rollback()
        print(f"Error al truncar tablas: {e}")
        return
    finally:
        cur.close()
        conn.close()

    print("Re-ejecutando init_db() para crear esquema y datos por defecto...")
    init_db()

if __name__ == "__main__":
    import bcrypt
    reset_db()
