/*************************************************
 * TEMPORARY EMPLOYEES JS
 * Handles temporary employee creation forms
 * Used by:
 *  - /admin/temporary-employees/create
 *  - /manager/temporary-employees/create
 *  - /admin/api/guests
 *  - /admin/api/temporary-employees
 *************************************************/

// Parse API error response and extract readable message
function getErrorMessage(response) {
    try {
        const data = JSON.parse(response);
        if (data.detail) {
            return typeof data.detail === 'object' ? JSON.stringify(data.detail) : data.detail;
        }
        return response;
    } catch (e) {
        return response || "Nieznany błąd";
    }
}

// Show error message to user
function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-alert';
    errorDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background-color: #f8d7da;
        color: #721c24;
        padding: 15px 20px;
        border: 1px solid #f5c6cb;
        border-radius: 4px;
        max-width: 400px;
        z-index: 9999;
        clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 0 100%);
        animation: slideIn 0.3s ease-out;
    `;
    errorDiv.textContent = message;
    document.body.appendChild(errorDiv);
    
    setTimeout(() => {
        errorDiv.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => errorDiv.remove(), 300);
    }, 5000);
}

// Show success message to user
function showSuccess(message) {
    const successDiv = document.createElement('div');
    successDiv.className = 'success-alert';
    successDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background-color: #d4edda;
        color: #155724;
        padding: 15px 20px;
        border: 1px solid #c3e6cb;
        border-radius: 4px;
        max-width: 400px;
        z-index: 9999;
        animation: slideIn 0.3s ease-out;
    `;
    successDiv.textContent = message;
    document.body.appendChild(successDiv);
    
    setTimeout(() => {
        successDiv.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => successDiv.remove(), 300);
    }, 3000);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(420px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(420px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

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
        const errorMessage = getErrorMessage(text);
        throw new Error(errorMessage);
    }

    return res.status === 204 ? null : res.json();
}

/* Na szerokim ekranie Chrome rysuje rozwiniętą listę gości przesuniętą w lewo
   względem swojego okienka i zjada początek każdego wiersza — nazwa karty
   znika, zostaje sam ogon z RFID. Wcięcie na starcie napisu oddaje te brakujące
   ~90 px z zapasem, żeby nazwa nie zaczynała się tuż przy krawędzi.
   Firetek, bo zwykłe spacje przeglądarka potrafi skleić.
   Jedna liczba do podkręcenia, jeśli obcięcie wyjdzie inne: 1 firet = 14 px. */
const WCIECIE = "\u2003".repeat(10);

function zWcieciem(tekst) {
    return WCIECIE + tekst;
}

/* Pierwsza pozycja siedzi w szablonie, a obcina ją tak samo jak resztę. */
function wcinajPierwsza(select) {
    if (select && select.options.length) {
        select.options[0].textContent = zWcieciem(select.options[0].textContent.trim());
    }
}

/* ================================
   LOAD UNUSED GUESTS
================================ */
async function loadGuests() {
    const guestSelect = document.getElementById("guestSelect");
    if (!guestSelect) return;

    try {
        const guests = await api("/admin/api/guests");
        
        wcinajPierwsza(guestSelect);

        // Clear existing options except the first one
        while (guestSelect.options.length > 1) {
            guestSelect.remove(1);
        }

        // Zajęte karty zostają na liście — widać, że istnieją i że są w użyciu —
        // ale nie da się ich wybrać. Serwer i tak odrzuciłby je ("Gość został
        // już użyty"), tylko dopiero po wypełnieniu całego formularza.
        // Zajętą poznać po napisie, nie po tle: pokolorowane <option> każe
        // przeglądarce rysować listę po swojemu.
        for (const guest of guests) {
            const option = document.createElement("option");
            option.value = guest.id;
            option.dataset.rfid = guest.rfid ?? "";
            option.textContent = zWcieciem(guest.used
                ? `${guest.name} (RFID: ${guest.rfid}) — zajęta`
                : `${guest.name} (RFID: ${guest.rfid})`);
            option.disabled = Boolean(guest.used);
            guestSelect.appendChild(option);
        }

        if (guests.length === 0) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = zWcieciem("Brak dostępnych gości");
            option.disabled = true;
            guestSelect.appendChild(option);
        }
    } catch (err) {
        console.error("❌ Error loading guests:", err);
        showError("Nie udało się załadować listy gości: " + err.message);
    }
}

