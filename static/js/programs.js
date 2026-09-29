// Program panel
async function loadPrograms() {
  const list = document.getElementById('prog-list');
  if (!list) return;
  try {
    const res = await fetch('/api/programs');
    const programs = await res.json();
    list.innerHTML = '';
    for (const [key, prog] of Object.entries(programs)) {
      // Program names are restricted server-side to [A-Za-z0-9_-]; labels and
      // descriptions come from user files / backups and are escaped.
      const isBuiltin = prog.builtin;
      list.innerHTML += `
        <div class="prog-item">
          <div class="prog-info">
            <div class="prog-name">${escapeHtml(prog.label)}</div>
            <div class="prog-desc">${escapeHtml(prog.description)}${isBuiltin ? ' <em style="color:var(--t3)">(eingebaut)</em>' : ''}</div>
          </div>
          <button class="btn btn-green" onclick="startProgram('${escapeHtml(key)}')" style="font-size:11px;padding:6px 10px;">▶ Start</button>
          ${!isBuiltin ? `<button class="btn btn-red" onclick="deleteProgram('${escapeHtml(key)}')" style="font-size:11px;padding:6px 8px;">✕</button>` : ''}
        </div>`;
    }
    if (!Object.keys(programs).length) {
      list.innerHTML = '<p style="color:var(--t3);font-size:12px;">Keine Programme verfügbar.</p>';
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
  logEntry('■ Programm gestoppt – Arm hält Position', 'warn');
}

async function deleteProgram(name) {
  if (!confirm(`Programm "${name}" löschen?`)) return;
  await fetch(`/api/programs/${name}`, {method: 'DELETE'});
  logEntry(`Programm "${name}" gelöscht`, 'info');
  loadPrograms();
}

// updateProgramUI() lives in ui.js.
