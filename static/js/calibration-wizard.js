// ── Interactive Calibration Wizard ────────────────────────
let _wizardState = {
  currentJoint: null,
  jointNames: ['J1 Basis', 'J2 Schulter', 'J3 Ellbogen', 'J4 Handgelenk', 'J5 Handgelenk Roll'],
  calibData: {},
  zeroPoints: {},
  minLimits: {},
  maxLimits: {},
  calibrated: new Set(),   // joints the user has actually touched in this run
  jogDir: 0,
};

// Absolute mechanical servo range – the wizard never lets the user save
// anything outside this; the server enforces the same independently.
const WIZARD_ABS_MIN = 0;
const WIZARD_ABS_MAX = 180;

function startCalibrationWizard() {
  showPanel('calib-wizard');
  wizardInitialize();
}

function wizardInitialize() {
  // Reset state
  _wizardState.calibData = {};
  _wizardState.zeroPoints = {};
  _wizardState.minLimits = {};
  _wizardState.maxLimits = {};
  _wizardState.calibrated = new Set();

  // Seed from the CURRENT live config/state so untouched joints keep their
  // existing calibration (we only persist joints the user actually edits).
  for (let i = 0; i < 5; i++) {
    _wizardState.minLimits[i] = JOINT_LIMITS[i][0];
    _wizardState.maxLimits[i] = JOINT_LIMITS[i][1];
    _wizardState.zeroPoints[i] = (State.joints[i] ?? 90);
  }

  // Show initial screen
  document.getElementById('wizard-initial').style.display = 'flex';
  document.getElementById('wizard-content').style.display = 'none';
}

function wizardStartSetup() {
  document.getElementById('wizard-initial').style.display = 'none';
  document.getElementById('wizard-content').style.display = 'block';
  wizardShowSelectScreen();
}

function wizardShowSelectScreen() {
  // Hide all steps
  document.getElementById('wizard-step-select').style.display = 'flex';
  document.getElementById('wizard-step-setup').style.display = 'none';
  document.getElementById('wizard-step-limits').style.display = 'none';
  document.getElementById('wizard-step-summary').style.display = 'none';

  // Generate joint selection buttons
  const container = document.getElementById('wizard-joint-buttons');
  container.innerHTML = '';
  for (let i = 0; i < 5; i++) {
    const btn = document.createElement('button');
    btn.className = 'btn btn-orange';
    btn.style.padding = '10px';
    btn.textContent = _wizardState.jointNames[i];
    btn.onclick = () => wizardSelectJoint(i);
    container.appendChild(btn);
  }
}

function wizardSelectJoint(jointIdx) {
  _wizardState.currentJoint = jointIdx;
  wizardShowSetupStep();
}

function wizardShowSetupStep() {
  const j = _wizardState.currentJoint;
  const jointLabel = _wizardState.jointNames[j];

  // Hide other steps
  document.getElementById('wizard-step-select').style.display = 'none';
  document.getElementById('wizard-step-setup').style.display = 'flex';
  document.getElementById('wizard-step-limits').style.display = 'none';
  document.getElementById('wizard-step-summary').style.display = 'none';

  // Update label and angle display
  document.getElementById('wizard-joint-label').textContent = jointLabel;
  document.getElementById('wizard-current-angle').textContent = State.joints[j].toFixed(1) + '°';
}

function wizardSetZeroPoint() {
  const j = _wizardState.currentJoint;
  _wizardState.zeroPoints[j] = State.joints[j];
  _wizardState.calibrated.add(j);
  logEntry(`${_wizardState.jointNames[j]}: Nullpunkt auf ${State.joints[j].toFixed(1)}° gesetzt`, 'ok');
  wizardShowLimitsStep();
}

function wizardShowLimitsStep() {
  const j = _wizardState.currentJoint;
  const jointLabel = _wizardState.jointNames[j];

  document.getElementById('wizard-step-setup').style.display = 'none';
  document.getElementById('wizard-step-limits').style.display = 'flex';

  document.getElementById('wizard-joint-label2').textContent = jointLabel;

  // Update displayed limits
  document.getElementById('wizard-min-val').textContent = _wizardState.minLimits[j].toFixed(0) + '°';
  document.getElementById('wizard-max-val').textContent = _wizardState.maxLimits[j].toFixed(0) + '°';
  document.getElementById('wizard-min-set').textContent = _wizardState.minLimits[j].toFixed(0) + '°';
  document.getElementById('wizard-max-set').textContent = _wizardState.maxLimits[j].toFixed(0) + '°';
}

let _wizardJogInterval = null;

function wizardMoveJoint(direction) {
  if (!State.enabled || State.estop) { logEntry('Arm nicht freigegeben', 'warn'); return; }
  _wizardState.jogDir = direction;
  const j = _wizardState.currentJoint;
  const step = 1; // 1 degree per tick
  _wizardJogInterval = setInterval(() => {
    if (!State.enabled || State.estop) { wizardStopJoint(); return; }
    sendWS({type: 'jog', joint: j, delta: direction * step, speed: 20});
  }, 100);
}

function wizardStopJoint() {
  clearInterval(_wizardJogInterval);
  _wizardJogInterval = null;
}

function _wizardClamp(v) {
  return Math.max(WIZARD_ABS_MIN, Math.min(WIZARD_ABS_MAX, Math.round(v)));
}

