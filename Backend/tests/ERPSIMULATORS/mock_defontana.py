"""
Mock ERP: Defontana
===================
Simula la API REST de Defontana para módulo de RRHH/Asistencia.
Basado en documentación oficial: https://defontana.atlassian.net/wiki/spaces/CDAV2/
Swagger producción: https://api.defontana.com/swagger/index.html
Swagger pruebas:    https://replapi.defontana.com/swagger/index.html

Autenticación:
  POST /api/Login/GetByCredentials  → retorna access_token (JWT)
  Header en las demás llamadas: Authorization: Bearer <access_token>

Módulos simulados: Auth + Paysheet (RRHH) con endpoint de marcajes.

Notas según docs:
  - La API acepta form-encoded Y JSON.
  - El token invalida todos los anteriores del mismo usuario.
  - Ambiente de pruebas disponible L-V de 09:00 a 20:00.

Uso:
  pip install flask pyjwt
  python mock_defontana.py
  → corre en http://localhost:8002

Configuración en tu panel SAS (tipo: defontana):
  Webhook URL : http://localhost:8002/api/Employee/AddAttendance
  Headers     : {"Content-Type":"application/json","Authorization":"Bearer TOKEN","X-Company-Id":"dfchile"}
  Field Map   : {"tipo":"tipoMarcaje","rut":"rutEmpleado","fecha_hora":"fechaHoraMarcaje"}
"""

from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from functools import wraps
import uuid, json

app = Flask(__name__)

# ── Base de datos en memoria ──────────────────────────────────────────────────
TOKENS = {}   # token → {"user": ..., "company": ..., "expires": datetime}

EMPLEADOS = {
    "12345678-9": {"rut": "12345678-9", "rut_fmt": "12.345.678-9", "nombre": "Juan Pérez",
                   "cargo": "Operario", "empresa": "dfchile", "activo": True},
    "9876543-2":  {"rut": "9876543-2",  "rut_fmt": "9.876.543-2",  "nombre": "María González",
                   "cargo": "Cajera",   "empresa": "dfchile", "activo": True},
    "15432100-K": {"rut": "15432100-K", "rut_fmt": "15.432.100-K", "nombre": "Carlos Rojas",
                   "cargo": "Supervisor","empresa": "dfchile","activo": True},
}

MARCAJES = []   # lista de registros recibidos

# Tipo marcaje según Defontana: 1=Entrada, 2=Salida, 3=Entrada Colación, 4=Salida Colación
TIPO_MAP = {
    "entrada": 1, "salida": 2,
    "colacion_entrada": 3, "colacion_salida": 4,
    "in": 1, "out": 2, "1": 1, "2": 2, "3": 3, "4": 4
}
TIPO_NOMBRE = {1: "Entrada", 2: "Salida", 3: "Entrada Colación", 4: "Salida Colación"}


def _clean_rut(rut: str) -> str:
    """Normaliza RUT: '12.345.678-9' → '12345678-9'"""
    return rut.replace(".", "").strip()


def _now_str():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ── Decorador de autenticación ────────────────────────────────────────────────
def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip()
        info  = TOKENS.get(token)
        if not info:
            return jsonify({"success": False, "message": "Token inválido o expirado",
                            "data": None}), 401
        if datetime.now() > info["expires"]:
            TOKENS.pop(token, None)
            return jsonify({"success": False, "message": "Token expirado",
                            "data": None}), 401
        request.token_info = info
        return f(*args, **kwargs)
    return decorated


