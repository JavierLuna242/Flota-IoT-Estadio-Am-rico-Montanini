# Flota IoT — Estadio Américo Montanini

**Parcial 1 · IoT + Cloud + Sistemas Distribuidos · 2026-II**
Universidad Autónoma de Bucaramanga (UNAB)

Escenario IoT completo sobre **Azure IoT Central**: una flota heterogénea de 10 dispositivos que simulan el monitoreo integral del Estadio Américo Montanini (cancha, graderías, accesos, camerinos, cuarto eléctrico, iluminación, parqueadero y zona de concessions), alimentada desde **7 orígenes de envío distintos** (Digital Twin nativo, Wokwi/ESP32, Python + Azure SDK, Node.js + AMQP, cliente MQTT explícito, replay de histórico y puentes HTTP/REST hacia APIs públicas).

---

## 📋 Tabla de contenido

- [Objetivo](#objetivo)
- [Escenario elegido](#escenario-elegido)
- [Catálogo de 10 dispositivos](#catálogo-de-10-dispositivos)
- [Datasheets de referencia](#datasheets-de-referencia)
- [Arquitectura de referencia](#arquitectura-de-referencia)
- [Mapa de zonas físicas](#mapa-de-zonas-físicas)
- [Infraestructura de despliegue](#infraestructura-de-despliegue)
- [Dashboard propio (Flask + SQLite)](#dashboard-propio-flask--sqlite)
- [Control room en IoT Central](#control-room-en-iot-central)
- [Ventana de 4 días no continuos](#ventana-de-4-días-no-continuos)
- [Decisiones técnicas y problemas resueltos](#decisiones-técnicas-y-problemas-resueltos)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Cómo correr un dispositivo localmente](#cómo-correr-un-dispositivo-localmente)
- [Créditos](#créditos)

---

## Objetivo

Diseñar, parametrizar y demostrar un escenario IoT completo sobre Azure IoT Central, cumpliendo:

- Digital Twin (Device Template) anclado a datasheets reales de sensores comerciales.
- 10 dispositivos con orígenes de envío heterogéneos (no todos simulados desde el mismo lugar).
- Asincronía visible (intervalos de muestreo distintos: 15 s, 30 s, 60 s, 5 min).
- Desconexión documentada y reconexión de al menos un dispositivo.
- Ventana de telemetría de 4 días no continuos.
- Diagrama de arquitectura con capa de telecomunicaciones.
- Dashboard tipo "cuarto de control" con identidad visual propia.
- Sustentación con dos códigos ejecutándose en vivo en dos equipos distintos.

## Escenario elegido

**Estadio Américo Montanini** — Sistema de monitoreo para cuarto de control en día de partido y en labores de mantenimiento, cubriendo confort, aforo y condiciones de juego.

Zonas cubiertas: cancha central, silletería norte, entrada/torniquete, calidad de aire exterior, meteorología de cubierta, camerinos, cuarto eléctrico/UPS, iluminación de cancha, acceso vehicular/parqueadero y zona de hidratación/concessions.

## Catálogo de 10 dispositivos

| ID | Zona / rol | Variables | Origen de envío | Protocolo / puerto | Intervalo |
|---|---|---|---|---|---|
| DEV-01 | Cancha central | Temp. césped, humedad de suelo, iluminancia | Digital Twin / simulador nativo de IoT Central | MQTT (nativo) | 60 s |
| DEV-02 | Silletería norte | Aforo estimado, temp. ambiente, CO₂ | Wokwi ESP32 (DPS embebido en el sketch) | MQTT / WiFi (Wokwi-GUEST), TLS 8883 | 15 s |
| DEV-03 | Entrada / torniquete | Flujo, estado de puerta, temp. | Python + SDK `azure-iot-device` | MQTT vía DPS, TLS 8883 | 30 s |
| DEV-04 | Calidad de aire exterior | PM2.5, PM10, AQI | Puente Python → API pública Open-Meteo Air Quality | HTTPS → MQTT | 5 min |
| DEV-05 | Meteorología de cubierta | Temp. ext., humedad, lluvia, viento | Puente Python → Azure Maps Weather API | HTTPS → MQTT | 5 min |
| DEV-06 | Camerinos | Temp., humedad, iluminancia | Node.js + `azure-iot-device-amqp` | **AMQP 1.0**, TLS 5671 | 60 s |
| DEV-07 | Cuarto eléctrico / UPS | Temp. tablero, humedad, estado UPS | Python + `paho-mqtt` (cliente MQTT explícito, sin SDK) | MQTT explícito, TLS 8883 | 15 s ⚠️ *dispositivo de la desconexión controlada* |
| DEV-08 | Iluminación de cancha | Lux, potencia, estado on/off | Replay de CSV histórico (Python + SDK) | MQTT vía DPS | 60 s |
| DEV-09 | Acceso vehicular / parqueadero | Ocupación, estado de barrera | Wokwi ESP32 (DPS embebido, comando `abrir_barrera`) | MQTT / WiFi (Wokwi-GUEST), TLS 8883 | 30 s |
| DEV-10 | Hidratación / concessions | Temp. nevera, estado de puerta, humedad | Puente Python → API pública wttr.in | HTTPS → MQTT | 5 min |

**Heterogeneidad de orígenes:** simulador nativo, firmware ESP32 real (Wokwi), SDK oficial de Microsoft en dos lenguajes (Python y Node.js), protocolo MQTT explícito sin SDK, protocolo AMQP 1.0 puro, replay de histórico y dos puentes contra APIs públicas de dominios distintos (calidad de aire, clima).

## Datasheets de referencia

Cada variable de telemetría está anclada a un sensor comercial real, con su rango de fabricante y el rango operativo usado en el escenario:

| Sensor | Variable | Rango fabricante | Precisión | Rango operativo |
|---|---|---|---|---|
| DS18B20 | Temperatura (suelo / nevera / tablero) | -55 a 125 °C | ±0.5 °C | -5 a 45 °C |
| DHT22 / AM2302 | Temp. / humedad ambiente | -40–80 °C · 0–100 %HR | ±0.5 °C / ±2 %HR | 5–35 °C · 30–95 %HR |
| BME280 | Temp. / humedad / presión | -40–85 °C · 0–100 %HR · 300–1100 hPa | ±3 %HR / ±1 hPa | igual a fabricante |
| BH1750 | Iluminancia | 1–65 535 lux | ±20 % | 0–100 000 lux |
| HC-SR04 | Distancia / ocupación | 2–400 cm | ±0.3 cm | 5–300 cm |
| MH-Z19B | CO₂ | 400–10 000 ppm | ±(50 ppm + 3 %) | 400–2000 ppm |
| PMS5003 | PM2.5 / PM10 | 0–500 µg/m³ | ±10 µg/m³ | 0–150 µg/m³ |
| Sensor capacitivo de humedad de suelo v1.2 | Humedad de suelo | 0–100 % (analógico) | calibración manual | 0–60 % |
| PZEM-004T | Potencia / corriente | 0–22 kW / 0–100 A | ±0.5 % | 0–5 kW |
| Pluviómetro de cangilón | Lluvia | 0.2 mm/tip | ±2 % | 0–50 mm/h |
| Anemómetro de copas | Viento | 6.5–128 km/h | — | 0–60 km/h |
| Reed switch / Hall | Puertas / barreras | Binario | — | abierto/cerrado |

## Arquitectura de referencia

Diagrama de 4 capas (dispositivo → red → plataforma → operación), con los 10 orígenes coloreados por protocolo para visualizar la heterogeneidad de un vistazo.

📎 `diagrama_arquitectura_estadio.svg`

- **Capa de dispositivo:** los 10 orígenes agrupados por tecnología.
- **Capa de red:** WiFi Wokwi-GUEST, TLS 8883 (MQTT), TLS 5671 (AMQP), HTTPS (APIs externas).
- **Capa de plataforma:** DPS (Device Provisioning Service), IoT Central (Device Templates / Digital Twin), IoT Hub subyacente.
- **Capa de operación:** Views por dispositivo, Rules y alertas, Control Room de IoT Central, dashboard propio en Flask.

## Mapa de zonas físicas

Plano 2D del estadio (basado en el plano real de referencia) con los 10 dispositivos ubicados en su zona física correspondiente, coloreados con la misma paleta del diagrama de arquitectura.

📎 `mapa_zonas_estadio.svg`

## Infraestructura de despliegue

- **Servidor:** máquina virtual Debian 12 en Azure, corriendo todos los orígenes basados en Python/Node.js como servicios `systemd` (arranque automático, reinicio ante fallos, logs vía `journalctl`).
- **Wokwi (DEV-02, DEV-09):** desarrollados y compilados **localmente** con PlatformIO + la extensión Wokwi para VS Code, para evitar los timeouts de compilación del simulador web. El aprovisionamiento DPS (generación de token SAS vía HMAC-SHA256) está embebido directamente en el firmware del ESP32, sin depender de ningún script externo.
- **Servicios systemd activos:**

  | Servicio | Dispositivo |
  |---|---|
  | `entrada-torniquete.service` | DEV-03 |
  | `dev04-aire.service` | DEV-04 |
  | `dev05-meteo.service` | DEV-05 |
  | `camerinos-amqp.service` | DEV-06 (Node.js) |
  | `electrico-paho.service` | DEV-07 |
  | `iluminacion-replay.service` | DEV-08 |
  | `concessions-rest.service` | DEV-10 |
  | `dashboard-telemetria.service` | Dashboard propio (Gunicorn) |

## Dashboard propio (Flask + SQLite)

Panel adicional (no exigido por el enunciado, pero construido para reforzar la evidencia de la flota) que centraliza toda la telemetría de los 10 orígenes en una base SQLite local, con una interfaz minimalista en tonos pastel:

- Endpoint `/ingest` — recibe telemetría de cada script/sketch además del envío a IoT Central.
- Endpoints `/api/devices`, `/api/data`, `/api/resumen` — consulta y agregación.
- Interfaz web con chips por dispositivo, gráfico de líneas (Chart.js), tabla de últimas lecturas y un panel de "Recursos gráficos" con el mapa de zonas del estadio.
- Corre 24/7 vía Gunicorn + systemd, expuesto en el puerto 5000.

## Control room en IoT Central

Dashboard de aplicación personalizado ("Estadio Américo Montanini — Control Room"), con:

- Logo y nombre del escenario (no el nombre genérico de Azure).
- Estado de conectividad por template (9 grupos de dispositivos — IoT Central solo permite un template por grupo, así que la flota heterogénea se visualiza en mini-tiles por tipo de origen).
- Gráficos de telemetría de cancha, silletería, entrada y camerinos (variables indispensables del escenario).
- KPIs de último valor y máximo/mínimo del día.
- Bloque de Rules activas (alta temperatura, CO₂ alto, calidad de aire, falla eléctrica/UPS, desconexión).
- Tile de imagen con el mapa de zonas del estadio.

## Ventana de 4 días no continuos

Telemetría capturada en 4 fechas no consecutivas, con evidencia de:

- **Asincronía:** 4 intervalos de muestreo distintos conviviendo en la misma flota (15 s / 30 s / 60 s / 5 min).
- **Desconexión y reconexión:** ciclo controlado sobre DEV-07 (Cuarto Eléctrico/UPS), documentado con capturas de estado *Connected → Disconnected → Connected* y el hueco correspondiente en la serie de datos.
- **Estadísticas por variable:** máximo, mínimo, promedio, recuento y sumatoria calculados sobre la ventana completa (`calcular_estadisticas.py` sobre la base SQLite del dashboard propio; para DEV-01 se calcularon manualmente a partir de las capturas de "Datos sin procesar" de IoT Central como verificación cruzada).

## Decisiones técnicas y problemas resueltos

Bitácora de los principales obstáculos encontrados durante el desarrollo y cómo se resolvieron (relevante para la sustentación):

- **AMQP en Python no es soportado por el SDK oficial.** `azure-iot-device` solo implementa MQTT para telemetría de dispositivo. Se intentó `python-qpid-proton` para AMQP puro, pero falló por problemas de compilación de SSL contra OpenSSL 3.x en Debian 12. Se resolvió migrando DEV-06 a **Node.js + `azure-iot-device-amqp`**, que sí expone AMQP de forma nativa y mantenida.
- **`PubSubClient` (Wokwi/ESP32) truncaba los mensajes.** El buffer por defecto (128 bytes) era insuficiente para el topic + payload JSON. Se corrigió con `setBufferSize(512)` y agregando las propiedades de sistema `$.ct`/`$.ce` al topic para que IoT Central mapeara correctamente la telemetría a las capabilities del template.
- **`paho-mqtt` con versiones distintas entre entornos.** El script de DEV-07 se hizo compatible con `paho-mqtt` 1.x y 2.x detectando en tiempo de ejecución si existe `CallbackAPIVersion`.
- **Device Groups de IoT Central están limitados a un solo Device Template por grupo.** No es posible crear un único grupo con los 10 templates distintos de la flota; se optó por 9 grupos (uno por template, ya que dos dispositivos comparten el template "Acceso / Torniquete").
- **Compilación web de Wokwi con timeouts frecuentes.** Se migró el desarrollo de los sketches ESP32 a VS Code + PlatformIO + extensión Wokwi, reduciendo el tiempo de compilación de minutos a segundos tras la primera build.

## Estructura del repositorio

> ⚠️ Ajusta esta sección si tus carpetas reales tienen otros nombres — está basada en los módulos que se construyeron durante el desarrollo, no en una verificación directa del árbol de archivos subido.

```
.
├── README.md
├── diagrama_arquitectura_estadio.svg        # Diagrama de 4 capas (arquitectura de referencia)
├── mapa_zonas_estadio.svg                   # Plano 2D del estadio con los 10 dispositivos
├── dashboard-local/                         # Dashboard propio (Flask + SQLite)
│   ├── app.py
│   ├── telemetria.db
│   ├── calcular_estadisticas.py
│   └── static/
│       ├── index.html
│       └── mapa_estadio.svg
├── entrada-torniquete/                      # DEV-03
│   └── entrada_torniquete.py
├── dev04-aire/                              # DEV-04
│   └── puente_api_aire.py
├── dev05-meteo/                             # DEV-05
│   └── puente_meteo.py
├── camerinos-amqp-node/                     # DEV-06
│   └── index.js
├── electrico-paho/                          # DEV-07
│   └── electrico_paho.py
├── iluminacion-csv/                         # DEV-08
│   ├── generar_historico.py
│   ├── historico_iluminacion.csv
│   └── iluminacion_replay.py
├── concessions-rest/                        # DEV-10
│   └── concessions_rest.py
├── estadio-silleteria-02/                   # DEV-02 (Wokwi, PlatformIO)
│   ├── platformio.ini
│   ├── wokwi.toml
│   ├── diagram.json
│   └── src/main.cpp
└── estadio-parking-09/                      # DEV-09 (Wokwi, PlatformIO)
    ├── platformio.ini
    ├── wokwi.toml
    ├── diagram.json
    └── src/main.cpp
```

## Cómo correr un dispositivo localmente

**Scripts Python** (DEV-03, DEV-04, DEV-05, DEV-07, DEV-08, DEV-10):

```bash
cd <carpeta-del-dispositivo>
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt   # o instalar manualmente: azure-iot-device, requests, python-dotenv, paho-mqtt según el script
cp .env.example .env    # completar ID_SCOPE, DEVICE_ID y PRIMARY_KEY desde IoT Central → Devices → Connect
python3 <script>.py
```

**Node.js** (DEV-06):

```bash
cd camerinos-amqp-node
npm install
cp .env.example .env
node index.js
```

**Wokwi / ESP32** (DEV-02, DEV-09):

```bash
cd estadio-silleteria-02   # o estadio-parking-09
pio run                     # compila (primera vez descarga el toolchain de ESP32)
# F1 → "Wokwi: Start Simulator" dentro de VS Code
```

Ninguna credencial real queda en el código: todas se cargan desde variables de entorno (`.env`), excluidas del control de versiones vía `.gitignore`.

## Créditos

Proyecto desarrollado para el curso **IoT + Cloud + Sistemas Distribuidos**, Parcial 1 (2026-II), Universidad Autónoma de Bucaramanga.

Documentación de Azure IoT Central: https://learn.microsoft.com/azure/iot-central/
