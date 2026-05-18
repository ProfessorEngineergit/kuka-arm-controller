// Main app entry point – WebSocket management + init
let _ws = null;
let _wsRetry = null;
const WS_RETRY_MS = 3000;

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url   = `${proto}//${location.host}/ws`;

  _ws = new WebSocket(url);

  _ws.onopen = () => {
    updateConnectionUI(true);
    logEntry('WebSocket verbunden ✓', 'ok');
    clearTimeout(_wsRetry);
  };

  _ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'state')   applyState(msg);
      if (msg.type === 'warning') logEntry('⚠ ' + msg.msg, 'warn');
      if (msg.type === 'error')   logEntry('✕ ' + msg.msg, 'error');
      if (msg.type === 'pong')    return;
    } catch { /* ignore malformed */ }
  };

  _ws.onclose = () => {
    updateConnectionUI(false);
    logEntry('WebSocket getrennt – versuche Reconnect…', 'warn');
    _wsRetry = setTimeout(connectWS, WS_RETRY_MS);
  };

  _ws.onerror = () => {
    _ws.close();
  };
}

function sendWS(obj) {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify(obj));
  }
}

// Keepalive ping every 30 s to prevent inactivity disconnect
setInterval(() => {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify({type: 'ping'}));
  }
}, 30_000);

// ── Keyboard shortcuts ────────────────────────────────────────
// Space → E-Stop | F → toggle Freigabe | H → Home | 1-6 = select axis
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return;
  if (e.code === 'Space') { e.preventDefault(); triggerEstop(); }
  if (e.key  === 'f' || e.key === 'F') toggleEnable();
  if (e.key  === 'h' || e.key === 'H') goHome();
  if (e.key  === 'Escape') acknowledgeEstop();
});

// ── Init ──────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  // Auth check
  const authRes = await fetch('/api/auth-check');
  const authData = await authRes.json();
  if (!authData.authenticated) {
    window.location.href = '/';
    return;
  }

  // Load robot config to set slider limits
  try {
    const cfgRes  = await fetch('/api/config');
    const cfg     = await cfgRes.json();
    cfg.joints.forEach((j, i) => {
      JOINT_LIMITS[i] = [j.min_angle, j.max_angle];
      State.joints[i] = j.home_angle;
    });
  } catch { /* use defaults */ }

  // Build UI
  buildAxisSliders();
  initRobot3D();
  initJoysticks();
  setStep(10);

  // Connect WebSocket
  connectWS();

  logEntry('KUKA-ARM Controller bereit', 'ok');
  logEntry('Leertaste = E-Stop | F = Freigabe | H = Home', 'info');
});
