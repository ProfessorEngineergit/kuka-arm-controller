// Frame switching – called from ui.js setFrame()
function updateFrameUI() {
  const f = State.frame;
  const ind = document.getElementById('frame-indicator');
  const vbg = document.getElementById('vp-frame-badge');
  const cpl = document.getElementById('cp-frame-label');
  if (ind) ind.textContent = f;
  if (vbg) vbg.textContent = f;
  if (cpl) cpl.textContent = f;

  const wBtn = document.getElementById('frame-world-btn');
  const tBtn = document.getElementById('frame-tcp-btn');
  if (wBtn) wBtn.className = 'mode-badge' + (f === 'WORLD' ? ' active' : '');
  if (tBtn) tBtn.className = 'mode-badge' + (f === 'TCP'   ? ' active' : '');
}
