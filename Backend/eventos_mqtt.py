import json
import time
from database import get_connection


def notificar_sincronizacion(empresa_id, tipo, accion, registro_id=None):
    """Publica un mensaje MQTT a cada dispositivo de la empresa para que sincronice.

    Args:
        empresa_id: ID de la empresa
        tipo: 'personas', 'turnos', 'asignaciones', 'asistencias' o 'todas'
        accion: 'crear', 'actualizar' o 'eliminar'
        registro_id: ID del registro que cambió
    """
    try:
        from mqtt_handler import _mqtt_client
    except ImportError:
        return

    if _mqtt_client is None:
        return

    conn = get_connection()
    cur = conn.cursor()
    try:
        if empresa_id is None and registro_id is not None:
            if tipo == 'personas':
                cur.execute("SELECT empresa_id FROM personas WHERE id = %s", (registro_id,))
            elif tipo == 'turnos':
                cur.execute("SELECT empresa_id FROM turnos WHERE id = %s", (registro_id,))
            elif tipo == 'asignaciones':
                cur.execute(
                    "SELECT p.empresa_id FROM personas p "
                    "JOIN asignaciones a ON a.persona_id = p.id WHERE a.id = %s",
                    (registro_id,)
                )
            elif tipo == 'asistencias':
                cur.execute(
                    "SELECT p.empresa_id FROM personas p "
                    "JOIN asistencias a ON a.persona_id = p.id WHERE a.id = %s",
                    (registro_id,)
                )
            row = cur.fetchone()
            empresa_id = row[0] if row else None

        if empresa_id is None:
            return

        cur.execute(
            "SELECT REPLACE(mac_address, ':', '') as mac FROM dispositivos "
            "WHERE empresa_id = %s AND enrolado = TRUE "
            "AND mac_address IS NOT NULL AND mac_address != ''",
            (empresa_id,)
        )
        dispositivos = cur.fetchall()
    except Exception as e:
        print(f"❌ Error consultando dispositivos para notificacion: {e}", flush=True)
        return
    finally:
        cur.close()
        conn.close()

    payload = json.dumps({
        "tipo": tipo,
        "accion": accion,
        "id": registro_id,
        "timestamp": time.time()
    })

    for (mac,) in dispositivos:
        try:
            topic = f"backend/notificacion/{mac}"
            _mqtt_client.publish(topic, payload)
        except Exception as e:
            print(f"❌ Error publicando notificacion a {mac}: {e}", flush=True)

    print(f"📡 MQTT notificacion [{tipo}/{accion}] enviada a {len(dispositivos)} dispositivo(s)", flush=True)
