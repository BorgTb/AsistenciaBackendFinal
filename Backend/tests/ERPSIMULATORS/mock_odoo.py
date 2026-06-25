from flask import Flask, request, jsonify, session
from datetime import datetime
import uuid

app = Flask(__name__)
app.secret_key = "odoo_mock_secret"

# ── Base de datos en memoria ──────────────────────────────────────────────────
EMPLOYEES = {
    1: {"id": 1, "name": "Juan Pérez",     "rut": "12.345.678-9", "job_title": "Operario", "active": True},
    2: {"id": 2, "name": "María González", "rut": "9.876.543-2",  "job_title": "Cajera",   "active": True},
    3: {"id": 3, "name": "Carlos Rojas",   "rut": "15.432.100-K", "job_title": "Supervisor","active": True},
}

ATTENDANCES = {}   # id → registro
SESSIONS    = {}   # session_token → uid

_next_att_id = 1


def _now():
    return datetime.utcnow().isoformat() + "Z"


def _require_session():
    """Verifica sesión activa. Retorna (uid, None) o (None, error_response)."""
    token = request.cookies.get("session_id") or request.json.get("session_id")
    uid   = SESSIONS.get(token)
    if not uid:
        return None, jsonify({
            "jsonrpc": "2.0", "id": None,
            "error": {"code": 100, "message": "Session expired or invalid",
                      "data": {"name": "SessionExpiredException"}}
        })
    return uid, None


# ── Autenticación ─────────────────────────────────────────────────────────────
@app.route("/web/session/authenticate", methods=["POST"])
def authenticate():
    """
    POST /web/session/authenticate
    Body: {"jsonrpc":"2.0","method":"call","params":{"db":"odoo_db","login":"admin","password":"admin"}}
    """
    data   = request.json or {}
    params = data.get("params", {})
    db     = params.get("db", "")
    login  = params.get("login", "")
    pwd    = params.get("password", "")

    # Mock: cualquier usuario/contraseña es válido
    if not login or not pwd:
        return jsonify({
            "jsonrpc": "2.0", "id": data.get("id"),
            "result": None,
            "error": {"code": 200, "message": "Login failed"}
        })

    uid   = 1
    token = str(uuid.uuid4())
    SESSIONS[token] = uid

    resp = jsonify({
        "jsonrpc": "2.0", "id": data.get("id"),
        "result": {
            "uid": uid,
            "session_id": token,
            "db": db,
            "username": login,
            "name": "Admin User",
            "partner_id": [3, "Admin User"],
        }
    })
    resp.set_cookie("session_id", token)
    print(f"[Odoo Mock] ✓ Autenticado: {login} → uid={uid}, token={token[:12]}...")
    return resp


# ── Endpoint principal JSON-RPC ───────────────────────────────────────────────
@app.route("/web/dataset/call_kw", methods=["POST"])
@app.route("/web/dataset/call_kw/<path:subpath>", methods=["POST"])
def call_kw(subpath=None):
    """
    POST /web/dataset/call_kw
    Body: {
      "jsonrpc": "2.0",
      "method":  "call",
      "params": {
        "model":  "hr.attendance",
        "method": "create",
        "args":   [{"employee_id": 1, "check_in": "2025-06-24T08:00:00Z"}],
        "kwargs": {}
      }
    }
    """
    global _next_att_id
    data   = request.json or {}
    params = data.get("params", {})
    model  = params.get("model", "")
    method = params.get("method", "")
    args   = params.get("args", [])
    kwargs = params.get("kwargs", {})

    print(f"[Odoo Mock] call_kw → model={model}, method={method}")

    # ── hr.employee ───────────────────────────────────────────────────────────
    if model == "hr.employee":
        if method in ("search_read", "read"):
            domain = args[0] if args else []
            fields = kwargs.get("fields", ["id", "name", "rut", "job_title"])
            result = [{k: v for k, v in emp.items() if k in fields}
                      for emp in EMPLOYEES.values() if emp["active"]]
            return _ok(data, result)

        if method == "search":
            # Buscar por rut si viene en el dominio
            domain = args[0] if args else []
            rut_filter = next((d[2] for d in domain if isinstance(d, list) and d[0] == "rut"), None)
            if rut_filter:
                ids = [e["id"] for e in EMPLOYEES.values() if e["rut"] == rut_filter]
            else:
                ids = list(EMPLOYEES.keys())
            return _ok(data, ids)

    # ── hr.attendance ─────────────────────────────────────────────────────────
    if model == "hr.attendance":
        if method == "create":
            record = args[0] if args else {}
            emp_id = record.get("employee_id")

            # Validaciones
            if emp_id not in EMPLOYEES:
                return _error(data, f"Employee with id={emp_id} not found")
            if not record.get("check_in"):
                return _error(data, "Field 'check_in' is required")

            new_id = _next_att_id
            _next_att_id += 1

            att = {
                "id":          new_id,
                "employee_id": [emp_id, EMPLOYEES[emp_id]["name"]],
                "check_in":    record["check_in"],
                "check_out":   record.get("check_out", False),
                "worked_hours":0.0,
                "write_date":  _now(),
            }
            ATTENDANCES[new_id] = att

            emp_name = EMPLOYEES[emp_id]["name"]
            print(f"[Odoo Mock] ✓ Attendance creada: id={new_id}, "
                  f"employee={emp_name}, check_in={record['check_in']}")
            return _ok(data, new_id)

        if method in ("search_read", "read"):
            fields = kwargs.get("fields", list(next(iter(ATTENDANCES.values()), {}).keys()))
            result = [{k: v for k, v in att.items() if not fields or k in fields}
                      for att in ATTENDANCES.values()]
            return _ok(data, result)

        if method == "write":
            ids    = args[0] if len(args) > 0 else []
            values = args[1] if len(args) > 1 else {}
            for att_id in ids:
                if att_id in ATTENDANCES:
                    ATTENDANCES[att_id].update(values)
                    print(f"[Odoo Mock] ✓ Attendance actualizada: id={att_id}")
            return _ok(data, True)

    return _error(data, f"Model '{model}' or method '{method}' not implemented in mock")


