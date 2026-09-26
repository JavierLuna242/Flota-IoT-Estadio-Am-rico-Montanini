import asyncio
import os
import json
import time
import random
import hmac
import hashlib
import base64
import logging
import ssl
import requests
from urllib.parse import quote_plus
from dotenv import load_dotenv

import paho.mqtt.client as mqtt
from azure.iot.device.aio import ProvisioningDeviceClient

load_dotenv()

logging.basicConfig(
    filename="electrico_paho.log",
    level=logging.INFO,
    format="%(asctime)s %(message)s"
)

ID_SCOPE = os.getenv("ID_SCOPE")
DEVICE_ID = os.getenv("DEVICE_ID")
PRIMARY_KEY = os.getenv("PRIMARY_KEY")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:5000/ingest")

INTERVAL_SECONDS = 15
TOKEN_LIFETIME_SECONDS = 3600

estado_conectado = False


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


def generar_sas_token(resource_uri: str, key: str, expiry_seconds: int = TOKEN_LIFETIME_SECONDS) -> str:
    ttl = int(time.time() + expiry_seconds)
    sign_key = f"{quote_plus(resource_uri)}\n{ttl}"
    firma = base64.b64encode(
        hmac.new(base64.b64decode(key), sign_key.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")

    return (
        "SharedAccessSignature "
        f"sr={quote_plus(resource_uri)}"
        f"&sig={quote_plus(firma)}"
        f"&se={ttl}"
    )


def on_connect(client, userdata, flags, reason_code, properties=None):
    global estado_conectado
    codigo = reason_code if isinstance(reason_code, int) else reason_code.value
    if codigo == 0:
        estado_conectado = True
        logging.info("Conectado a IoT Central (MQTT explícito)")
        print(">> Conectado a IoT Central (MQTT explícito)")
    else:
        estado_conectado = False
        logging.error(f"Fallo de conexión, código: {codigo}")
        print(f">> Fallo de conexión, código: {codigo}")


def on_disconnect(client, userdata, *args):
    global estado_conectado
    estado_conectado = False
    logging.warning("Desconectado de IoT Central")
    print(">> Desconectado")


def on_publish(client, userdata, mid, *args):
    logging.info(f"Mensaje {mid} publicado correctamente")


def crear_cliente_mqtt(hostname: str, device_id: str, primary_key: str) -> mqtt.Client:
    resource_uri = f"{hostname}/devices/{device_id}"
    sas_token = generar_sas_token(resource_uri, primary_key)
    username = f"{hostname}/{device_id}/?api-version=2021-04-12"

    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(
            client_id=device_id,
            protocol=mqtt.MQTTv311,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
    else:
        client = mqtt.Client(client_id=device_id, protocol=mqtt.MQTTv311)

    client.username_pw_set(username=username, password=sas_token)
    client.tls_set(tls_version=ssl.PROTOCOL_TLSv1_2)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish

    client.connect(hostname, 8883, keepalive=60)
    client.loop_start()

    return client


def generar_lectura():
    return {
        "temp_tablero": round(random.uniform(20, 40), 1),
        "humedad": round(random.uniform(20, 60), 1),
        "estado_ups": random.choice(["normal", "normal", "normal", "alarma"]),
    }


def ejecutar(hostname: str):
    while True:
        try:
            client = crear_cliente_mqtt(hostname, DEVICE_ID, PRIMARY_KEY)
            inicio_token = time.time()

            topic = (
                f"devices/{DEVICE_ID}/messages/events/"
                "%24.ct=application%2Fjson&%24.ce=utf-8"
            )

            while time.time() - inicio_token < (TOKEN_LIFETIME_SECONDS - 300):
                if estado_conectado:
                    payload = generar_lectura()
                    cuerpo = json.dumps(payload)
                    resultado = client.publish(topic, cuerpo, qos=1)
                    resultado.wait_for_publish(timeout=5)

                    logging.info(f"Enviado (MQTT explícito): {cuerpo}")
                    print(f"Enviado: {cuerpo}")

                    enviar_a_dashboard(DEVICE_ID, "Cuarto Eléctrico / UPS", payload)
                else:
                    print("Esperando conexión...")

                time.sleep(INTERVAL_SECONDS)

            logging.info("Renovando token SAS y reconectando...")
            client.loop_stop()
            client.disconnect()

        except Exception as e:
            logging.error(f"Error de conexión MQTT: {e}")
            print(f"Error de conexión MQTT: {e} — reintentando en 10s")
            time.sleep(10)


async def main():
    logging.info("Iniciando aprovisionamiento DPS...")
    hub = await provisionar()
    logging.info(f"Aprovisionado en hub: {hub}")
    print(f">> Hub asignado: {hub}")

    ejecutar(hub)


if __name__ == "__main__":
    asyncio.run(main())
