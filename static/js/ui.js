// Global state mirrored from WebSocket
const State = {
  joints: [90, 90, 90, 90, 0],   // 5-DOF: Metal MG996R (J1), MG996R (J2), MG90S (J3-J5)
  pose: {x:0, y:0, z:0, a:0, b:0, c:0},
  enabled: false,
  estop: false,
  frame: 'WORLD',
  program: null,
  connected: false,
  speed: 30,          // percent
  cartStep: 10,       // mm/deg per button click
};

// ── Panel routing ──────────────────────────────────────────
let _activePanel = null;

function showPanel(name) {
  document.querySelectorAll('.content-panel').forEach(p => p.classList.remove('visible'));
  document.querySelectorAll('.sidebar-btn').forEach(b => b.classList.remove('active'));

  if (_activePanel === name) {
    _activePanel = null;
    return;
  }
  _activePanel = name;
  const panel = document.getElementById('panel-' + name);
  if (panel) panel.classList.add('visible');

  const btn = document.querySelector(`[onclick="showPanel('${name}')"]`);
  if (btn) btn.classList.add('active');

  if (name === 'programs') loadPrograms();
  if (name === 'calibration') buildCalibRows();
}

// ── E-Stop ──────────────────────────────────────────────────
function triggerEstop() {
  sendWS({type: 'estop'});
}

function acknowledgeEstop() {
  if (!confirm('E-Stop quittieren und Arm wieder freigeben?')) return;
  sendWS({type: 'acknowledge'});
}

function updateEstopUI() {
  const badge  = document.getElementById('header-estop-badge');
  const ackBtn = document.getElementById('btn-acknowledge');
  const msg    = document.getElementById('estop-msg');

  if (State.estop) {
    badge.style.display  = 'inline';
    ackBtn.classList.add('visible');
    msg.textContent      = 'E-STOP AKTIV – Arm gesperrt';
    document.body.style.setProperty('--estop-indicator', '1');
  } else {
    badge.style.display  = 'none';
    ackBtn.classList.remove('visible');
    msg.textContent      = '';
  }
}

// ── Enable / Disable ────────────────────────────────────────
function toggleEnable() {
  if (State.estop) { logEntry('E-Stop aktiv – erst quittieren', 'warn'); return; }
  if (State.enabled) {
    sendWS({type: 'disable'});
  } else {
    sendWS({type: 'enable'});
  }
}

function disableArm() {
  sendWS({type: 'disable'});
}

function updateEnableUI() {
  const btn = document.getElementById('btn-enable');
  if (State.enabled) {
    btn.textContent = 'FREIGABE ✓';
    btn.classList.add('enabled');
  } else {
    btn.textContent = 'FREIGABE';
    btn.classList.remove('enabled');
  }
}

// ── Home ────────────────────────────────────────────────────
function goHome() {
  if (!State.enabled || State.estop) { logEntry('Arm nicht freigegeben', 'warn'); return; }
  sendWS({type: 'home'});
  logEntry('→ Home-Position', 'info');
}

// ── Connection status ────────────────────────────────────────
function updateConnectionUI(connected) {
  State.connected = connected;
  const dot   = document.getElementById('status-dot');
  const label = document.getElementById('status-label');
  dot.classList.toggle('connected', connected);
  label.textContent = connected ? 'VERBUNDEN' : 'GETRENNT';
}

// ── Pose display ─────────────────────────────────────────────
function updatePoseDisplay() {
  const p = State.pose;
  document.getElementById('pose-x').textContent = p.x + ' mm';
  document.getElementById('pose-y').textContent = p.y + ' mm';
  document.getElementById('pose-z').textContent = p.z + ' mm';
  document.getElementById('pose-a').textContent = p.a + '°';
  document.getElementById('pose-b').textContent = p.b + '°';
  document.getElementById('pose-c').textContent = p.c + '°';
  document.getElementById('ov-x').textContent = p.x;
  document.getElementById('ov-y').textContent = p.y;
  document.getElementById('ov-z').textContent = p.z;
  const full = document.getElementById('full-pose-display');
  if (full) full.innerHTML =
    `X: ${p.x} mm &nbsp; Y: ${p.y} mm &nbsp; Z: ${p.z} mm<br>` +
    `A: ${p.a}° &nbsp; B: ${p.b}° &nbsp; C: ${p.c}°`;
}

// ── Speed ────────────────────────────────────────────────────
function onSpeedChange(val) {
  State.speed = parseInt(val);
  document.getElementById('speed-display').textContent = val + '%';
}

function setStep(val) {
  State.cartStep = val;
  document.querySelectorAll('[id^="step-"]').forEach(b => b.classList.remove('btn-orange'));
  const el = document.getElementById('step-' + val);
  if (el) el.classList.add('btn-orange');
}

