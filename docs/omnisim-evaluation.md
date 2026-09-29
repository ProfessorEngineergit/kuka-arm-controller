# OmniSim-Auswertung (OmniLink Team)

Das OmniLink-Team hat den Arm ausschließlich aus den öffentlichen Dateien
dieses Repositories in ihrem Simulator OmniSim nachgebaut und vermessen.
Dieses Dokument fasst ihre Ergebnisse zusammen und hält fest, was im
Repository daraufhin geändert wurde.

> Alle Zahlen stammen von OmniLink. Massen und Trägheiten im Simulationsmodell
> sind **ihre Annahmen** (das Repository veröffentlicht keine), die
> Durchhang-Werte haben also die richtige Form, sind aber nicht die Werte des
> echten Arms. Es wurde nicht die Hardware gemessen, keine Greifergeometrie
> modelliert, keine Kontaktkräfte oder Momente ausgewertet (die
> Momentenrückmeldung des Simulators liefert fest 0), und alles lief auf einer
> Maschine.

## Methode

- Ein URDF wurde aus der DH-Tabelle und den Gelenkgrenzen in
  `config/robot.yaml` erzeugt und gegen `forward_kinematics()` des Controllers
  geprüft: **max. 2,28e-06 mm Abweichung über sechs Posen**.
- Alle vier eingebauten Programme (`home`, `rotate_all`, `wave`,
  `gripper_test`) wurden abgespielt: **25 Bewegungen**, je 5 s Einschwingzeit.
- Ein erster Lauf mit überlappender Basis (J1 blieb bei 0,295 rad statt
  1,571 rad hängen) wurde von OmniLink selbst gefunden, das Modell korrigiert
  und alles neu gerechnet. Alle Zahlen unten stammen aus dem korrigierten Lauf.

## Ergebnisse

### Nachführfehler (größter Fehler je Achse über alle 25 Bewegungen)

| Achse | Fehler [rad] | Fehler [°] |
|---|---|---|
| J2 Schulter | 5,665e-03 | 0,325 |
| J3 Ellbogen | 5,606e-03 | 0,321 |
| J4 Handgelenk | 6,437e-04 | 0,037 |
| J1 Basis | 4,87e-08 | < 0,001 |
| J5 Greifer | 2,43e-09 | < 0,001 |

Die Reihenfolge entspricht der Schwerkraftlast: die beiden Achsen, die das
Armgewicht tragen, hängen durch; die lastfreien Achsen sind praktisch exakt.
J2 hing zusätzlich in Ruhe unter Eigengewicht um 5,06e-04 rad durch.
`rotate_all` nutzt 100 % des Bereichs jeder Achse.

### Kontakt (Absenk-Treppe gegen einen Block)

| Schulterwinkel | Kontakt |
|---|---|
| 124° | nein |
| 127° | ja – `link_5` ↔ Block |

Beim Zurückziehen löst der Kontakt. Der Positionsfehler der Achse bestätigt
das unabhängig:

| Zustand | Positionsfehler [rad] |
|---|---|
| frei | +1,022e-02 |
| im Kontakt | −4,086e-03 |
| nach dem Lösen | +8,694e-03 (bitgleich mit dem freien Wert an dieser Pose) |

Das Vorzeichen des Positionsfehlers ist damit selbst ein Kontaktsignal – bei
einem Arm ohne Kraftsensor interessant (Servo drückt nach unten, Block drückt
zurück).

### Begrenzung an den Anschlägen

| Achse | Verlust am oberen Anschlag |
|---|---|
| J1 | 0,0100027 rad (0,57°) |
| J4 | 0,0100027 rad (0,57°) |
| J2 | 3,9e-06 rad – Rundung, kein echter Verlust |

## Befunde im Repository und was geändert wurde

### 1. J5 kann den TCP nicht bewegen

*Befund:* Die DH-Zeile von J5 hat Länge und Verdrehung 0, J5 dreht also um
die Werkzeugachse. `[90, 90, 90, 90, 0]` und `[90, 90, 90, 90, 90]` ergeben
dieselbe TCP-Position – J5 ist kinematisch eine Roll-Achse, nicht ein Greifer.

