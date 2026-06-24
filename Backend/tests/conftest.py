import sys
import os
import time
import subprocess
from unittest.mock import MagicMock

# ------------------------------------------------------------
# 0. sys.path — permite imports como "from app import app"
# ------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ------------------------------------------------------------
# 1. Variables de entorno — ANTES de cualquier import del backend
# ------------------------------------------------------------
os.environ.update({
    'DATABASE_URL': 'postgresql://test:test@localhost:5433/test_db',
    'JWT_SECRET': 'test-jwt-secret-for-tests-only',
    'BIOMETRIC_KEY': 'test-biometric-key-32chars!!',
    'MQTT_HOST': 'localhost',
    'MQTT_PORT': '1883',
    'DISABLE_ASYNC_DISPATCH': '1',
})

# ------------------------------------------------------------
# 2. Mock deepface + cv2 — evita carga de modelos ML en imports
# ------------------------------------------------------------
_mock_deepface = MagicMock()
_mock_deepface.DeepFace.build_model.return_value = None
_mock_deepface.DeepFace.represent.return_value = [{'embedding': [0.1] * 128}]
sys.modules['deepface'] = _mock_deepface

_mock_cv2 = MagicMock()
_mock_cv2_laplacian = MagicMock()
_mock_cv2_laplacian.var.return_value = 120.0
_mock_cv2.Laplacian.return_value = _mock_cv2_laplacian
_mock_cv2.imread.return_value = MagicMock(shape=[640, 480, 3])
_mock_cv2.cvtColor.return_value = MagicMock()
_mock_cv2.CV_64F = 6
_mock_cv2.CV_8U = 0
_mock_cv2.COLOR_BGR2GRAY = 6
_mock_cv2.COLOR_BGR2RGB = 4
_mock_cv2.COLOR_GRAY2BGR = 8
_mock_cv2.IMREAD_GRAYSCALE = 0
_mock_cv2.IMREAD_COLOR = 1
_mock_cv2.meanStdDev.return_value = (MagicMock(), MagicMock())
sys.modules['cv2'] = _mock_cv2

# ------------------------------------------------------------
# 3. Fixtures
# ------------------------------------------------------------
import pytest
import psycopg2

COMPOSE_FILE = os.path.join(os.path.dirname(__file__), 'docker-compose.test.yml')
TEST_DB_URL = 'postgresql://test:test@localhost:5433/test_db'


