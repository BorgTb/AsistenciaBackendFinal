"""
Mock ERP: Buk Asistencia
========================
Simula la API REST de Buk Asistencia.
Basado en documentación oficial: https://app.swaggerhub.com/apis-docs/BUKASISTENCIA/ApiAsistencia/1.0.0
Centro de ayuda: https://supportcenter.buk.cl/hc/es-419/articles/50240904785051

Autenticación:
  Header: auth_token: <TOKEN>   (solicitado al equipo SAC de Buk)

Endpoints simulados:
  GET  /attendances              → marcajes del período
  POST /attendances/inject       → inyección de marcajes (el que usa tu sistema SAS)
  GET  /employees                → nómina
  GET  /shifts                   → turnos asignados
  GET  /premises                 → recintos

IMPORTANTE según docs:
  - La API es principalmente de LECTURA (pull). Buk extrae datos, no recibe push nativo.
  - El endpoint de inyección (/inject) es el único de escritura disponible.
  - Fechas en formato UTC.
  - Requiere usuario perfil "Autoservicio" en módulo de Asistencia.

Uso:
  pip install flask
  python mock_buk.py
  → corre en http://localhost:8003

Configuración en tu panel SAS (tipo: buk):
  Webhook URL : http://localhost:8003/attendances/inject
  Headers     : {"Content-Type":"application/json","auth_token":"MI_TOKEN_BUK"}
  Field Map   : {"tipo":"type","fecha_hora":"datetime","rut":"rut"}
"""

from flask import Flask, request, jsonify
from datetime import datetime
from functools import wraps

app = Flask(__name__)

# ── Base de datos en memoria ──────────────────────────────────────────────────
VALID_TOKENS = {"MI_TOKEN_BUK", "test_token_123", "buk_api_key"}

EMPLOYEES = [
    {"id": 101, "rut": "12345678-9", "rut_fmt": "12.345.678-9",
     "full_name": "Juan Pérez",     "role": "Operario",   "premise_id": 1, "active": True},
    {"id": 102, "rut": "9876543-2",  "rut_fmt": "9.876.543-2",
     "full_name": "María González", "role": "Cajera",     "premise_id": 1, "active": True},
    {"id": 103, "rut": "15432100-K", "rut_fmt": "15.432.100-K",
     "full_name": "Carlos Rojas",   "role": "Supervisor", "premise_id": 2, "active": True},
]

PREMISES = [
    {"id": 1, "name": "Casa Matriz",   "address": "Av. Principal 123", "city": "Santiago"},
    {"id": 2, "name": "Sucursal Norte","address": "Calle Norte 456",   "city": "Antofagasta"},
]

SHIFTS = [
    {"employee_id": 101, "rut": "12345678-9", "shift_name": "Turno Mañana",
     "start_time": "08:00", "end_time": "17:00", "days": ["Mon","Tue","Wed","Thu","Fri"]},
    {"employee_id": 102, "rut": "9876543-2",  "shift_name": "Turno Tarde",
     "start_time": "14:00", "end_time": "22:00", "days": ["Mon","Tue","Wed","Thu","Fri"]},
]

INJECTED_ATTENDANCES = []  # registros inyectados via POST /attendances/inject

# Marcajes históricos de ejemplo (lo que devuelve GET /attendances)
HISTORICAL_ATTENDANCES = [
    {"id": 1, "rut": "12345678-9", "employee_name": "Juan Pérez",
     "type": "in",  "datetime": "2025-06-23T08:02:00Z", "premise_id": 1, "source": "biometric"},
    {"id": 2, "rut": "12345678-9", "employee_name": "Juan Pérez",
     "type": "out", "datetime": "2025-06-23T17:05:00Z", "premise_id": 1, "source": "biometric"},
]


def _clean_rut(rut: str) -> str:
    return rut.replace(".", "").strip()


