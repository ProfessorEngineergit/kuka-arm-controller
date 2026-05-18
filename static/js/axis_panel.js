// Axis sliders in the right panel
// 5-DOF: Metal MG996R (J1), MG996R (J2), MG90S (J3/J4/J5)
const JOINT_LABELS = ['J1 Basis', 'J2 Schulter', 'J3 Ellbogen', 'J4 Handgelenk', 'J5 Greifer'];
const JOINT_LIMITS = [
  [0, 180], [30, 150], [0, 160], [0, 180], [0, 90]
];

function buildAxisSliders() {
  const container = document.getElementById('axis-sliders');
  if (!container) return;
  container.innerHTML = '';

  JOINT_LABELS.forEach((label, i) => {
    const [mn, mx] = JOINT_LIMITS[i];
    const angle = State.joints[i] ?? 90;
    container.innerHTML += `
      <div class="axis-row" title="${label}">
        <span class="axis-label">J${i+1}</span>
        <input type="range" class="axis-slider" id="slider-j${i}"
               min="${mn}" max="${mx}" step="0.5" value="${angle}"
               oninput="onSliderInput(${i}, this.value)"
               onchange="onSliderCommit(${i}, this.value)">
        <span class="axis-value" id="val-j${i}">${angle.toFixed(0)}°</span>
      </div>`;
  });
}

function updateAxisSliders() {
  State.joints.forEach((angle, i) => {
    const slider = document.getElementById(`slider-j${i}`);
    const val    = document.getElementById(`val-j${i}`);
    if (slider) slider.value = angle;
    if (val)    val.textContent = angle.toFixed(0) + '°';
    if (slider) slider.disabled = State.estop || !State.enabled;
  });
}

// Live preview while dragging (updates 3D only, no servo command yet)
function onSliderInput(jointId, value) {
  const val = parseFloat(value);
  document.getElementById(`val-j${jointId}`).textContent = val.toFixed(0) + '°';
  // Update local state for 3D preview
  State.joints[jointId] = val;
  if (typeof updateRobot3D === 'function') updateRobot3D();
}

// Commit on mouseup / touchend → send to servo
let _sliderDebounce = null;
function onSliderCommit(jointId, value) {
  if (!State.enabled || State.estop) {
    // Revert slider to actual state
    updateAxisSliders();
    logEntry('Arm nicht freigegeben', 'warn');
    return;
  }
  clearTimeout(_sliderDebounce);
  _sliderDebounce = setTimeout(() => {
    sendWS({
      type: 'jog_abs',
      joint: jointId,
      angle: parseFloat(value),
      speed: State.speed,
    });
  }, 50);
}
