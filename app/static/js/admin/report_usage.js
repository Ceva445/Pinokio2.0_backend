/*************************************************
 * RAPORT: WYKORZYSTANIE SPRZĘTU
 *
 * Dwie listy — sprzęt u ludzi i sprzęt leżący — obie posortowane od
 * najdłuższego. Minuty liczy serwer; ekran tylko je pokazuje i filtruje.
 *
 * Pracuje z:
 *  - /admin/api/reports/usage
 *  - /admin/api/reports/usage.xlsx
 *************************************************/

"use strict";

const USAGE_STEP = 20;

let usageDevices = [];
let usageShownInUse = 10;
let usageShownFree = 10;

const $u = (id) => document.getElementById(id);

function usageEscape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[ch]);
}

/* Godziny i minuty. Powyżej trzech dób same godziny przestają cokolwiek
   znaczyć, więc wtedy dochodzą dni — tak samo liczy to plik XLSX. */
function usageTime(minutes) {
    if (minutes == null) return "—";
    const h = Math.floor(minutes / 60), m = Math.round(minutes % 60);
    if (h >= 72) return `${Math.floor(h / 24)}d ${h % 24}h`;
    return h ? `${h}h ${String(m).padStart(2, "0")}min` : `${m}min`;
}

/* Progi: dniówka to 8h, zmiana z okładem 12h, powyżej doby to już zaleganie. */
function usageLevel(minutes) {
    if (minutes == null) return "none";
    if (minutes < 8 * 60) return "ok";
    if (minutes < 12 * 60) return "warn";
    if (minutes < 24 * 60) return "long";
    return "crit";
}

const USAGE_COLOR = {
    ok: "var(--usage-ok)", warn: "var(--usage-warn)", long: "var(--usage-long)",
    crit: "var(--usage-crit)", none: "var(--text-secondary)"
};
const USAGE_LEVEL_PL = {
    ok: "do 8h", warn: "8–12h", long: "12–24h",
    crit: "ponad dobę", none: "bez historii"
};

function usageMedian(values) {
    const sorted = values.filter((v) => v != null).sort((a, b) => a - b);
    return sorted.length ? sorted[Math.floor(sorted.length / 2)] : null;
}

function usageFiltered() {
    const type = $u("usageType").value;
    const site = $u("usageSite").value;
    const needle = $u("usageSearch").value.trim().toLowerCase();

    return usageDevices.filter((d) => {
        if (type && d.type !== type) return false;
        if (site && d.site !== site) return false;
        if (!needle) return true;
        const haystack = [d.name, d.employee?.wms_login, d.employee?.first_name,
                          d.employee?.last_name].filter(Boolean).join(" ").toLowerCase();
        return haystack.includes(needle);
    });
}

// ---------------------------------------------------------------------------
// Podpowiedź przy najechaniu — cel jest całym wierszem, nie samym paskiem.
// ---------------------------------------------------------------------------
function usageShowTip(event, device) {
    const tip = $u("usageTip");
    const person = device.employee;

    tip.innerHTML =
        `<b>${usageEscape(device.name)}</b> ` +
        `<span class="m">${device.type === "scanner" ? "skaner" : "drukarka"}</span><br>` +
        (person
            ? `<span class="m">u:</span> ${usageEscape(person.wms_login ?? "—")}` +
              `${person.first_name ? " · " + usageEscape(person.first_name + " " + person.last_name) : ""}<br>`
            : `<span class="m">wolne</span><br>`) +
        `<span class="m">site:</span> ${usageEscape(device.site ?? "—")} · ` +
        `<span class="m">status:</span> ${usageEscape(device.status ?? "—")}<br>` +
        `<span class="m">${device.in_use ? "w użyciu od" : "wolne od"}:</span> ` +
        `${usageEscape(device.since ?? "—")}<br>` +
        `<b>${usageTime(device.minutes)}</b> ` +
        `<span class="m">(${USAGE_LEVEL_PL[usageLevel(device.minutes)]})</span>`;

    tip.style.opacity = 1;
    tip.style.left = Math.min(event.clientX + 14, window.innerWidth - 300) + "px";
    tip.style.top = Math.min(event.clientY + 14, window.innerHeight - 150) + "px";
}

function usageHideTip() {
    $u("usageTip").style.opacity = 0;
}

