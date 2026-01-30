/*************************************************
 * ADMIN PANEL JS
 * Працює з:
 *  - /admin/employees
 *  - /admin/employees/{id}
 *  - /admin/api/employees
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

    tbody.innerHTML = "<tr><td colspan='5'>Завантаження...</td></tr>";

    try {
        const url = q
            ? `/admin/api/employees?q=${encodeURIComponent(q)}`
            : "/admin/api/employees";

        const employees = await api(url);

        tbody.innerHTML = "";

        for (const e of employees) {
            const tr = document.createElement("tr");

            tr.innerHTML = `
                <td>${e.wms_login}</td>
                <td>${e.first_name}</td>
                <td>${e.last_name}</td>
                <td>${e.company}</td>
                <td>${e.rfid}</td>
                <td>
                    <a href="/admin/employees/${e.id}">✏️</a>
                </td>
            `;

            tbody.appendChild(tr);
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5">Помилка: ${err.message}</td></tr>`;
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

    await api(`/admin/api/employees/${employeeId}`, {
        method: "DELETE"
    });

    window.location.href = "/admin/employees";
}


/* ================================
   СТВОРЕННЯ ПРАЦІВНИКА
================================ */

async function createEmployee() {
    const first_name = prompt("Імʼя:");
    if (!first_name) return;

    const last_name = prompt("Прізвище:");
    const company = prompt("Компанія:");
    const rfid = prompt("RFID:");
    const wms_login = prompt("WMS_LOGIN:");

    await api("/admin/api/employees", {
        method: "POST",
        body: JSON.stringify({
            wms_login,
            first_name,
            last_name,
            company,
            rfid
        })
    });

    loadEmployees();
}


/* ================================
   АВТОЗАПУСК
================================ */

document.addEventListener("DOMContentLoaded", () => {
    loadEmployees();

    const searchInput = document.getElementById("search");
    if (searchInput) {
        let timeout;
        searchInput.addEventListener("input", () => {
            clearTimeout(timeout);
            timeout = setTimeout(loadEmployees, 300);
        });
    }

    if (typeof employeeId !== "undefined") {
        loadEmployeeDetail(employeeId);
    }
});
