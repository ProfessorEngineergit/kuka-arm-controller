// ── Robot configuration (GET /api/config) ─────────────────────
// Defaults mirror config/robot.yaml; main.js replaces them with the live
// values on startup and after every calibration.
const RobotConfig = {
  joints: [
    {name: 'J1', label: 'Basis',      type: 'revolute', servo_type: 'mg996r_metal', min_angle: 0,  max_angle: 180, home_angle: 90},
    {name: 'J2', label: 'Schulter',   type: 'revolute', servo_type: 'mg996r',       min_angle: 30, max_angle: 150, home_angle: 90},
    {name: 'J3', label: 'Ellbogen',   type: 'revolute', servo_type: 'mg90s',        min_angle: 0,  max_angle: 160, home_angle: 90},
    {name: 'J4', label: 'Handgelenk', type: 'revolute', servo_type: 'mg90s',        min_angle: 0,  max_angle: 180, home_angle: 90},
    {name: 'J5', label: 'Greifer',    type: 'gripper',  servo_type: 'mg90s',        min_angle: 0,  max_angle: 90,  home_angle: 0},
  ],
  dh_parameters: [[0, 90, 60, 0], [100, 0, 0, 0], [90, 0, 0, 0], [0, 90, 0, 0], [0, 0, 55, 0]],
  servos: {default_speed: 8, types: {}},
  mock: false,
};

function applyRobotConfig(cfg) {
  if (!cfg || !Array.isArray(cfg.joints)) return;
  RobotConfig.joints = cfg.joints;
  if (Array.isArray(cfg.dh_parameters)) RobotConfig.dh_parameters = cfg.dh_parameters;
  if (cfg.servos) RobotConfig.servos = cfg.servos;
  RobotConfig.mock = !!cfg.mock;
  cfg.joints.forEach((j, i) => {
    JOINT_LIMITS[i] = [j.min_angle, j.max_angle];
    JOINT_LABELS[i] = `${j.name} ${j.label}`;
  });
}

async function reloadRobotConfig() {
  try {
    applyRobotConfig(await fetch('/api/config').then(r => r.json()));
  } catch { /* keep defaults */ }
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

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
  if (name === 'prog') showPanel('programs');
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
  if (name === 'programs')    loadPrograms();
  if (name === 'calibration') buildCalibRows();
  if (name === 'settings') {
    const inp = document.getElementById('inp-speed');
    if (inp) inp.value = RobotConfig.servos.default_speed;
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

// Saves the base speed (°/s) from the settings panel. The override slider is
// a per-move percentage of this value and is not persisted.
async function saveSpeed() {
  const speed = parseFloat(document.getElementById('inp-speed')?.value);
  const resp = await fetch('/api/config/speed', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({speed}),
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try { detail = (await resp.json()).detail || detail; } catch { /* ignore */ }
    logEntry('Geschwindigkeit nicht gespeichert: ' + detail, 'err');
    return;
  }
  await reloadRobotConfig();
  logEntry(`Geschwindigkeit gespeichert: ${speed} °/s`, 'ok');
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
// Rows are always seeded from the live robot.yaml values, so pressing
// "Speichern" without edits writes back exactly what is configured.
function buildCalibRows() {
  const container = document.getElementById('calib-rows');
  if (!container) return;
  container.innerHTML = '';
  RobotConfig.joints.forEach((j, i) => {
    container.innerHTML += `
      <div class="calib-row">
        <span class="calib-jlabel">${escapeHtml(j.name)}</span>
        <span style="font-size:10px;color:var(--t3);width:80px;">${escapeHtml(j.label)}<br><em style="font-size:9px">${escapeHtml(j.servo_type)} · ch${escapeHtml(j.channel)}</em></span>
        <div class="calib-inputs">
          <div class="calib-field"><label>Min</label><input type="number" id="c-min-${i}" value="${j.min_angle}" min="0" max="180"></div>
          <div class="calib-field"><label>Home</label><input type="number" id="c-home-${i}" value="${j.home_angle}" min="0" max="180"></div>
          <div class="calib-field"><label>Max</label><input type="number" id="c-max-${i}" value="${j.max_angle}" min="0" max="180"></div>
        </div>
        <button class="btn" style="font-size:10px;padding:3px 6px;" title="Aktuelle Stellung als Home übernehmen" onclick="captureJoint(${i})">←</button>
      </div>`;
  });
}

function captureJoint(i) {
  const el = document.getElementById(`c-home-${i}`);
  if (el) el.value = State.joints[i].toFixed(1);
}

async function saveCalibration() {
  const changed = [];
  RobotConfig.joints.forEach((j, i) => {
    const val = key => parseFloat(document.getElementById(`c-${key}-${i}`)?.value);
    const next = {min_angle: val('min'), home_angle: val('home'), max_angle: val('max')};
    if (Object.values(next).some(v => !Number.isFinite(v))) return;
    if (next.min_angle === j.min_angle && next.max_angle === j.max_angle &&
        next.home_angle === j.home_angle) return;
    changed.push([i, next]);
  });
  if (!changed.length) { logEntry('Keine Änderungen', 'info'); return; }

  try {
    for (const [i, next] of changed) {
      if (next.min_angle >= next.max_angle) throw new Error(`${RobotConfig.joints[i].name}: Min muss kleiner als Max sein`);
      // Widen first, so an intermediate state can never be min > max.
      const order = next.max_angle >= RobotConfig.joints[i].max_angle
        ? ['max_angle', 'min_angle', 'home_angle'] : ['min_angle', 'max_angle', 'home_angle'];
      for (const field of order) {
        const resp = await fetch('/api/calibrate', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({joint: i, field, value: next[field]}),
        });
        if (!resp.ok) {
          let detail = `HTTP ${resp.status}`;
          try { detail = (await resp.json()).detail || detail; } catch { /* ignore */ }
          throw new Error(`${RobotConfig.joints[i].name}: ${detail}`);
        }
      }
    }
    logEntry(`Kalibrierung gespeichert ✓ (${changed.length} Gelenk(e))`, 'ok');
  } catch (e) {
    logEntry('Kalibrierung fehlgeschlagen: ' + e.message, 'err');
  }
  await reloadRobotConfig();
  buildCalibRows();
  if (typeof buildJointBars === 'function') buildJointBars();
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
