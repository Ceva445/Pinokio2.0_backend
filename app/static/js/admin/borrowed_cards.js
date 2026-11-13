/*************************************************
 * KARTY ZASTĘPCZE
 * /manager/borrowed-cards, /admin/borrowed-cards
 *
 * Pracownik zapomniał własnej karty — dostaje na zmianę kartę gościa.
 * Numer w kadrach zostaje nietknięty, więc własna karta działa dalej.
 *************************************************/

const BORROWED_API = "/admin/api/borrowed-cards";

async function borrowedApi(url, options = {}) {
    const res = await fetch(url, {
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        ...options,
    });

    if (!res.ok) {
        let komunikat = res.statusText;
        try {
            const dane = await res.json();
            komunikat = dane.detail ?? komunikat;
        } catch (e) { /* odpowiedź bez JSON-a — zostaje status */ }
        throw new Error(komunikat);
    }
    return res.status === 204 ? null : res.json();
}

function borrowedAlert(tekst, czyBlad) {
    const box = document.createElement("div");
    box.textContent = tekst;
    box.style.cssText = `
        position: fixed; top: 20px; right: 20px; z-index: 9999;
        max-width: 420px; padding: 15px 20px; border-radius: 4px;
        background: ${czyBlad ? "#f8d7da" : "#d4edda"};
        color: ${czyBlad ? "#721c24" : "#155724"};
        border: 1px solid ${czyBlad ? "#f5c6cb" : "#c3e6cb"};
    `;
    document.body.appendChild(box);
    setTimeout(() => box.remove(), czyBlad ? 6000 : 3500);
}

/* Lista rozwijana ucina początek wiersza na szerokim ekranie — to samo
   wcięcie co w formularzu pracownika tymczasowego. */
const WCIECIE = " ".repeat(10);
const zWcieciem = (tekst) => WCIECIE + tekst;

function zostaloTekst(sekundy) {
    if (sekundy <= 0) return "po terminie";
    const godziny = Math.floor(sekundy / 3600);
    const minuty = Math.floor((sekundy % 3600) / 60);
    return godziny ? `${godziny} h ${minuty} min` : `${minuty} min`;
}

async function ladujPracownikow(szukaj) {
    const select = document.getElementById("borrowedEmployeeSelect");
    if (!select) return;

    const wybrany = select.value;
    const adres = szukaj
        ? `/admin/api/employees/with-card?q=${encodeURIComponent(szukaj)}`
        : "/admin/api/employees/with-card";

    try {
        const pracownicy = await borrowedApi(adres);
        select.options[0].textContent = zWcieciem("-- Wybierz pracownika --");
        while (select.options.length > 1) select.remove(1);

        for (const p of pracownicy) {
            const opcja = document.createElement("option");
            opcja.value = p.id;
            opcja.textContent = zWcieciem(
                `${p.last_name} ${p.first_name} — ${p.wms_login || "bez loginu"} (${p.company})`);
            select.appendChild(opcja);
        }

        if (!pracownicy.length) {
            const pusta = document.createElement("option");
            pusta.value = "";
            pusta.disabled = true;
            pusta.textContent = zWcieciem("Nic nie znaleziono");
            select.appendChild(pusta);
        }
        select.value = wybrany;
    } catch (err) {
        borrowedAlert("Nie udało się załadować pracowników: " + err.message, true);
    }
}

async function ladujKarty() {
    const select = document.getElementById("borrowedGuestSelect");
    if (!select) return;

    try {
        // Zajęte karty w ogóle tu nie trafiają: ekran ma pokazywać to, co
        // naprawdę da się wydać.
        const wolne = await borrowedApi("/admin/api/guests?unused_only=true");
        select.options[0].textContent = zWcieciem("-- Wybierz kartę --");
        while (select.options.length > 1) select.remove(1);

        for (const k of wolne) {
            const opcja = document.createElement("option");
            opcja.value = k.id;
            opcja.textContent = zWcieciem(`${k.name} (RFID: ${k.rfid})`);
            select.appendChild(opcja);
        }

        if (!wolne.length) {
            const pusta = document.createElement("option");
            pusta.value = "";
            pusta.disabled = true;
            pusta.textContent = zWcieciem("Brak wolnych kart");
            select.appendChild(pusta);
        }
    } catch (err) {
        borrowedAlert("Nie udało się załadować kart: " + err.message, true);
    }
}

