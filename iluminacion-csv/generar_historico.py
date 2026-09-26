import csv
from datetime import datetime, timedelta
import random

INICIO = datetime(2026, 9, 20, 15, 0, 0)  # tarde de un día de partido
DURACION_MINUTOS = 240                    # 4 horas de histórico
INTERVALO_SEGUNDOS = 60                   # mismo intervalo del catálogo

filas = []
tiempo = INICIO
minutos_transcurridos = 0

while minutos_transcurridos <= DURACION_MINUTOS:
    hora = tiempo.hour + tiempo.minute / 60
    encendido = hora >= 18.0 or hora < 0.5

    if encendido:
        lux = round(random.uniform(600, 900), 1)
        potencia = round(random.uniform(3.5, 4.8), 2)  # kW, rango operativo PZEM (0-5kW)
        estado = 1
    else:
        lux = round(random.uniform(0, 50), 1)
        potencia = 0.0
        estado = 0

    filas.append({
        "timestamp": tiempo.isoformat(),
        "lux": lux,
        "potencia": potencia,
        "estado": estado
    })

    tiempo += timedelta(seconds=INTERVALO_SEGUNDOS)
    minutos_transcurridos += INTERVALO_SEGUNDOS / 60

with open("historico_iluminacion.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["timestamp", "lux", "potencia", "estado"])
    writer.writeheader()
    writer.writerows(filas)

print(f"Generadas {len(filas)} filas en historico_iluminacion.csv")
