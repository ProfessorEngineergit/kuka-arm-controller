// Coordinate frame management UI
function setFrame(frame) {
  if (frame !== 'WORLD' && frame !== 'TCP') return;
  sendWS({type: 'frame', frame});
  logEntry(`Frame → ${frame}`, 'info');
}

function updateFrameUI() {
  const frame = State.frame;

  // Right panel select
  const sel = document.getElementById('frame-select');
  if (sel) sel.value = frame;

  // Viewport badge
  const badge = document.getElementById('frame-badge');
  if (badge) badge.textContent = frame;

  // Coordinate panel cards
  const worldCheck = document.getElementById('frame-world-check');
  const tcpCheck   = document.getElementById('frame-tcp-check');
  if (worldCheck) worldCheck.textContent = frame === 'WORLD' ? '●' : '○';
  if (tcpCheck)   tcpCheck.textContent   = frame === 'TCP'   ? '●' : '○';
  if (worldCheck) worldCheck.style.color = frame === 'WORLD' ? 'var(--orange)' : 'var(--text-dim)';
  if (tcpCheck)   tcpCheck.style.color   = frame === 'TCP'   ? 'var(--orange)' : 'var(--text-dim)';
}