async function ladujAktywne() {
    const tabela = document.getElementById("borrowedCardsTable");
    if (!tabela) return;
    const tbody = tabela.querySelector("tbody");
    const mozeZwolnic = tabela.dataset.canRelease === "true";
    const kolumny = mozeZwolnic ? 7 : 6;

    try {
        const pozyczki = await borrowedApi(BORROWED_API);
        tbody.innerHTML = "";

        if (!pozyczki.length) {
            tbody.innerHTML = `<tr><td colspan="${kolumny}">Żadna karta nie jest teraz pożyczona</td></tr>`;
            return;
        }

        for (const p of pozyczki) {
            const tr = document.createElement("tr");
            const pracownik = p.employee
                ? `${p.employee.last_name} ${p.employee.first_name} (${p.employee.wms_login ?? "—"})`
                : "—";
            const wydal = p.issued_by
                ? `${p.issued_by.first_name} ${p.issued_by.last_name}`
                : "—";

            tr.innerHTML = `
                <td>${pracownik}</td>
                <td>${p.card ? `${p.card.name} (${p.card.rfid})` : "—"}</td>
                <td>${new Date(p.issued_at + "Z").toLocaleString()}</td>
                <td>${new Date(p.expires_at + "Z").toLocaleString()}</td>
                <td>${zostaloTekst(p.seconds_left)}</td>
                <td>${wydal}</td>
                ${mozeZwolnic ? `<td><button class="btn" data-zwolnij="${p.id}">Zwolnij</button></td>` : ""}
            `;
            tbody.appendChild(tr);
        }

        for (const przycisk of tbody.querySelectorAll("[data-zwolnij]")) {
            przycisk.addEventListener("click", () => zwolnij(przycisk.dataset.zwolnij));
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="${kolumny}">Błąd: ${err.message}</td></tr>`;
    }
}

async function zwolnij(id) {
    if (!confirm("Zwolnić kartę i oddać ją do puli?")) return;
    try {
        const odp = await borrowedApi(`${BORROWED_API}/${id}/return`, { method: "POST" });
        borrowedAlert(odp.message, false);
        await Promise.all([ladujAktywne(), ladujKarty()]);
    } catch (err) {
        borrowedAlert(err.message, true);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("borrowedCardForm");
    if (!form) return;

    ladujPracownikow("");
    ladujKarty();
    ladujAktywne();

    // Szukanie po wpisaniu, ale nie na każdą literę z osobna.
    let licznik = null;
    const szukajka = document.getElementById("borrowedEmployeeSearch");
    szukajka?.addEventListener("input", () => {
        clearTimeout(licznik);
        licznik = setTimeout(() => ladujPracownikow(szukajka.value.trim()), 300);
    });

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const dane = new FormData(form);
        const przycisk = form.querySelector('button[type="submit"]');
        przycisk.disabled = true;

        try {
            const odp = await borrowedApi(BORROWED_API, {
                method: "POST",
                body: JSON.stringify({
                    employee_id: Number(dane.get("employee_id")),
                    guest_id: Number(dane.get("guest_id")),
                }),
            });
            borrowedAlert(odp.message, false);
            form.reset();
            await Promise.all([ladujAktywne(), ladujKarty()]);
        } catch (err) {
            borrowedAlert(err.message, true);
        } finally {
            przycisk.disabled = false;
        }
    });

    // Licznik „zostało" ma sens tylko wtedy, gdy sam się odświeża.
    setInterval(ladujAktywne, 60_000);
});
