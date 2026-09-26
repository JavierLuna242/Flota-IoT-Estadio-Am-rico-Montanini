import asyncio
import os
import json
import random
import datetime
import logging
import requests
from dotenv import load_dotenv

from azure.iot.device.aio import ProvisioningDeviceClient
from azure.iot.device.aio import IoTHubDeviceClient

load_dotenv()

logging.basicConfig(
    filename="concessions_rest.log",
    level=logging.INFO,
    format="%(asctime)s %(message)s"
)

ID_SCOPE = os.getenv("ID_SCOPE")
DEVICE_ID = os.getenv("DEVICE_ID")
PRIMARY_KEY = os.getenv("PRIMARY_KEY")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:5000/ingest")

INTERVAL_SECONDS = 300
CIUDAD = "Bucaramanga"


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


def consultar_wttr():
    url = f"https://wttr.in/{CIUDAD}?format=j1"
    respuesta = requests.get(url, timeout=10)
    respuesta.raise_for_status()
    datos = respuesta.json()

    condicion_actual = datos["current_condition"][0]
    humedad = float(condicion_actual["humidity"])
    timestamp_fuente = condicion_actual["localObsDateTime"]

    return humedad, timestamp_fuente


def generar_lectura_local():
    return {
        "temp_nevera": round(random.uniform(2, 8), 1),
        "estado_puerta": random.choice([True, False]),
    }


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

    try:
        while True:
            try:
                humedad, timestamp_fuente = consultar_wttr()
            except Exception as e:
                logging.warning(f"Fallo al consultar wttr.in: {e} — usando último valor plausible")
                humedad = round(random.uniform(40, 70), 1)
                timestamp_fuente = None

            local = generar_lectura_local()
            timestamp_ingestion = datetime.datetime.utcnow().isoformat()

            payload = {
                "temp_nevera": local["temp_nevera"],
                "estado_puerta": local["estado_puerta"],
                "humedad": humedad,
                "timestamp_fuente": timestamp_fuente,
                "timestamp_ingestion": timestamp_ingestion,
            }

            await client.send_message(json.dumps(payload))
            logging.info(f"Enviado: {payload}")
            print(f"Enviado: {payload}")

            enviar_a_dashboard(DEVICE_ID, "Hidratación / Concessions", payload)

            await asyncio.sleep(INTERVAL_SECONDS)

    except asyncio.CancelledError:
        logging.info("Deteniendo cliente...")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