def _now_utc():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Decorador de autenticación ────────────────────────────────────────────────
def require_auth_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("auth_token", "")
        if not token:
            return jsonify({"error": "auth_token header requerido",
                            "detail": "Incluir el token de la empresa como header 'auth_token'"}), 401
        if token not in VALID_TOKENS:
            return jsonify({"error": "Token inválido",
                            "detail": f"Token '{token[:8]}...' no reconocido"}), 403
        return f(*args, **kwargs)
    return decorated


# ── Nómina ────────────────────────────────────────────────────────────────────
@app.route("/employees", methods=["GET"])
@require_auth_token
def get_employees():
    """
    GET /employees
    Parámetros: page=0, page_size=25
    Retorna nómina completa para mapear RUT → datos del colaborador.
    """
    page      = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 25))
    start     = (page - 1) * page_size
    items     = EMPLOYEES[start: start + page_size]

    return jsonify({
        "pagination": {
            "count": len(EMPLOYEES),
            "total_pages": max(1, (len(EMPLOYEES) + page_size - 1) // page_size),
            "next": None, "previous": None
        },
        "data": items
    })


# ── Recintos ──────────────────────────────────────────────────────────────────
@app.route("/premises", methods=["GET"])
@require_auth_token
def get_premises():
    """GET /premises → lista de recintos (lugares de trabajo)."""
    return jsonify({
        "pagination": {"count": len(PREMISES), "total_pages": 1},
        "data": PREMISES
    })


# ── Turnos asignados ──────────────────────────────────────────────────────────
@app.route("/shifts", methods=["GET"])
@require_auth_token
def get_shifts():
    """
    GET /shifts?desde=2025-06-01&hasta=2025-06-30
    Retorna turnos asignados por colaborador en el período.
    """
    return jsonify({
        "pagination": {"count": len(SHIFTS), "total_pages": 1},
        "data": SHIFTS
    })


# ── Marcajes: consulta ────────────────────────────────────────────────────────
@app.route("/attendances", methods=["GET"])
@require_auth_token
def get_attendances():
    """
    GET /attendances?desde=2025-06-01&hasta=2025-06-30&page=1&page_size=25
    Retorna marcajes del período. Fechas en formato UTC según docs.
    """
    desde    = request.args.get("desde", "")
    hasta    = request.args.get("hasta", "")
    page     = int(request.args.get("page", 1))
    page_size= int(request.args.get("page_size", 25))

    all_records = HISTORICAL_ATTENDANCES + INJECTED_ATTENDANCES
    start = (page - 1) * page_size

    return jsonify({
        "pagination": {
            "count": len(all_records),
            "total_pages": max(1, (len(all_records) + page_size - 1) // page_size),
            "from_date": desde, "to_date": hasta
        },
        "data": all_records[start: start + page_size]
    })


# ── Inyección de marcajes ─────────────────────────────────────────────────────
@app.route("/attendances/inject", methods=["POST"])
@require_auth_token
def inject_attendance():
    """
    POST /attendances/inject
    Endpoint de ESCRITURA: inyecta marcaciones manuales en Buk.
    Las marcaciones aparecen como "tipo manual" en el módulo de asistencia.

    Body (mapeado desde tu field_map):
    {
      "rut":        "12.345.678-9",
      "type":       "in",           ← "in" o "out" (mapeado desde "tipo")
      "datetime":   "2025-06-24T08:05:00Z",
      "premise_id": 1               ← opcional, ID del recinto
    }

    También acepta el formato bruto de tu sistema sin field_map:
    {
      "rut":        "12.345.678-9",
      "tipo":       "entrada",
      "fecha_hora": "2025-06-24T08:05:00Z"
    }
    """
    body = request.json or {}

    # Soportar tanto nombres mapeados como originales
    rut_raw  = body.get("rut",       "")
    type_raw = body.get("type",      "") or body.get("tipo", "")
    dt_raw   = body.get("datetime",  "") or body.get("fecha_hora", "")
    premise  = body.get("premise_id", 1)

    # Validaciones según docs de Buk
    if not rut_raw:
        return jsonify({"error": "Campo 'rut' requerido"}), 400
    if not dt_raw:
        return jsonify({"error": "Campo 'datetime' requerido (formato UTC: YYYY-MM-DDTHH:MM:SSZ)"}), 400

    # Normalizar tipo: "entrada"→"in", "salida"→"out"
    type_map = {"entrada": "in", "salida": "out", "in": "in", "out": "out"}
    tipo_norm = type_map.get(str(type_raw).lower(), "in")

    # Buscar colaborador
    rut_clean = _clean_rut(str(rut_raw))
    emp = next((e for e in EMPLOYEES
                if _clean_rut(e["rut"]) == rut_clean or _clean_rut(e["rut_fmt"]) == rut_clean), None)
    if not emp:
        return jsonify({
            "error": "Colaborador no encontrado",
            "detail": f"RUT '{rut_raw}' no existe en la nómina. "
                      "Verificar sincronización de nómina con Buk."
        }), 422

    new_id = len(INJECTED_ATTENDANCES) + 100
    record = {
        "id":            new_id,
        "rut":           emp["rut_fmt"],
        "employee_name": emp["full_name"],
        "type":          tipo_norm,
        "datetime":      dt_raw,
        "premise_id":    premise,
        "source":        "manual",          # Buk lo marca como manual
        "injected_at":   _now_utc(),
    }
    INJECTED_ATTENDANCES.append(record)

    tipo_label = "Entrada" if tipo_norm == "in" else "Salida"
    print(f"[Buk Mock] ✓ Marcaje inyectado: {emp['full_name']} ({emp['rut_fmt']}) "
          f"→ {tipo_label} — {dt_raw}")

    return jsonify({
        "id":            new_id,
        "rut":           emp["rut_fmt"],
        "employee_name": emp["full_name"],
        "type":          tipo_norm,
        "datetime":      dt_raw,
        "premise_id":    premise,
        "status":        "injected",
        "message":       "Marcaje registrado correctamente como tipo manual"
    }), 200


# ── Inasistencias y horas extra ───────────────────────────────────────────────
@app.route("/absences", methods=["GET"])
@require_auth_token
def get_absences():
    """GET /absences → inasistencias del período."""
    return jsonify({"data": [], "pagination": {"count": 0, "total_pages": 1}})


# ── Auxiliares ────────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok", "mock": "Buk Asistencia",
        "docs": "https://app.swaggerhub.com/apis-docs/BUKASISTENCIA/ApiAsistencia/1.0.0",
        "soporte": "https://supportcenter.buk.cl/hc/es-419/articles/50240904785051",
        "employees": len(EMPLOYEES), "premises": len(PREMISES),
        "injected_attendances": len(INJECTED_ATTENDANCES)
    })

