// Joint angle bars in left panel (read-only display, not sliders)
const JOINT_LABELS = ['J1 Basis', 'J2 Schulter', 'J3 Ellbogen', 'J4 Handgelenk', 'J5 Greifer'];
const JOINT_LIMITS = [[0,180],[30,150],[0,160],[0,180],[0,90]];

function buildJointBars() {
  const container = document.getElementById('joint-bars');
  if (!container) return;
  container.innerHTML = '';
  JOINT_LABELS.forEach((label, i) => {
    const [mn, mx] = JOINT_LIMITS[i];
    const angle = State.joints[i] ?? 0;
    const pct = ((angle - mn) / (mx - mn)) * 100;
    container.innerHTML += `
      <div class="joint-row" title="${label}">
        <span class="joint-key">J${i+1}</span>
        <div class="joint-bar-bg">
          <div class="joint-bar-fill" id="jbar-${i}" style="width:${pct}%"></div>
        </div>
        <span class="joint-val" id="jval-${i}">${angle.toFixed(0)}°</span>
      </div>`;
  });
}

function updateJointBars() {
  State.joints.forEach((angle, i) => {
    const [mn, mx] = JOINT_LIMITS[i] || [0, 180];
    const pct = Math.max(0, Math.min(100, ((angle - mn) / (mx - mn)) * 100));
    const bar = document.getElementById(`jbar-${i}`);
    const val = document.getElementById(`jval-${i}`);
    if (bar) bar.style.width = pct + '%';
    if (val) val.textContent = angle.toFixed(0) + '°';
  });
}
