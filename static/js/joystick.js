// Dual nipplejs joystick in the bottom bar
// Left:  J1 (yaw) + J2 (shoulder)  or  X/Y cartesian
// Right: J3 (elbow) + J4 (wrist)   or  Z + rotation

let _leftJoy = null, _rightJoy = null;
let _lv = {x:0, y:0}, _rv = {x:0, y:0};
let _jogTimer = null;

function initJoysticks() {
  if (typeof nipplejs === 'undefined') return;
  const base = {mode:'static', position:{left:'50%',top:'50%'}, color:'#ff6600', size:60, threshold:0.08};

  _leftJoy  = nipplejs.create({zone: document.getElementById('joystick-left'),  ...base});
  _rightJoy = nipplejs.create({zone: document.getElementById('joystick-right'), ...base});

  _leftJoy.on('move',  (_, d) => { const r = Math.min(d.distance/30,1); _lv = {x: Math.cos(d.angle.radian)*r, y: Math.sin(d.angle.radian)*r}; });
  _leftJoy.on('end',   ()     => { _lv = {x:0, y:0}; });
  _rightJoy.on('move', (_, d) => { const r = Math.min(d.distance/30,1); _rv = {x: Math.cos(d.angle.radian)*r, y: Math.sin(d.angle.radian)*r}; });
  _rightJoy.on('end',  ()     => { _rv = {x:0, y:0}; });

  _jogTimer = setInterval(_tick, 50);
}

function _tick() {
  if (!State.enabled || State.estop) return;
  const lx = _lv.x, ly = _lv.y, rx = _rv.x, ry = _rv.y;
  if (Math.abs(lx)+Math.abs(ly)+Math.abs(rx)+Math.abs(ry) < 0.05) return;

  const spd = State.override;
  const mm  = (State.override / 100) * 4;

  // In WORLD or TCP mode: cartesian
  sendWS({
    type: 'cartesian',
    dx:  lx * mm,
    dy:  ly * mm,
    dz:  ry * mm,
    da: -rx * (spd / 100) * 3,
    frame: State.frame,
    speed: spd,
  });
}
