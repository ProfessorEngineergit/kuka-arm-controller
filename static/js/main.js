// ── WebSocket ────────────────────────────────────────────────
let _ws = null;
let _wsRetry = null;

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  _ws = new WebSocket(`${proto}//${location.host}/ws`);

  _ws.onopen = () => {
    updateConnectionUI(true);
    logEntry('Verbunden ✓', 'ok');
    clearTimeout(_wsRetry);
  };

  _ws.onmessage = ev => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'state')   applyState(msg);
      if (msg.type === 'warning') logEntry('⚠ ' + msg.msg, 'warn');
      if (msg.type === 'error')   logEntry('✕ ' + msg.msg, 'err');
    } catch { /* ignore */ }
  };

  _ws.onclose = () => {
    updateConnectionUI(false);
    logEntry('Verbindung getrennt – Reconnect…', 'warn');
    _wsRetry = setTimeout(connectWS, 3000);
  };

  _ws.onerror = () => _ws.close();
}

function sendWS(obj) {
  if (_ws && _ws.readyState === WebSocket.OPEN)
    _ws.send(JSON.stringify(obj));
}

setInterval(() => {
  if (_ws && _ws.readyState === WebSocket.OPEN)
    _ws.send(JSON.stringify({type: 'ping'}));
}, 25000);

// ── Keyboard shortcuts ────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.code  === 'Space')                { e.preventDefault(); triggerEstop(); }
  if (e.key   === 'f' || e.key === 'F')   toggleEnable();
  if (e.key   === 'h' || e.key === 'H')   goHome();
  if (e.key   === 'Escape')               acknowledgeEstop();
  // Digit keys 1-5: jog shortcuts (hold not supported via keyboard, single step)
});

// ── Init ──────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  // Load robot config (limits, labels, DH table for the 3D view)
  await reloadRobotConfig();
  RobotConfig.joints.forEach((j, i) => { State.joints[i] = j.home_angle; });
  if (RobotConfig.mock) {
    const kss = document.getElementById('sb-kss');
    if (kss) kss.textContent += ' · SIMULATION (kein PCA9685)';
  }

  // A failing optional view must never stop the control connection below.
  for (const [name, init] of [['Gelenkanzeige', buildJointBars], ['3D-Ansicht', initRobot3D],
                              ['Joysticks', initJoysticks]]) {
    try { init(); } catch (e) { console.error(e); logEntry(`${name} nicht verfügbar: ${e.message}`, 'warn'); }
  }
  setStep(10);
  setNav('jog');

  connectWS();
  logEntry('KUKA-ARM smartPAD bereit', 'ok');
  logEntry('SPACE=E-Stop  F=Freigabe  H=Home  ESC=Quittieren', 'info');
});
