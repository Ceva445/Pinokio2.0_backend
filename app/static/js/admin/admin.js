/*************************************************
 * ADMIN PANEL JS
 * Працює з:
 *  - /admin/employees
 *  - /admin/employees/{id}
 *  - /admin/api/employees
 *  - /admin/devices
 *  - /admin/api/devices
 *************************************************/

/* ================================
   УТИЛІТИ
================================ */

async function api(url, options = {}) {
    const res = await fetch(url, {
        credentials: "include",
        headers: {
            "Content-Type": "application/json"
        },
        ...options
    });

    if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "API error");
    }

    return res.status === 204 ? null : res.json();
}

/* ================================
   СПИСОК ПРАЦІВНИКІВ
================================ */

async function loadEmployees() {
    const tbody = document.querySelector("#employeesTable tbody");
    const searchInput = document.getElementById("search");
    const q = searchInput?.value ?? "";

    if (!tbody) return;

    tbody.innerHTML = "<tr><td colspan='6'>Завантаження...</td></tr>";

    try {
        const url = q
            ? `/admin/api/employees?q=${encodeURIComponent(q)}`
            : "/admin/api/employees";

        const employees = await api(url);
        tbody.innerHTML = "";

        for (const e of employees) {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${e.wms_login ?? ""}</td>
                <td>${e.first_name}</td>
                <td>${e.last_name}</td>
                <td>${e.company}</td>
                <td>${e.rfid}</td>
                <td><a href="/admin/employees/${e.id}">✏️</a></td>
            `;
            tbody.appendChild(tr);
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6">Помилка: ${err.message}</td></tr>`;
    }
}

/* ================================
   ДЕТАЛІ ПРАЦІВНИКА
================================ */

async function loadEmployeeDetail(employeeId) {
    const form = document.getElementById("employeeForm");
    if (!form) return;

    try {
        const employee = await api(`/admin/api/employees/${employeeId}`);

        form.wms_login.value = employee.wms_login ?? "";
        form.first_name.value = employee.first_name ?? "";
        form.last_name.value = employee.last_name ?? "";
        form.company.value = employee.company ?? "";
        form.rfid.value = employee.rfid ?? "";
    } catch (err) {
        alert("Не вдалося завантажити працівника ❌");
        console.error(err);
    }

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        await api(`/admin/api/employees/${employeeId}`, {
            method: "PUT",
            body: JSON.stringify({
                wms_login: form.wms_login.value,
                first_name: form.first_name.value,
                last_name: form.last_name.value,
                company: form.company.value,
                rfid: form.rfid.value
            })
        });

        alert("Збережено ✅");
    });
}

async function deleteEmployee(employeeId) {
    if (!confirm("Ви впевнені?")) return;
    await api(`/admin/api/employees/${employeeId}`, { method: "DELETE" });
    window.location.href = "/admin/employees";
}

/* ================================
   СТВОРЕННЯ ПРАЦІВНИКА
================================ */

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("employeeCreateForm");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        try {
            await api("/admin/api/employees", {
                method: "POST",
                body: JSON.stringify({
                    wms_login: form.wms_login.value || null,
                    first_name: form.first_name.value,
                    last_name: form.last_name.value,
                    company: form.company.value,
                    rfid: form.rfid.value
                })
            });

            alert("Працівника створено ✅");
            window.location.href = "/admin/employees";
        } catch (err) {
            alert("Помилка створення ❌\n" + err.message);
        }
    });
});

/* ================================
   СПИСОК ПРИСТРОЇВ
================================ */

async function loadDevices() {
    const tbody = document.querySelector("#devicesTable tbody");
    const search = document.getElementById("deviceSearch");
    if (!tbody) return;

    const q = search?.value ?? "";
    const url = q
        ? `/admin/api/devices?q=${encodeURIComponent(q)}`
        : "/admin/api/devices";

    try {
        const devices = await api(url);
        tbody.innerHTML = "";

        for (const d of devices) {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${d.name}</td>
                <td>${d.type}</td>
                <td>${d.serial_number}</td>
                <td>${d.rfid}</td>
                <td><a href="/admin/devices/${d.id}">✏️</a></td>
            `;
            tbody.appendChild(tr);
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5">Помилка: ${err.message}</td></tr>`;
    }
}

/* ================================
   CREATE DEVICE
================================ */

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("deviceCreateForm");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        await api("/admin/api/devices", {
            method: "POST",
            body: JSON.stringify({
                name: form.name.value,
                type: form.type.value,
                serial_number: form.serial_number.value,
                rfid: form.rfid.value
            })
        });

        alert("Пристрій створено ✅");
        window.location.href = "/admin/devices";
    });
});

/* ================================
   DEVICE DETAIL
================================ */

async function loadDeviceDetail(deviceId) {
    const form = document.getElementById("deviceForm");
    if (!form) return;

    const d = await api(`/admin/api/devices/${deviceId}`);

    form.name.value = d.name;
    form.type.value = d.type;
    form.serial_number.value = d.serial_number;
    form.rfid.value = d.rfid;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        await api(`/admin/api/devices/${deviceId}`, {
            method: "PUT",
            body: JSON.stringify({
                name: form.name.value,
                type: form.type.value,
                serial_number: form.serial_number.value,
                rfid: form.rfid.value
            })
        });

        alert("Збережено ✅");
    });
}

async function deleteDevice() {
    if (!confirm("Видалити пристрій?")) return;
    await api(`/admin/api/devices/${deviceId}`, { method: "DELETE" });
    window.location.href = "/admin/devices";
}

/* ================================
   АВТОЗАПУСК
================================ */

document.addEventListener("DOMContentLoaded", () => {
    loadEmployees();

    if (document.querySelector("#devicesTable")) {
        loadDevices();
    }

    const searchInput = document.getElementById("search");
    if (searchInput) {
        let timeout;
        searchInput.addEventListener("input", () => {
            clearTimeout(timeout);
            timeout = setTimeout(loadEmployees, 300);
        });
    }

    const deviceSearch = document.getElementById("deviceSearch");
    if (deviceSearch) {
        let timeout;
        deviceSearch.addEventListener("input", () => {
            clearTimeout(timeout);
            timeout = setTimeout(loadDevices, 300);
        });
    }

    if (typeof employeeId !== "undefined") {
        loadEmployeeDetail(employeeId);
    }

    if (typeof deviceId !== "undefined") {
        loadDeviceDetail(deviceId);
    }
});
