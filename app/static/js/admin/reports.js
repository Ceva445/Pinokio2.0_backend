/*************************************************
 * RAPORT — HISTORIA REJESTRACJI
 * Pracuje z:
 *  - /admin/api/reports/registrations/options
 *  - /admin/api/reports/registrations          (podgląd)
 *  - /admin/api/reports/registrations.xlsx     (plik)
 *************************************************/

"use strict";

// Urządzenia można wklejać listą; średnik jest separatorem z WMS, ale przecinek
// i nowa linia trafiają się równie często przy kopiowaniu z maila.
const DEVICE_LIST_SEPARATORS = /[;,\n\r\t]+/;

const PREVIEW_DEBOUNCE_MS = 350;

let allDevices = [];
const selectedDeviceIds = new Set();
let previewTimer = null;

const $r = (id) => document.getElementById(id);


/* ================================
   FILTRY -> ZAPYTANIE
================================ */
function reportParams() {
    const params = new URLSearchParams();

    const dateFrom = $r("reportDateFrom").value;
    const dateTo = $r("reportDateTo").value;
    const department = $r("reportDepartment").value;

    if (dateFrom) params.append("date_from", dateFrom);
    if (dateTo) params.append("date_to", dateTo);
    if (department) params.append("department", department);
    for (const id of selectedDeviceIds) params.append("device_ids", id);

    return params;
}


/* ================================
   WYBÓR URZĄDZEŃ
================================ */
function renderDeviceChips() {
    const box = $r("devicePickerChips");
    box.innerHTML = "";

    if (!selectedDeviceIds.size) {
        box.innerHTML = `<span class="drill-muted">Wszystkie urządzenia</span>`;
        return;
    }

    const chosen = allDevices.filter((d) => selectedDeviceIds.has(d.id));
    for (const device of chosen) {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.innerHTML = `${esc(device.name)}<button type="button" title="Usuń">×</button>`;
        chip.querySelector("button").addEventListener("click", () => {
            selectedDeviceIds.delete(device.id);
            refreshDevicePicker();
        });
        box.appendChild(chip);
    }
}

function renderDeviceList() {
    const list = $r("devicePickerList");
    const needle = $r("devicePickerSearch").value.trim().toLowerCase();

    // Wklejona lista ma własną obsługę — dopóki w polu jest separator, nie
    // filtrujemy po niej, bo nic by nie zostało na ekranie.
    const filtering = needle && !DEVICE_LIST_SEPARATORS.test(needle);
    const shown = filtering
        ? allDevices.filter((d) => d.name.toLowerCase().includes(needle))
        : allDevices;

    list.innerHTML = "";

    if (!shown.length) {
        list.innerHTML = `<div class="picker__empty">Nic nie znaleziono</div>`;
        return;
    }

    for (const device of shown) {
        const row = document.createElement("label");
        row.className = "picker__row";
        row.innerHTML = `
            <input type="checkbox" value="${device.id}" ${selectedDeviceIds.has(device.id) ? "checked" : ""}>
            <span>${esc(device.name)}</span>
            <span class="drill-muted">${device.type === "scanner" ? "📦 Skaner" : "🖨 Drukarka"}</span>
            ${device.enabled ? "" : `<span class="drill-flag">niedostępny</span>`}
        `;
        row.querySelector("input").addEventListener("change", (event) => {
            if (event.target.checked) selectedDeviceIds.add(device.id);
            else selectedDeviceIds.delete(device.id);
            renderDeviceChips();
            schedulePreview();
        });
        list.appendChild(row);
    }
}

function refreshDevicePicker() {
    renderDeviceChips();
    renderDeviceList();
    schedulePreview();
}

/**
 * Wklejony ciąg "TERM003;TERM004" zaznacza urządzenia zamiast filtrować listę.
 * Nazwy porównujemy bez wielkości liter i spacji — kopiuje się je z różnych
 * miejsc. Czego nie ma w słowniku, o tym mówimy wprost, zamiast po cichu pomijać.
 */
function applyPastedDeviceList(text) {
    const names = text.split(DEVICE_LIST_SEPARATORS).map((n) => n.trim()).filter(Boolean);
    if (!names.length) return false;

    const byName = new Map(allDevices.map((d) => [d.name.trim().toLowerCase(), d]));
    const matched = [];
    const missing = [];

    for (const name of names) {
        const device = byName.get(name.toLowerCase());
        if (device) {
            selectedDeviceIds.add(device.id);
            matched.push(device.name);
        } else {
            missing.push(name);
        }
    }

    const info = $r("devicePickerPasteInfo");
    const parts = [`Dopasowano: ${matched.length} z ${names.length}`];
    if (missing.length) parts.push(`nie znaleziono: ${missing.join(", ")}`);
    info.textContent = parts.join(" · ");
    info.classList.toggle("picker__info--warn", missing.length > 0);
    info.classList.remove("hidden");

    $r("devicePickerSearch").value = "";
    refreshDevicePicker();
    return true;
}


