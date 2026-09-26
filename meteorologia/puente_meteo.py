import asyncio
import os
import json
import datetime
import requests

from azure.iot.device.aio import ProvisioningDeviceClient
from azure.iot.device.aio import IoTHubDeviceClient
from dotenv import load_dotenv

# Cargar variables del archivo .env
load_dotenv()

ID_SCOPE = os.getenv("ID_SCOPE")
DEVICE_ID = os.getenv("DEVICE_ID")
PRIMARY_KEY = os.getenv("PRIMARY_KEY")
AZURE_MAPS_KEY = os.getenv("AZURE_MAPS_KEY")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:5000/ingest")

# Azure Maps Weather
WEATHER_URL = "https://atlas.microsoft.com/weather/currentConditions/json"

LATITUDE = 7.12
LONGITUDE = -73.12


def enviar_a_dashboard(device_id, nombre, payload):
    try:
        requests.post(
            DASHBOARD_URL,
            json={"device_id": device_id, "device_name": nombre, "payload": payload},
            timeout=3
        )
    except Exception as e:
        print("No se pudo enviar al dashboard local:", e)


async def provision():
    print("Conectando con Azure IoT Central...")

    provisioning_client = ProvisioningDeviceClient.create_from_symmetric_key(
        provisioning_host="global.azure-devices-provisioning.net",
        registration_id=DEVICE_ID,
        id_scope=ID_SCOPE,
        symmetric_key=PRIMARY_KEY,
    )

    result = await provisioning_client.register()

    if result.status != "assigned":
        raise RuntimeError(
            f"No se pudo aprovisionar el dispositivo: {result.status}"
        )

    print("Dispositivo aprovisionado correctamente.")
    print(f"IoT Hub: {result.registration_state.assigned_hub}")

    return result


def obtener_clima():
    params = {
        "api-version": "1.1",
        "query": f"{LATITUDE},{LONGITUDE}",
        "subscription-key": AZURE_MAPS_KEY
    }

    response = requests.get(
        WEATHER_URL,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    clima = data["results"][0]

    temp_ext = clima["temperature"]["value"]
    humedad = clima["relativeHumidity"]
    lluvia = clima["precipitationSummary"]["pastHour"]["value"]
    viento = clima["wind"]["speed"]["value"]

    timestamp_fuente = clima["dateTime"]
    timestamp_ingestion = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()

    return {
        "temp_ext": temp_ext,
        "humedad": humedad,
        "lluvia": lluvia,
        "viento": viento,
        "timestamp_fuente": timestamp_fuente,
        "timestamp_ingestion": timestamp_ingestion
    }


async def main():

    if not all([ID_SCOPE, DEVICE_ID, PRIMARY_KEY, AZURE_MAPS_KEY]):
        print("ERROR: Faltan variables en el archivo .env")
        return

    result = await provision()

    connection_string = (
        f"HostName={result.registration_state.assigned_hub};"
        f"DeviceId={result.registration_state.device_id};"
        f"SharedAccessKey={PRIMARY_KEY}"
    )

    client = IoTHubDeviceClient.create_from_connection_string(
        connection_string
    )

    await client.connect()

    print("DEV-05 conectado a Azure IoT Central.")

    try:
        while True:

            try:
                payload = obtener_clima()

                await client.send_message(
                    json.dumps(payload)
                )

                enviar_a_dashboard(DEVICE_ID, "Meteorología de Cubierta", payload)

                print("\n==================================")
                print("Datos meteorologicos enviados")
                print("==================================")
                print(f"Temperatura : {payload['temp_ext']} C")
                print(f"Humedad     : {payload['humedad']} %")
                print(f"Lluvia      : {payload['lluvia']} mm")
                print(f"Viento      : {payload['viento']} km/h")
                print(f"Fuente      : {payload['timestamp_fuente']}")
                print(f"Ingesta     : {payload['timestamp_ingestion']}")
                print("==================================")
                print("\nEsperando 5 minutos...")

            except Exception as e:
                print(f"Error obteniendo/enviando datos: {e}")

            await asyncio.sleep(300)

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
