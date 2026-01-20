/* === WebSocket (WS / WSS auto) === */
const wsProtocol = location.protocol === "https:" ? "wss" : "ws";
const ws = new WebSocket(`${wsProtocol}://${location.host}/ws`);

let devicesCache = {};
let activeDevice = null;

const endBtn = document.getElementById("endSessionBtn");

/* === WebSocket events === */
ws.onopen = () => {
    console.log("WebSocket connected");
};

ws.onclose = () => {
    console.warn("WebSocket disconnected");
};

ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.type === "device_list") {
        devicesCache = msg.data.devices;
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
    }
};

/* ===== Status UI ===== */
function showStatus(status, message) {
    const el = document.getElementById("status");

    el.className = "";
    el.textContent = message;

    if (status === "success") el.classList.add("status-success");
    else if (status === "error") el.classList.add("status-error");
    else el.classList.add("status-info");

    el.style.display = "block";

    // автоочистка через 5 сек
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

        activeDevice = null;
        document.getElementById("output").textContent = "No device subscribed";
    } else {
        if (activeDevice) {
            ws.send(JSON.stringify({
                command: "unsubscribe",
                device_id: activeDevice
            }));
        }

        ws.send(JSON.stringify({
            command: "subscribe",
            device_id: deviceId
        }));

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