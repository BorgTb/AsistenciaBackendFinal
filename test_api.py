"""
Script de ejemplo para probar la API de gestión de turnos
"""
import requests
import json

API_URL = "http://localhost:5000/api"

def print_response(title, response):
    """Imprime la respuesta de la API de forma legible"""
    print(f"\n{'='*60}")
    print(f"🔷 {title}")
    print(f"{'='*60}")
    print(f"Status Code: {response.status_code}")
    print(f"Response:")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    print()

def test_api():
    """Prueba todos los endpoints de la API"""
    
    print("🚀 Iniciando pruebas de API...")
    
    # 1. Health Check
    try:
        response = requests.get(f"{API_URL}/health")
        print_response("Health Check", response)
    except Exception as e:
        print(f"❌ Error en health check: {e}\n")
        return
    
    # 2. Obtener todas las personas
    try:
        response = requests.get(f"{API_URL}/personas")
        print_response("Listado de Personas", response)
    except Exception as e:
        print(f"❌ Error obteniendo personas: {e}\n")
    
    # 3. Obtener todos los turnos
    try:
        response = requests.get(f"{API_URL}/turnos")
        print_response("Listado de Turnos", response)
    except Exception as e:
        print(f"❌ Error obteniendo turnos: {e}\n")
    
    # 4. Obtener todas las asignaciones
    try:
        response = requests.get(f"{API_URL}/asignaciones")
        print_response("Listado de Asignaciones", response)
    except Exception as e:
        print(f"❌ Error obteniendo asignaciones: {e}\n")
    
    # 5. Crear un nuevo turno
    try:
        nuevo_turno = {
            "nombre_turno": "Fin de Semana",
            "hora_inicio": "09:00",
            "hora_fin": "18:00",
            "dias_semana": "S,D"
        }
        response = requests.post(f"{API_URL}/turnos", json=nuevo_turno)
        print_response("Crear Nuevo Turno", response)
    except Exception as e:
        print(f"❌ Error creando turno: {e}\n")
    
    # 6. Asignar turno (ejemplo - requiere que existan personas y turnos)
    try:
        # Primero obtener una persona y un turno disponibles
        personas = requests.get(f"{API_URL}/personas").json()
        turnos = requests.get(f"{API_URL}/turnos").json()
        
        if personas.get('total', 0) > 0 and turnos.get('total', 0) > 0:
            asignacion = {
                "persona_id": personas['personas'][0]['id'],
                "turno_id": turnos['turnos'][0]['id']
            }
            response = requests.post(f"{API_URL}/asignaciones", json=asignacion)
            print_response("Asignar Turno a Persona", response)
        else:
            print("\n⚠️ No hay personas o turnos disponibles para asignar")
    except Exception as e:
        print(f"❌ Error asignando turno: {e}\n")
    
    # 7. Obtener detalle de una persona específica
    try:
        personas = requests.get(f"{API_URL}/personas").json()
        if personas.get('total', 0) > 0:
            persona_id = personas['personas'][0]['id']
            response = requests.get(f"{API_URL}/personas/{persona_id}")
            print_response(f"Detalle de Persona ID {persona_id}", response)
        else:
            print("\n⚠️ No hay personas registradas para obtener detalles")
    except Exception as e:
        print(f"❌ Error obteniendo detalle: {e}\n")
    
    print("\n✅ Pruebas completadas!")

if __name__ == "__main__":
    test_api()
