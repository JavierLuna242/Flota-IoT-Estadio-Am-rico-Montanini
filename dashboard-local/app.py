import sqlite3
import json
import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory

DB_PATH = os.path.join(os.path.dirname(__file__), "telemetria.db")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = Flask(__name__, static_folder=STATIC_DIR)


def obtener_conexion():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_db():
    conn = obtener_conexion()
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS telemetria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            device_name TEXT,
            payload_json TEXT NOT NULL,
            recibido_en TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_device_time ON telemetria(device_id, recibido_en)")
    conn.commit()
    conn.close()


@app.route("/ingest", methods=["POST"])
def ingest():
    data = request.get_json(force=True, silent=True)
    if not data or "device_id" not in data or "payload" not in data:
        return jsonify({"error": "Formato inválido, se requiere device_id y payload"}), 400

    device_id = data["device_id"]
    device_name = data.get("device_name", device_id)
    payload = data["payload"]
    recibido_en = datetime.now(timezone.utc).isoformat()

    conn = obtener_conexion()
    conn.execute(
        "INSERT INTO telemetria (device_id, device_name, payload_json, recibido_en) VALUES (?, ?, ?, ?)",
        (device_id, device_name, json.dumps(payload), recibido_en)
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"}), 201


@app.route("/api/devices", methods=["GET"])
def listar_dispositivos():
    conn = obtener_conexion()
    filas = conn.execute("""
        SELECT device_id, device_name, COUNT(*) as total,
               MAX(recibido_en) as ultimo_dato
        FROM telemetria
        GROUP BY device_id
        ORDER BY device_name
    """).fetchall()
    conn.close()
    return jsonify([dict(f) for f in filas])


@app.route("/api/data", methods=["GET"])
def obtener_datos():
    device_id = request.args.get("device_id")
    limite = int(request.args.get("limite", 300))

    conn = obtener_conexion()
    if device_id:
        filas = conn.execute(
            "SELECT * FROM telemetria WHERE device_id = ? ORDER BY recibido_en DESC LIMIT ?",
            (device_id, limite)
        ).fetchall()
    else:
        filas = conn.execute(
            "SELECT * FROM telemetria ORDER BY recibido_en DESC LIMIT ?",
            (limite,)
        ).fetchall()
    conn.close()

    resultado = []
    for f in filas:
        fila = dict(f)
        fila["payload"] = json.loads(fila["payload_json"])
        del fila["payload_json"]
        resultado.append(fila)

    resultado.reverse()
    return jsonify(resultado)


@app.route("/api/resumen", methods=["GET"])
def resumen():
    conn = obtener_conexion()
    total = conn.execute("SELECT COUNT(*) as c FROM telemetria").fetchone()["c"]
    dispositivos = conn.execute("SELECT COUNT(DISTINCT device_id) as c FROM telemetria").fetchone()["c"]
    conn.close()
    return jsonify({"total_mensajes": total, "dispositivos_activos": dispositivos})


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


if __name__ == "__main__":
    inicializar_db()
    app.run(host="0.0.0.0", port=5000)