async function saveSpeed() {
  try {
    await fetch('/api/config/speed', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({speed: State.speed * 1.8}),
    });
    logEntry('Geschwindigkeit gespeichert', 'ok');
  } catch { logEntry('Fehler beim Speichern', 'error'); }
}

// ── Cartesian jog buttons ─────────────────────────────────────
function cartJog(delta) {
  if (!State.enabled || State.estop) { logEntry('Arm nicht freigegeben', 'warn'); return; }
  const s = State.cartStep;
  sendWS({
    type: 'cartesian',
    dx: (delta.dx || 0) * (s / 10),
    dy: (delta.dy || 0) * (s / 10),
    dz: (delta.dz || 0) * (s / 10),
    da: (delta.da || 0) * (s / 10),
    db: (delta.db || 0) * (s / 10),
    dc: (delta.dc || 0) * (s / 10),
    frame: State.frame,
    speed: State.speed,
  });
}

// ── Calibration ──────────────────────────────────────────────
const _calibData = {};

function buildCalibRows() {
  const container = document.getElementById('calib-rows');
  // 5-DOF: Metal MG996R, MG996R, MG90S, MG90S, MG90S
  const labels = ['J1 Basis (Metal MG996R)', 'J2 Schulter (MG996R)', 'J3 Ellbogen (MG90S)', 'J4 Handgelenk (MG90S)', 'J5 Greifer (MG90S)'];
  container.innerHTML = '';
  State.joints.forEach((angle, i) => {
    _calibData[i] = _calibData[i] || {home_angle: angle, min_angle: 0, max_angle: 180};
    container.innerHTML += `
      <div class="calib-row">
        <span class="calib-label">J${i+1}</span>
        <span style="font-size:12px;color:var(--text-secondary);width:80px;">${labels[i]}</span>
        <div class="calib-inputs">
          <div class="calib-field">
            <label>Min</label>
            <input type="number" id="calib-min-${i}" value="${_calibData[i].min_angle}" min="0" max="180">
          </div>
          <div class="calib-field">
            <label>Home</label>
            <input type="number" id="calib-home-${i}" value="${_calibData[i].home_angle}" min="0" max="180">
          </div>
          <div class="calib-field">
            <label>Max</label>
            <input type="number" id="calib-max-${i}" value="${_calibData[i].max_angle}" min="0" max="180">
          </div>
        </div>
        <button class="btn" style="font-size:11px;padding:4px 8px;" onclick="setCalibHome(${i})">→ Jetzt</button>
      </div>`;
  });
}

function setCalibHome(i) {
  const el = document.getElementById(`calib-home-${i}`);
  if (el) el.value = State.joints[i].toFixed(1);
}

async function saveCalibration() {
  const n = State.joints.length;
  for (let i = 0; i < n; i++) {
    for (const field of ['min_angle', 'home_angle', 'max_angle']) {
      const key = field === 'min_angle' ? 'min' : field === 'home_angle' ? 'home' : 'max';
      const el = document.getElementById(`calib-${key}-${i}`);
      if (!el) continue;
      await fetch('/api/calibrate', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({joint: i, field, value: parseFloat(el.value)}),
      });
    }
  }
  logEntry('Kalibrierung gespeichert ✓', 'ok');
}

// ── Logout ───────────────────────────────────────────────────
async function logout() {
  await fetch('/api/logout', {method: 'POST'});
  window.location.href = '/';
}

// ── Log ──────────────────────────────────────────────────────
function logEntry(msg, level = 'info') {
  const out = document.getElementById('log-output');
  if (!out) return;
  const ts = new Date().toLocaleTimeString('de-DE');
  const div = document.createElement('div');
  div.className = `log-entry ${level}`;
  div.textContent = `[${ts}] ${msg}`;
  out.prepend(div);
  if (out.children.length > 200) out.lastChild.remove();
}

function clearLog() {
  const out = document.getElementById('log-output');
  if (out) out.innerHTML = '';
}

// ── Global state apply ───────────────────────────────────────
function applyState(data) {
  if (data.joints) State.joints = data.joints;
  if (data.pose)   State.pose   = data.pose;
  if ('enabled' in data) State.enabled = data.enabled;
  if ('estop' in data)   State.estop   = data.estop;
  if (data.frame)  State.frame  = data.frame;
  if ('program' in data) State.program = data.program;

  updateEstopUI();
  updateEnableUI();
  updatePoseDisplay();

  if (typeof updateAxisSliders === 'function') updateAxisSliders();
  if (typeof updateRobot3D === 'function')     updateRobot3D();
  if (typeof updateFrameUI === 'function')     updateFrameUI();
  if (typeof updateProgramUI === 'function')   updateProgramUI();
}
