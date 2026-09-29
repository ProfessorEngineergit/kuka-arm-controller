#!/usr/bin/env python3
"""
Hardware test script – run directly on Raspberry Pi.
Tests each servo on the PCA9685.

Channels, limits and pulse widths are read from config/robot.yaml, so this
script can never disagree with the controller about which channel drives
which joint, or drive a joint past its configured limits.

Usage:
  python3 test_servo.py                 # alle Gelenke nacheinander testen
  python3 test_servo.py --joint J2      # nur ein Gelenk (Name oder Nummer 1-5)
  python3 test_servo.py --ch 4          # nur einen PCA9685-Kanal
  python3 test_servo.py --ch 4 --angle 60   # Kanal auf Winkel fahren und halten
  python3 test_servo.py --list          # Kanalbelegung anzeigen
  python3 test_servo.py --scan          # I²C-Scan
"""
import argparse
import sys
import time
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "robot.yaml"
UNASSIGNED_PULSE = (600, 2400)  # conservative range for channels without a joint


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def joint_info(cfg: dict) -> list:
    """One dict per joint: name, label, channel, limits, pulse range, invert."""
    types = cfg["servos"]["types"]
    out = []
    for j in cfg["joints"]:
        stype = types.get(j.get("servo_type", ""), {})
        out.append({
            "name": j["name"],
            "label": j.get("label", ""),
            "type": j.get("type", "revolute"),
            "channel": int(j["channel"]),
            "servo_type": j.get("servo_type", "?"),
            "min": float(j["min_angle"]),
            "max": float(j["max_angle"]),
            "home": float(j["home_angle"]),
            "invert": bool(j.get("invert", False)),
            "pulse": (stype.get("pulse_min_us", 500), stype.get("pulse_max_us", 2500)),
        })
    return out


def angle_to_duty(freq: float, pulse: tuple, angle: float) -> int:
    p_min, p_max = pulse
    pulse_us = p_min + (p_max - p_min) * (angle / 180.0)
    period_us = 1_000_000 / freq
    return max(0, min(0xFFFF, int((pulse_us / period_us) * 0xFFFF)))


def init_pca(freq: float):
    try:
        import board
        from adafruit_pca9685 import PCA9685
        pca = PCA9685(board.I2C())
        pca.frequency = freq
        print("[OK] PCA9685 gefunden @ I2C-Adresse 0x40")
        return pca
    except Exception as e:
        print(f"[FEHLER] PCA9685 nicht gefunden: {e}")
        print("  → I²C aktiviert? 'sudo i2cdetect -y 1' prüfen")
        print("  → Verkabelung: SDA→GPIO2 (Pin 3), SCL→GPIO3 (Pin 5), VCC→3.3V (Pin 1), GND→GND (Pin 6)")
        sys.exit(1)


def i2c_scan():
    print("=== I²C Bus Scan ===")
    try:
        import subprocess
        result = subprocess.run(['i2cdetect', '-y', '1'], capture_output=True, text=True)
        print(result.stdout)
    except FileNotFoundError:
        print("i2cdetect nicht gefunden. Installieren: sudo apt-get install i2c-tools")


def print_mapping(joints: list):
    print("Kanal  Gelenk  Funktion      Servo          Bereich     Home")
    print("─────  ──────  ────────────  ─────────────  ──────────  ─────")
    used = {j["channel"] for j in joints}
    for j in sorted(joints, key=lambda j: j["channel"]):
        rng = f"{j['min']:.0f}–{j['max']:.0f}°"
        print(f"ch{j['channel']:<4} {j['name']:<7} {j['label']:<13} {j['servo_type']:<14} "
              f"{rng:<10}  {j['home']:>4.0f}°")
    free = [c for c in range(16) if c not in used]
    print(f"Frei: {', '.join(f'ch{c}' for c in free)}")


def _set(pca, freq, j, angle):
    actual = (180.0 - angle) if j["invert"] else angle
    pca.channels[j["channel"]].duty_cycle = angle_to_duty(freq, j["pulse"], actual)


