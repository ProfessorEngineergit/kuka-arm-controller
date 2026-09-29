// Three.js 3D view – built from the same DH table as the controller's forward
// kinematics (GET /api/config), so the picture always matches the numbers.
let _scene, _camera, _renderer, _controls;
let _robotRoot = null;     // robot Z-up → three.js Y-up
let _jointMeshes = [];     // one sphere per arm joint
let _linkMeshes  = [];     // one cylinder per DH row
let _gripper     = null;   // group at the TCP
let _tcpAxes     = null;

const JOINT_COLORS = [0xff6b00, 0xff8c33, 0x88ccff, 0xaaddff, 0x00aa44];
const JOINT_RADIUS = [10, 9, 6, 5, 5];
const LINK_COLOR   = 0x3a3a3a;
const _UP = (typeof THREE !== 'undefined') ? new THREE.Vector3(0, 1, 0) : null;

function initRobot3D() {
  const canvas = document.getElementById('three-canvas');
  if (!canvas || typeof THREE === 'undefined') return;

  _scene = new THREE.Scene();
  _scene.background = new THREE.Color(0x111111);
  _scene.fog = new THREE.Fog(0x111111, 600, 1200);

  _camera = new THREE.PerspectiveCamera(45, canvas.clientWidth / canvas.clientHeight, 1, 2000);
  _camera.position.set(300, 250, 350);

  _renderer = new THREE.WebGLRenderer({canvas, antialias: true});
  _renderer.setPixelRatio(window.devicePixelRatio);
  _renderer.setSize(canvas.clientWidth, canvas.clientHeight);

  if (THREE.OrbitControls) {
    _controls = new THREE.OrbitControls(_camera, _renderer.domElement);
    _controls.target.set(0, 100, 0);
    _controls.enableDamping = true;
    _controls.dampingFactor = 0.08;
  }
  _camera.lookAt(0, 100, 0);

  _scene.add(new THREE.AmbientLight(0x404040, 2));
  const dirLight = new THREE.DirectionalLight(0xffffff, 2);
  dirLight.position.set(200, 400, 200);
  _scene.add(dirLight);
  const fillLight = new THREE.DirectionalLight(0xff6b00, 0.3);
  fillLight.position.set(-200, 100, -200);
  _scene.add(fillLight);

  _scene.add(new THREE.GridHelper(400, 20, 0x333333, 0x222222));

  // Everything below lives in robot coordinates (mm, Z up).
  _robotRoot = new THREE.Group();
  _robotRoot.rotation.x = -Math.PI / 2;
  _scene.add(_robotRoot);
  _robotRoot.add(_makeAxes(40));

  const base = new THREE.Mesh(new THREE.CylinderGeometry(30, 35, 12, 32),
                              new THREE.MeshPhongMaterial({color: 0x555555}));
  base.rotation.x = Math.PI / 2;       // cylinder axis along robot Z
  base.position.z = -6;
  _robotRoot.add(base);

  _buildArm();

  window.addEventListener('resize', _onResize);
  _animate();
  updateRobot3D();
}

function _makeAxes(size) {
  const g = new THREE.Group();
  const mat = [0xff2222, 0x22ff22, 0x2222ff];
  const dirs = [[1,0,0],[0,1,0],[0,0,1]];
  dirs.forEach((d, i) => {
    const dir = new THREE.Vector3(...d);
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(1.5, 1.5, size, 8),
                                 new THREE.MeshPhongMaterial({color: mat[i]}));
    shaft.quaternion.setFromUnitVectors(_UP, dir);
    shaft.position.copy(dir.clone().multiplyScalar(size / 2));
    g.add(shaft);
    const cone = new THREE.Mesh(new THREE.ConeGeometry(3, 8, 8),
                                new THREE.MeshPhongMaterial({color: mat[i]}));
    cone.quaternion.setFromUnitVectors(_UP, dir);
    cone.position.copy(dir.clone().multiplyScalar(size));
    g.add(cone);
  });
  return g;
}

