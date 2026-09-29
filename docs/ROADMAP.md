# Roadmap & Refresh-Plan

Stand: 2026-09-29.

## 1. Abgleich lokal ↔ Remote

In der Cloud-Sitzung dieses Refreshs war `main` identisch mit `origin/main`
(`b823123`, 13 Commits, keine offenen Branches oder PRs). Unveröffentlichte
Arbeit auf deinen lokalen Rechnern ist von dort aus nicht sichtbar – bitte in
jedem lokalen Klon prüfen:

```bash
git fetch --all --prune
git status -sb                    # "ahead N" = lokale Commits nicht gepusht
git log --oneline origin/main..   # welche Commits fehlen remote
git stash list                    # vergessene Zwischenstände
git diff --stat                   # ungesicherte Änderungen
```

Besonders auf dem **Raspberry Pi**: Kalibrierungen aus der Oberfläche
schreiben direkt in `config/robot.yaml`, eigene Programme liegen in
`config/programs/` (nicht im Git). Vor einem `git pull` auf dem Pi:
Einstellungen → Backup exportieren, danach `git diff config/robot.yaml`
ansehen und echte Kalibrierwerte ins Repository übernehmen.

## 2. In diesem Refresh erledigt

- OmniSim-Befunde umgesetzt – siehe [omnisim-evaluation.md](omnisim-evaluation.md).
- `robot.yaml` ist die einzige Quelle; README/`test_servo.py`/UI/URDF lesen daraus,
  Tests und CI prüfen die Übereinstimmung.
- URDF-Generator mit Selbstprüfung gegen die Vorwärtskinematik.
- Sicherheits- und Funktionsfehler behoben (Auszug):
  - E-Stop wartete hinter aufgestauten Jog-Befehlen; eine gehaltene Jog-Taste
    fuhr nach dem Loslassen noch sekundenlang weiter.
  - Inaktivitäts-Timeout griff bei offener Oberfläche nie (Ping zählte als Bedienung).
  - 3D-Ansicht und Joysticks luden nie: die CDN-Pfade existieren in three 0.160 /
    nipplejs 0.10.1 nicht, und mit Internetzugang verhinderte der Fehler in der
    3D-Ansicht sogar den WebSocket-Aufbau. Bibliotheken liegen jetzt lokal (Hotspot hat kein Internet).
  - Einfache Kalibrierung hätte beim Speichern alle Grenzen auf 0–180° gesetzt
    (J2 und Greifer über ihre Anschläge).
  - „Übernehmen“ in den Einstellungen speicherte Override × 1,8 statt der
    eingegebenen Geschwindigkeit (bis 180 °/s); `max_speed_dps` wurde nie
    durchgesetzt.
  - Home sprang ungebremst in die Zielstellung; Programme/REST-Jogs liefen ohne
    Bewegungssperre parallel zu Handbefehlen.
  - Gespeicherter Zustand wich von der Servostellung ab, wenn ein Ziel außerhalb
    der Grenzen lag (Anzeige/Pose falsch).
  - Programmliste blieb leer (falsche Element-ID), Programmnamen/-inhalte ohne
    Prüfung, Labels ungeschützt ins HTML.
  - `setup.sh` erwartete `~/kuka-arm`, das Repository heißt `kuka-arm-controller`.

## 3. Offen – braucht den echten Arm

| # | Prüfung | Warum |
|---|---|---|
| H1 | Home fahren und mit der 3D-Ansicht vergleichen | Laut DH-Tabelle steht der Oberarm in Home senkrecht und der Unterarm zeigt waagerecht in Richtung **−Y** (TCP bei X = 0, Y = −145, Z = 160 mm). Weicht der echte Arm ab, `theta_offset` bzw. `invert` in `robot.yaml` korrigieren, dann `tools/generate_urdf.py`. |
| H2 | Greifer bei 0° – drückt er gegen einen Anschlag? | Home = Min = 0°. Ein blockierter Servo zieht Dauerstrom und wird warm. Ggf. `min_angle`/`home_angle` z. B. auf 5°. |
| H3 | `python3 test_servo.py` einmal komplett | Neue, grenzentreue Testroutine bestätigen. |
| H4 | Link-Längen nachmessen (60/100/90/55 mm) | Die DH-Werte sind nie als vermessen markiert gewesen. |
| H5 | E-Stop unter Last | Absacken von J2/J3 beobachten → entscheidet über Punkt E1. |
| H6 | Netzteil unter Last messen | README empfiehlt jetzt ≥ 5 A (Blockierstrom MG996R ≈ 2,5 A). |

