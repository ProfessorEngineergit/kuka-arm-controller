// Three.js 3D Robot Arm Visualization
let _scene, _camera, _renderer, _controls;
let _joints3D = [];      // joint pivot objects
let _segments  = [];     // link mesh objects
let _tcpAxes   = null;

// 5 joints: Metal MG996R, MG996R, MG90S, MG90S, MG90S
const JOINT_COLORS = [0xff6b00, 0xff8c33, 0x88ccff, 0xaaddff, 0x00aa44];
const JOINT_RADIUS_PER = [10, 9, 6, 5, 5];  // MG996R bigger, MG90S smaller
const LINK_COLOR   = 0x3a3a3a;

// Approximate link lengths (mm) matching DH params in robot.yaml
const LINK_LENGTHS = [60, 100, 90, 55, 0];

function initRobot3D() {
  const canvas = document.getElementById('three-canvas');
  if (!canvas || typeof THREE === 'undefined') return;

  _scene = new THREE.Scene();
  _scene.background = new THREE.Color(0x111111);
  _scene.fog = new THREE.Fog(0x111111, 600, 1200);

  _camera = new THREE.PerspectiveCamera(45, canvas.clientWidth / canvas.clientHeight, 1, 2000);
  _camera.position.set(300, 200, 350);
  _camera.lookAt(0, 100, 0);

  _renderer = new THREE.WebGLRenderer({canvas, antialias: true});
  _renderer.setPixelRatio(window.devicePixelRatio);
  _renderer.setSize(canvas.clientWidth, canvas.clientHeight);
  _renderer.shadowMap.enabled = true;

  _controls = new THREE.OrbitControls(_camera, _renderer.domElement);
  _controls.target.set(0, 100, 0);
  _controls.enableDamping = true;
  _controls.dampingFactor = 0.08;

  // Lights
  const ambient = new THREE.AmbientLight(0x404040, 2);
  _scene.add(ambient);
  const dirLight = new THREE.DirectionalLight(0xffffff, 2);
  dirLight.position.set(200, 400, 200);
  dirLight.castShadow = true;
  _scene.add(dirLight);
  const fillLight = new THREE.DirectionalLight(0xff6b00, 0.3);
  fillLight.position.set(-200, 100, -200);
  _scene.add(fillLight);

  // Grid
  const grid = new THREE.GridHelper(400, 20, 0x333333, 0x222222);
  _scene.add(grid);

  // World axes
  _scene.add(_makeAxes(40, 0, 0, 0));

  // Base plate
  const baseGeo = new THREE.CylinderGeometry(30, 35, 12, 32);
  const baseMat = new THREE.MeshPhongMaterial({color: 0x555555});
  const base    = new THREE.Mesh(baseGeo, baseMat);
  base.position.y = 6;
  base.castShadow = true;
  _scene.add(base);

  // Build arm segments
  _buildArmSegments();

  // TCP axes indicator
  _tcpAxes = _makeAxes(30, 0, 0, 0);
  _scene.add(_tcpAxes);

  window.addEventListener('resize', _onResize);
  _animate();
  updateRobot3D();
}

function _makeAxes(size, x, y, z) {
  const g = new THREE.Group();
  const mat = [0xff2222, 0x22ff22, 0x2222ff];
  const dirs = [[1,0,0],[0,1,0],[0,0,1]];
  dirs.forEach(([dx,dy,dz], i) => {
    const geo = new THREE.CylinderGeometry(1.5, 1.5, size, 8);
    const mesh = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({color: mat[i]}));
    mesh.position.set(dx*size/2, dy*size/2, dz*size/2);
    if (i === 0) mesh.rotation.z = -Math.PI/2;
    if (i === 2) mesh.rotation.x =  Math.PI/2;
    g.add(mesh);
    // Arrow head
    const coneGeo = new THREE.ConeGeometry(3, 8, 8);
    const cone = new THREE.Mesh(coneGeo, new THREE.MeshPhongMaterial({color: mat[i]}));
    cone.position.set(dx*size, dy*size, dz*size);
    if (i === 0) cone.rotation.z = -Math.PI/2;
    if (i === 2) cone.rotation.x =  Math.PI/2;
    g.add(cone);
  });
  g.position.set(x, y, z);
  return g;
}

