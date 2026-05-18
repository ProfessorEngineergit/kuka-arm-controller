#!/usr/bin/env python3
"""
Hardware test script – run directly on Raspberry Pi.
Tests each servo channel individually on the PCA9685.

Usage:
  python3 test_servo.py            # test all channels
  python3 test_servo.py --ch 0     # test only channel 0
  python3 test_servo.py --scan     # I2C scan only
"""
import argparse
import time
import sys

FREQ = 50  # Hz

# Per-Kanal Pulse-Breiten (µs)
# Metal MG996R (CH0) + MG996R (CH1): 500–2500µs
# MG90S (CH2, CH3, CH4):             600–2400µs (konservativ)
PULSE_RANGES = {
    0: (500, 2500),   # J1 Metal MG996R
    1: (500, 2500),   # J2 MG996R
    2: (600, 2400),   # J3 MG90S
    3: (600, 2400),   # J4 MG90S
    4: (600, 2400),   # J5 MG90S Greifer
}


def us_to_duty(pulse_us: float) -> int:
    period_us = 1_000_000 / FREQ
    return int((pulse_us / period_us) * 0xFFFF)


def angle_to_duty(channel: int, angle: float) -> int:
    p_min, p_max = PULSE_RANGES.get(channel, (500, 2500))
    pulse = p_min + (p_max - p_min) * (angle / 180.0)
    return us_to_duty(pulse)


def init_pca():
    try:
        import board
        import busio
        from adafruit_pca9685 import PCA9685
        i2c = busio.I2C(board.SCL, board.SDA)
        pca = PCA9685(i2c)
        pca.frequency = FREQ
        print(f"[OK] PCA9685 gefunden @ I2C-Adresse 0x40")
        return pca
    except Exception as e:
        print(f"[FEHLER] PCA9685 nicht gefunden: {e}")
        print("  → I²C aktiviert? 'sudo i2cdetect -y 1' prüfen")
        print("  → Verkabelung: SDA→GPIO2 (Pin3), SCL→GPIO3 (Pin5), VCC→3.3V, GND→GND")
        sys.exit(1)


def i2c_scan():
    print("=== I²C Bus Scan ===")
    try:
        import subprocess
        result = subprocess.run(['i2cdetect', '-y', '1'], capture_output=True, text=True)
        print(result.stdout)
    except FileNotFoundError:
        print("i2cdetect nicht gefunden. Installieren: sudo apt-get install i2c-tools")


def test_channel(pca, ch: int, label: str = ""):
    print(f"\n--- Kanal {ch} {label} ---")
    p_min, p_max = PULSE_RANGES.get(ch, (500, 2500))
    print(f"  Pulse-Bereich: {p_min}–{p_max} µs")

    print(f"  → 0° (Minimum)  ", end='', flush=True)
    pca.channels[ch].duty_cycle = angle_to_duty(ch, 0)
    time.sleep(1.0)
    print("OK")

    print(f"  → 90° (Mitte)   ", end='', flush=True)
    pca.channels[ch].duty_cycle = angle_to_duty(ch, 90)
    time.sleep(1.0)
    print("OK")

    print(f"  → 180° (Maximum)", end='', flush=True)
    pca.channels[ch].duty_cycle = angle_to_duty(ch, 180)
    time.sleep(1.0)
    print("OK")

    print(f"  → 90° (zurück)  ", end='', flush=True)
    pca.channels[ch].duty_cycle = angle_to_duty(ch, 90)
    time.sleep(0.5)
    print("OK")

    pca.channels[ch].duty_cycle = 0
    print(f"  Kanal {ch} ✓")


JOINT_MAP = {
    0: "J1 Basis          → Metal MG996R  (CH0)",
    1: "J2 Schulter       → MG996R        (CH1)",
    2: "J3 Ellbogen       → MG90S         (CH2)",
    3: "J4 Handgelenk     → MG90S         (CH3)",
    4: "J5 Greifer        → MG90S         (CH4)",
}


def main():
    parser = argparse.ArgumentParser(description='KUKA-ARM Servo-Test')
    parser.add_argument('--ch', type=int, default=None, help='Nur diesen Kanal testen (0-15)')
    parser.add_argument('--scan', action='store_true', help='Nur I²C-Scan durchführen')
    parser.add_argument('--angle', type=float, default=None, help='Fährt Kanal auf diesen Winkel (mit --ch)')
    args = parser.parse_args()

    if args.scan:
        i2c_scan()
        return

    print("=== KUKA-ARM Servo-Test ===")
    print("Externe 5-6V Versorgung muss an V+/GND des PCA9685 angeschlossen sein!\n")

    pca = init_pca()

    if args.ch is not None:
        if args.angle is not None:
            print(f"Kanal {args.ch} → {args.angle}°")
            pca.channels[args.ch].duty_cycle = angle_to_duty(args.ch, args.angle)
            print("Drücke STRG+C zum Beenden.")
            try:
                while True: time.sleep(1)
            except KeyboardInterrupt:
                pca.channels[args.ch].duty_cycle = 0
        else:
            label = JOINT_MAP.get(args.ch, "")
            test_channel(pca, args.ch, label)
    else:
        print("Teste alle 6 Gelenke sequenziell...")
        print("Drücke STRG+C um abzubrechen.\n")
        try:
            for ch, label in JOINT_MAP.items():
                input(f"[ENTER] Kanal {ch} ({label}) testen...")
                test_channel(pca, ch, label)
        except KeyboardInterrupt:
            print("\nAbgebrochen.")
        finally:
            for ch in range(16):
                pca.channels[ch].duty_cycle = 0
            print("\nAlle Servos gestoppt. Test beendet.")


if __name__ == '__main__':
    main()