def test_joint(pca, freq: float, j: dict, dwell: float = 1.0):
    """Home → Min → Max → Home, strictly inside the configured limits."""
    print(f"\n--- {j['name']} {j['label']} (ch{j['channel']}, {j['servo_type']}) ---")
    print(f"  Bereich {j['min']:.0f}–{j['max']:.0f}°, Home {j['home']:.0f}°, "
          f"Puls {j['pulse'][0]}–{j['pulse'][1]} µs")
    for text, angle in (("Home", j["home"]), ("Min", j["min"]), ("Max", j["max"]), ("Home", j["home"])):
        print(f"  → {text:<5}{angle:6.1f}° ", end='', flush=True)
        _set(pca, freq, j, angle)
        time.sleep(dwell)
        print("OK")
    print(f"  {j['name']} ✓ (Signal bleibt an, Servo hält Home)")


def find_joint(joints: list, key: str):
    key = key.strip().upper()
    for idx, j in enumerate(joints):
        if key in (j["name"].upper(), str(idx + 1)):
            return j
    return None


def main():
    parser = argparse.ArgumentParser(description='KUKA-ARM Servo-Test')
    parser.add_argument('--joint', help='Nur dieses Gelenk testen (z. B. J2 oder 2)')
    parser.add_argument('--ch', type=int, default=None, help='Nur diesen PCA9685-Kanal (0-15)')
    parser.add_argument('--angle', type=float, default=None,
                        help='Mit --ch/--joint: auf diesen Winkel fahren und halten (auf Grenzen begrenzt)')
    parser.add_argument('--list', action='store_true', help='Kanalbelegung aus robot.yaml anzeigen')
    parser.add_argument('--scan', action='store_true', help='Nur I²C-Scan durchführen')
    args = parser.parse_args()

    cfg = load_config()
    freq = cfg["servos"]["frequency"]
    joints = joint_info(cfg)

    if args.scan:
        i2c_scan()
        return
    if args.list:
        print_mapping(joints)
        return

    target = None
    if args.joint:
        target = find_joint(joints, args.joint)
        if target is None:
            sys.exit(f"Gelenk '{args.joint}' nicht in robot.yaml")
    elif args.ch is not None:
        if not 0 <= args.ch <= 15:
            sys.exit("Kanal muss zwischen 0 und 15 liegen")
        target = next((j for j in joints if j["channel"] == args.ch), None)
        if target is None:
            print(f"[WARNUNG] ch{args.ch} ist in robot.yaml keinem Gelenk zugeordnet – "
                  f"teste mit {UNASSIGNED_PULSE[0]}–{UNASSIGNED_PULSE[1]} µs und 0–180°")
            target = {"name": f"ch{args.ch}", "label": "(frei)", "channel": args.ch,
                      "servo_type": "?", "min": 0.0, "max": 180.0, "home": 90.0,
                      "invert": False, "pulse": UNASSIGNED_PULSE}

    print("=== KUKA-ARM Servo-Test ===")
    print(f"Konfiguration: {CONFIG_PATH}")
    print("Externe 5-6V Versorgung muss an V+/GND des PCA9685 angeschlossen sein!\n")
    pca = init_pca(freq)

    try:
        if target is not None and args.angle is not None:
            angle = max(target["min"], min(target["max"], args.angle))
            if angle != args.angle:
                print(f"[HINWEIS] {args.angle}° auf Grenze {angle}° begrenzt")
            print(f"{target['name']} (ch{target['channel']}) → {angle}°")
            _set(pca, freq, target, angle)
            print("Drücke STRG+C zum Beenden.")
            while True:
                time.sleep(1)
        elif target is not None:
            test_joint(pca, freq, target)
        else:
            print(f"Teste alle {len(joints)} Gelenke nacheinander (Reihenfolge wie robot.yaml).")
            print("Drücke STRG+C um abzubrechen.\n")
            print_mapping(joints)
            for j in joints:
                input(f"\n[ENTER] {j['name']} {j['label']} auf ch{j['channel']} testen...")
                test_joint(pca, freq, j)
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
    finally:
        for ch in range(16):
            pca.channels[ch].duty_cycle = 0
        print("\nPWM aus. Test beendet.")


if __name__ == '__main__':
    main()
