// ── Global State ────────────────────────────────────────────
const State = {
  joints:    [90, 90, 90, 90, 0],
  pose:      {x:0, y:0, z:0, a:0, b:0, c:0},
  enabled:   false,
  estop:     false,
  frame:     'WORLD',
  program:   null,
  connected: false,
  override:  30,     // percent
  cartStep:  10,     // mm per button press
};

// ── Navigation ──────────────────────────────────────────────
let _activePanel = null;
let _activeNav   = 'jog';

function setNav(name) {
  _activeNav = name;
  document.querySelectorAll('.nav-section').forEach(s => s.style.display = 'none');
  const sec = document.getElementById('nav-' + name);
  if (sec) sec.style.display = 'block';
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  const tabs = document.querySelectorAll('.nav-tab');
  const idx = ['jog','prog','cfg'].indexOf(name);
  if (tabs[idx]) tabs[idx].classList.add('active');

  if (name === 'jog')  showPanel(null);
  if (name === 'prog') { showPanel('programs'); loadPrograms(); }
}

function showPanel(name) {
  document.querySelectorAll('.content-panel').forEach(p => p.classList.remove('visible'));
  document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('active'));
  _activePanel = name;

  if (name) {
    const p = document.getElementById('panel-' + name);
    if (p) p.classList.add('visible');
    const mi = document.getElementById('mi-' + name.replace('-','_').replace('-','_'));
    const mi2 = document.querySelector(`[onclick="showPanel('${name}')"]`);
    if (mi2) mi2.classList.add('active');
  }

  // Update vp mode badge
  const badges = {
    null: 'JOG', 'jog-joint': 'JOG', 'jog-cart': 'KART',
    programs: 'PROG', calibration: 'KALIB', settings: 'CFG', log: 'LOG',
  };
  const badge = document.getElementById('vp-mode-badge');
  if (badge) badge.textContent = badges[name] || 'JOG';
}

// ── E-Stop ──────────────────────────────────────────────────
function triggerEstop() {
  sendWS({type: 'estop'});
}

function acknowledgeEstop() {
  sendWS({type: 'acknowledge'});
}

function updateEstopUI() {
  const banner  = document.getElementById('estop-banner');
  const ackBtn  = document.getElementById('btn-ack');
  const ledStop = document.getElementById('led-estop');

  banner.classList.toggle('visible', State.estop);
  ackBtn.classList.toggle('visible', State.estop);

  ledStop.className = 'led ' + (State.estop ? 'red' : '');
}

// ── Enable / Disable ────────────────────────────────────────
function toggleEnable() {
  if (State.estop) { logEntry('E-Stop aktiv – erst quittieren', 'warn'); return; }
  sendWS({type: State.enabled ? 'disable' : 'enable'});
}

function goHome() {
  if (!State.enabled || State.estop) { logEntry('Arm nicht freigegeben', 'warn'); return; }
  sendWS({type: 'home'});
}

function updateEnableUI() {
  const btn     = document.getElementById('btn-enable');
  const ledEn   = document.getElementById('led-enable');
  const vsBadge = document.getElementById('vp-status-badge');

  btn.classList.toggle('enabled', State.enabled);
  btn.textContent = State.enabled ? 'FREIGABE ✓' : 'FREIGABE';

  ledEn.className = 'led ' + (State.enabled ? 'green' : '');

  if (vsBadge) {
    vsBadge.textContent = State.estop ? 'E-STOP' : (State.enabled ? 'AKTIV' : 'BEREIT');
    vsBadge.className   = 'vp-badge ' + (State.estop ? 'red' : (State.enabled ? 'green' : ''));
  }

  // Lock jog buttons when not enabled
  document.querySelectorAll('.jog-btn').forEach(b => {
    b.classList.toggle('locked', !State.enabled || State.estop);
  });
}

// ── Jog buttons (right panel, hold) ─────────────────────────
let _jogInterval = null;
const JOG_HZ = 20;

function startJog(joint, dir) {
  if (!State.enabled || State.estop) return;
  stopJog();
  const step = (State.override / 100) * 3;   // degrees per tick
  _jogInterval = setInterval(() => {
    if (!State.enabled || State.estop) { stopJog(); return; }
    sendWS({type: 'jog', joint, delta: dir * step, speed: State.override});
  }, 1000 / JOG_HZ);
}