function wizardSetMinLimit() {
  const j = _wizardState.currentJoint;
  _wizardState.minLimits[j] = _wizardClamp(State.joints[j]);
  _wizardState.calibrated.add(j);
  document.getElementById('wizard-min-set').textContent = _wizardState.minLimits[j].toFixed(0) + '°';
  document.getElementById('wizard-min-val').textContent = _wizardState.minLimits[j].toFixed(0) + '°';
  logEntry(`${_wizardState.jointNames[j]}: Min = ${_wizardState.minLimits[j]}°`, 'ok');
}

function wizardSetMaxLimit() {
  const j = _wizardState.currentJoint;
  _wizardState.maxLimits[j] = _wizardClamp(State.joints[j]);
  _wizardState.calibrated.add(j);
  document.getElementById('wizard-max-set').textContent = _wizardState.maxLimits[j].toFixed(0) + '°';
  document.getElementById('wizard-max-val').textContent = _wizardState.maxLimits[j].toFixed(0) + '°';
  logEntry(`${_wizardState.jointNames[j]}: Max = ${_wizardState.maxLimits[j]}°`, 'ok');
}

function _wizardValidateJoint(j) {
  // Returns an error string, or null if the joint's envelope is safe.
  const mn = _wizardState.minLimits[j];
  const mx = _wizardState.maxLimits[j];
  const hm = _wizardState.zeroPoints[j];
  if (mn >= mx) return `Min (${mn}°) muss kleiner als Max (${mx}°) sein`;
  if (hm < mn || hm > mx) return `Nullpunkt (${hm.toFixed(1)}°) liegt außerhalb [${mn}°, ${mx}°]`;
  return null;
}

function wizardNextJoint() {
  const j = _wizardState.currentJoint;
  const err = _wizardValidateJoint(j);
  if (err) {
    logEntry(`${_wizardState.jointNames[j]}: ${err}`, 'err');
    alert(`${_wizardState.jointNames[j]}\n\n${err}\n\nBitte korrigieren, bevor Sie fortfahren.`);
    return;
  }
  if (j < 4) {
    _wizardState.currentJoint = j + 1;
    wizardShowSetupStep();
  } else {
    wizardShowSummaryStep();
  }
}

function wizardShowSummaryStep() {
  document.getElementById('wizard-step-setup').style.display = 'none';
  document.getElementById('wizard-step-limits').style.display = 'none';
  document.getElementById('wizard-step-summary').style.display = 'flex';

  // Generate summary
  const summaryList = document.getElementById('wizard-summary-list');
  summaryList.innerHTML = '';
  for (let i = 0; i < 5; i++) {
    const entry = document.createElement('div');
    entry.style.padding = '6px 0';
    entry.style.borderBottom = '1px solid var(--border)';
    entry.innerHTML = `
      <div style="color:var(--orange);font-weight:700;">${_wizardState.jointNames[i]}</div>
      <div>Zero: ${_wizardState.zeroPoints[i].toFixed(1)}°</div>
      <div>Min: ${_wizardState.minLimits[i].toFixed(0)}° | Max: ${_wizardState.maxLimits[i].toFixed(0)}°</div>
    `;
    summaryList.appendChild(entry);
  }
}

function wizardCancelStep() {
  wizardShowSelectScreen();
}

function wizardCancel() {
  showPanel('calibration');
  wizardInitialize();
}

async function _wizardPostField(joint, field, value) {
  const resp = await fetch('/api/calibrate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({joint, field, value}),
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try { detail = (await resp.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return resp.json();
}

async function wizardSaveAll() {
  const targets = [..._wizardState.calibrated].sort((a, b) => a - b);
  if (targets.length === 0) {
    logEntry('Keine Gelenke kalibriert – nichts zu speichern', 'warn');
    return;
  }

  // Pre-flight: validate every joint client-side so we never write a
  // partial/inconsistent calibration to the robot.
  for (const j of targets) {
    const err = _wizardValidateJoint(j);
    if (err) {
      logEntry(`${_wizardState.jointNames[j]}: ${err}`, 'err');
      alert(`Speichern abgebrochen.\n\n${_wizardState.jointNames[j]}: ${err}`);
      return;
    }
  }

  try {
    for (const j of targets) {
      // Order matters: widen max first so an intermediate min>max state
      // can't be rejected by the server's coherence check.
      await _wizardPostField(j, 'max_angle', _wizardState.maxLimits[j]);
      await _wizardPostField(j, 'min_angle', _wizardState.minLimits[j]);
      await _wizardPostField(j, 'home_angle', _wizardState.zeroPoints[j]);
      JOINT_LIMITS[j] = [_wizardState.minLimits[j], _wizardState.maxLimits[j]];
    }
    logEntry(`Kalibrierung gespeichert ✓ (${targets.length} Gelenk(e))`, 'ok');
    showPanel('calibration');
    if (typeof buildCalibRows === 'function') buildCalibRows();
    wizardInitialize();
  } catch (e) {
    logEntry('Fehler beim Speichern: ' + e.message, 'err');
    alert('Speichern fehlgeschlagen:\n\n' + e.message +
          '\n\nDie Kalibrierung wurde möglicherweise nur teilweise übernommen.');
  }
}
