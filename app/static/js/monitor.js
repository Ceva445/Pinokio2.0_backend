/* === WebSocket (WS / WSS auto) === */
const wsProtocol = location.protocol === "https:" ? "wss" : "ws";
let ws;
let wsHeartbeat = null;
let wsClosedByServer = false;   // сервер вилогував → не перепідключатись

let devicesCache = {};
let activeDevice = null;

let countdownInterval = null;

const endBtn = document.getElementById("endSessionBtn");

/* === Роль + прив'язаний ESP (для менеджерів) === */
let userRole = null;
let boundDevice = null;

(async function initAuth() {
    try {
        const res = await fetch("/auth/me", { credentials: "include" });
        if (!res.ok) return;   // гість → інформаційний режим (дивиться, але не реєструє)
        const me = await res.json();
        userRole = me.role;
        boundDevice = me.bound_device || null;
        if (userRole !== "admin") {
            if (!boundDevice) { location.href = "/login"; return; }
            activeDevice = boundDevice;        // менеджер прив'язаний до одного ESP
            if (endBtn) endBtn.disabled = false;
            renderDevices();
        }
    } catch (e) {}
})();

/* === Масив для останніх повідомлень === */
const lastActions = [];

/* === WebSocket onmessage === */
function onWsMessage(e) {
    const msg = JSON.parse(e.data);

    // сервер вилогував менеджера (простій на ESP) → на сторінку входу з причиною
    if (msg.type === "force_logout") {
        wsClosedByServer = true;
        clearInterval(wsHeartbeat);
        try { ws.close(); } catch (err) {}
        location.href = "/login?reason=" + encodeURIComponent(msg.reason || "idle");
        return;
    }

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
}

/* === Авто-реконект + keepalive (щоб після простою не «мовчало» до F5) === */
function connectWs() {
    ws = new WebSocket(`${wsProtocol}://${location.host}/ws`);

    ws.onopen = () => {
        console.log("WebSocket connected");
        // адмін: після реконекту повторно підписатись на активний девайс
        if (activeDevice && (userRole === "admin" || userRole === null)) {
            ws.send(JSON.stringify({ command: "subscribe", device_id: activeDevice }));
        }
        clearInterval(wsHeartbeat);
        wsHeartbeat = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ command: "ping" }));
        }, 25000);
    };

    ws.onmessage = onWsMessage;

    ws.onclose = () => {
        console.warn("WebSocket disconnected — reconnecting in 2s...");
        clearInterval(wsHeartbeat);
        if (wsClosedByServer) return;
        setTimeout(connectWs, 2000);
    };

    ws.onerror = () => { try { ws.close(); } catch (e) {} };
}
connectWs();

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
        const isMine = activeDevice === d.id;

        div.className =
            `device ${d.is_online ? "online" : "offline"} ` +
            (isMine ? "active" : "");

        const watcherLine = (d.watched_by && !isMine)
            ? `<br><small>śledzi: ${d.watched_by}</small>` : "";

        div.innerHTML = `
            <b>${d.name}</b><br>
            ${d.is_online ? "🟢 Online" : "🔴 Offline"}${watcherLine}
        `;

        if (userRole === "admin" || userRole === null) {
            div.onclick = () => toggleSubscribe(d.id);     // адмін/гість — стара логіка
        } else if (!isMine) {
            div.style.opacity = "0.5";                     // менеджер: чужі сірі, клік заблоковано
            div.style.cursor = "not-allowed";
        }

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