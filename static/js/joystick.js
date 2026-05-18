// Virtual Joystick control via nipplejs
// Left joystick  → J1 (base yaw) + J2 (shoulder)  OR  X/Y cartesian
// Right joystick → J3 (elbow) + J4 (wrist)         OR  Z/rotation

let _leftJoy = null, _rightJoy = null;
let _leftVec = {x:0, y:0}, _rightVec = {x:0, y:0};
let _jogTimer = null;
const JOG_HZ    = 20;      // commands per second
const JOG_SPEED = 2.0;     // degrees per tick at full deflection
const CART_SPEED = 3.0;    // mm per tick at full deflection

function initJoysticks() {
  if (typeof nipplejs === 'undefined') return;

  const opts = {
    mode: 'static',
    position: {left: '50%', top: '50%'},
    color: '#ff6b00',
    size: 72,
    threshold: 0.1,
  };

  _leftJoy = nipplejs.create({zone: document.getElementById('joystick-left'), ...opts});
  _rightJoy = nipplejs.create({zone: document.getElementById('joystick-right'), ...opts});

  _leftJoy.on('move', (e, d) => {
    const r = d.distance / 36;  // normalise 0–1
    _leftVec = {
      x: Math.cos(d.angle.radian) * Math.min(r, 1),
      y: Math.sin(d.angle.radian) * Math.min(r, 1),
    };
  });
  _leftJoy.on('end', () => { _leftVec = {x:0, y:0}; });

  _rightJoy.on('move', (e, d) => {
    const r = d.distance / 36;
    _rightVec = {
      x: Math.cos(d.angle.radian) * Math.min(r, 1),
      y: Math.sin(d.angle.radian) * Math.min(r, 1),
    };
  });
  _rightJoy.on('end', () => { _rightVec = {x:0, y:0}; });

  _jogTimer = setInterval(_sendJogFromJoysticks, 1000 / JOG_HZ);
}

function _sendJogFromJoysticks() {
  if (!State.enabled || State.estop) return;
  const lx = _leftVec.x, ly = _leftVec.y;
  const rx = _rightVec.x, ry = _rightVec.y;
  if (Math.abs(lx) < 0.05 && Math.abs(ly) < 0.05 &&
      Math.abs(rx) < 0.05 && Math.abs(ry) < 0.05) return;

  if (State.frame === 'WORLD' || State.frame === 'TCP') {
    // Cartesian mode
    sendWS({
      type: 'cartesian',
      dx:  lx * CART_SPEED,
      dy:  ly * CART_SPEED,
      dz:  ry * CART_SPEED,
      da: -rx * JOG_SPEED,
      frame: State.frame,
      speed: State.speed,
    });
  } else {
    // Joint mode fallback
    const deltas = [0,0,0,0,0,0];
    deltas[0] =  lx * JOG_SPEED;
    deltas[1] =  ly * JOG_SPEED;
    deltas[2] =  ry * JOG_SPEED;
    deltas[3] = -rx * JOG_SPEED;
    for (let i = 0; i < 4; i++) {
      if (Math.abs(deltas[i]) > 0.05) {
        sendWS({type: 'jog', joint: i, delta: deltas[i], speed: State.speed});
      }
    }
  }
}
