# KUKA-ARM – 5-DOF Roboterarm mit Raspberry Pi

Ein vollständig funktionsfähiger Roboterarm-Controller basierend auf einem 3D-gedruckten 5-DOF-Arm. Das System nutzt einen Raspberry Pi, einen PCA9685 16-Kanal PWM-Treiber und handelsübliche Servo-Motoren für eine Web-basierte Steuerung mit 3D-Visualisierung.

## 📋 Inhaltsverzeichnis

1. [Hardware-Übersicht](#hardware-übersicht)
2. [Servo-Spezifikationen](#servo-spezifikationen)
3. [Netzteil-Dimensionierung](#netzteil-dimensionierung)
4. [Verdrahtungsanleitung](#verdrahtungsanleitung)
5. [Installation](#installation)
6. [Inbetriebnahme](#inbetriebnahme)
7. [Fehlerbehebung](#fehlerbehebung)
8. [Sicherheit](#sicherheit)

---

## Hardware-Übersicht

### Komponenten

| Komponente | Typ/Modell | Funktion | Bemerkung |
|---|---|---|---|
| **Raspberry Pi** | 4B oder neuer | Kontrolle + Web-Server | 2GB RAM mindestens |
| **PCA9685** | 16-Kanal PWM Treiber | Servo-PWM-Erzeugung | I²C-gesteuert |
| **J1 (Basis)** | Metal MG996R | Basis-Rotation | 1A @ 6V, 500-2500µs |
| **J2 (Schulter)** | MG996R | Schulter-Hebung | 0.8A @ 6V, 500-2500µs |
| **J3 (Ellbogen)** | MG90S | Ellbogen-Bewegung | 0.3A @ 5V, 600-2400µs |
| **J4 (Handgelenk Pitch)** | MG90S | Handgelenk-Neigung | 0.3A @ 5V, 600-2400µs |
| **J5 (Handgelenk Roll)** | MG90S | Handgelenk-Rotation | 0.3A @ 5V, 600-2400µs |
| **Stromversorgung** | 5-6V, min. 3.5A | Externe Versorgung | NICHT vom Pi! |

### Anforderungen

- **Stromversorgung**: Externe 5-6V Gleichspannungsquelle mit mindestens **3.5A** Leistung
- **Netzwerk**: WiFi oder LAN (für Web-Zugriff)
- **Python**: 3.8 oder neuer

---

## Servo-Spezifikationen

### Pulse-Breiten-Übersicht

Die Servosteuerung erfolgt über PWM-Signale bei 50 Hz. Jeder Servo-Typ hat unterschiedliche Pulse-Breiten für 0° und 180°:

| Servo-Typ | 0° (Min) | 90° (Mittel) | 180° (Max) | Sicherheit | Notizen |
|---|---|---|---|---|---|
| **Metal MG996R** | 500µs | 1500µs | 2500µs | ±10µs | Robust, höheres Drehmoment |
| **MG996R** | 500µs | 1500µs | 2500µs | ±10µs | Standard-Servo |
| **MG90S** | 600µs | 1500µs | 2400µs | ±20µs | Konservativ: verhindert Beschädigungen |

**Wichtig**: MG90S-Servos verwenden engere Pulse-Breiten (600-2400µs statt 500-2500µs) zum Schutz vor Beschädigung bei falscher Steuerung.

### Winkelbereich je Gelenk

| Gelenk | Min | Mittel (Home) | Max | Grund |
|---|---|---|---|---|
| **J1 Basis** | 0° | 90° | 180° | Vollständige Rotation |
| **J2 Schulter** | 30° | 90° | 150° | Mechanische Limits |
| **J3 Ellbogen** | 0° | 90° | 160° | Arbeitsraum |
| **J4 Pitch** | 0° | 90° | 180° | Greifer-Neigung |
| **J5 Roll** | 0° | 90° | 180° | Greifer-Rotation |

---

## Netzteil-Dimensionierung

### Stromberechnung

Die Gesamtleistung ist die Summe aller Servo-Stromaufnahmen **im worst-case** (alle Servos gleichzeitig unter Last):

```
J1 (Metal MG996R) @ 6V:       1.0A
J2 (MG996R)       @ 6V:       0.8A
J3 (MG90S)        @ 5V:       0.3A
J4 (MG90S)        @ 5V:       0.3A
J5 (MG90S)        @ 5V:       0.3A
─────────────────────────────────
Gesamt:                       2.7A @ avg

Mit Reserve (15%):            3.1A
Mit Sicherheitspuffer:        3.5A empfohlen
```

**Empfehlung**: Mindestens **3.5A @ 5-6V** externe Stromversorgung

### Netzteil-Auswahl

- **Zu wenig Strom** → Servos zittern, reagieren langsam oder frieren ein
- **Zu viel Strom** → keine Probleme (modernes Netzteil regelt runter)
- **Falsche Spannung** → Servos beschädigt

**Gute Optionen**:
- Mean Well LRS-50-5 (5V, 10A) – robust, industriell
- Meanwell GSM90A05 (5V, 18A) – overkill, aber sicher
- USB-C Power Delivery 5V/3A+ (einfach zu beschaffen)
- Alte Laptop-Netzteile (bei Kompatibilität überprüfen)

### Stromanschluss

```
┌─────────────────────────────────────────────┐
│  Externe Stromversorgung (5-6V, 3.5A+)     │
└──────┬──────────────────────────┬───────────┘
       │                          │
       │ (Red +)                 │ (Black -)
       └────┬─────────────────────┴────┐
            │                          │
     ┌──────▼────────────────────────▼─┐
     │  PCA9685 Schraubklemmen        │
     │  V+: Rot vom Netzteil          │
     │  GND: Schwarz vom Netzteil     │
     └────┬─────────────────────────┬──┘
          │                         │
     (Intern an alle Servos)   (GND gemeinsam mit Pi)
```

---

## Verdrahtungsanleitung

### 1. Raspberry Pi ↔ PCA9685 (I²C-Bus)

Der PCA9685 wird über I²C (GPIO 2 und 3) mit dem Pi verbunden:

```
Raspberry Pi Pin   →   PCA9685 Pin   Funktion
─────────────────────────────────────────────
Pin 1 (3.3V)      →   VCC           3.3V Logik
Pin 3 (GPIO2/SDA) →   SDA           I²C Daten
Pin 5 (GPIO3/SCL) →   SCL           I²C Takt
Pin 6 (GND)       →   GND           Masse (Pin 2)
Pin 6 (GND)       →   OE            Output Enable (dauerhaft aktiv)
```

**Raspberry Pi GPIO-Header (Vorderseite, 2×20 Pin):**

```
   3V3  [1] [2]  5V     ← Hier KEINE Verbindung zur 3.3V!
   SDA  [3] [4]  5V     ← GPIO2 = SDA
   SCL  [5] [6]  GND    ← GPIO3 = SCL, GND
```

### 2. PCA9685 ↔ Servos

Der PCA9685 hat 16 Kanäle (0-15). Wir verwenden die ersten 5 für die Gelenke:

```
PCA9685        Gelenk    Servo-Typ           Signal-Pin
───────────────────────────────────────────────────────
PWM 0          J1        Metal MG996R        +Rot, GND, Signal(gelb)
PWM 1          J2        MG996R              +Rot, GND, Signal(gelb)
PWM 2          J3        MG90S               +Rot, GND, Signal(gelb)
PWM 3          J4        MG90S               +Rot, GND, Signal(gelb)
PWM 4          J5        MG90S               +Rot, GND, Signal(gelb)
```

**Servo-Stecker (Standard 3-Pin):**

```
Servo-Stecker          PCA9685 Anschluss
──────────────────────────────────────────
Signal (gelb/weiß)  →  PWM-Pin (0-4)
+Power (rot)        →  V+ (Schraubklemme)
Ground (braun/schwarz) → GND (Schraubklemme)
```

### 3. Stromversorgung (KRITISCH!)

```
┌──────────────────────────────────────────────┐
│ Externe Stromversorgung (5-6V, min. 3.5A)   │
│  + (Rot) → PCA9685 V+ (Schraubklemme)       │
│  - (Schwarz) → PCA9685 GND (Schraubklemme)  │
└──────────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ↓                       ↓
    Alle Servo-Plus      Alle Servo-Minus
    (gemeinsame Leitung) (gemeinsame Leitung)
         │                       │
         └───────────┬───────────┘
                     │
              (Mit Pi GND verbunden)
```

**Fehler vermeiden:**
- ❌ **Nicht** den Pi's 5V-Pin für Servo-Stromversorgung verwenden
- ❌ **Nicht** den Pi's 3.3V mit PCA9685 VCC verbinden (nur 3.3V für Logik)
- ✅ **Immer** Pi und Servos mit gemeinsamer Masse (GND) verbinden

### 4. Beispiel-Verdrahtungsdiagramm (ASCII)

```
                  Raspberry Pi 4
                  ┌──────────────┐
              3V3 │[1] [2] 5V    │
              SDA │[3] [4] 5V    │
              SCL │[5] [6] GND   │
                  └───┬──────┬───┘
                      │      │
                    [SDA]  [SCL]
                      │      │
            ┌─────────┴──────┴─────┐
            │   PCA9685 PWM Board  │
            │ VCC (3.3V von Pi)    │
            │ GND (mit Pi GND)     │
            │ SDA / SCL            │
            │                      │
            │ PWM 0,1,2,3,4 (→Servos)
            │ V+ / GND (Externe Stromvers.)
            └──────┬──────────┬────┘
                   │          │
         ┌─────────┴┐      ┌──┴──────┐
         │ +6V      │      │ GND     │
         ↓          ↓      ↓         ↓
    ┌────────┐ ┌────────┐ (gemeinsame Rückleitung)
    │J1 Servo│ │J2 Servo│ (alle Servos teilen sich GND)
    │MG996R  │ │MG996R  │
    └────────┘ └────────┘
    
    ┌────────┐ ┌────────┐ ┌────────┐
    │J3 Servo│ │J4 Servo│ │J5 Servo│
    │MG90S   │ │MG90S   │ │MG90S   │
    └────────┘ └────────┘ └────────┘
```

---

## Installation

### Schritt 1: Raspberry Pi vorbereiten

```bash
# 1. SSH in den Pi (falls nicht lokal)
ssh pi@<pi-ip>

# 2. System aktualisieren
sudo apt update && sudo apt upgrade -y

# 3. Git und Python-Tools installieren
sudo apt install -y git python3-pip python3-venv
```

### Schritt 2: I²C aktivieren

```bash
# Bearbeitungstool öffnen (oder via raspi-config)
sudo nano /boot/firmware/config.txt

# Suche nach dieser Zeile und stelle sicher, dass sie nicht kommentiert ist:
# dtparam=i2c_arm=on

# Falls nicht vorhanden, am Ende der Datei hinzufügen:
# dtparam=i2c_arm=on

# Speichern (Ctrl+X, dann Y, Enter)
```

**Alternativ mit raspi-config:**
```bash
sudo raspi-config
# → Interface Options → I2C → Enable
# → Finish
```

**I²C-Devices überprüfen:**
```bash
sudo i2cdetect -y 1

# Erwartete Ausgabe:
#      0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
# 00:          -- -- -- -- -- -- -- -- -- -- -- -- --
# 10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
# 20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
# 30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
# 40: 40 -- -- -- -- -- -- -- -- -- -- -- -- -- -- --   ← 0x40 ist der PCA9685
# ...
```

### Schritt 3: Repository klonen

```bash
# Repository auf dem Pi klonen
cd ~
git clone https://github.com/<dein-github>/kuka-arm.git
cd kuka-arm
```

### Schritt 4: Abhängigkeiten installieren

```bash
# Python Virtual Environment erstellen
python3 -m venv venv
source venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt
```

### Schritt 5: Konfiguration

```bash
# .env-Datei erstellen
nano .env

# Folgende Inhalte eintragen:
WIFI_SSID=KUKA-ARM
WIFI_PASSWORD=kuka1234
LOGIN_USER=admin
LOGIN_PASSWORD=kuka123
SECRET_KEY=your-random-32-char-secret-key
PORT=80
```

### Schritt 6: Setup-Skript ausführen

```bash
# Setup-Skript ausführbar machen
chmod +x setup.sh
chmod +x setup_hotspot.sh

# Setup ausführen (erstellt Systemd-Service, etc.)
sudo ./setup.sh
```

### Schritt 7: Hotspot konfigurieren (optional)

Falls der Pi als **WiFi-Hotspot** fungieren soll:

```bash
# Hotspot einrichten
sudo ./setup_hotspot.sh

# Nach Reboot ist der Pi unter 192.168.4.1 erreichbar
# Verbindung: KUKA-ARM, Passwort: kuka1234
```

### Schritt 8: App starten

```bash
# Manuell starten (für Tests)
./start.sh

# ODER Systemd-Service starten (läuft beim Boot automatisch)
sudo systemctl start kuka-arm
sudo systemctl status kuka-arm
```

---

## Inbetriebnahme

### 1. Hardware-Test

Nach der Verdrahtung **VOR der ersten Benutzung** testen:

```bash
# Im kuka-arm-Verzeichnis:
python3 test_servo.py

# Folgende Abläufe sollten zu sehen sein:
# - J1 (Basis) dreht langsam 0° → 180° → 0°
# - J2 (Schulter) folgt
# - J3-J5 folgen
# Falls ein Servo nicht reagiert: Verdrahtung/PWM-Kanal überprüfen
```

### 2. Web-Oberfläche aufrufen

**Wenn Pi direkt mit Netzwerk verbunden:**
```
http://<pi-ip>:80
```

**Wenn Pi als Hotspot läuft:**
```
1. WiFi-Netzwerk "KUKA-ARM" verbinden
2. Browser öffnen: http://192.168.4.1
3. Ein Gerät nach dem anderen verbinden (1 Session)
```

### 3. Erste Bewegungen

```
1. Oberfläche laden → "KUKA-ARM smartPAD bereit"
2. [FREIGABE] Button drücken (grün)
3. Mit Joystick oder Achsen-Schiebereglern testen
4. [E-STOP] (rotes X) sollte sofort stoppen
5. Nach E-Stop: [ESC]-Taste drücken um zu quittieren
```

### 4. Kalibrierung

**Erste Kalibrierung durchführen:**
```
1. Menü: "Kalibrierung"
2. Pro Gelenk (J1-J5):
   - "Jetzt anfahren" drücken
   - Roboter-Position von Hand einstellen
   - "Position setzen" drücken
   - Min/Max-Grenzen mit Buttons testen
3. "Speichern" drücken → robot.yaml wird aktualisiert
```

---

## Fehlerbehebung

### Problem: PCA9685 nicht erkannt

**Symptom:** `I2C device 0x40 not found`

**Lösungen:**
1. I²C aktivieren überprüfen:
   ```bash
   sudo i2cdetect -y 1
   # Sollte "40" in der Matrix zeigen
   ```

2. Pin-Verdrahtung überprüfen:
   - SDA (Pi Pin 3) → PCA9685 SDA
   - SCL (Pi Pin 5) → PCA9685 SCL
   - GND (Pi Pin 6) → PCA9685 GND

3. Pull-up-Widerstände:
   - Oft schon auf dem PCA9685-Board vorhanden
   - Falls nicht: 4.7kΩ zwischen SDA+3.3V und SCL+3.3V

### Problem: Servos bewegen sich gar nicht

**Überprüfung:**
```bash
# Test-Script mit Debugging starten
python3 test_servo.py
# → Sollte jeden Servo einzeln anfahren

# Wenn keine Bewegung:
# 1. Externe Stromversorgung überprüfen (Voltmeter: 5-6V zwischen V+ und GND)
# 2. Servo-Stecker überprüfen (Signal/Plus/Minus richtig angesteckt?)
# 3. Servo-Kanal in test_servo.py richtig?
```

### Problem: Servos zittern oder frieren

**Ursachen:**
- **Zu wenig Strom**: Netzteil-Ampere erhöhen
- **Zu wenig Stabilisierung**: Große Kondensatoren (1000µF) zwischen V+ und GND hinzufügen
- **Rauschen auf Signal**: Servo-Signal-Leitung weg von Stromkabeln führen

**Erste Hilfe:**
```bash
# Wenn in Betrieb, Arm deaktivieren
# (FREIGABE-Button)
# → Servos geben sofort los
```

### Problem: Web-Oberfläche reagiert nicht

```bash
# Service-Status überprüfen
sudo systemctl status kuka-arm

# Logs ansehen
sudo journalctl -u kuka-arm -f

# Manuell starten (mit Output)
cd /home/pi/kuka-arm
source venv/bin/activate
python3 app/main.py
```

### Problem: Hotspot startet nicht

```bash
# Hostapd Status überprüfen
sudo systemctl status hostapd

# Logs
sudo journalctl -u hostapd -f

# Neustart
sudo systemctl restart hostapd dnsmasq
```

### Problem: Servo zuckt beim Einschalten

**Normal**: Beim Power-up können Servos zucken (PCA9685 sucht sich Null-Punkt).

**Wenn es problematisch ist:**
1. Servo-Kalibrierung überprüfen (robot.yaml)
2. External Power Supply durchmessen (sollte stabil 5-6V sein)

---

## Sicherheit

### Elektrische Sicherheit

- **Externe Stromversorgung verwenden** – nicht vom Pi
- **Netzteil abschalten** vor Verdrahtungsänderungen
- **Gesamtstrom überwachen** – bei >4A: Fehlersuche
- **Kabelquerschnitt** – mindestens 1mm² für Servokabel

### Mechanische Sicherheit

- **E-Stop** immer erreichbar (rotes X auf Web-Oberfläche)
- **Freigabe-Schaltung** (grüner FREIGABE-Button) nutzen
- **Arbeitsraum-Limits** im Konfigurationsmenu einstellen
- **Beobachtung** während der Bewegung erforderlich
- **Notfall**: Stromversorgung abschalten

### Software-Sicherheit

- **Einzige aktive Session** – neuer Login invalidiert alte
- **Timeout nach 10 min** inaktiv – Arm deaktiviert sich selbst
- **WebSocket-Verschlüsselung** (WSS) in Produktion nutzen

---

## Weiterführende Ressourcen

- **PCA9685 Datenblatt**: Adafruit PCA9685 Servo Driver
- **Servo-Datenblätter**: MG996R, MG90S Spezifikationen
- **Three.js Dokumentation**: https://threejs.org/docs/
- **FastAPI Dokumentation**: https://fastapi.tiangolo.com/
- **Raspberry Pi I²C**: https://www.raspberrypi.org/documentation/hardware/raspberrypi/spi/README.md

---

## Support & Fehlerberichte

Bugs oder Fragen? Öffne ein Issue auf GitHub oder kontaktiere den Maintainer.

**Lizenz**: MIT

---

**Letztes Update**: Mai 2026