function stopJog() {
  clearInterval(_jogInterval);
  _jogInterval = null;
}

// ── Cartesian jog ────────────────────────────────────────────
let _cartInterval = null;

function startCartJog(delta) {
  if (!State.enabled || State.estop) return;
  stopCartJog();
  _cartInterval = setInterval(() => {
    if (!State.enabled || State.estop) { stopCartJog(); return; }
    const s = State.cartStep / 10;
    sendWS({
      type: 'cartesian',
      dx: (delta.dx || 0) * s, dy: (delta.dy || 0) * s, dz: (delta.dz || 0) * s,
      da: (delta.da || 0) * s, db: (delta.db || 0) * s, dc: (delta.dc || 0) * s,
      frame: State.frame,
      speed: State.override,
    });
  }, 50);
}

function stopCartJog() {
  clearInterval(_cartInterval);
  _cartInterval = null;
}

function setStep(val) {
  State.cartStep = val;
  document.querySelectorAll('[id^="step-"]').forEach(b => {
    b.className = b.id === 'step-' + val ? 'btn btn-orange' : 'btn';
  });
}

// ── Override (speed) ─────────────────────────────────────────
function onOverrideChange(val) {
  State.override = parseInt(val);
  const el = document.getElementById('override-value');
  if (el) el.textContent = val;
}

async function saveSpeed() {
  await fetch('/api/config/speed', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({speed: State.override * 1.8}),
  });
  logEntry('Geschwindigkeit gespeichert', 'ok');
}

// ── Frame ────────────────────────────────────────────────────
function setFrame(frame) {
  sendWS({type: 'frame', frame});
}

function updateFrameUI() {
  const f = State.frame;

  document.getElementById('frame-indicator').textContent = f;
  document.getElementById('vp-frame-badge').textContent  = f;
  const cpLabel = document.getElementById('cp-frame-label');
  if (cpLabel) cpLabel.textContent = f;

  const wBtn = document.getElementById('frame-world-btn');
  const tBtn = document.getElementById('frame-tcp-btn');
  if (wBtn) { wBtn.className = 'mode-badge' + (f === 'WORLD' ? ' active' : ''); }
  if (tBtn) { tBtn.className = 'mode-badge' + (f === 'TCP'   ? ' active' : ''); }
}

// ── Pose display ─────────────────────────────────────────────
function updatePoseDisplay() {
  const p = State.pose;
  document.getElementById('p-x').textContent = p.x + ' mm';
  document.getElementById('p-y').textContent = p.y + ' mm';
  document.getElementById('p-z').textContent = p.z + ' mm';
  document.getElementById('p-a').textContent = p.a + '°';
  document.getElementById('p-b').textContent = p.b + '°';
  document.getElementById('p-c').textContent = p.c + '°';
  document.getElementById('ov-x').textContent = p.x;
  document.getElementById('ov-y').textContent = p.y;
  document.getElementById('ov-z').textContent = p.z;
}

// ── Connection ───────────────────────────────────────────────
function updateConnectionUI(connected) {
  State.connected = connected;
  const ledConn = document.getElementById('led-conn');
  if (ledConn) ledConn.className = 'led ' + (connected ? 'green' : '');
  const label = document.getElementById('sb-conn-label');
  if (label) label.textContent = connected ? 'VERBUNDEN' : 'GETRENNT';
  if (!connected) {
    const badge = document.getElementById('vp-status-badge');
    if (badge) { badge.textContent = 'OFFLINE'; badge.className = 'vp-badge'; }
  }
}

// ── Calibration ──────────────────────────────────────────────
const JOINT_SERVO_LABELS = [
  'Metal MG996R', 'MG996R', 'MG90S', 'MG90S', 'MG90S'
];
const _calibData = {};

