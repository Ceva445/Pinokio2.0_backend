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
            document.getElementById("output").textContent = "Device disconnected";
            endBtn.disabled = true;
        }

        renderDevices();
    }

    if (msg.type === "esp32_data") {
        if (msg.device_id === activeDevice) {
            document.getElementById("output").textContent =
                JSON.stringify(msg.data, null, 2);
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
        ws.send(JSON.stringify({
            command: "unsubscribe",
            device_id: deviceId
        }));
        fetch(`/api/unsubscribe-esp/${deviceId}`, { method: "POST" });

        activeDevice = null;
        document.getElementById("output").textContent = "No device subscribed";
    } else {
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
    }

    endBtn.disabled = !activeDevice;
    renderDevices();
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