/*************************************************
 * ADMIN PANEL JS
 * Працює з:
 *  - /admin/employees
 *  - /admin/employees/{id}
 *  - /admin/api/employees
 *  - /admin/devices
 *  - /admin/api/devices
 *  - /admin/users
 *  - /admin/api/users
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
        alert("Nie udało się załadować pracownika ❌");
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

        alert("Zapisano ✅");
    });
}

async function deleteEmployee(employeeId) {
    if (!confirm("Czy jesteś pewien?")) return;
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

            alert("Pracownika stworzono ✅");
            window.location.href = "/admin/employees";
        } catch (err) {
            alert("Błąd tworzenia ❌\n" + err.message);
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
        tbody.innerHTML = `<tr><td colspan="5">Błąd: ${err.message}</td></tr>`;
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

        alert("Przyrząd stworzono ✅");
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

        alert("Zapisano ✅");
    });
}

async function deleteDevice() {
    if (!confirm("Czy usunąć urządzenie?")) return;
    await api(`/admin/api/devices/${deviceId}`, { method: "DELETE" });
    window.location.href = "/admin/devices";
}

/* ================================
   USERS
================================ */

async function loadUsers() {
    const tbody = document.querySelector("#usersTable tbody");
    const search = document.getElementById("userSearch");
    if (!tbody) return;

    const q = search?.value ?? "";
    const url = q
        ? `/admin/api/users?q=${encodeURIComponent(q)}`
        : "/admin/api/users";

    try {
        const users = await api(url);
        tbody.innerHTML = "";

        for (const u of users) {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${u.username}</td>
                <td>${u.first_name}</td>
                <td>${u.last_name}</td>
                <td>${u.role}</td>
                <td>${u.is_active ? "✅" : "❌"}</td>
                <td><a href="/admin/users/${u.id}">✏️</a></td>
            `;
            tbody.appendChild(tr);
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6">Błąd: ${err.message}</td></tr>`;
    }
}

async function loadUserDetail(userId) {
    const form = document.getElementById("userForm");
    if (!form) return;

    const u = await api(`/admin/api/users/${userId}`);

    form.first_name.value = u.first_name;
    form.last_name.value = u.last_name;
    form.role.value = u.role;
    form.is_active.checked = u.is_active;

    form.addEventListener("submit", async e => {
        e.preventDefault();

        await api(`/admin/api/users/${userId}`, {
            method: "PUT",
            body: JSON.stringify({
                first_name: form.first_name.value,
                last_name: form.last_name.value,
                password: form.password.value || null,
                role: form.role.value,
                is_active: form.is_active.checked
            })
        });

        alert("Zapisano ✅");
    });
}

async function deleteUser() {
    if (!confirm("Czy usunąć użytkownika?")) return;
    await api(`/admin/api/users/${userId}`, { method: "DELETE" });
    window.location.href = "/admin/users";
}

/* ================================
   CREATE USER
================================ */

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("userCreateForm");
    if (!form) return;

    form.addEventListener("submit", async e => {
        e.preventDefault();

        await api("/admin/api/users", {
            method: "POST",
            body: JSON.stringify({
                username: form.username.value,
                first_name: form.first_name.value,
                last_name: form.last_name.value,
                password: form.password.value,
                role: form.role.value
            })
        });

        alert("Korzystnik stworzono ✅");
        window.location.href = "/admin/users";
    });
});

/* ================================
   АВТОЗАПУСК
================================ */

document.addEventListener("DOMContentLoaded", () => {
    loadEmployees();

    if (document.querySelector("#devicesTable")) {
        loadDevices();
    }

    if (document.querySelector("#usersTable")) {
        loadUsers();
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

    const userSearch = document.getElementById("userSearch");
    if (userSearch) {
        let timeout;
        userSearch.addEventListener("input", () => {
            clearTimeout(timeout);
            timeout = setTimeout(loadUsers, 300);
        });
    }

    if (typeof employeeId !== "undefined") {
        loadEmployeeDetail(employeeId);
    }

    if (typeof deviceId !== "undefined") {
        loadDeviceDetail(deviceId);
    }

    if (typeof userId !== "undefined") {
        loadUserDetail(userId);
    }
});

/* ================================
   TRANSACTIONS 
================================ */

let transactionsPage = 1;
const TRANSACTIONS_PER_PAGE = 10;

async function loadTransactions(page = 1) {
    const tbody = document.querySelector("#transactionsTable tbody");
    if (!tbody) return;

    const employeeInput = document.getElementById("transactionEmployeeSearch");
    const deviceInput = document.getElementById("transactionDeviceSearch");
    const dateFromInput = document.getElementById("transactionDateFrom");
    const dateToInput = document.getElementById("transactionDateTo");
    const typeInput = document.getElementById("transactionType");

    const employee_q = employeeInput?.value ?? "";
    const device_q = deviceInput?.value ?? "";
    const date_from = dateFromInput?.value ?? "";
    const date_to = dateToInput?.value ?? "";
    const tx_type = typeInput?.value ?? "";

    const params = new URLSearchParams({
        page: page,
        limit: TRANSACTIONS_PER_PAGE
    });

    if (employee_q) params.append("employee_q", employee_q);
    if (device_q) params.append("device_q", device_q);
    if (date_from) params.append("date_from", date_from);
    if (date_to) params.append("date_to", date_to);
    if (tx_type) params.append("tx_type", tx_type);

    tbody.innerHTML = `<tr><td colspan="4">Ładowanie danych...</td></tr>`;

    try {
        const data = await api(`/admin/api/transactions?${params.toString()}`);

        tbody.innerHTML = "";

        if (data.items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4">Nic nie znaleziono</td></tr>`;
        }

        for (const t of data.items) {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${new Date(t.timestamp).toLocaleString()}</td>
                <td>${t.type}</td>
                <td>
                    ${t.employee
                        ? `${t.employee.wms_login ?? ""} ${t.employee.first_name} ${t.employee.last_name}`
                        : "—"}
                </td>
                <td>${t.device?.name ?? "—"}</td>
            `;
            tbody.appendChild(tr);
        }

        renderTransactionsPagination(data.page, data.pages);

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4">Błąd: ${err.message}</td></tr>`;
    }
}

function renderTransactionsPagination(page, pages) {
    const container = document.getElementById("transactionsPagination");
    if (!container) return;

    container.innerHTML = "";

    for (let p = 1; p <= pages; p++) {
        const btn = document.createElement("button");
        btn.textContent = p;
        btn.disabled = p === page;
        btn.addEventListener("click", () => loadTransactions(p));
        container.appendChild(btn);
    }
}

/* ================================
   TRANSACTIONS AUTOSTART
================================ */

document.addEventListener("DOMContentLoaded", () => {
    if (!document.querySelector("#transactionsTable")) return;

    loadTransactions();

    const employeeInput = document.getElementById("transactionEmployeeSearch");
    const deviceInput = document.getElementById("transactionDeviceSearch");
    const dateFromInput = document.getElementById("transactionDateFrom");
    const dateToInput = document.getElementById("transactionDateTo");
    const typeInput = document.getElementById("transactionType");

    let timeout;

    // текстові поля — debounce
    [employeeInput, deviceInput].forEach(input => {
        if (!input) return;
        input.addEventListener("input", () => {
            clearTimeout(timeout);
            timeout = setTimeout(() => loadTransactions(1), 300);
        });
    });

    // date + select — одразу
    [dateFromInput, dateToInput, typeInput].forEach(input => {
        if (!input) return;
        input.addEventListener("change", () => loadTransactions(1));
    });
});
