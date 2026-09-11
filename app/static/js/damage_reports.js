/*************************************************
 * PROTOKÓŁ USZKODZENIA SPRZĘTU
 * Ten sam ekran w panelu kierownika i administratora.
 *
 * Pracuje z:
 *  - /api/damage-reports        (GET lista, POST nowy protokół)
 *  - /manager/api/devices       (lista urządzeń do wyboru)
 *************************************************/

"use strict";

const DAMAGE_SEARCH_DEBOUNCE_MS = 200;

let damageDevices = [];
let damageSearchTimer = null;

const $dmg = (id) => document.getElementById(id);

function dmgEscape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[ch]);
}

async function dmgApi(url, options = {}) {
    const response = await fetch(url, {
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        ...options
    });

    if (!response.ok) {
        let detail = response.statusText;
        try {
            detail = (await response.json()).detail ?? detail;
        } catch (err) {
            /* odpowiedź bez JSON — zostaje statusText */
        }
        throw new Error(detail);
    }

    return response.status === 204 ? null : response.json();
}

function dmgDeviceLabel(device) {
    const type = device.type === "scanner" ? "skaner" : "drukarka";
    const holder = device.employee
        ? `${device.employee.wms_login ?? ""}`.trim()
        : "wolne";
    return `${device.name} — ${type} — ${device.serial_number} — ${holder}`;
}

// Lista ma dwieście kilkadziesiąt pozycji, więc filtrujemy w przeglądarce:
// urządzenia i tak są już pobrane, a każde wciśnięcie klawisza nie musi
// obciążać serwera.
function dmgRenderDeviceOptions() {
    const select = $dmg("damageDeviceSelect");
    const hint = $dmg("damageDeviceHint");
    const needle = $dmg("damageDeviceSearch").value.trim().toLowerCase();

    const matching = needle
        ? damageDevices.filter((d) => dmgDeviceLabel(d).toLowerCase().includes(needle))
        : damageDevices;

    const selected = select.value;
    select.innerHTML = matching
        .map((d) => `<option value="${d.id}">${dmgEscape(dmgDeviceLabel(d))}</option>`)
        .join("");

    // Wybór przeżywa filtrowanie, dopóki wybrane urządzenie wciąż pasuje.
    if (matching.some((d) => String(d.id) === selected)) {
        select.value = selected;
    }

    hint.textContent = needle
        ? `Pasuje: ${matching.length} z ${damageDevices.length}`
        : `Urządzeń: ${damageDevices.length}`;
}

async function dmgLoadDevices() {
    try {
        damageDevices = await dmgApi("/manager/api/devices");
        dmgRenderDeviceOptions();
    } catch (err) {
        $dmg("damageDeviceHint").textContent = `Nie udało się pobrać urządzeń: ${err.message}`;
    }
}

function dmgPersonLabel(person) {
    if (!person) return "—";
    const name = [person.first_name, person.last_name].filter(Boolean).join(" ").trim();
    const login = person.wms_login ?? person.username;
    if (!login) return name || "—";
    return name ? `${login} — ${name}` : login;
}

async function dmgLoadReports() {
    const tbody = document.querySelector("#damageTable tbody");
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="5">Ładowanie danych...</td></tr>`;

    try {
        const reports = await dmgApi("/api/damage-reports");

        if (!reports.length) {
            tbody.innerHTML = `<tr><td colspan="5">Jeszcze nic nie zgłoszono</td></tr>`;
            return;
        }

        tbody.innerHTML = reports.map((r) => `
            <tr>
                <td>${new Date(r.timestamp).toLocaleString()}</td>
                <td>${dmgEscape(r.device?.name ?? "—")}</td>
                <td>${dmgEscape(dmgPersonLabel(r.employee))}</td>
                <td>${dmgEscape(dmgPersonLabel(r.reported_by))}</td>
                <td>${dmgEscape(r.description)}</td>
            </tr>`).join("");

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5">Błąd: ${dmgEscape(err.message)}</td></tr>`;
    }
}

/**
 * Co powiedzieć po zapisie.
 *
 * Protokół i mail to dwie osobne rzeczy: zapis zostaje nawet wtedy, gdy poczta
 * milczy. Komunikat ma to rozdzielić, zamiast pokazywać surowe liczby, z
 * których nie wiadomo, czy zgłoszenie w ogóle się udało.
 */
function dmgResultText(response) {
    const id = response.report.id;
    const { recipients, sent, errors } = response;

    if (!recipients) {
        return `Protokół #${id} zapisany. Maila nie wysłano — grupa ALL nie ma żadnego adresu.`;
    }

    if (!errors) {
        return `Protokół #${id} zapisany i wysłany do ${sent} `
            + `${sent === 1 ? "adresata" : "adresatów"} z grupy ALL.`;
    }

    if (!sent) {
        return `Protokół #${id} zapisany, ale mail nie dotarł do nikogo `
            + `(${recipients}) — sprawdź konfigurację poczty. Zgłoszenie jest w systemie.`;
    }

    return `Protokół #${id} zapisany. Mail poszedł do ${sent} z ${recipients} `
        + `adresatów — ${errors} nie wyszło, sprawdź konfigurację poczty.`;
}


async function dmgSubmit(event) {
    event.preventDefault();

    const button = $dmg("damageSubmit");
    const result = $dmg("damageResult");
    const deviceId = $dmg("damageDeviceSelect").value;
    const description = $dmg("damageDescription").value.trim();

    if (!deviceId) {
        result.className = "form-note form-note--warn";
        result.textContent = "Najpierw wybierz urządzenie z listy.";
        return;
    }

    if (!description) {
        result.className = "form-note form-note--warn";
        result.textContent = "Komentarz z opisem uszkodzenia jest wymagany.";
        return;
    }

    // Zapis rusza wysyłkę maili, więc drugie kliknięcie w trakcie oznaczałoby
    // drugi protokół i drugą turę listów.
    button.disabled = true;
    result.className = "form-note";
    result.textContent = "Zapisywanie i wysyłka...";

    try {
        const response = await dmgApi("/api/damage-reports", {
            method: "POST",
            body: JSON.stringify({ device_id: Number(deviceId), description })
        });

        result.textContent = dmgResultText(response);
        result.className = response.sent === response.recipients
            ? "form-note form-note--ok"
            : "form-note form-note--warn";

        $dmg("damageDescription").value = "";
        await dmgLoadReports();

    } catch (err) {
        result.className = "form-note form-note--warn";
        result.textContent = `Nie udało się zapisać protokołu: ${err.message}`;
    } finally {
        button.disabled = false;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    if (!$dmg("damageForm")) return;

    dmgLoadDevices();
    dmgLoadReports();

    $dmg("damageDeviceSearch").addEventListener("input", () => {
        clearTimeout(damageSearchTimer);
        damageSearchTimer = setTimeout(dmgRenderDeviceOptions, DAMAGE_SEARCH_DEBOUNCE_MS);
    });

    $dmg("damageForm").addEventListener("submit", dmgSubmit);
});
