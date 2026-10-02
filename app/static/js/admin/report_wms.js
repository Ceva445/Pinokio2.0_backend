/*************************************************
 * RAPORT: PRACA W WMS BEZ POBRANEGO SPRZĘTU
 *
 * Plik z WMS zostaje w przeglądarce. Przy analizie i przy pobieraniu jedzie
 * na serwer jako multipart — nic nie jest przechowywane między żądaniami.
 *
 * Pracuje z:
 *  - POST /admin/api/reports/wms
 *  - POST /admin/api/reports/wms.xlsx
 *************************************************/

"use strict";

let wmsRaport = null;

const $w = (id) => document.getElementById(id);

function wmsEscape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[ch]);
}

function wmsKomunikat(tekst, blad = false) {
    const pole = $w("wmsMessage");
    pole.textContent = tekst;
    pole.style.color = blad ? "var(--usage-crit)" : "";
}

/* Ten sam formularz idzie i po wynik, i po plik — stąd jedno miejsce. */
function wmsFormData() {
    const plik = $w("wmsFile").files[0];
    if (!plik) {
        wmsKomunikat("Najpierw wybierz plik z WMS.", true);
        return null;
    }
    const dane = new FormData();
    dane.append("file", plik);
    return dane;
}

/* 1 ruch, 2–4 ruchy, 5+ ruchów — bez tego lista mówi "1 ruchów". */
function wmsRuchy(ile) {
    const dziesiatki = ile % 100;
    if (ile === 1) return "1 ruch";
    if (dziesiatki < 10 || dziesiatki > 20) {
        const jednosci = ile % 10;
        if (jednosci >= 2 && jednosci <= 4) return `${ile} ruchy`;
    }
    return `${ile} ruchów`;
}

function wmsKody(kody) {
    return kody.map(([kod, ile]) => `${wmsEscape(kod)} ×${ile}`).join(", ");
}

function wmsOsoba(w) {
    const imie = [w.first_name, w.last_name].filter(Boolean).join(" ");
    return imie ? `${wmsEscape(w.login)} · ${wmsEscape(imie)}` : wmsEscape(w.login);
}

function wmsWierszBrak(w) {
    return `
        <div class="usage-row">
            <div class="usage-name">${wmsRuchy(w.moves_without)}<br>
                <span class="usage-who">z ${w.moves} w pliku</span></div>
            <div style="flex:1">
                <div>${wmsOsoba(w)}</div>
                <div class="usage-who">
                    ${wmsEscape(w.company ?? "—")} · ${wmsEscape(w.site ?? "brak site")}
                    · bez sprzętu: ${wmsEscape(w.first_without)} – ${wmsEscape(w.last_without)}
                </div>
                <div class="usage-who">${wmsKody(w.codes)}</div>
                <div class="usage-who">ostatnia rejestracja:
                    ${w.last_registration ? wmsEscape(w.last_registration) : "nigdy"}</div>
            </div>
        </div>`;
}

function wmsWierszNieznany(w) {
    return `
        <div class="usage-row">
            <div class="usage-name">${wmsRuchy(w.moves)}</div>
            <div style="flex:1">
                <div>${wmsEscape(w.login)}</div>
                <div class="usage-who">${wmsEscape(w.first)} – ${wmsEscape(w.last)}</div>
                <div class="usage-who">${wmsKody(w.codes)}</div>
            </div>
        </div>`;
}

function wmsRysuj(raport) {
    const t = raport.totals;

    $w("wmsStamp").textContent =
        `Okres z pliku: ${raport.from} – ${raport.to} (${raport.hours} h).`;

    $w("wmsTiles").innerHTML = `
        <div class="usage-tile warn">
            <div class="k">Bez sprzętu</div><div class="v">${t.not_registered}</div>
            <div class="n">pracowali, nie mając wydanego urządzenia</div>
        </div>
        <div class="usage-tile accent">
            <div class="k">Ze sprzętem</div><div class="v">${t.with_device}</div>
            <div class="n">wszystko się zgadza</div>
        </div>
        <div class="usage-tile">
            <div class="k">Nieznane loginy</div><div class="v">${t.unknown}</div>
            <div class="n">nie ma ich w naszej bazie</div>
        </div>
        <div class="usage-tile">
            <div class="k">Ruchy w pliku</div><div class="v">${t.rows_total}</div>
            <div class="n">${t.logins_in_window} loginów w tym okresie</div>
        </div>`;

    $w("wmsListMissing").innerHTML = raport.not_registered.length
        ? raport.not_registered.map(wmsWierszBrak).join("")
        : `<div class="drill-muted">Nikt taki się nie znalazł — każdy, kto pracował, miał wydany sprzęt.</div>`;

    $w("wmsListUnknown").innerHTML = raport.unknown.length
        ? raport.unknown.map(wmsWierszNieznany).join("")
        : `<div class="drill-muted">Wszystkie loginy z pliku są w naszej bazie.</div>`;
}

async function wmsAnalizuj() {
    const dane = wmsFormData();
    if (!dane) return;

    $w("wmsRun").disabled = true;
    wmsKomunikat("Analizuję…");

    try {
        const odpowiedz = await fetch("/admin/api/reports/wms", {
            method: "POST",
            body: dane,
            credentials: "include",
            headers: { "X-Requested-With": "XMLHttpRequest" }
        });
        const tresc = await odpowiedz.json();
        if (!odpowiedz.ok) throw new Error(tresc.detail ?? odpowiedz.statusText);

        wmsRaport = tresc;
        wmsKomunikat("");
        wmsRysuj(tresc);
        $w("wmsDownload").disabled = false;
    } catch (err) {
        wmsRaport = null;
        $w("wmsDownload").disabled = true;
        wmsKomunikat("Błąd: " + err.message, true);
    } finally {
        $w("wmsRun").disabled = false;
    }
}

/* Plik składa serwer z tego samego wsadu, więc wysyłamy go drugi raz —
   inaczej XLSX pokazywałby co innego niż ekran. */
async function wmsPobierz() {
    const dane = wmsFormData();
    if (!dane) return;

    $w("wmsDownload").disabled = true;
    try {
        const odpowiedz = await fetch("/admin/api/reports/wms.xlsx", {
            method: "POST",
            body: dane,
            credentials: "include",
            headers: { "X-Requested-With": "XMLHttpRequest" }
        });
        if (!odpowiedz.ok) {
            const tresc = await odpowiedz.json().catch(() => ({}));
            throw new Error(tresc.detail ?? odpowiedz.statusText);
        }

        const blob = await odpowiedz.blob();
        const adres = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = adres;
        link.download = "Praca_WMS_bez_sprzetu.xlsx";
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(adres);
    } catch (err) {
        wmsKomunikat("Nie udało się pobrać pliku: " + err.message, true);
    } finally {
        $w("wmsDownload").disabled = false;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    if (!$w("wmsRun")) return;

    $w("wmsRun").addEventListener("click", wmsAnalizuj);
    $w("wmsDownload").addEventListener("click", wmsPobierz);

    // Nowy plik unieważnia poprzedni wynik — inaczej na ekranie zostałby
    // raport z pliku, którego już nie ma w polu.
    $w("wmsFile").addEventListener("change", () => {
        wmsRaport = null;
        $w("wmsDownload").disabled = true;
        wmsKomunikat("Plik wybrany. Kliknij „Analizuj”.");
    });
});
