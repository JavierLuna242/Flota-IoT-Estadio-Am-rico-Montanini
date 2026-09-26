#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include "mbedtls/base64.h"
#include "mbedtls/md.h"

const char *ssid = "Wokwi-GUEST";
const char *password = "";

const char *ID_SCOPE = "0ne010F6D57";
const char *DEVICE_ID = "1qbnxha79ua";
const char *PRIMARY_KEY = "EQVEEed+feA4EfFM1QjVAC0rSOpa5KL4AXfOrZC9Lwc=";

const char *DASHBOARD_URL = "http://57.156.61.152:5000/ingest";

#define TRIG_PIN 5
#define ECHO_PIN 18
#define SERVO_PIN 19
#define LED_PIN 2

Servo barrera;
bool barreraAbierta = false;

String assignedHub = "";
WiFiClientSecure espClient;
PubSubClient client(espClient);

String urlEncode(const String &s)
{
    String encoded = "";
    for (unsigned int i = 0; i < s.length(); i++)
    {
        char c = s.charAt(i);
        if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~')
        {
            encoded += c;
        }
        else
        {
            char buf[4];
            sprintf(buf, "%%%02X", (unsigned char)c);
            encoded += buf;
        }
    }
    return encoded;
}

String hmacSha256Base64(uint8_t *key, size_t keyLen, const String &msg)
{
    uint8_t hmacResult[32];
    mbedtls_md_context_t ctx;
    mbedtls_md_init(&ctx);
    mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
    mbedtls_md_hmac_starts(&ctx, key, keyLen);
    mbedtls_md_hmac_update(&ctx, (const unsigned char *)msg.c_str(), msg.length());
    mbedtls_md_hmac_finish(&ctx, hmacResult);
    mbedtls_md_free(&ctx);

    unsigned char b64out[64];
    size_t b64len;
    mbedtls_base64_encode(b64out, sizeof(b64out), &b64len, hmacResult, 32);
    b64out[b64len] = '\0';
    return String((char *)b64out);
}

String generarSasToken(const String &resourceUri, const char *key, unsigned long expirySeconds)
{
    uint8_t decodedKey[128];
    size_t decodedKeyLen;
    mbedtls_base64_decode(decodedKey, sizeof(decodedKey), &decodedKeyLen,
                          (const unsigned char *)key, strlen(key));

    unsigned long expiry = time(nullptr) + expirySeconds;
    String stringToSign = urlEncode(resourceUri) + "\n" + String(expiry);
    String signature = hmacSha256Base64(decodedKey, decodedKeyLen, stringToSign);

    return "SharedAccessSignature sr=" + urlEncode(resourceUri) +
           "&sig=" + urlEncode(signature) +
           "&se=" + String(expiry);
}

bool registrarDPS()
{
    String resourceUri = String(ID_SCOPE) + "/registrations/" + DEVICE_ID;
    String sasToken = generarSasToken(resourceUri, PRIMARY_KEY, 3600);

    WiFiClientSecure dpsClient;
    dpsClient.setInsecure();
    HTTPClient https;

    String url = "https://global.azure-devices-provisioning.net/" + String(ID_SCOPE) +
                 "/registrations/" + String(DEVICE_ID) + "/register?api-version=2021-06-01";

    https.begin(dpsClient, url);
    https.addHeader("Content-Type", "application/json");
    https.addHeader("Authorization", sasToken);

    String body = "{\"registrationId\":\"" + String(DEVICE_ID) + "\"}";
    int httpCode = https.PUT(body);

    if (httpCode != 202)
    {
        Serial.println("Error registro DPS, codigo: " + String(httpCode));
        Serial.println(https.getString());
        https.end();
        return false;
    }

    String resp = https.getString();
    https.end();

    StaticJsonDocument<512> doc;
    deserializeJson(doc, resp);
    String operationId = doc["operationId"].as<String>();

    for (int i = 0; i < 10; i++)
    {
        delay(2000);
        String pollUrl = "https://global.azure-devices-provisioning.net/" + String(ID_SCOPE) +
                         "/registrations/" + String(DEVICE_ID) +
                         "/operations/" + operationId + "?api-version=2021-06-01";

        HTTPClient poll;
        poll.begin(dpsClient, pollUrl);
        poll.addHeader("Authorization", sasToken);
        poll.GET();
        String pollResp = poll.getString();
        poll.end();

        StaticJsonDocument<512> pollDoc;
        deserializeJson(pollDoc, pollResp);
        String status = pollDoc["status"].as<String>();
        Serial.println("Estado DPS: " + status);

        if (status == "assigned")
        {
            assignedHub = pollDoc["registrationState"]["assignedHub"].as<String>();
            Serial.println(">> Hub asignado: " + assignedHub);
            return true;
        }
    }
    Serial.println("Timeout esperando asignacion DPS");
    return false;
}

