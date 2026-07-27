// Керування прошивками (OTA)

function fmtSize(bytes) {
    if (bytes == null) return '—';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('pl-PL', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit'
    });
}

function showMessage(message, type) {
    const el = document.getElementById('fwStatusMessage');
    el.textContent = message;
    el.className = `status-message ${type}`;
    if (type === 'success') {
        setTimeout(() => { el.className = ''; el.textContent = ''; }, 3000);
    }
}

async function loadFirmware() {
    try {
        const res = await fetch('/admin/api/firmware', { credentials: 'include' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        // Активна
        const active = data.active;
        document.getElementById('activeVersion').textContent = active ? active.version : '—';
        document.getElementById('activeMeta').textContent = active
            ? `${active.filename} · ${fmtSize(active.size)} · ${fmtDate(active.uploaded_at)}`
            : 'Brak aktywnej firmware';

        // Історія
        renderHistory(data.history || []);
    } catch (err) {
        console.error(err);
        showMessage('Błąd ładowania: ' + err.message, 'error');
    }
}

function renderHistory(history) {
    const tbody = document.querySelector('#fwHistoryTable tbody');
    tbody.innerHTML = '';

    if (!history.length) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;opacity:.6;">Brak wgranych wersji</td></tr>';
        return;
    }

    for (const fw of history) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${fw.version}</strong></td>
            <td>${fw.filename}</td>
            <td>${fmtSize(fw.size)}</td>
            <td>${fw.uploaded_by || '—'}</td>
            <td>${fmtDate(fw.uploaded_at)}</td>
            <td>${fw.is_active ? '✅ aktywna' : '—'}</td>
            <td></td>
        `;
        const actions = tr.querySelector('td:last-child');

        if (!fw.is_active) {
            const activateBtn = document.createElement('button');
            activateBtn.className = 'btn btn-primary';
            activateBtn.textContent = 'Aktywuj';
            activateBtn.onclick = () => activateFirmware(fw.id, fw.version);
            actions.appendChild(activateBtn);

            const delBtn = document.createElement('button');
            delBtn.className = 'btn';
            delBtn.textContent = '🗑';
            delBtn.style.marginLeft = '.4rem';
            delBtn.onclick = () => deleteFirmware(fw.id, fw.version);
            actions.appendChild(delBtn);
        }
        tbody.appendChild(tr);
    }
}

async function activateFirmware(id, version) {
    if (!confirm(`Aktywować wersję ${version}? Urządzenia zaktualizują się do niej.`)) return;
    try {
        const res = await fetch(`/admin/api/firmware/${id}/activate`, {
            method: 'POST', credentials: 'include'
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        showMessage(`✅ Aktywowano ${version}`, 'success');
        loadFirmware();
    } catch (err) {
        showMessage('❌ ' + err.message, 'error');
    }
}

async function deleteFirmware(id, version) {
    if (!confirm(`Usunąć wersję ${version}?`)) return;
    try {
        const res = await fetch(`/admin/api/firmware/${id}`, {
            method: 'DELETE', credentials: 'include'
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        showMessage(`🗑 Usunięto ${version}`, 'success');
        loadFirmware();
    } catch (err) {
        showMessage('❌ ' + err.message, 'error');
    }
}

document.getElementById('firmwareForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const version = document.getElementById('fwVersion').value.trim();
    const fileInput = document.getElementById('fwFile');
    if (!version || !fileInput.files.length) {
        showMessage('Podaj wersję i plik .bin', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('version', version);
    formData.append('file', fileInput.files[0]);

    const submitBtn = e.target.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.textContent = '⏳ Wgrywanie...';

    try {
        const res = await fetch('/admin/api/firmware', {
            method: 'POST', credentials: 'include', body: formData
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }
        showMessage(`✅ Wgrano i aktywowano ${version}`, 'success');
        e.target.reset();
        loadFirmware();
    } catch (err) {
        showMessage('❌ ' + err.message, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '⬆️ Wgraj i aktywuj';
    }
});

document.addEventListener('DOMContentLoaded', loadFirmware);
