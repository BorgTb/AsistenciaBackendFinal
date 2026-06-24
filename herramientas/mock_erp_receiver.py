import json
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

received = []


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True)
    headers = dict(request.headers)

    record = {
        'id': len(received) + 1,
        'timestamp': datetime.now().isoformat(),
        'method': request.method,
        'headers': {k: v for k, v in headers.items()
                     if k.lower() not in ('authorization', 'cookie')},
        'payload': data,
        'source_ip': request.remote_addr,
    }
    received.append(record)

    print(f"\n{'='*60}")
    print(f"  ERP WEBHOOK #{record['id']} — {record['timestamp']}")
    print(f"{'='*60}")
    print(f"  Headers:")
    for k, v in record['headers'].items():
        print(f"    {k}: {v}")
    print(f"\n  Payload:")
    print(json.dumps(data, indent=4, ensure_ascii=False))
    print(f"{'='*60}\n")

    return jsonify({'ok': True, 'received_id': record['id']}), 200


@app.route('/webhook/<erp_type>', methods=['POST'])
def webhook_with_type(erp_type):
    return webhook()


@app.route('/admin', methods=['GET'])
def admin():
    return jsonify({
        'total': len(received),
        'recebidos': [
            {
                'id': r['id'],
                'timestamp': r['timestamp'],
                'payload': r['payload'],
            }
            for r in received[-20:]
        ]
    })


@app.route('/admin/clear', methods=['POST'])
def clear():
    received.clear()
    return jsonify({'ok': True, 'mensaje': 'Historial limpiado'})


if __name__ == '__main__':
    print(f"\n  Mock ERP Receiver corriendo en http://0.0.0.0:5050")
    print(f"  URL para probar: http://localhost:5050/webhook")
    print(f"  Admin: http://localhost:5050/admin")
    app.run(host='0.0.0.0', port=5050, debug=True)