void setup_wifi()
{
    Serial.print("Conectando a WiFi");
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED)
    {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi conectado");
}

void sincronizarHora()
{
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    Serial.print("Sincronizando hora");
    while (time(nullptr) < 100000)
    {
        delay(500);
        Serial.print(".");
    }
    Serial.println(" listo");
}

long medirDistanciaCM()
{
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);
    long duracion = pulseIn(ECHO_PIN, HIGH, 30000);
    return duracion * 0.034 / 2;
}

void enviarADashboard(const char *payloadJson)
{
    HTTPClient http;
    http.begin(DASHBOARD_URL);
    http.addHeader("Content-Type", "application/json");

    String body = String("{\"device_id\":\"") + DEVICE_ID +
                  "\",\"device_name\":\"Parqueadero\",\"payload\":" + payloadJson + "}";

    int code = http.POST(body);
    if (code > 0)
    {
        Serial.println("Dashboard local: OK (" + String(code) + ")");
    }
    else
    {
        Serial.println("Dashboard local: fallo al enviar");
    }
    http.end();
}

void callback(char *topic, byte *payload, unsigned int length)
{
    String msg;
    for (unsigned int i = 0; i < length; i++)
        msg += (char)payload[i];
    Serial.println("Comando recibido: " + msg);

    if (msg.indexOf("abrir_barrera") >= 0)
    {
        barrera.write(90);
        barreraAbierta = true;
        Serial.println(">> Barrera ABIERTA");
    }
    else if (msg.indexOf("cerrar_barrera") >= 0)
    {
        barrera.write(0);
        barreraAbierta = false;
        Serial.println(">> Barrera CERRADA");
    }
}

void reconnect()
{
    while (!client.connected())
    {
        Serial.println("Conectando a IoT Central (MQTT)...");
        digitalWrite(LED_PIN, LOW);

        String resourceUri = assignedHub + "/devices/" + DEVICE_ID;
        String sasToken = generarSasToken(resourceUri, PRIMARY_KEY, 3600);
        String username = assignedHub + "/" + DEVICE_ID + "/?api-version=2021-04-12";

        if (client.connect(DEVICE_ID, username.c_str(), sasToken.c_str()))
        {
            Serial.println(">> Conectado a IoT Central");
            digitalWrite(LED_PIN, HIGH);
            client.subscribe("$iothub/methods/POST/#");
        }
        else
        {
            Serial.print(">> Fallo rc=");
            Serial.print(client.state());
            Serial.println(" — reintentando en 5s");
            digitalWrite(LED_PIN, LOW);
            delay(5000);
        }
    }
}

void setup()
{
    Serial.begin(115200);
    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    barrera.attach(SERVO_PIN);
    barrera.write(0);

    setup_wifi();
    sincronizarHora();

    if (!registrarDPS())
    {
        Serial.println("No se pudo registrar en DPS, reiniciando en 5s...");
        delay(5000);
        ESP.restart();
    }

    espClient.setInsecure();
    client.setServer(assignedHub.c_str(), 8883);
    client.setBufferSize(512);
    client.setCallback(callback);
}

unsigned long lastMsg = 0;
const long interval = 30000;

void loop()
{
    if (!client.connected())
    {
        reconnect();
    }
    client.loop();

    unsigned long now = millis();
    if (now - lastMsg > interval)
    {
        lastMsg = now;

        long distancia = medirDistanciaCM();
        bool ocupado = distancia < 100;

        StaticJsonDocument<200> doc;
        doc["ocupacion"] = ocupado ? 1 : 0;
        doc["estado_puerta"] = barreraAbierta;

        char payload[200];
        serializeJson(doc, payload);

        String topic = "devices/" + String(DEVICE_ID) +
                       "/messages/events/%24.ct=application%2Fjson&%24.ce=utf-8";

        bool ok = client.publish(topic.c_str(), payload);

        Serial.print("Publicado: ");
        Serial.print(payload);
        Serial.println(ok ? " [OK]" : " [FALLO]");

        if (ok)
        {
            digitalWrite(LED_PIN, LOW);
            delay(100);
            digitalWrite(LED_PIN, HIGH);
            enviarADashboard(payload);
        }
    }
}