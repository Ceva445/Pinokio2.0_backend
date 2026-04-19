/* === WebSocket (WS / WSS auto) === */
const wsProtocol = location.protocol === "https:" ? "wss" : "ws";
const ws = new WebSocket(`${wsProtocol}://${location.host}/ws`);

let devicesCache = {};
let activeDevice = null;

let countdownInterval = null;

const endBtn = document.getElementById("endSessionBtn");

/* === Масив для останніх повідомлень === */
const lastActions = [];

/* === WebSocket events === */
ws.onopen = () => {
    console.log("WebSocket connected");
};

ws.onclose = () => {
    console.warn("WebSocket disconnected");
};

/* === WebSocket onmessage === */
ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.type === "device_list") {
        devicesCache = msg.data.devices;

        if (activeDevice && !devicesCache[activeDevice]) {
            activeDevice = null;
            const outputEl = document.getElementById("output");
            if (outputEl) outputEl.textContent = "Device disconnected";
            endBtn.disabled = true;
        }

        renderDevices();
    }

    if (msg.type === "esp32_data") {
        if (msg.device_id === activeDevice) {
            const outputEl = document.getElementById("output");
            if (outputEl) {
                outputEl.textContent = JSON.stringify(msg.data, null, 2);
            }
        }
    }

    if (msg.type === "registration_status") {
        showStatus(msg.status, msg.message);
        if (msg.session) {
            startCountdown(msg.session.timeout_seconds);
        } else {
            stopCountdown();
        }
    }
};

function startCountdown(timeoutSeconds) {
    stopCountdown();

    let left = timeoutSeconds;
    renderCountdown(left);

    countdownInterval = setInterval(() => {
        left -= 0.1;
        if (left <= 0) {
            stopCountdown();
            left = 0;
        }
        renderCountdown(left);
    }, 100);
}

function stopCountdown() {
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }
    renderCountdown(0);
}

function renderCountdown(seconds) {
    const el = document.getElementById("countdownCircle");
    el.textContent = seconds.toFixed(1);
}

/* ===== Status UI ===== */
function showStatus(status, message) {
    const el = document.getElementById("status");

    el.className = "";
    el.textContent = message;

    if (status === "success") el.classList.add("status-success");
    else if (status === "error") el.classList.add("status-error");
    else el.classList.add("status-info");

    el.style.display = "block";

    // Додаємо в Last 5 Device Actions тільки якщо статус містить ключові слова
    if (message && (
        message.includes("Rejestracja zakończona") ||
        message.includes("przypisano do") ||
        message.includes("został odpięty")
    )) {
        lastActions.unshift(`${new Date().toLocaleTimeString()} - ${message}`);
        if (lastActions.length > 5) lastActions.pop();
        renderLastActions();
    }

    // автоочистка через 15 сек
    setTimeout(() => {
        el.style.display = "none";
    }, 10000);
}

/* === UI rendering === */
function renderDevices() {
    const el = document.getElementById("devices");
    el.innerHTML = "";

    Object.values(devicesCache).forEach(d => {
        const div = document.createElement("div");

        div.className =
            `device ${d.is_online ? "online" : "offline"} ` +
            (activeDevice === d.id ? "active" : "");

        div.innerHTML = `
            <b>${d.name}</b><br>
            ${d.is_online ? "🟢 Online" : "🔴 Offline"}
        `;

        div.onclick = () => toggleSubscribe(d.id);
        el.appendChild(div);
    });
}

/* === Subscribe / Unsubscribe === */
function toggleSubscribe(deviceId) {
    if (activeDevice === deviceId) {
        // Unsubscribe from current device
        ws.send(JSON.stringify({
            command: "unsubscribe",
            device_id: deviceId
        }));
        fetch(`/api/unsubscribe-esp/${deviceId}`, { method: "POST" });

        activeDevice = null;
        const outputEl = document.getElementById("output");
        if (outputEl) outputEl.textContent = "No device subscribed";
    } else {
        // If already subscribed to a device, show confirmation dialog
        if (activeDevice) {
            const currentDevice = devicesCache[activeDevice];
            const newDevice = devicesCache[deviceId];
            const currentName = currentDevice ? currentDevice.name : "Unknown";
            const newName = newDevice ? newDevice.name : "Unknown";
            
            showDeviceSwitchAlert(currentName, newName, () => {
                // Callback to execute switch
                performDeviceSwitch(deviceId);
            });
        } else {
            // No active device, can switch directly
            performDeviceSwitch(deviceId);
        }
    }

    endBtn.disabled = !activeDevice;
    renderDevices();
}

/* === Perform device switch === */
function performDeviceSwitch(deviceId) {
    if (activeDevice) {
        ws.send(JSON.stringify({
            command: "unsubscribe",
            device_id: activeDevice
        }));
        fetch(`/api/unsubscribe-esp/${activeDevice}`, { method: "POST" });
    }

    ws.send(JSON.stringify({
        command: "subscribe",
        device_id: deviceId
    }));
    fetch(`/api/subscribe-esp/${deviceId}`, { method: "POST" });

    activeDevice = deviceId;
    endBtn.disabled = !activeDevice;
    renderDevices();
}

/* === Show device switch confirmation alert === */
function showDeviceSwitchAlert(currentDeviceName, newDeviceName, onConfirm) {
    // Remove existing modal if any
    const existingModal = document.getElementById("deviceSwitchModal");
    if (existingModal) existingModal.remove();

    // Create modal overlay
    const overlay = document.createElement("div");
    overlay.id = "deviceSwitchModal";
    overlay.className = "modal-overlay";

    // Create modal content
    const modal = document.createElement("div");
    modal.className = "modal-content";
    modal.innerHTML = `
        <h2>Przełączanie urządzenia ?</h2>
        <p>Aktualnie masz połączenie z <strong>${escapeHtml(currentDeviceName)}</strong></p>
        <p>Czy chcesz przełączyć się na <strong>${escapeHtml(newDeviceName)}</strong>?</p>
        <div class="modal-buttons">
            <button class="modal-btn cancel-btn">Anulować</button>
            <button class="modal-btn submit-btn">Przełącz</button>
        </div>
    `;

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // Get buttons
    const cancelBtn = modal.querySelector(".cancel-btn");
    const submitBtn = modal.querySelector(".submit-btn");

    // Cancel handler
    cancelBtn.onclick = () => {
        overlay.remove();
    };

    // Submit handler
    submitBtn.onclick = () => {
        overlay.remove();
        onConfirm();
    };

    // Close on overlay click
    overlay.onclick = (e) => {
        if (e.target === overlay) {
            overlay.remove();
        }
    };
}

/* === Escape HTML to prevent XSS === */
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

endBtn.onclick = async () => {
    if (!activeDevice) return;

    const res = await fetch(`/api/end-session/${activeDevice}`, { method: "POST" });
    const data = await res.json();
    showStatus(data.status, data.message);
};

/* === Функція рендеру останніх 5 дій === */
function renderLastActions() {
    const el = document.getElementById("lastActions");
    if (!el) return;

    if (lastActions.length === 0) {
        el.textContent = "No actions yet";
    } else {
        el.textContent = lastActions.join("\n");
    }
}