## 4. Entscheidungen

- **Lizenz:** README sagt MIT, es gibt aber keine `LICENSE`-Datei. Ohne sie gilt
  rechtlich „alle Rechte vorbehalten“.
- **OmniLink-Daten:** Vor dem Veröffentlichen von `omnisim-evaluation.md` die
  ausdrückliche Zustimmung von OmniLink einholen (in ihrer Antwort nicht
  explizit enthalten).
- **E-Stop-Verhalten (E1):** aktuell STOP 0 (PWM aus, Arm sackt). Alternative
  STOP 1: erst anhalten und Position halten, dann nach Quittierung/Timeout
  abschalten. Hängt von H5 ab.
- **Pi 5:** `RPi.GPIO` läuft auf dem Pi 5 nicht; Blinka nutzt dort `lgpio`.
  Bei einem Umstieg `requirements.txt` anpassen.

## 5. Nächste Funktionen (Vorschläge)

1. **Teach-in:** aktuelle Stellung als Programmschritt übernehmen, Programme in der
   Oberfläche anlegen/bearbeiten (API und Validierung existieren schon).
2. **Kartesische Programmschritte** (`{"type": "move", "x":…, "y":…, "z":…, "b":…}`)
   – die neue IK kann das.
3. **Schwerkraft-Vorsteuerung** für J2/J3: OmniSim zeigt ~0,3° Durchhang;
   mit echten Massen (CAD) als winkelabhängigen Offset.
4. **Soft-Limits** (z. B. 2° Abstand zu den Grenzen im Handbetrieb).
5. **Kontakterkennung:** Das OmniSim-Vorzeichen-Signal braucht eine gemessene
   Ist-Position. MG996R/MG90S liefern keine – nur mit Feedback-Servos
   (z. B. Servos mit Potentiometer-Abgriff oder serielle Smart-Servos).

## 6. CAD-Anbindung (Planung)

Ziel: Das (noch nicht öffentliche) CAD-Modell liefert, was `robot.yaml` fehlt
– ohne dass CAD-Quelldaten ins Repository müssen.

**Schnittstelle – pro Glied ein Export:**

| Feld | Einheit | Ziel |
|---|---|---|
| Gelenk-Frames (Ursprung + Achse) | mm | Abgleich mit der DH-Tabelle (Skript meldet Abweichungen) |
| Masse | kg | `dynamics.<link>.mass_kg` → URDF-Inertial |
| Schwerpunkt | m, im Link-Frame der URDF | `dynamics.<link>.com_m` |
| Trägheitstensor | kg·m², um den Schwerpunkt | `dynamics.<link>.inertia` |
| Mesh (STL oder GLB), vereinfacht | m | URDF-`<visual>`/`<collision>`, 3D-Ansicht |
| Greifer-Geometrie + Fingerweg über 0–90° | mm | Greifermodell in URDF und 3D-Ansicht |

Link-Namen und -Frames sind durch die generierte URDF festgelegt (`base_link`,
`link_j1` … `link_j4`, `tool0`; Frame = DH-Frame, Nullstellung = Servo-Mitte).
Das CAD-Modell sollte in genau dieser Stellung (alle Servos 90°) exportiert werden.

**Ablauf:** CAD-Export → `description/cad/` (nur Exporte, keine Quelldateien) →
`tools/generate_urdf.py` liest Massen/Meshes → CI prüft wie bisher gegen die
Vorwärtskinematik → 3D-Ansicht lädt dieselben Meshes.

## 7. Doku-Refresh für die übrigen Projekte

Vorlage, die hier angewendet wurde:

1. Eine Konfigurationsdatei als einzige Quelle; Doku spiegelt sie nur.
2. Ein Test, der Doku-Tabellen gegen diese Quelle prüft.
3. CI bei jedem Push (Tests + Generatoren im `--check`-Modus).
4. README: was, Hardware, Installation vom echten Repo-Namen aus, Betrieb,
   Fehlerbehebung, Sicherheit, „Letztes Update“.
5. Offene Hardware-Prüfungen und Entscheidungen in einer ROADMAP statt im Kopf.