@app.route("/marcajes-recibidos", methods=["GET"])
def ver_inyectados():
    """Ver solo los marcajes inyectados por tu sistema SAS."""
    return jsonify({"total": len(INJECTED_ATTENDANCES), "records": INJECTED_ATTENDANCES})


if __name__ == "__main__":
    print("=" * 60)
    print("  Mock ERP: Buk Asistencia")
    print("  Docs:    https://supportcenter.buk.cl/hc/es-419/articles/50240904785051")
    print("  Swagger: https://app.swaggerhub.com/apis-docs/BUKASISTENCIA/ApiAsistencia/1.0.0")
    print("  Puerto:  http://localhost:8003")
    print("=" * 60)
    print("\nAutenticación:")
    print("  Header: auth_token: MI_TOKEN_BUK")
    print("  Tokens válidos para pruebas: MI_TOKEN_BUK, test_token_123, buk_api_key")
    print("\nEndpoints:")
    print("  POST /attendances/inject  → inyectar marcaje (← SAS apunta aquí)")
    print("  GET  /attendances         → consultar marcajes del período")
    print("  GET  /employees           → nómina de colaboradores")
    print("  GET  /premises            → recintos disponibles")
    print("  GET  /shifts              → turnos asignados")
    print("  GET  /marcajes-recibidos  → ver inyecciones recibidas")
    print("  GET  /health              → estado del mock")
    print()
    print("  Field Map recomendado en SAS:")
    print('  {"tipo":"type","fecha_hora":"datetime"}')
    print()
    app.run(port=8003, debug=True)