# ── Autenticación ─────────────────────────────────────────────────────────────
@app.route("/api/Login/GetByCredentials", methods=["POST"])
def login():
    """
    POST /api/Login/GetByCredentials
    Body (form-encoded o JSON):
      username=usuario&password=clave&client=dfchile&company=dfchile

    Según docs, el token de acceso viene en authResult.access_token
    y puede haber múltiples empresas (jumpUsers).
    """
    # Acepta form-encoded o JSON (tal como documenta Defontana)
    if request.is_json:
        body = request.json or {}
    else:
        body = request.form.to_dict()

    username = body.get("username", "")
    password = body.get("password", "")
    client   = body.get("client", "dfchile")
    company  = body.get("company", "dfchile")

    if not username or not password:
        return jsonify({
            "success": False,
            "message": "Credenciales requeridas (username, password)",
            "jumpUsers": [], "authResult": None
        }), 400

    # Mock: invalida tokens anteriores del mismo usuario (como indica la doc)
    for tok in list(TOKENS.keys()):
        if TOKENS[tok]["user"] == username:
            del TOKENS[tok]

    token = str(uuid.uuid4()).replace("-", "")
    TOKENS[token] = {
        "user": username, "company": company,
        "expires": datetime.now() + timedelta(days=4)   # ~378604799s según docs
    }

    print(f"[Defontana Mock] ✓ Login: {username}@{company} → token={token[:16]}...")
    return jsonify({
        "success": True,
        "message": None,
        "jumpUsers": [{"client": client, "company": company,
                       "user": username, "service": "international"}],
        "authResult": {
            "success": True,
            "message": None,
            "access_token": token,
            "expires_in": 378604799,
            "token_type": "bearer"
        }
    })


# ── RRHH: Empleados ───────────────────────────────────────────────────────────
@app.route("/api/Employee/GetAll", methods=["GET"])
@require_token
def get_employees():
    """
    GET /api/Employee/GetAll
    Retorna nómina de empleados de la empresa.
    """
    company = request.headers.get("X-Company-Id", "")
    page      = int(request.args.get("page", 0))
    per_page  = int(request.args.get("itemsPerPage", 10))

    emps = [e for e in EMPLEADOS.values()
            if not company or e["empresa"] == company]

    return jsonify({
        "totalItems": len(emps),
        "page": page,
        "itemsPerPage": per_page,
        "items": emps[page * per_page: (page + 1) * per_page]
    })


@app.route("/api/Employee/GetByRut", methods=["GET"])
@require_token
def get_employee_by_rut():
    """GET /api/Employee/GetByRut?rut=12345678-9"""
    rut = _clean_rut(request.args.get("rut", ""))
    emp = EMPLEADOS.get(rut)
    if not emp:
        return jsonify({"success": False, "message": f"Empleado {rut} no encontrado",
                        "data": None}), 404
    return jsonify({"success": True, "message": None, "data": emp})


# ── RRHH: Marcajes de Asistencia ──────────────────────────────────────────────
@app.route("/api/Employee/AddAttendance", methods=["POST"])
@require_token
def add_attendance():
    """
    POST /api/Employee/AddAttendance
    Este es el endpoint que tu sistema SAS debe apuntar.

    Body esperado (mapeado con tu field_map):
    {
      "rutEmpleado":      "12.345.678-9",   ← viene de rut via field_map
      "tipoMarcaje":      1,                 ← 1=entrada 2=salida (viene de tipo via field_map)
      "fechaHoraMarcaje": "2025-06-24T08:05:00",
      "codigoEmpresa":    "dfchile",
      "origen":           "biometrico"
    }
    """
    body = request.json or {}

    rut_raw   = body.get("rutEmpleado", "") or body.get("rut", "")
    tipo_raw  = body.get("tipoMarcaje",  "") or body.get("tipo", "")
    fecha_str = body.get("fechaHoraMarcaje", "") or body.get("fecha_hora", "")
    empresa   = body.get("codigoEmpresa", request.headers.get("X-Company-Id", "dfchile"))

    # Normalizar RUT
    rut_clean = _clean_rut(str(rut_raw))

    # Validaciones
    if not rut_clean:
        return jsonify({"success": False, "message": "Campo 'rutEmpleado' requerido"}), 400
    if not fecha_str:
        return jsonify({"success": False, "message": "Campo 'fechaHoraMarcaje' requerido"}), 400

    # Convertir tipo
    if isinstance(tipo_raw, str):
        tipo_num = TIPO_MAP.get(tipo_raw.lower(), 1)
    else:
        tipo_num = int(tipo_raw) if tipo_raw else 1

    # Buscar empleado
    emp = EMPLEADOS.get(rut_clean)
    if not emp:
        # Defontana retorna error si el RUT no existe
        return jsonify({
            "success": False,
            "message": f"El RUT '{rut_raw}' no existe en la nómina de la empresa '{empresa}'",
            "data": None
        }), 422

    # Registrar marcaje
    marcaje = {
        "id":               len(MARCAJES) + 1,
        "rutEmpleado":      emp["rut_fmt"],
        "nombreEmpleado":   emp["nombre"],
        "tipoMarcaje":      tipo_num,
        "descripcionTipo":  TIPO_NOMBRE.get(tipo_num, "Desconocido"),
        "fechaHoraMarcaje": fecha_str,
        "codigoEmpresa":    empresa,
        "origen":           body.get("origen", "externo"),
        "fechaIngreso":     _now_str(),
    }
    MARCAJES.append(marcaje)

    print(f"[Defontana Mock] ✓ Marcaje registrado: "
          f"{emp['nombre']} ({emp['rut_fmt']}) → "
          f"{TIPO_NOMBRE.get(tipo_num)} — {fecha_str}")

    return jsonify({"success": True, "message": None, "data": marcaje})


