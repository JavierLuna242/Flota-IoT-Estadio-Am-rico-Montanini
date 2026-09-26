import asyncio
import os
import csv
import json
import logging
import requests
from dotenv import load_dotenv
from azure.iot.device.aio import ProvisioningDeviceClient
from azure.iot.device.aio import IoTHubDeviceClient

load_dotenv()

logging.basicConfig(
    filename="iluminacion_replay.log",
    level=logging.INFO,
    format="%(asctime)s %(message)s"
)

ID_SCOPE = os.getenv("ID_SCOPE")
DEVICE_ID = os.getenv("DEVICE_ID")
PRIMARY_KEY = os.getenv("PRIMARY_KEY")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:5000/ingest")

CSV_PATH = "historico_iluminacion.csv"
INTERVAL_SECONDS = 60


def enviar_a_dashboard(device_id, nombre, payload):
    try:
        requests.post(
            DASHBOARD_URL,
            json={"device_id": device_id, "device_name": nombre, "payload": payload},
            timeout=3
        )
    except Exception as e:
        logging.warning(f"No se pudo enviar al dashboard local: {e}")


async def provisionar():
    provisioning_client = ProvisioningDeviceClient.create_from_symmetric_key(
        provisioning_host="global.azure-devices-provisioning.net",
        registration_id=DEVICE_ID,
        id_scope=ID_SCOPE,
        symmetric_key=PRIMARY_KEY,
    )
    resultado = await provisioning_client.register()
    return resultado.registration_state.assigned_hub


def leer_filas_csv():
    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


async def main():
    logging.info("Iniciando aprovisionamiento DPS...")
    hub = await provisionar()
    logging.info(f"Aprovisionado en hub: {hub}")
    print(f">> Hub asignado: {hub}")

    conn_str = (
        f"HostName={hub};"
        f"DeviceId={DEVICE_ID};"
        f"SharedAccessKey={PRIMARY_KEY}"
    )
    client = IoTHubDeviceClient.create_from_connection_string(conn_str)
    await client.connect()
    logging.info("Conectado a IoT Central")
    print(">> Conectado a IoT Central")

    filas = leer_filas_csv()
    if not filas:
        print("El CSV está vacío. Corre primero generar_historico.py")
        return

    try:
        while True:
            for fila in filas:
                payload = {
                    "lux": float(fila["lux"]),
                    "potencia": float(fila["potencia"]),
                    "estado_on_off": fila["estado"] == "1",
                }
                await client.send_message(json.dumps(payload))
                logging.info(f"Reproducido: {payload} (origen: {fila['timestamp']})")
                print(f"Reproducido: {payload}  [origen: {fila['timestamp']}]")

                enviar_a_dashboard(DEVICE_ID, "Iluminación Cancha", payload)

                await asyncio.sleep(INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logging.info("Deteniendo replay...")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