/* ================================
   LOAD EMPLOYEES WITHOUT A CARD
================================ */
async function loadReusableEmployees() {
    const select = document.getElementById("reuseEmployeeSelect");
    if (!select) return;

    try {
        const pracownicy = await api("/admin/api/employees/without-card");

        // Ta sama lista rozwijana, ta sama obcięta krawędź.
        wcinajPierwsza(select);

        for (const p of pracownicy) {
            const option = document.createElement("option");
            option.value = p.id;
            option.dataset.wmsLogin = p.wms_login ?? "";
            option.dataset.firstName = p.first_name ?? "";
            option.dataset.lastName = p.last_name ?? "";
            option.dataset.company = p.company ?? "";
            option.dataset.siteId = p.site_id ?? "";
            option.textContent = zWcieciem(
                `${p.wms_login || "bez loginu"} — ${p.first_name} ${p.last_name} (${p.company})`);
            select.appendChild(option);
        }

        if (pracownicy.length === 0) {
            const option = document.createElement("option");
            option.value = "";
            option.disabled = true;
            option.textContent = zWcieciem("Brak pracowników bez karty");
            select.appendChild(option);
        }
    } catch (err) {
        console.error("❌ Error loading employees without card:", err);
        showError("Nie udało się załadować pracowników bez karty: " + err.message);
    }
}

/* Dane wybranego pracownika idą z bazy: pokazujemy je, ale nie pozwalamy
   zmieniać — ponowne wydanie karty nie jest edycją kadr. Przy "nowym
   pracowniku" pola wracają puste i znowu wymagane. */
function ustawPolaPracownika(form, dane) {
    for (const nazwa of ["wms_login", "first_name", "last_name", "company"]) {
        const pole = form[nazwa];
        if (!pole) continue;
        pole.value = dane ? dane[nazwa] : "";
        pole.readOnly = Boolean(dane);
        // Pracownik z bazy może nie mieć loginu WMS, a required na pustym
        // polu tylko do wglądu nie dałby wysłać formularza.
        pole.required = !dane;
    }

    const site = form.site_id;
    if (site) {
        site.value = dane ? dane.site_id : "";
        site.disabled = Boolean(dane);
    }
}

/* ================================
   LOAD SITES
================================ */
async function loadSitesForTemporary() {
    const select = document.getElementById("temporaryEmployeeSiteSelect");
    if (!select) return;

    try {
        const sites = await api("/admin/api/sites");

        for (const s of sites) {
            if (!s.enabled) continue;
            const option = document.createElement("option");
            option.value = s.id;
            option.textContent = s.name;
            select.appendChild(option);
        }
    } catch (err) {
        console.error("Error loading sites:", err);
    }
}

/* ================================
   FORM INITIALIZATION
================================ */
document.addEventListener("DOMContentLoaded", () => {
    // Load guests when page loads
    loadGuests();
    loadSitesForTemporary();
    loadReusableEmployees();

    const form = document.getElementById("temporaryEmployeeCreateForm");
    if (!form) return;

    const guestSelect = document.getElementById("guestSelect");
    const rfidDisplay = form.rfid_display;
    const reuseSelect = document.getElementById("reuseEmployeeSelect");

    if (reuseSelect) {
        reuseSelect.addEventListener("change", () => {
            const wybrany = reuseSelect.options[reuseSelect.selectedIndex];
            ustawPolaPracownika(form, reuseSelect.value ? {
                wms_login: wybrany.dataset.wmsLogin ?? "",
                first_name: wybrany.dataset.firstName ?? "",
                last_name: wybrany.dataset.lastName ?? "",
                company: wybrany.dataset.company ?? "",
                site_id: wybrany.dataset.siteId ?? ""
            } : null);
        });
    }

    // When guest is selected, update the RFID display
    if (guestSelect) {
        guestSelect.addEventListener("change", () => {
            const selectedOption = guestSelect.options[guestSelect.selectedIndex];
            if (selectedOption.value) {
                // RFID z atrybutu, a nie z napisu — napis ma teraz dopisek
                // " — zajęta" i wyrażenie regularne przestałoby pasować.
                rfidDisplay.value = selectedOption.dataset.rfid ?? "";
            } else {
                rfidDisplay.value = "";
            }
        });
    }

    // Form submission handler
    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        if (!guestSelect.value) {
            showError("Proszę wybrać gościa");
            return;
        }

        try {
            // Przy ponownym zatrudnieniu wysyłamy samo id: pola są tylko do
            // wglądu, a dane bierze się z bazy.
            const ponownie = reuseSelect && reuseSelect.value;
            const result = await api("/admin/api/temporary-employees", {
                method: "POST",
                body: JSON.stringify(ponownie ? {
                    guest_id: parseInt(guestSelect.value),
                    employee_id: parseInt(reuseSelect.value)
                } : {
                    guest_id: parseInt(guestSelect.value),
                    wms_login: form.wms_login.value || null,
                    first_name: form.first_name.value,
                    last_name: form.last_name.value,
                    company: form.company.value,
                    site_id: form.site_id.value ? parseInt(form.site_id.value) : null
                })
            });

            showSuccess(result?.message || "Pracownik tymczasowy został utworzony ✅");
            // Ten skrypt obsługuje formularz i u admina, i u kierownika. Stały
            // adres /admin/employees wyrzucał kierownika na logowanie (403),
            // więc dokąd wrócić, mówi sama strona.
            const dokad = form.dataset.afterCreate || "/admin/employees";
            setTimeout(() => {
                window.location.href = dokad;
            }, 1500);
        } catch (err) {
            showError(err.message);
        }
    });
});
