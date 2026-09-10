/*************************************************
 * PANEL KIEROWNIKA — URZĄDZENIA (tylko podgląd)
 * Pracuje z:
 *  - /manager/api/devices
 *  - /manager/api/devices/statuses
 *
 * Świadomie bez odnośników do /admin/* — kierownik dostałby tam 403 i pustą
 * stronę, więc nazwy zostają tekstem.
 *************************************************/

"use strict";

const SEARCH_DEBOUNCE_MS = 300;

let searchTimer = null;
let requestId = 0;

const $d = (id) => document.getElementById(id);

// Nazwy urządzeń i osób wpisuje admin, a wiersze składamy przez innerHTML.
function escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[ch]);
}

async function api(url) {
    const resp = await fetch(url, { credentials: "include" });
    if (!resp.ok) {
        let detail = resp.statusText;
        try {
            detail = (await resp.json()).detail ?? detail;
        } catch (err) {
            /* odpowiedź bez JSON — zostaje statusText */
        }
        throw new Error(detail);
    }
    return resp.json();
}

function deviceParams() {
    const params = new URLSearchParams();
    const search = $d("deviceSearch").value.trim();
    const type = $d("deviceTypeFilter").value;
    const status = $d("deviceStatusFilter").value;
    const assigned = $d("deviceAssignedFilter").value;

    if (search) params.append("q", search);
    if (type) params.append("type", type);
    if (status) params.append("status_ids", status);
    if (assigned) params.append("assigned", assigned);

    return params;
}

function personLabel(employee) {
    // Ten sam zapis co w panelach dashboardu: login WMS pierwszy.
    const name = [employee.first_name, employee.last_name].filter(Boolean).join(" ").trim();
    if (!employee.wms_login) return name || "—";
    return name ? `${employee.wms_login} — ${name}` : employee.wms_login;
}

async function loadDevices() {
    const tbody = document.querySelector("#managerDevicesTable tbody");
    const summary = $d("deviceSummary");
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="9">Ładowanie danych...</td></tr>`;

    // Szybkie pisanie w wyszukiwarce wysyła kilka zapytań naraz, a odpowiedzi
    // potrafią wrócić w innej kolejności — starsza nie może nadpisać nowszej.
    const myRequest = ++requestId;

    try {
        const devices = await api(`/manager/api/devices?${deviceParams().toString()}`);
        if (myRequest !== requestId) return;

        tbody.innerHTML = "";

        if (!devices.length) {
            tbody.innerHTML = `<tr><td colspan="9">Nic nie znaleziono</td></tr>`;
            summary.textContent = "";
            return;
        }

        for (const device of devices) {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${escape(device.name)}</td>
                <td>${device.type === "scanner" ? "📦 Skaner" : "🖨 Drukarka"}</td>
                <td>${escape(device.serial_number)}</td>
                <td>${escape(device.rfid)}</td>
                <td>${escape(device.site ?? "—")}</td>
                <td>${escape(device.status_name ?? "—")}</td>
                <td>${device.enabled ? "✅" : "❌"}</td>
                <td>${device.employee
                    ? escape(personLabel(device.employee))
                    : `<span class="drill-muted">wolne</span>`}</td>
                <td>${escape(device.employee?.site ?? "—")}</td>
            `;
            tbody.appendChild(tr);
        }

        const held = devices.filter((d) => d.employee).length;
        summary.textContent = `Znaleziono: ${devices.length} · wydane: ${held} · wolne: ${devices.length - held}`;

    } catch (err) {
        if (myRequest !== requestId) return;
        tbody.innerHTML = `<tr><td colspan="9">Błąd: ${escape(err.message)}</td></tr>`;
        summary.textContent = "";
    }
}

async function loadStatuses() {
    const select = $d("deviceStatusFilter");
    try {
        for (const status of await api("/manager/api/devices/statuses")) {
            const option = document.createElement("option");
            option.value = status.id;
            option.textContent = status.name;
            select.appendChild(option);
        }
    } catch (err) {
        // Brak słownika nie może wywalić całej strony — lista urządzeń i tak działa.
        console.warn("Nie udało się pobrać statusów:", err.message);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    if (!document.querySelector("#managerDevicesTable")) return;

    loadStatuses();
    loadDevices();

    $d("deviceSearch").addEventListener("input", () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(loadDevices, SEARCH_DEBOUNCE_MS);
    });

    ["deviceTypeFilter", "deviceStatusFilter", "deviceAssignedFilter"].forEach((id) => {
        $d(id).addEventListener("change", loadDevices);
    });

    $d("deviceFiltersReset").addEventListener("click", () => {
        $d("deviceSearch").value = "";
        ["deviceTypeFilter", "deviceStatusFilter", "deviceAssignedFilter"].forEach((id) => {
            $d(id).value = "";
        });
        loadDevices();
    });
});