/* ================================
   PODGLĄD
================================ */
function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(loadReportPreview, PREVIEW_DEBOUNCE_MS);
}

async function loadReportPreview() {
    const tbody = document.querySelector("#reportPreviewTable tbody");
    const summary = $r("reportSummary");
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="5">Ładowanie danych...</td></tr>`;

    try {
        const data = await api(`/admin/api/reports/registrations?${reportParams().toString()}`);

        tbody.innerHTML = "";

        if (!data.rows.length) {
            tbody.innerHTML = `<tr><td colspan="5">Nic nie znaleziono</td></tr>`;
        }

        for (const row of data.rows) {
            const tr = document.createElement("tr");
            tr.innerHTML = row.map((value) => `<td>${esc(value ?? "—")}</td>`).join("");
            tbody.appendChild(tr);
        }

        summary.textContent = data.total > data.rows.length
            ? `Wierszy: ${data.total} (podgląd pierwszych ${data.rows.length}) · plik: ${data.file_name}`
            : `Wierszy: ${data.total} · plik: ${data.file_name}`;

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5">Błąd: ${esc(err.message)}</td></tr>`;
        summary.textContent = "";
    }
}


/* ================================
   POBRANIE PLIKU
================================ */
async function downloadReport() {
    const button = $r("reportDownload");
    const label = button.textContent;
    button.disabled = true;
    button.textContent = "Generowanie…";

    try {
        // Przez fetch, a nie zwykły link — inaczej błąd 401/500 otworzyłby się
        // jako strona zamiast wylądować w komunikacie.
        const resp = await fetch(`/admin/api/reports/registrations.xlsx?${reportParams().toString()}`, {
            credentials: "include"
        });
        if (!resp.ok) throw new Error(getErrorMessage(await resp.text()));

        const blob = await resp.blob();
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = fileNameFromResponse(resp) || "raport.xlsx";
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(link.href);

        showSuccess(`Pobrano: ${link.download}`);
    } catch (err) {
        showError(err.message);
    } finally {
        button.disabled = false;
        button.textContent = label;
    }
}

function fileNameFromResponse(resp) {
    const header = resp.headers.get("Content-Disposition") || "";
    const match = header.match(/filename="([^"]+)"/);
    return match ? match[1] : null;
}


/* ================================
   START
================================ */
async function initRegistrationsReport() {
    const search = $r("devicePickerSearch");

    try {
        const options = await api("/admin/api/reports/registrations/options");
        allDevices = options.devices;

        const departmentSelect = $r("reportDepartment");
        for (const department of options.departments) {
            const option = document.createElement("option");
            option.value = department;
            option.textContent = department;
            departmentSelect.appendChild(option);
        }
    } catch (err) {
        showError(err.message);
        $r("devicePickerList").innerHTML = `<div class="picker__empty">Błąd: ${esc(err.message)}</div>`;
        return;
    }

    renderDeviceChips();
    renderDeviceList();
    loadReportPreview();

    search.addEventListener("input", () => {
        if (DEVICE_LIST_SEPARATORS.test(search.value)) {
            applyPastedDeviceList(search.value);
            return;
        }
        renderDeviceList();
    });

    // Wklejenie jednej nazwy (bez separatora) też ma zaznaczać, jeśli trafia
    // dokładnie w urządzenie — Enter potwierdza wybór z wyszukiwarki.
    search.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        applyPastedDeviceList(search.value);
    });

    $r("devicePickerClear").addEventListener("click", () => {
        selectedDeviceIds.clear();
        search.value = "";
        $r("devicePickerPasteInfo").classList.add("hidden");
        refreshDevicePicker();
    });

    for (const id of ["reportDateFrom", "reportDateTo", "reportDepartment"]) {
        $r(id).addEventListener("change", schedulePreview);
    }

    $r("reportDownload").addEventListener("click", downloadReport);

    $r("reportReset").addEventListener("click", () => {
        $r("reportDateFrom").value = "";
        $r("reportDateTo").value = "";
        $r("reportDepartment").value = "";
        selectedDeviceIds.clear();
        search.value = "";
        $r("devicePickerPasteInfo").classList.add("hidden");
        refreshDevicePicker();
    });
}

document.addEventListener("DOMContentLoaded", () => {
    if ($r("registrationsReportForm")) initRegistrationsReport();
});
