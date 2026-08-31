let currentConfig = {};

// Завантажити конфіг з сервера при завантаженні сторінки
async function loadConfig() {
    try {
        const response = await fetch('/admin/api/system-config', {
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        currentConfig = data.config;

        // Заповнити форму поточними значеннями
        fillForm(currentConfig);
        updateLastUpdatedTime(currentConfig.updated_at);
    } catch (error) {
        console.error('Error loading config:', error);
        showMessage('Błąd przy ładowaniu konfiguracji: ' + error.message, 'error');
    }
}

// Заповнити форму значеннями
function fillForm(config) {
    const fields = {
        'accessTokenExpire': config.access_token_expire_minutes,
        'deviceTimeout': config.device_timeout_minutes,
        'registrationTimeout': config.registration_timeout_seconds,
        'deviceCleanupInterval': config.device_cleanup_interval_seconds,
        'authCleanupInterval': config.auth_cleanup_interval_seconds,
        'deviceNotReturnedHours': config.device_not_returned_hours,
        'temporaryCardDurationHours': config.temporary_card_duration_hours
    };
    
    // Set text/number inputs
    for (const [id, value] of Object.entries(fields)) {
        const element = document.getElementById(id);
        if (element) {
            element.value = value;
        }
    }
    
    // Set checkbox
    const checkbox = document.getElementById('allowRegistrationWithoutLogin');
    if (checkbox) {
        checkbox.checked = config.allow_registration_without_login;
    }

    // Email notifications
    const emailEnabled = document.getElementById('emailNotificationsEnabled');
    if (emailEnabled) {
        emailEnabled.checked = config.email_notifications_enabled !== false;
    }
    renderEmailTimes(config.email_send_times || '');
}

// Відрендерити рядки годин з рядка "HH:MM,HH:MM"
function renderEmailTimes(timesStr) {
    const container = document.getElementById('emailTimesContainer');
    if (!container) return;
    container.innerHTML = '';
    const times = String(timesStr).split(',').map(t => t.trim()).filter(Boolean);
    (times.length ? times : ['09:00']).forEach(t => addEmailTimeRow(t));
}

// Додати один рядок з time-picker + кнопкою видалення
function addEmailTimeRow(value) {
    const container = document.getElementById('emailTimesContainer');
    if (!container) return;
    const row = document.createElement('div');
    row.className = 'email-time-row';
    row.style.cssText = 'display:flex; gap:8px; align-items:center; margin-bottom:6px;';
    row.innerHTML = `
        <input type="time" class="config-input email-time-input" value="${value || ''}" style="width:auto; margin:0;">
        <button type="button" class="btn email-time-remove" title="Usuń">✕</button>
    `;
    row.querySelector('.email-time-remove').addEventListener('click', () => row.remove());
    container.appendChild(row);
}

// Оновити час останньої оновації
function updateLastUpdatedTime(timestamp) {
    if (!timestamp) return;
    
    const date = new Date(timestamp);
    const formattedDate = date.toLocaleString('pl-PL', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    
    document.getElementById('lastUpdated').textContent = `${formattedDate}`;
}

// Показати повідомлення
function showMessage(message, type) {
    const msgEl = document.getElementById('statusMessage');
    msgEl.textContent = message;
    msgEl.className = `status-message ${type}`;
    
    if (type === 'success') {
        setTimeout(() => {
            msgEl.className = '';
        }, 3000);
    }
}

// Обробити відправку форми
document.getElementById('configForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const updates = {};
    
    for (const [key, value] of formData.entries()) {
        // Перетворити числа на числа
        if (key.includes('minutes') || key.includes('seconds') || key.includes('hours')) {
            updates[key] = parseInt(value, 10);
        } else {
            updates[key] = value;
        }
    }
    
    // Явно обробити checkbox, оскільки FormData не містить unchecked checkboxes
    updates['allow_registration_without_login'] = document.getElementById('allowRegistrationWithoutLogin').checked;

    // Email-нотифікації: enabled + зібрані години
    updates['email_notifications_enabled'] = document.getElementById('emailNotificationsEnabled').checked;
    const emailTimes = Array.from(document.querySelectorAll('#emailTimesContainer .email-time-input'))
        .map(i => i.value).filter(Boolean);
    updates['email_send_times'] = emailTimes.join(',');
    
    try {
        const response = await fetch('/admin/api/system-config', {
            method: 'PUT',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(updates)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        currentConfig = data.config;
        fillForm(currentConfig);
        updateLastUpdatedTime(currentConfig.updated_at);
        showMessage('✅ Konfiguracja zaktualizowana sukcesnie!', 'success');
    } catch (error) {
        console.error('Error updating config:', error);
        showMessage('❌ Błąd przy aktualizacji: ' + error.message, 'error');
    }
});

// Resetuj formulę
document.getElementById('resetBtn').addEventListener('click', () => {
    fillForm(currentConfig);
});

// Кнопка «Dodaj godzinę»
document.getElementById('addEmailTimeBtn')?.addEventListener('click', () => addEmailTimeRow(''));

// Загрузити конфіг при завантаженні сторінки
document.addEventListener('DOMContentLoaded', loadConfig);
