require('dotenv').config();
const http = require('http');
const { SymmetricKeySecurityClient } = require('azure-iot-security-symmetric-key');
const { ProvisioningDeviceClient } = require('azure-iot-provisioning-device');
const { Mqtt: ProvisioningTransport } = require('azure-iot-provisioning-device-mqtt');
const { Client, Message } = require('azure-iot-device');
const { Amqp } = require('azure-iot-device-amqp');

const idScope = process.env.ID_SCOPE;
const deviceId = process.env.DEVICE_ID;
const primaryKey = process.env.PRIMARY_KEY;
const dashboardUrl = process.env.DASHBOARD_URL || 'http://localhost:5000/ingest';

const INTERVAL_MS = 60 * 1000;

function generarLectura() {
  return {
    temp: +(18 + Math.random() * 12).toFixed(1),
    humedad: +(30 + Math.random() * 40).toFixed(1),
    iluminancia: Math.round(100 + Math.random() * 400),
  };
}

function enviarADashboard(deviceId, nombre, payload) {
  try {
    const url = new URL(dashboardUrl);
    const data = JSON.stringify({ device_id: deviceId, device_name: nombre, payload });

    const req = http.request({
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) },
    });

    req.on('error', (e) => console.warn('No se pudo enviar al dashboard local:', e.message));
    req.write(data);
    req.end();
  } catch (e) {
    console.warn('Error preparando envío al dashboard:', e.message);
  }
}

function provisionar() {
  return new Promise((resolve, reject) => {
    const securityClient = new SymmetricKeySecurityClient(deviceId, primaryKey);
    const provisioningClient = ProvisioningDeviceClient.create(
      'global.azure-devices-provisioning.net',
      idScope,
      new ProvisioningTransport(),
      securityClient
    );

    provisioningClient.register((err, result) => {
      if (err) return reject(err);
      resolve(result);
    });
  });
}

async function main() {
  console.log('Iniciando aprovisionamiento DPS...');
  const result = await provisionar();
  console.log('>> Hub asignado:', result.assignedHub);

  const connectionString =
    `HostName=${result.assignedHub};DeviceId=${result.deviceId};SharedAccessKey=${primaryKey}`;

  const client = Client.fromConnectionString(connectionString, Amqp);

  client.on('error', (err) => {
    console.error('Error del cliente:', err.message);
  });

  client.on('disconnect', async () => {
    console.log('Desconectado, reintentando en 5s...');
    setTimeout(() => {
      client.open().catch((e) => console.error('Fallo al reconectar:', e.message));
    }, 5000);
  });

  await client.open();
  console.log('>> Conectado a IoT Central por AMQP');

  setInterval(async () => {
    const lectura = generarLectura();
    const mensaje = new Message(JSON.stringify(lectura));
    mensaje.contentType = 'application/json';
    mensaje.contentEncoding = 'utf-8';

    try {
      await client.sendEvent(mensaje);
      console.log('Enviado (AMQP):', JSON.stringify(lectura));

      enviarADashboard(deviceId, 'Camerinos', lectura);
    } catch (err) {
      console.error('Error al enviar:', err.message);
    }
  }, INTERVAL_MS);
}

main().catch((err) => {
  console.error('Error fatal:', err);
  process.exit(1);
});
