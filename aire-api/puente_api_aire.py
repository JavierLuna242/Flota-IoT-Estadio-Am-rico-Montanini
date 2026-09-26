import asyncio
import json
import os
import datetime
import requests

from dotenv import load_dotenv
from azure.iot.device.aio import ProvisioningDeviceClient, IoTHubDeviceClient
from azure.iot.device import Message


# ============================================================
# CARGAR CREDENCIALES
# ============================================================

load_dotenv()

ID_SCOPE = os.getenv("ID_SCOPE")
DEVICE_ID = os.getenv("DEVICE_ID")
DEVICE_KEY = os.getenv("DEVICE_KEY")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:5000/ingest")

PROVISIONING_HOST = "global.azure-devices-provisioning.net"


# ============================================================
# API OPEN-METEO - BUCARAMANGA
# ============================================================

LATITUDE = 7.12
LONGITUDE = -73.12

API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


# ============================================================
# ENVIAR AL DASHBOARD LOCAL
# ============================================================

def enviar_a_dashboard(device_id, nombre, payload):
    try:
        requests.post(
            DASHBOARD_URL,
            json={"device_id": device_id, "device_name": nombre, "payload": payload},
            timeout=3
        )
    except Exception as e:
        print("No se pudo enviar al dashboard local:", e)


# ============================================================
# CALCULAR AQI APROXIMADO A PARTIR DE PM2.5
# ============================================================

def calcular_aqi(pm25):
    if pm25 <= 12:
        return round((50 / 12) * pm25)

    elif pm25 <= 35.4:
        return round(
            ((100 - 51) / (35.4 - 12.1))
            * (pm25 - 12.1) + 51
        )

    elif pm25 <= 55.4:
        return round(
            ((150 - 101) / (55.4 - 35.5))
            * (pm25 - 35.5) + 101
        )

    elif pm25 <= 150.4:
        return round(
            ((200 - 151) / (150.4 - 55.5))
            * (pm25 - 55.5) + 151
        )

    elif pm25 <= 250.4:
        return round(
            ((300 - 201) / (250.4 - 150.5))
            * (pm25 - 150.5) + 201
        )

    else:
        return 301


# ============================================================
# OBTENER DATOS DE OPEN-METEO
# ============================================================

def obtener_calidad_aire():

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "pm2_5,pm10",
        "timezone": "UTC",
        "forecast_days": 1
    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    tiempos = data["hourly"]["time"]
    valores_pm25 = data["hourly"]["pm2_5"]
    valores_pm10 = data["hourly"]["pm10"]

    # Buscar el último dato disponible que no sea None
    indice = None

    for i in range(len(tiempos) - 1, -1, -1):
        if valores_pm25[i] is not None and valores_pm10[i] is not None:
            indice = i
            break

    if indice is None:
        raise ValueError("Open-Meteo no devolvió datos válidos.")

    pm25 = valores_pm25[indice]
    pm10 = valores_pm10[indice]
    timestamp_fuente = tiempos[indice]

    return pm25, pm10, timestamp_fuente


# ============================================================
# CONECTAR CON AZURE IOT CENTRAL
# ============================================================

async def conectar_iot_central():

    if not ID_SCOPE or not DEVICE_ID or not DEVICE_KEY:
        raise ValueError(
            "Faltan ID_SCOPE, DEVICE_ID o DEVICE_KEY en el archivo .env"
        )

    print("Conectando con Azure IoT Central...")

    provisioning_client = ProvisioningDeviceClient.create_from_symmetric_key(
        provisioning_host=PROVISIONING_HOST,
        registration_id=DEVICE_ID,
        id_scope=ID_SCOPE,
        symmetric_key=DEVICE_KEY
    )

    registration_result = await provisioning_client.register()

    if registration_result.status != "assigned":
        raise RuntimeError(
            f"No se pudo aprovisionar el dispositivo: "
            f"{registration_result.status}"
        )

    hostname = registration_result.registration_state.assigned_hub

    print("Dispositivo aprovisionado correctamente.")
    print("IoT Hub:", hostname)

    device_client = IoTHubDeviceClient.create_from_symmetric_key(
        symmetric_key=DEVICE_KEY,
        hostname=hostname,
        device_id=DEVICE_ID
    )

    await device_client.connect()

    print("DEV-04 conectado a Azure IoT Central.")

    return device_client


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

async def main():

    device_client = None

    try:
        device_client = await conectar_iot_central()

        while True:

            try:
                pm25, pm10, timestamp_fuente = obtener_calidad_aire()

                aqi = calcular_aqi(pm25)

                timestamp_ingestion = (
                    datetime.datetime.now(datetime.timezone.utc)
                    .isoformat()
                )

                payload = {
                    "pm25": pm25,
                    "pm10": pm10,
                    "aqi": aqi,
                    "timestamp_fuente": timestamp_fuente,
                    "timestamp_ingestion": timestamp_ingestion
                }

                mensaje = Message(json.dumps(payload))
                mensaje.content_encoding = "utf-8"
                mensaje.content_type = "application/json"

                await device_client.send_message(mensaje)

                enviar_a_dashboard(DEVICE_ID, "Calidad de Aire Exterior", payload)

                print("\n====================================")
                print("Datos enviados a IoT Central")
                print("====================================")
                print("PM2.5:", pm25, "ug/m3")
                print("PM10 :", pm10, "ug/m3")
                print("AQI  :", aqi)
                print("Fuente:", timestamp_fuente)
                print("Ingesta:", timestamp_ingestion)
                print("====================================")

            except Exception as error:
                print("Error obteniendo/enviando datos:", error)

            print("\nEsperando 5 minutos...")
            await asyncio.sleep(300)

    except KeyboardInterrupt:
        print("\nPrograma detenido.")

    except Exception as error:
        print("\nERROR:", error)

    finally:
        if device_client:
            await device_client.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
