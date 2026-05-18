// Program panel
async function loadPrograms() {
  const list = document.getElementById('program-list');
  if (!list) return;
  try {
    const res = await fetch('/api/programs');
    const programs = await res.json();
    list.innerHTML = '';
    for (const [key, prog] of Object.entries(programs)) {
      const isBuiltin = prog.builtin;
      list.innerHTML += `
        <div class="program-item">
          <div class="prog-info">
            <div class="prog-name">${prog.label}</div>
            <div class="prog-desc">${prog.description}${isBuiltin ? ' <em style="color:var(--text-dim)">(eingebaut)</em>' : ''}</div>
          </div>
          <button class="btn btn-green" onclick="startProgram('${key}')" style="font-size:11px;padding:6px 10px;">▶ Start</button>
          ${!isBuiltin ? `<button class="btn btn-red" onclick="deleteProgram('${key}')" style="font-size:11px;padding:6px 8px;">✕</button>` : ''}
        </div>`;
    }
    if (!Object.keys(programs).length) {
      list.innerHTML = '<p style="color:var(--text-dim);font-size:12px;">Keine Programme verfügbar.</p>';
    }
  } catch { logEntry('Fehler beim Laden der Programme', 'error'); }
}

async function startProgram(name) {
  if (!State.enabled || State.estop) { logEntry('Arm nicht freigegeben', 'warn'); return; }
  try {
    const res = await fetch(`/api/programs/${name}/run`, {method: 'POST'});
    if (!res.ok) {
      const err = await res.json();
      logEntry('Programm-Start fehlgeschlagen: ' + err.detail, 'error');
    } else {
      logEntry(`▶ Programm "${name}" gestartet`, 'ok');
    }
  } catch { logEntry('Verbindungsfehler', 'error'); }
}

async function stopProgram() {
  await fetch('/api/programs/stop', {method: 'POST'});
  logEntry('■ Programm gestoppt', 'warn');
}

async function deleteProgram(name) {
  if (!confirm(`Programm "${name}" löschen?`)) return;
  await fetch(`/api/programs/${name}`, {method: 'DELETE'});
  logEntry(`Programm "${name}" gelöscht`, 'info');
  loadPrograms();
}

function updateProgramUI() {
  const nameEl = document.getElementById('running-prog-name');
  const stopBtn = document.getElementById('btn-stop-prog');
  if (nameEl) nameEl.textContent = State.program || '—';
  if (stopBtn) stopBtn.style.display = State.program ? 'block' : 'none';
}