# ── Rutas auxiliares ──────────────────────────────────────────────────────────
@app.route("/web/dataset/call_kw/hr.attendance/create", methods=["POST"])
def call_kw_shortcut():
    """Alias con path explícito que algunos clientes usan."""
    return call_kw()


@app.route("/api/attendance", methods=["POST"])
def rest_attendance():
    """
    Endpoint REST simplificado para pruebas directas desde tu sistema SAS.
    Acepta el payload de tu sistema y lo convierte al formato Odoo internamente.

    Body esperado (viene de tu field_map):
    {
      "employee_rut":  "12.345.678-9",
      "check_type":    "entrada",
      "datetime":      "2025-06-24T08:05:00Z",
      "employee_name": "Juan Pérez"
    }
    """
    global _next_att_id
    body = request.json or {}

    rut        = body.get("employee_rut") or body.get("rut", "")
    check_type = body.get("check_type")   or body.get("tipo", "")
    dt         = body.get("datetime")     or body.get("fecha_hora", "")
    name       = body.get("employee_name") or body.get("nombre", "")

    # Buscar empleado por RUT
    emp = next((e for e in EMPLOYEES.values() if e["rut"] == rut), None)
    if not emp:
        return jsonify({"ok": False, "error": f"Empleado con RUT {rut} no encontrado"}), 404

    new_id = _next_att_id
    _next_att_id += 1

    att = {
        "id":          new_id,
        "employee_id": emp["id"],
        "employee_name": emp["name"],
        "check_in":    dt if check_type in ("entrada", "in") else False,
        "check_out":   dt if check_type in ("salida",  "out") else False,
        "write_date":  _now(),
    }
    ATTENDANCES[new_id] = att

    print(f"[Odoo Mock REST] ✓ Marcaje registrado: {emp['name']} — {check_type} — {dt}")
    return jsonify({"ok": True, "id": new_id, "employee": emp["name"],
                    "check_type": check_type, "datetime": dt})


@app.route("/api/attendances", methods=["GET"])
def list_attendances():
    """Ver todos los marcajes recibidos."""
    return jsonify({"count": len(ATTENDANCES), "records": list(ATTENDANCES.values())})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "mock": "Odoo HR", "version": "17.0",
                    "employees": len(EMPLOYEES), "attendances": len(ATTENDANCES)})


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ok(data, result):
    return jsonify({"jsonrpc": "2.0", "id": data.get("id"), "result": result})

def _error(data, msg, code=200):
    print(f"[Odoo Mock] ✗ Error: {msg}")
    return jsonify({
        "jsonrpc": "2.0", "id": data.get("id"),
        "error": {"code": code, "message": msg,
                  "data": {"name": "ValidationError", "debug": msg}}
    }), 400


if __name__ == "__main__":
    print("=" * 55)
    print("  Mock ERP: Odoo HR Attendance")
    print("  Docs reales: https://www.odoo.com/documentation/")
    print("  Corriendo en: http://localhost:8001")
    print("=" * 55)
    print("\nEndpoints disponibles:")
    print("  POST /web/session/authenticate  → Login")
    print("  POST /web/dataset/call_kw       → API JSON-RPC")
    print("  POST /api/attendance            → REST simplificado (para SAS)")
    print("  GET  /api/attendances           → Ver marcajes recibidos")
    print("  GET  /health                    → Estado del mock")
    print()
    app.run(port=8001, debug=True)
