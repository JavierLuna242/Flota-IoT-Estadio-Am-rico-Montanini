import asyncio
import os
import random
import json
import logging
import requests
from azure.iot.device.aio import ProvisioningDeviceClient
from azure.iot.device.aio import IoTHubDeviceClient
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    filename="entrada_torniquete.log",
    level=logging.INFO,
    format="%(asctime)s %(message)s"
)

ID_SCOPE = os.getenv("ID_SCOPE")
DEVICE_ID = os.getenv("DEVICE_ID")
PRIMARY_KEY = os.getenv("PRIMARY_KEY")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:5000/ingest")


def enviar_a_dashboard(device_id, nombre, payload):
    try:
        requests.post(
            DASHBOARD_URL,
            json={"device_id": device_id, "device_name": nombre, "payload": payload},
            timeout=3
        )
    except Exception as e:
        logging.warning(f"No se pudo enviar al dashboard local: {e}")


async def provision():
    provisioning_client = ProvisioningDeviceClient.create_from_symmetric_key(
        provisioning_host="global.azure-devices-provisioning.net",
        registration_id=DEVICE_ID,
        id_scope=ID_SCOPE,
        symmetric_key=PRIMARY_KEY,
    )
    return await provisioning_client.register()


async def main():
    result = await provision()
    conn_str = (
        f"HostName={result.registration_state.assigned_hub};"
        f"DeviceId={result.registration_state.device_id};"
        f"SharedAccessKey={PRIMARY_KEY}"
    )
    client = IoTHubDeviceClient.create_from_connection_string(conn_str)
    await client.connect()
    print("Conectado a IoT Central")

    while True:
        payload = {
            "flujo": random.randint(0, 15),
            "estado_puerta": random.choice([True, False]),
            "temp": round(random.uniform(18, 28), 1)
        }
        await client.send_message(json.dumps(payload))
        print("Enviado:", payload)

        enviar_a_dashboard(DEVICE_ID, "Entrada / Torniquete", payload)

        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
