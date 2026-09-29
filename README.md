# KUKA-ARM – 5-DOF Roboterarm mit Raspberry Pi

Web-Controller für einen 3D-gedruckten Desktop-Roboterarm: vier Arm-Achsen
plus Greifer, angesteuert von einem Raspberry Pi über einen PCA9685
16-Kanal-PWM-Treiber. Die Bedienoberfläche ist einem KUKA smartPAD
nachempfunden (Achs- und kartesisches Verfahren, Programme, Kalibrierung,
3D-Ansicht) und läuft im Browser – der Pi spannt dafür ein eigenes WLAN auf.

> **Eine Quelle für alles:** [`config/robot.yaml`](config/robot.yaml) ist die
> einzige Stelle, an der Kanäle, Grenzen und Kinematik stehen. Controller,
> `test_servo.py`, Web-Oberfläche, 3D-Ansicht und die generierte URDF lesen
> daraus; die Tabellen in dieser README werden von den Tests gegen
> `robot.yaml` geprüft.

## 📋 Inhaltsverzeichnis

1. [Hardware-Übersicht](#hardware-übersicht)
2. [Kinematik & Robotermodell (URDF)](#kinematik--robotermodell-urdf)
3. [Netzteil-Dimensionierung](#netzteil-dimensionierung)
4. [Verdrahtung](#verdrahtung)
5. [Installation](#installation)
6. [Inbetriebnahme](#inbetriebnahme)
7. [Programme](#programme)
8. [Entwicklung & Tests](#entwicklung--tests)
9. [Fehlerbehebung](#fehlerbehebung)
10. [Sicherheit](#sicherheit)
11. [Externe Simulation (OmniSim)](#externe-simulation-omnisim)

---

## Hardware-Übersicht

### Komponenten

| Komponente | Typ/Modell | Funktion | Bemerkung |
|---|---|---|---|
| **Raspberry Pi** | 4B oder neuer | Steuerung + Web-Server | Raspberry Pi OS (Debian Trixie) |
| **PCA9685** | 16-Kanal PWM-Treiber | Servo-PWM-Erzeugung | I²C, Adresse 0x40 |
| **J1–J2** | Metal MG996R / MG996R | Basis, Schulter | 500–2500 µs |
| **J3–J5** | MG90S | Ellbogen, Handgelenk, Greifer | 600–2400 µs (konservativ) |
| **Stromversorgung** | 5–6 V, ≥ 5 A | Servos | **Nicht** vom Pi! |

### Kanalbelegung und Achsgrenzen

Per Hardware-Test verifiziert am 2026-05-18. Kanal 3 ist frei.

| Gelenk | Funktion | PCA9685-Kanal | Servo | Bereich | Home |
|---|---|---|---|---|---|
| **J1** | Basis | 5 | Metal MG996R | 0–180° | 90° |
| **J2** | Schulter | 4 | MG996R | 30–150° | 90° |
| **J3** | Ellbogen | 2 | MG90S | 0–160° | 90° |
| **J4** | Handgelenk | 1 | MG90S | 0–180° | 90° |
| **J5** | Greifer | 0 | MG90S | 0–90° | 0° |

Winkel sind Servo-Winkel (0–180°, 90° = Servo-Mitte). `python3 test_servo.py --list`
zeigt dieselbe Tabelle direkt aus `robot.yaml`.

### Pulsbreiten und Geschwindigkeit

| Servo-Typ | 0° | 90° | 180° | max. Geschwindigkeit |
|---|---|---|---|---|
| **Metal MG996R / MG996R** | 500 µs | 1500 µs | 2500 µs | 20 °/s |
| **MG90S** | 600 µs | 1500 µs | 2400 µs | 30 °/s |

Die Grundgeschwindigkeit ist 8 °/s (der Arm hat kein Gegengewicht). Der
Override-Regler in der Oberfläche ist ein Prozentsatz davon; zusätzlich ist
jede Achse hart auf die Maximalgeschwindigkeit ihres Servotyps begrenzt.

---

## Kinematik & Robotermodell (URDF)

Der Arm hat **vier Arm-Achsen und einen Greifer**:

- **J1** dreht die Basis um die Hochachse.
- **J2, J3, J4** schwenken in einer gemeinsamen Ebene (Schulter, Ellbogen, Handgelenk-Neigung).
- **J5** öffnet und schließt den Greifer. Er bewegt den TCP nicht und ist
  deshalb nicht Teil der kinematischen Kette (`type: gripper` in `robot.yaml`).

Denavit-Hartenberg-Tabelle (`[a mm, alpha °, d mm, theta_offset °]`, theta = Servo-Winkel + Offset):

| Zeile | a | alpha | d | Bedeutung |
|---|---|---|---|---|
| J1 | 0 | 90 | 60 | Höhe der Schulterachse |
| J2 | 100 | 0 | 0 | Oberarm |
| J3 | 90 | 0 | 0 | Unterarm |
| J4 | 0 | 90 | 0 | Handgelenk-Neigung |
| TCP | 0 | 0 | 55 | fester Versatz Handgelenk → Greifermitte |

**Kartesisches Verfahren:** Mit vier Achsen sind genau vier TCP-Koordinaten
frei wählbar: **X, Y, Z und die Neigung B** des Werkzeugs in der Armebene.
Die Gier (A) folgt immer der Basisdrehung, eine Roll-Achse (C) gibt es nicht.
A/C-Tasten sind deshalb gesperrt, und ein unerreichbares Ziel wird mit einer
Meldung abgelehnt statt ungenau angefahren (Toleranz 0,5 mm / 0,5°).

**3D-Ansicht:** wird im Browser aus derselben DH-Tabelle berechnet wie die
Vorwärtskinematik. Wenn die 3D-Ansicht in Home-Stellung nicht wie der echte
Arm aussieht, stimmt die DH-Tabelle (oder ein `theta_offset`) nicht.

**URDF:** [`description/kuka_arm.urdf`](description/kuka_arm.urdf) wird aus
`robot.yaml` erzeugt und prüft sich selbst gegen die Vorwärtskinematik
(Abweichung < 1e-6 mm, CI schlägt bei veralteter URDF fehl):

```bash
python3 tools/generate_urdf.py          # nach Änderungen an robot.yaml
python3 tools/generate_urdf.py --check  # nur prüfen
```

- Einheiten m / rad; **URDF-Nullstellung = Servo-Mitte**: `servo_deg = degrees(q) + 90`.
  Die Nullkonfiguration liegt damit mitten im Bereich statt auf einem Anschlag.
- Der Greifer ist kein URDF-Gelenk; sein DH-Eintrag ist der feste Frame `tool0`.
- Keine Massen/Trägheiten, weil keine veröffentlicht sind. Ein optionaler
  Abschnitt `dynamics` in `robot.yaml` (z. B. aus CAD) wird mit ausgegeben:
  `dynamics: {link_j2: {mass_kg: 0.08, com_m: [0.05, 0, 0], inertia: [ixx, iyy, izz, ixy, ixz, iyz]}}`.

---

## Netzteil-Dimensionierung

| Servo | Anzahl | Betrieb (ca.) | Blockierstrom (ca., 6 V) |
|---|---|---|---|
| MG996R (J1, J2) | 2 | 0,5–0,9 A | 2,5 A |
| MG90S (J3–J5) | 3 | 0,1–0,3 A | 0,7 A |
| **Summe** | | **≈ 2,7 A** | **≈ 7 A** |

**Empfehlung:** 5–6 V mit **mindestens 5 A** (z. B. Mean Well LRS-50-5, 10 A).
Ein unterdimensioniertes Netzteil bricht beim Anfahren unter Last ein – die
Servos zittern und der Pi kann neu starten. Ein 1000 µF-Elko an V+/GND des
PCA9685 puffert Stromspitzen.

---

## Verdrahtung

### Raspberry Pi ↔ PCA9685 (I²C)

```
Raspberry Pi            PCA9685
───────────────────────────────────────
Pin 1  (3,3 V)      →   VCC   (Logikversorgung)
Pin 3  (GPIO2/SDA)  →   SDA
Pin 5  (GPIO3/SCL)  →   SCL
Pin 6  (GND)        →   GND
                        OE    offen lassen (intern auf aktiv gezogen)
```

```
   3V3  [1] [2]  5V     ← Pin 1 = VCC des PCA9685 (NICHT 5 V!)
   SDA  [3] [4]  5V
   SCL  [5] [6]  GND
```

### PCA9685 ↔ Servos

Servostecker: Signal (gelb/weiß) → PWM, Plus (rot) → V+, Masse (braun/schwarz) → GND.

```
PCA9685-Kanal   Gelenk   Servo
───────────────────────────────────
ch0             J5       MG90S          Greifer
ch1             J4       MG90S          Handgelenk
ch2             J3       MG90S          Ellbogen
ch3             —        (frei)
ch4             J2       MG996R         Schulter
ch5             J1       Metal MG996R   Basis
```

### Stromversorgung

```
Netzteil 5–6 V ── + ──► PCA9685 V+ (Schraubklemme) ──► alle Servo-Plus
               └─ − ──► PCA9685 GND (Schraubklemme) ──► alle Servo-Minus
                                   │
                                   └── gemeinsame Masse mit Pi-GND
```

- ❌ Servos **nicht** aus dem 5-V-Pin des Pi versorgen.
- ❌ VCC des PCA9685 **nicht** an 5 V – nur 3,3 V (Logik).
- ✅ Pi-GND und Servo-GND immer verbinden.

---

## Installation

```bash
# 1. System vorbereiten
sudo apt update && sudo apt upgrade -y
sudo apt install -y git

# 2. Repository klonen
cd ~
git clone https://github.com/ProfessorEngineergit/kuka-arm-controller.git
cd kuka-arm-controller

# 3. Setup (I²C, venv, Hotspot, systemd-Service)
sudo ./setup.sh
sudo reboot
```

`setup.sh` installiert aus dem Verzeichnis, in das geklont wurde, und legt –
falls nicht vorhanden – eine `.env` an:

```ini
WIFI_SSID=KUKA-ARM
WIFI_PASSWORD=kuka1234   # bitte ändern
PORT=80
```

Der Hotspot läuft über NetworkManager (`setup_hotspot.sh`, Verbindung
`kuka-hotspot`, IP `192.168.4.1`). Achtung: das Einrichten trennt eine
bestehende WLAN-/SSH-Verbindung.

```bash
sudo systemctl start kuka-arm      # Service starten
sudo systemctl status kuka-arm
sudo journalctl -u kuka-arm -f     # Logs
./start.sh                         # manuell (Vordergrund)
```

---

## Inbetriebnahme

### 1. Servo-Test (vor dem ersten Start)

`test_servo.py` liest Kanäle, Grenzen und Pulsbreiten aus `robot.yaml` und
fährt jedes Gelenk nur innerhalb seiner Grenzen (Home → Min → Max → Home):

```bash
source venv/bin/activate
python3 test_servo.py --list          # Kanalbelegung anzeigen
python3 test_servo.py                 # alle Gelenke nacheinander (mit ENTER)
python3 test_servo.py --joint J2      # ein Gelenk
python3 test_servo.py --ch 3          # freien Kanal testen (0–180°, Warnung)
python3 test_servo.py --scan          # I²C-Scan
```

Bewegt sich beim Test von J2 ein anderes Gelenk, ist die Kanalbelegung in
`robot.yaml` falsch – dort korrigieren, nirgendwo sonst.

### 2. Web-Oberfläche

1. Mit dem WLAN **KUKA-ARM** verbinden.
2. **http://192.168.4.1** öffnen (die Oberfläche braucht kein Internet).
3. **FREIGABE** (Taste `F`), dann mit den J1–J5-Tasten, dem Joystick oder
   kartesisch verfahren. **E-STOP** = `Leertaste`, quittieren = `Esc`, Home = `H`.

Ohne PCA9685 (z. B. am PC) läuft der Controller im Simulationsmodus; die
Statusleiste zeigt dann „SIMULATION“.

### 3. Kalibrierung

CFG → **Kalibrierung** zeigt die aktuellen Werte aus `robot.yaml`. Werte
ändern und **Speichern** – nur geänderte Gelenke werden geschrieben, jede
Änderung wird sofort wirksam. Der **Wizard** führt Gelenk für Gelenk durch
Home, Min und Max. Kalibrierung und Programme lassen sich unter
**Einstellungen → Lokale Backups** als ZIP sichern.

Nach einer Änderung der DH-Tabelle: `python3 tools/generate_urdf.py`.

---

## Programme

Eingebaut: `home`, `rotate_all` (jede Arm-Achse Min → Max → Home), `wave`,
`gripper_test`. Eigene Programme liegen als JSON in `config/programs/`
(Name: `A–Z a–z 0–9 _ -`) und werden beim Speichern geprüft:

```json
{
  "label": "Greifen",
  "description": "Greifer öffnen, absenken, schließen",
  "steps": [
    {"type": "jog",  "joint": 4, "target": "max", "speed": 20},
    {"type": "jog",  "joint": 1, "target": 70,    "speed": 10},
    {"type": "wait", "ms": 500},
    {"type": "jog",  "joint": 4, "target": "min", "speed": 20},
    {"type": "home"}
  ]
}
```

- `joint`: Index 0–4 (= J1–J5). `target`: Winkel in ° oder `"min"`/`"max"`/`"home"`
  (zur Laufzeit aus `robot.yaml`, folgt also jeder Kalibrierung).
- `speed` in °/s, begrenzt auf Grundgeschwindigkeit und Servo-Limit.
- **STOPP** beendet ein Programm; der Arm bleibt freigegeben und hält die Position.
  Während ein Programm läuft, ist manuelles Verfahren gesperrt.

---

## Entwicklung & Tests

Auf dem PC (ohne Hardware, Simulationsmodus):

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt   # Blinka/RPi.GPIO ggf. weglassen
uvicorn app.main:app --port 8000      # http://localhost:8000
python -m pytest                      # Tests
python tools/generate_urdf.py --check
```

Die Tests prüfen u. a., dass der Greifer die Pose nicht verändert, dass IK und
URDF mit der Vorwärtskinematik übereinstimmen, dass README, `test_servo.py` und
`robot.yaml` dieselben Kanäle/Grenzen haben, und dass E-Stop auch während einer
laufenden Bewegung sofort greift. GitHub Actions führt sie bei jedem Push aus.

| Pfad | Inhalt |
|---|---|
| `app/` | FastAPI-Backend: Kinematik, Servo-Ansteuerung, REST + WebSocket |
| `static/` | Oberfläche (HTML/CSS/JS), `static/vendor/` = three.js, nipplejs (lokal) |
| `config/robot.yaml` | Kanäle, Grenzen, Servotypen, DH-Tabelle |
| `description/` | generierte URDF |
| `tools/` | URDF-Generator |
| `tests/` | pytest-Suite |
| `docs/` | Simulationsauswertung, Roadmap |

---

## Fehlerbehebung

**PCA9685 nicht erkannt** – `sudo i2cdetect -y 1` muss `40` zeigen. Sonst I²C
aktivieren (`dtparam=i2c_arm=on` in `/boot/firmware/config.txt`, erledigt
`setup.sh`), Verdrahtung SDA/SCL/GND/VCC prüfen, neu starten.

**Falsches Gelenk bewegt sich** – `python3 test_servo.py --list` mit der
Verkabelung vergleichen und `channel:` in `robot.yaml` korrigieren.

**Servos zittern / Pi startet neu** – Netzteil zu schwach (siehe
[Netzteil](#netzteil-dimensionierung)), Elko ergänzen, Signalleitungen weg von
Stromleitungen führen.

**Arm sackt nach E-Stop ab** – erwartet, siehe [Sicherheit](#sicherheit).

**Web-Oberfläche nicht erreichbar**

```bash
sudo systemctl status kuka-arm
sudo journalctl -u kuka-arm -f
cd ~/kuka-arm-controller && ./start.sh     # manuell mit Ausgabe
```

**Hotspot startet nicht**

```bash
nmcli con show                 # kuka-hotspot vorhanden?
sudo nmcli con up kuka-hotspot
journalctl -u NetworkManager -f
sudo ./setup_hotspot.sh        # neu einrichten
```

**Servo zuckt beim Einschalten** – beim Start setzt der Controller sofort alle
Home-Winkel. Steht der Arm vorher weit weg von Home, springt er einmal dorthin;
vor dem Ausschalten daher Home anfahren.

---

## Sicherheit

**Elektrisch:** Servos nur über das externe Netzteil versorgen, vor
Verdrahtungsänderungen Netzteil ausschalten, Zuleitung Netzteil → PCA9685 ≥ 1 mm².

**Bewegung:**

- **E-STOP** (Oberfläche, `Leertaste` oder `POST /api/estop`) wird sofort
  ausgeführt – auch während einer Bewegung und vor allen noch wartenden
  Befehlen – und schaltet das PWM-Signal ab. Die Servos (MG996R/MG90S) sind
  danach **kraftlos**: ein nicht ausbalancierter Arm sinkt unter seinem Gewicht
  ab. Arm deshalb nicht über Hindernissen/Personen betreiben.
- Nach dem Quittieren und erneuter Freigabe fährt der nächste Befehl von der
  zuletzt gesendeten Position aus; ist der Arm abgesackt, springt er zuerst
  dorthin zurück. Nach einem E-Stop zuerst **Home** fahren.
- **FREIGABE** aus schaltet ebenfalls das PWM-Signal ab.
- Programm-**STOPP** hält dagegen die Position (Servos bleiben bestromt).
- Nach **10 min ohne Bedienung** wird der Arm automatisch deaktiviert.
- Eine gehaltene Jog-Taste fährt nach dem Loslassen höchstens noch einen
  Schritt (keine aufgestauten Befehle).
- Achsgrenzen und Geschwindigkeitslimits werden serverseitig durchgesetzt,
  unabhängig davon, was ein Client sendet.

**Netzwerk:** Die Oberfläche hat bewusst **keinen Login**. Sie ist nur für das
isolierte Hotspot-WLAN gedacht – Hotspot-Passwort ändern und den Pi nicht in
ein offenes Netz hängen.

---

## Externe Simulation (OmniSim)

Das OmniLink-Team hat den Arm aus den öffentlichen Dateien in OmniSim
nachgebaut, alle vier eingebauten Programme abgespielt und dabei drei
Unstimmigkeiten im Repository gefunden. Ergebnisse und was daraus geändert
wurde: [docs/omnisim-evaluation.md](docs/omnisim-evaluation.md).

---

## Weiterführende Ressourcen

- Adafruit PCA9685 Servo Driver – Datenblatt und CircuitPython-Bibliothek
- MG996R / MG90S Servo-Datenblätter
- three.js: https://threejs.org/docs/ · FastAPI: https://fastapi.tiangolo.com/
- URDF: https://wiki.ros.org/urdf/XML

**Lizenz**: MIT

**Letztes Update**: September 2026