function _buildArmSegments() {
  // 5-DOF: Metal MG996R (J1), MG996R (J2), MG90S (J3), MG90S (J4), MG90S (J5/Gripper)
  let parent = _scene;
  let yOffset = 12;

  for (let i = 0; i < 5; i++) {
    const pivot = new THREE.Group();
    pivot.position.y = yOffset;
    parent.add(pivot);
    _joints3D.push(pivot);

    const r = JOINT_RADIUS_PER[i];
    const jGeo = new THREE.SphereGeometry(r, 16, 16);
    const jMat = new THREE.MeshPhongMaterial({color: JOINT_COLORS[i], emissive: JOINT_COLORS[i], emissiveIntensity: 0.15});
    const jMesh = new THREE.Mesh(jGeo, jMat);
    jMesh.castShadow = true;
    pivot.add(jMesh);

    const len = LINK_LENGTHS[i];
    if (i < 4 && len > 0) {
      const lGeo = new THREE.CylinderGeometry(r * 0.5, r * 0.5, len, 12);
      const lMat = new THREE.MeshPhongMaterial({color: LINK_COLOR});
      const link  = new THREE.Mesh(lGeo, lMat);
      link.position.y = len / 2;
      link.castShadow = true;
      pivot.add(link);
      _segments.push(link);
      yOffset = len;
    } else if (i === 4) {
      // Gripper (MG90S)
      _addGripper(pivot);
      yOffset = 40;
    }

    parent = pivot;
  }
}

function _addGripper(parent) {
  const mat = new THREE.MeshPhongMaterial({color: 0x888888});
  // Two fingers
  [-10, 10].forEach(x => {
    const geo  = new THREE.BoxGeometry(4, 20, 4);
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, 10, 0);
    parent.add(mesh);
  });
  const palmGeo = new THREE.BoxGeometry(26, 4, 6);
  const palm    = new THREE.Mesh(palmGeo, mat);
  palm.position.y = 2;
  parent.add(palm);
}

function updateRobot3D() {
  if (_joints3D.length < 5) return;
  const a = State.joints;

  // J1 Metal MG996R – Basis-Rotation um Y
  _joints3D[0].rotation.y = THREE.MathUtils.degToRad(a[0] - 90);

  // J2 MG996R – Schulter-Pitch um Z
  _joints3D[1].rotation.z = THREE.MathUtils.degToRad(-(a[1] - 90));

  // J3 MG90S – Ellbogen-Pitch um Z
  _joints3D[2].rotation.z = THREE.MathUtils.degToRad(-(a[2] - 90));

  // J4 MG90S – Handgelenk-Pitch um Z
  _joints3D[3].rotation.z = THREE.MathUtils.degToRad(a[3] - 90);

  // J5 MG90S – Greifer (open/close)
  const openFactor = 1 + (a[4] / 90) * 0.9;
  const g = _joints3D[4];
  if (g.children[1]) g.children[1].position.x = -8 * openFactor;
  if (g.children[2]) g.children[2].position.x =  8 * openFactor;

  // TCP axes folgen dem letzten Gelenk
  if (_tcpAxes && _joints3D[4]) {
    const wp = new THREE.Vector3();
    _joints3D[4].getWorldPosition(wp);
    _tcpAxes.position.copy(wp);
    const wq = new THREE.Quaternion();
    _joints3D[4].getWorldQuaternion(wq);
    _tcpAxes.quaternion.copy(wq);
  }
}

function _animate() {
  requestAnimationFrame(_animate);
  _controls.update();
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