def _docker_available():
    """Check if Docker is running."""
    try:
        result = subprocess.run(
            ['docker', 'info'], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.fixture(scope='session')
def postgres():
    """Start PostgreSQL Docker container for the entire test session."""
    if not _docker_available():
        pytest.skip("Docker no disponible — saltando tests de integracion")

    subprocess.run(
        ['docker', 'compose', '-f', COMPOSE_FILE, 'down', '-v'],
        check=False, capture_output=True
    )
    try:
        subprocess.run(
            ['docker', 'compose', '-f', COMPOSE_FILE, 'up', '-d'],
            check=True, capture_output=True, text=True, timeout=120
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pytest.skip("Docker compose fallo — saltando tests de integracion")

    for _ in range(40):
        try:
            conn = psycopg2.connect(TEST_DB_URL)
            conn.close()
            break
        except psycopg2.OperationalError:
            time.sleep(0.5)
    else:
        subprocess.run(
            ['docker', 'compose', '-f', COMPOSE_FILE, 'down', '-v'],
            check=False, capture_output=True
        )
        pytest.fail("PostgreSQL test no arranco en 20s")

    yield

    subprocess.run(
        ['docker', 'compose', '-f', COMPOSE_FILE, 'down', '-v'],
        check=False, capture_output=True
    )


@pytest.fixture(scope='session')
def _schema(postgres):
    """Create database schema once per session."""
    from app import app as flask_app
    with flask_app.app_context():
        from database import init_db
        init_db()


@pytest.fixture
def app(_schema):
    """Flask app with fresh database per test (truncate + re-seed)."""
    from app import app as flask_app
    from database import get_connection, init_db

    flask_app.config['TESTING'] = True

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        TRUNCATE TABLE
            encodings_faciales, logs_biometricos, eliminaciones_biometricas,
            consentimientos, asistencias, asignaciones, turnos,
            integraciones_erp, dispositivos, personas,
            usuario_empresa, usuarios_web, empresas,
            sincronizacion_log
        RESTART IDENTITY CASCADE
    """)
    conn.commit()
    cur.close()
    conn.close()

    with flask_app.app_context():
        init_db()

    yield flask_app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


# ------------------------------------------------------------
# 4. Auth tokens
# ------------------------------------------------------------
@pytest.fixture
def admin_token(client):
    """JWT for admin@empresa.cl / admin123."""
    resp = client.post('/api/auth/login', json={
        'email': 'admin@empresa.cl', 'password': 'admin123'
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['token']


@pytest.fixture
def empleador_token(client, admin_token):
    """JWT for empleador in empresa 2.
    
    Note: crear_empresa ahora acepta mode='new' con datos del usuario inline.
    """
    resp = client.post('/api/auth/empresas',
        headers={'Authorization': f'Bearer {admin_token}'},
        json={
            'nombre': 'Empresa Test',
            'rut_empresa': '11.111.111-1',
            'mode': 'new',
            'nombre_usuario': 'Empleador Test',
            'email_usuario': 'empleador@test.cl',
            'password_usuario': 'test1234',
            'rol_usuario': 'empleador'
        }
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    resp = client.post('/api/auth/login', json={
        'email': 'empleador@test.cl', 'password': 'test1234', 'empresa_id': 2
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['token']


@pytest.fixture
def trabajador_token(client, empleador_token):
    """JWT for trabajador (persona 1) in empresa 2."""
    client.post('/api/personas',
        headers={'Authorization': f'Bearer {empleador_token}'},
        json={'nombre': 'Trabajador Test', 'rut': '22.222.222-2', 'email': 'trab@test.cl'}
    )
    client.post('/api/auth/register',
        headers={'Authorization': f'Bearer {empleador_token}'},
        json={'nombre': 'Trabajador User', 'email': 'trabajador@test.cl',
              'password': 'test1234', 'rol': 'trabajador', 'empresa_id': 2}
    )
    resp = client.post('/api/auth/login', json={
        'email': 'trabajador@test.cl', 'password': 'test1234', 'empresa_id': 2
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['token']


# ------------------------------------------------------------
# 5. Mock fixtures (para usar con mocker dentro de tests)
# ------------------------------------------------------------
@pytest.fixture
def mock_deepface_repr(mocker):
    """Mock DeepFace.represent con embedding fijo."""
    import numpy as np
    mock = mocker.patch('deepface.DeepFace.represent')
    mock.return_value = [{'embedding': [0.1] * 128}]
    return mock


@pytest.fixture
def mock_requests_post(mocker):
    """Mock requests.post."""
    mock = mocker.patch('requests.post')
    mock.return_value.status_code = 200
    mock.return_value.text = '{"ok": true}'
    mock.return_value.json.return_value = {'ok': True}
    return mock


@pytest.fixture
def mock_requests_get(mocker):
    """Mock requests.get."""
    mock = mocker.patch('requests.get')
    mock.return_value.status_code = 200
    mock.return_value.json.return_value = {'ok': True, 'estado': 'activo'}
    mock.return_value.text = '{"ok": true}'
    return mock


@pytest.fixture
def mock_paho_client(mocker):
    """Mock paho.mqtt.client.Client."""
    mock_class = mocker.patch('mqtt_handler.mqtt.Client')
    instance = mock_class.return_value
    instance.connect.return_value = 0
    instance.loop_start.return_value = None
    instance.publish.return_value.return_value = 0
    return instance


@pytest.fixture(autouse=True)
def mock_thread(mocker):
    """Mock threading.Thread para no disparar threads reales.

    Es autouse para evitar que los hilos asincronos (push ERP / email) abran
    conexiones a la BD y provoquen deadlocks contra el TRUNCATE entre tests.
    """
    return mocker.patch('threading.Thread')


# ------------------------------------------------------------
# 6. Helper: crear persona con datos completos
# ------------------------------------------------------------
@pytest.fixture
def persona_factory(client):
    """Factory function: create a persona via API and return its ID."""
    def _create(nombre='Persona Test', rut='11.111.111-1',
                email='test@test.cl', token=None):
        headers = {}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        resp = client.post('/api/personas',
            headers=headers,
            json={'nombre': nombre, 'rut': rut, 'email': email}
        )
        if resp.status_code == 200:
            data = resp.get_json()
            return data.get('id', data.get('persona_id'))
        raise RuntimeError(f"Failed to create persona: {resp.get_data(as_text=True)}")
    return _create