function buildCalibRows() {
  const container = document.getElementById('calib-rows');
  if (!container) return;
  const jnames = ['Basis', 'Schulter', 'Ellbogen', 'Handgelenk', 'Greifer'];
  container.innerHTML = '';
  State.joints.forEach((angle, i) => {
    _calibData[i] = _calibData[i] || {min_angle: 0, home_angle: angle, max_angle: 180};
    container.innerHTML += `
      <div class="calib-row">
        <span class="calib-jlabel">J${i+1}</span>
        <span style="font-size:10px;color:var(--t3);width:80px;">${jnames[i]}<br><em style="font-size:9px">${JOINT_SERVO_LABELS[i]}</em></span>
        <div class="calib-inputs">
          <div class="calib-field"><label>Min</label><input type="number" id="c-min-${i}" value="0" min="0" max="180"></div>
          <div class="calib-field"><label>Home</label><input type="number" id="c-home-${i}" value="${angle.toFixed(0)}" min="0" max="180"></div>
          <div class="calib-field"><label>Max</label><input type="number" id="c-max-${i}" value="180" min="0" max="180"></div>
        </div>
        <button class="btn" style="font-size:10px;padding:3px 6px;" onclick="captureJoint(${i})">←</button>
      </div>`;
  });
}

function captureJoint(i) {
  const el = document.getElementById(`c-home-${i}`);
  if (el) el.value = State.joints[i].toFixed(1);
}

async function saveCalibration() {
  for (let i = 0; i < 5; i++) {
    for (const [field, key] of [['min_angle','min'],['home_angle','home'],['max_angle','max']]) {
      const el = document.getElementById(`c-${key}-${i}`);
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

// ── Programs UI ──────────────────────────────────────────────
function updateProgramUI() {
  const nameEl  = document.getElementById('running-prog');
  const stopBtn = document.getElementById('btn-stop-prog');
  const bbProg  = document.getElementById('bb-prog');
  if (nameEl)  nameEl.textContent = State.program || '—';
  if (stopBtn) stopBtn.style.display = State.program ? 'block' : 'none';
  if (bbProg)  bbProg.textContent = State.program ? '▶ ' + State.program : '—';
}

// ── Log ──────────────────────────────────────────────────────
function logEntry(msg, level = 'info') {
  const out = document.getElementById('log-output');
  if (!out) return;
  const ts  = new Date().toLocaleTimeString('de-DE');
  const div = document.createElement('div');
  div.className = `log-line ${level}`;
  div.textContent = `[${ts}] ${msg}`;
  out.prepend(div);
  if (out.children.length > 300) out.lastChild.remove();
}

function clearLog() {
  const out = document.getElementById('log-output');
  if (out) out.innerHTML = '';
}

// ── Clock ────────────────────────────────────────────────────
function _updateClock() {
  const el = document.getElementById('sb-time');
  if (el) el.textContent = new Date().toLocaleTimeString('de-DE');
}
setInterval(_updateClock, 1000);
_updateClock();

// ── Apply full state from WebSocket ─────────────────────────
function applyState(data) {
  if (data.joints)            State.joints  = data.joints;
  if (data.pose)              State.pose    = data.pose;
  if ('enabled' in data)      State.enabled = data.enabled;
  if ('estop'   in data)      State.estop   = data.estop;
  if (data.frame)             State.frame   = data.frame;
  if ('program' in data)      State.program = data.program;

  updateEstopUI();
  updateEnableUI();
  updatePoseDisplay();
  updateFrameUI();
  updateProgramUI();

  if (typeof updateJointBars  === 'function') updateJointBars();
  if (typeof updateRobot3D    === 'function') updateRobot3D();
}

// ── Backup / Restore ────────────────────────────────────────
async function exportBackup() {
  try {
    const resp = await fetch('/api/backup/export');
    if (!resp.ok) { logEntry('Backup-Export fehlgeschlagen', 'err'); return; }
    const blob = await resp.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = resp.headers.get('content-disposition')?.split('filename=')[1]?.trim() || 'kuka-backup.zip';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    logEntry('Backup exportiert ✓', 'ok');
  } catch (e) {
    logEntry('Backup-Export Fehler: ' + e.message, 'err');
  }
}

function triggerRestoreUpload() {
  document.getElementById('restore-file-input').click();
}

async function importBackup(event) {
  const file = event.target.files[0];
  if (!file) return;

  try {
    const formData = new FormData();
    formData.append('file', file);

    const resp = await fetch('/api/backup/import', {
      method: 'POST',
      body: formData,
    });

    if (!resp.ok) {
      const err = await resp.json();
      logEntry('Fehler: ' + (err.detail || 'Unbekannter Fehler'), 'err');
      return;
    }

    logEntry('Backup wiederhergestellt ✓', 'ok');
    // Reload config after restore
    location.reload();
  } catch (e) {
    logEntry('Backup-Import Fehler: ' + e.message, 'err');
  }

  // Clear file input
  event.target.value = '';
}
