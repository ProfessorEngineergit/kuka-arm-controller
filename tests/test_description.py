"""The robot description (URDF, test script, README) must agree with
config/robot.yaml – audit finding 2 was three files disagreeing."""
import re
import subprocess
import sys

from app import config
from tests.conftest import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import generate_urdf  # noqa: E402
import test_servo  # noqa: E402


def test_urdf_matches_forward_kinematics():
    cfg = config.get()
    assert generate_urdf.verify(generate_urdf.build_urdf(cfg), cfg) < 1e-6


def test_checked_in_urdf_is_up_to_date():
    result = subprocess.run([sys.executable, "tools/generate_urdf.py", "--check"],
                            cwd=ROOT, capture_output=True, text=True,
                            env={"PATH": "/usr/bin:/bin"})
    assert result.returncode == 0, result.stderr


def test_urdf_zero_is_not_on_a_stop():
    """Audit finding 3: the URDF zero configuration must lie strictly inside
    every arm joint's limits (servo centre), not on an end stop."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring((ROOT / "description" / "kuka_arm.urdf").read_text())
    for joint in root.findall("joint[@type='revolute']"):
        limit = joint.find("limit")
        assert float(limit.get("lower")) < 0 < float(limit.get("upper")), joint.get("name")


def test_channels_unique_and_home_inside_limits():
    joints = config.get()["joints"]
    channels = [j["channel"] for j in joints]
    assert len(channels) == len(set(channels))
    for j in joints:
        assert 0 <= j["min_angle"] <= j["home_angle"] <= j["max_angle"] <= 180


def test_servo_test_script_reads_robot_yaml():
    info = test_servo.joint_info(config.load_file(ROOT / "config" / "robot.yaml"))
    for j, cfg_j in zip(info, config.load_file(ROOT / "config" / "robot.yaml")["joints"]):
        assert j["channel"] == cfg_j["channel"]
        assert (j["min"], j["max"], j["home"]) == (cfg_j["min_angle"], cfg_j["max_angle"], cfg_j["home_angle"])


def test_readme_channel_table_matches_robot_yaml():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cfg = config.load_file(ROOT / "config" / "robot.yaml")
    for j in cfg["joints"]:
        row = (rf"^\| \*\*{j['name']}\*\* \| {j['label']} \| {j['channel']} \| [^|]+ \| "
               rf"{j['min_angle']}–{j['max_angle']}° \| {j['home_angle']}° \|")
        assert re.search(row, readme, re.M), f"README-Zeile für {j['name']} fehlt oder weicht ab"