// ---------------------------------------------------------------------------
function usageRenderList(container, devices, shown, withPerson) {
    if (!devices.length) {
        container.innerHTML = `<div class="drill-muted">Nic nie pasuje do filtrów</div>`;
        return;
    }

    const slice = devices.slice(0, shown);

    // Pierwiastek zamiast wprost proporcji: obok siebie stoją godziny i tygodnie,
    // a przy zwykłej skali jeden sprzęt stojący miesiąc sprowadza resztę pasków
    // do kresek. Kolejność zostaje ta sama, a dokładny czas i tak stoi obok.
    const max = Math.max(...slice.map((d) => d.minutes ?? 0), 1);

    container.innerHTML = slice.map((d) => {
        const width = Math.max(2, Math.sqrt((d.minutes ?? 0) / max) * 100);
        const person = d.employee;
        const caption = withPerson && person
            ? `<div class="usage-who">${usageEscape(person.wms_login ?? "")}` +
              `${person.first_name ? " · " + usageEscape(person.first_name + " " + person.last_name) : ""}` +
              ` · ${usageEscape(d.site ?? "—")}</div>`
            : "";

        return `
            <div class="usage-row" data-name="${usageEscape(d.name)}">
                <div class="usage-name">${usageEscape(d.name)}</div>
                <div class="usage-track">
                    <div class="usage-bar" style="width:${width.toFixed(1)}%;
                         background:${USAGE_COLOR[usageLevel(d.minutes)]}"></div>
                </div>
                <div class="usage-value">${usageTime(d.minutes)}</div>
            </div>${caption}`;
    }).join("");

    container.querySelectorAll(".usage-row").forEach((row) => {
        const device = devices.find((d) => d.name === row.dataset.name);
        row.addEventListener("mousemove", (event) => usageShowTip(event, device));
        row.addEventListener("mouseleave", usageHideTip);
    });
}

function usageRenderTiles(devices) {
    const inUse = devices.filter((d) => d.in_use);
    const free = devices.filter((d) => !d.in_use);
    const overdue = inUse.filter((d) => (d.minutes ?? 0) >= 12 * 60);
    const longest = [...inUse].sort((a, b) => (b.minutes ?? 0) - (a.minutes ?? 0))[0];

    $u("usageTiles").innerHTML = `
        <div class="usage-tile accent">
            <div class="k">W użyciu</div><div class="v">${inUse.length}</div>
            <div class="n">z ${devices.length} urządzeń</div>
        </div>
        <div class="usage-tile">
            <div class="k">Mediana użycia</div>
            <div class="v">${usageTime(usageMedian(inUse.map((d) => d.minutes)))}</div>
            <div class="n">od ostatniej rejestracji</div>
        </div>
        <div class="usage-tile">
            <div class="k">Wolne</div><div class="v">${free.length}</div>
            <div class="n">mediana postoju ${usageTime(usageMedian(free.map((d) => d.minutes)))}</div>
        </div>
        <div class="usage-tile warn">
            <div class="k">Ponad 12h u pracownika</div><div class="v">${overdue.length}</div>
            <div class="n">najdłużej: ${longest
                ? usageEscape(longest.name) + " · " + usageTime(longest.minutes) : "—"}</div>
        </div>`;
}

function usageRender() {
    const devices = usageFiltered();
    usageRenderTiles(devices);

    const inUse = devices.filter((d) => d.in_use)
        .sort((a, b) => (b.minutes ?? 0) - (a.minutes ?? 0));
    const free = devices.filter((d) => !d.in_use)
        .sort((a, b) => (b.minutes ?? 0) - (a.minutes ?? 0));

    usageRenderList($u("usageListInUse"), inUse, usageShownInUse, true);
    usageRenderList($u("usageListFree"), free, usageShownFree, false);

    [["usageMoreInUse", inUse.length, usageShownInUse],
     ["usageMoreFree", free.length, usageShownFree]].forEach(([id, total, shown]) => {
        const button = $u(id);
        button.style.display = total > 10 ? "" : "none";
        button.textContent = shown >= total
            ? `Wszystkie ${total}`
            : `Pokaż więcej (${total - shown})`;
    });
}

async function usageLoad() {
    const listInUse = $u("usageListInUse");
    listInUse.innerHTML = "Ładowanie danych...";

    try {
        const response = await fetch("/admin/api/reports/usage", {
            credentials: "include",
            headers: { "X-Requested-With": "XMLHttpRequest" }
        });
        if (!response.ok) throw new Error((await response.json()).detail ?? response.statusText);

        const data = await response.json();
        usageDevices = data.devices;

        $u("usageStamp").textContent = `Stan na ${data.generated_at}.`;
        $u("usageSite").innerHTML = '<option value="">Wszystkie site</option>' +
            [...new Set(usageDevices.map((d) => d.site).filter(Boolean))].sort()
                .map((s) => `<option>${usageEscape(s)}</option>`).join("");

        usageRender();

    } catch (err) {
        listInUse.innerHTML = `Błąd: ${usageEscape(err.message)}`;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    if (!$u("usageListInUse")) return;

    usageLoad();

    ["usageType", "usageSite", "usageSearch"].forEach((id) =>
        $u(id).addEventListener("input", () => {
            usageShownInUse = 10;
            usageShownFree = 10;
            usageRender();
        }));

    $u("usageReset").addEventListener("click", () => {
        ["usageType", "usageSite", "usageSearch"].forEach((id) => { $u(id).value = ""; });
        usageShownInUse = 10;
        usageShownFree = 10;
        usageRender();
    });

    $u("usageMoreInUse").addEventListener("click", () => { usageShownInUse += USAGE_STEP; usageRender(); });
    $u("usageMoreFree").addEventListener("click", () => { usageShownFree += USAGE_STEP; usageRender(); });
});