@app.route("/api/Employee/GetAttendance", methods=["GET"])
@require_token
def get_attendance():
    """
    GET /api/Employee/GetAttendance?desde=2025-06-01&hasta=2025-06-30
    Retorna marcajes en un rango de fechas (formato UTC según docs).
    """
    desde    = request.args.get("desde", "")
    hasta    = request.args.get("hasta", "")
    page     = int(request.args.get("page", 0))
    per_page = int(request.args.get("itemsPerPage", 10))

    result = MARCAJES  # En prod filtraría por fecha

    return jsonify({
        "totalItems": len(result),
        "page": page,
        "itemsPerPage": per_page,
        "items": result[page * per_page: (page + 1) * per_page]
    })


# ── Auxiliares ────────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "mock": "Defontana ERP",
                    "swagger_real": "https://api.defontana.com/swagger/index.html",
                    "swagger_pruebas": "https://replapi.defontana.com/swagger/index.html",
                    "empleados": len(EMPLEADOS), "marcajes": len(MARCAJES)})

@app.route("/api/marcajes", methods=["GET"])
def ver_marcajes():
    """Endpoint extra para inspeccionar lo recibido durante pruebas."""
    return jsonify({"total": len(MARCAJES), "records": MARCAJES})


if __name__ == "__main__":
    print("=" * 60)
    print("  Mock ERP: Defontana")
    print("  Docs oficiales: https://defontana.atlassian.net/wiki/spaces/CDAV2/")
    print("  Swagger real:   https://api.defontana.com/swagger/index.html")
    print("  Corriendo en:   http://localhost:8002")
    print("=" * 60)
    print("\nFlujo de autenticación:")
    print("  1. POST /api/Login/GetByCredentials → obtener access_token")
    print("  2. Header: Authorization: Bearer <token>")
    print("\nEndpoints de asistencia:")
    print("  POST /api/Employee/AddAttendance    → registrar marcaje (← SAS apunta aquí)")
    print("  GET  /api/Employee/GetAttendance    → consultar marcajes")
    print("  GET  /api/Employee/GetAll           → nómina")
    print("  GET  /api/Employee/GetByRut?rut=... → buscar empleado")
    print("  GET  /api/marcajes                  → ver todos los marcajes recibidos")
    print("  GET  /health                        → estado del mock")
    print()
    print("  Field Map recomendado en SAS:")
    print('  {"tipo":"tipoMarcaje","rut":"rutEmpleado","fecha_hora":"fechaHoraMarcaje"}')
    print()
    app.run(port=8002, debug=True)