*Einordnung:* Hardware-Test (2026-05-18) und Controller behandeln J5 als
**Greifer**. Falsch war das Modell: die Vorwärtskinematik hat den
Greiferwinkel trotzdem als Drehung des TCP-Frames eingerechnet – die
angezeigte Orientierung (A/B/C) änderte sich beim Öffnen des Greifers, und
die IK durfte den Greifer verstellen, um eine Orientierung zu erreichen.

*Geändert:*
- `robot.yaml`: `type: gripper` für J5; die fünfte DH-Zeile ist als fester
  TCP-Versatz dokumentiert.
- Vorwärts-/Rückwärtskinematik nutzen nur `type: revolute`-Gelenke. Die IK
  löst jetzt genau die vier steuerbaren Koordinaten (X, Y, Z, Neigung B),
  lässt den Greifer unverändert und lehnt unerreichbare Ziele ab.
- README, Kalibrier-Wizard („J5 Handgelenk Roll“) und 3D-Ansicht bezeichnen
  J5 einheitlich als Greifer.
- Test: `tests/test_kinematics.py::test_gripper_does_not_move_tcp`.

### 2. README, test_servo.py und robot.yaml widersprachen sich

*Befund:* J5-Bereich 0–180° vs. 0–90°, und vier von fünf Kanälen verschieden.

*Einordnung:* `robot.yaml` ist korrekt (Kanäle per Hardware-Test verifiziert).
README und `test_servo.py` stammten noch aus der Zeit vor dem Test. Besonders
kritisch: `test_servo.py` fuhr jeden Kanal stur 0° → 180° – auf ch1 (J4) mit
MG996R-Pulsbreiten und J2/J5 über ihre Grenzen hinaus.

*Geändert:*
- `test_servo.py` liest Kanäle, Grenzen und Pulsbreiten aus `robot.yaml` und
  fährt nur Home → Min → Max → Home. `--list` zeigt die Belegung.
- README-Tabellen neu; ein Test vergleicht sie mit `robot.yaml`
  (`tests/test_description.py`), doppelte Kanäle werden beim Backup-Import
  abgewiesen.

### 3. Nullstellung liegt auf dem Anschlag

*Befund:* Für vier von fünf Achsen ist 0 die untere Grenze; das Modell meldete
beim Start vier Anschlag-Ereignisse in 8 ms.

*Einordnung:* Die Home-Stellung von J1–J4 ist 90° (Bereichsmitte). Das
Problem ist die Konvention: Servo-Winkel = Gelenkwinkel, also ist
Gelenkwinkel 0 der Servo-Anschlag – ein Modell, das bei q = 0 startet, steht
auf vier Anschlägen. Nur J5 (Greifer) hat Home = Min = 0°.

*Geändert:* Die generierte URDF (`description/kuka_arm.urdf`) legt die
Nullstellung auf die Servo-Mitte (`servo_deg = degrees(q) + 90`). q = 0 ist
damit die Home-Stellung, mit Abstand zu beiden Anschlägen
(`tests/test_description.py::test_urdf_zero_is_not_on_a_stop`). Die
eingebauten Programme verwenden `"min"`/`"max"`/`"home"` aus `robot.yaml` statt
fester Zahlen und folgen so jeder Kalibrierung.

*Offen:* Ob der Greifer bei 0° gegen einen mechanischen Anschlag drückt, muss
am echten Arm geprüft werden (siehe [ROADMAP](ROADMAP.md)).

## Eigene URDF

Statt die OmniLink-URDF zu übernehmen, erzeugt das Repository jetzt selbst
eine aus `robot.yaml` (`tools/generate_urdf.py`) und prüft sie bei jedem
Lauf gegen die eigene Vorwärtskinematik (Abweichung ~3e-09 mm über 200
Zufallsposen). So kann die Beschreibung nicht mehr unbemerkt vom Controller
abweichen. Massen und Trägheiten fehlen weiterhin – sie sollen aus dem
CAD-Modell kommen.