function _buildArm() {
  const dh = RobotConfig.dh_parameters;
  const linkGeo = new THREE.CylinderGeometry(1, 1, 1, 12);   // scaled per link
  const linkMat = new THREE.MeshPhongMaterial({color: LINK_COLOR});
  dh.forEach(() => {
    const link = new THREE.Mesh(linkGeo, linkMat);
    _robotRoot.add(link);
    _linkMeshes.push(link);
  });
  RobotConfig.joints.forEach((j, i) => {
    if ((j.type || 'revolute') !== 'revolute') return;
    const r = JOINT_RADIUS[i] || 5;
    const color = JOINT_COLORS[i % JOINT_COLORS.length];
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(r, 16, 16),
      new THREE.MeshPhongMaterial({color, emissive: color, emissiveIntensity: 0.15}));
    mesh.userData.joint = i;
    _robotRoot.add(mesh);
    _jointMeshes.push(mesh);
  });

  _gripper = new THREE.Group();
  const gMat = new THREE.MeshPhongMaterial({color: 0x888888});
  const palm = new THREE.Mesh(new THREE.BoxGeometry(26, 6, 4), gMat);
  palm.position.z = -2;
  _gripper.add(palm);
  [-1, 1].forEach(side => {
    const finger = new THREE.Mesh(new THREE.BoxGeometry(4, 6, 20), gMat);
    finger.userData.side = side;
    finger.position.z = 10;
    _gripper.add(finger);
  });
  _robotRoot.add(_gripper);

  _tcpAxes = _makeAxes(30);
  _robotRoot.add(_tcpAxes);
}

// DH transform, same convention as app/kinematics.py:
// T = Rz(theta) · Tz(d) · Tx(a) · Rx(alpha)
function _dhMatrix(a, alphaDeg, d, thetaDeg) {
  const deg = Math.PI / 180;
  return new THREE.Matrix4()
    .makeRotationZ(thetaDeg * deg)
    .multiply(new THREE.Matrix4().makeTranslation(0, 0, d))
    .multiply(new THREE.Matrix4().makeTranslation(a, 0, 0))
    .multiply(new THREE.Matrix4().makeRotationX(alphaDeg * deg));
}

// Cumulative base→frame transforms: frames[0] = base, frames[k] = after DH row k.
function _dhFrames(angles) {
  const frames = [new THREE.Matrix4()];
  RobotConfig.dh_parameters.forEach(([a, alpha, d, offset], i) => {
    const j = RobotConfig.joints[i];
    const moving = j && (j.type || 'revolute') === 'revolute';
    const theta = (moving ? (angles[i] ?? 0) : 0) + offset;
    frames.push(frames[i].clone().multiply(_dhMatrix(a, alpha, d, theta)));
  });
  return frames;
}

function _placeLink(mesh, from, to, radius) {
  const dir = to.clone().sub(from);
  const len = dir.length();
  mesh.visible = len > 0.5;
  if (!mesh.visible) return;
  mesh.position.copy(from).add(to).multiplyScalar(0.5);
  mesh.quaternion.setFromUnitVectors(_UP, dir.normalize());
  mesh.scale.set(radius, len, radius);
}

function updateRobot3D() {
  if (!_robotRoot) return;
  const frames = _dhFrames(State.joints);
  const origins = frames.map(f => new THREE.Vector3().setFromMatrixPosition(f));

  _linkMeshes.forEach((mesh, k) => {
    const r = (JOINT_RADIUS[k] || 5) * 0.5;
    _placeLink(mesh, origins[k], origins[k + 1], r);
  });

  // Joint i rotates about the Z axis of frame i (before its own DH row).
  _jointMeshes.forEach(mesh => mesh.position.copy(origins[mesh.userData.joint]));

  // Gripper + TCP axes at the last frame; fingers open with the gripper joint.
  const tcp = frames[frames.length - 1];
  const pos = new THREE.Vector3(), quat = new THREE.Quaternion(), scale = new THREE.Vector3();
  tcp.decompose(pos, quat, scale);
  _gripper.position.copy(pos);
  _gripper.quaternion.copy(quat);
  _tcpAxes.position.copy(pos);
  _tcpAxes.quaternion.copy(quat);

  const gi = RobotConfig.joints.findIndex(j => j.type === 'gripper');
  let open = 0.5;
  if (gi >= 0) {
    const j = RobotConfig.joints[gi];
    open = Math.max(0, Math.min(1, ((State.joints[gi] ?? j.min_angle) - j.min_angle) /
                                  Math.max(1, j.max_angle - j.min_angle)));
  }
  _gripper.children.forEach(c => {
    if (c.userData.side) c.position.x = c.userData.side * (4 + 8 * open);
  });
}

function _animate() {
  requestAnimationFrame(_animate);
  if (_controls) _controls.update();
  _renderer.render(_scene, _camera);
}

function _onResize() {
  const canvas = document.getElementById('three-canvas');
  if (!canvas || !_renderer) return;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  _camera.aspect = w / h;
  _camera.updateProjectionMatrix();
  _renderer.setSize(w, h);
}
