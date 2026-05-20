async function loadGuests() {
    const tbody = document.querySelector("#guestsTable tbody");
    const q = document.getElementById("search")?.value ?? "";
    if (!tbody) return;

    tbody.innerHTML = "<tr><td colspan='4'>Ładowanie...</td></tr>";

    try {
        const url = q
            ? `/admin/api/guests?q=${encodeURIComponent(q)}`
            : "/admin/api/guests";

        const guests = await api(url);
        tbody.innerHTML = "";

        for (const g of guests) {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${g.name}</td>
                <td>${g.rfid || '-'}</td>
                <td>${g.used ? '✓' : ''}</td>
                <td><a href="/admin/guests/${g.id}">✏️</a></td>
            `;
            tbody.appendChild(tr);
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4">Błąd: ${err.message}</td></tr>`;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const listTable = document.querySelector("#guestsTable");
    if (listTable) {
        loadGuests();
        const searchInput = document.getElementById("search");
        if (searchInput) {
            let timeout;
            searchInput.addEventListener("input", () => {
                clearTimeout(timeout);
                timeout = setTimeout(loadGuests, 300);
            });
        }
    }

    const createForm = document.getElementById("guestCreateForm");
    if (createForm) {
        createForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            await api("/admin/api/guests", {
                method: "POST",
                body: JSON.stringify({
                    name: createForm.name.value,
                    rfid: createForm.rfid.value || null
                })
            });
            alert("Gość stworzony ✅");
            window.location.href = "/admin/guests";
        });
    }

    const detailForm = document.getElementById("guestForm");
    if (detailForm && typeof guestId !== "undefined") {
        loadGuestDetail(guestId);

        detailForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            await api(`/admin/api/guests/${guestId}`, {
                method: "PUT",
                body: JSON.stringify({
                    name: detailForm.name.value,
                    rfid: detailForm.rfid.value || null
                })
            });
            alert("Zapisano ✅");
        });

        const deleteBtn = document.getElementById("deleteBtn");
        deleteBtn?.addEventListener("click", async () => {
            if (!confirm("Czy usunąć gościa?")) return;
            await api(`/admin/api/guests/${guestId}`, { method: "DELETE" });
            window.location.href = "/admin/guests";
        });
    }
});

async function loadGuestDetail(id) {
    const form = document.getElementById("guestForm");
    if (!form) return;

    const g = await api(`/admin/api/guests/${id}`);
    form.name.value = g.name;
    form.rfid.value = g.rfid || "";
    form.used.checked = g.used;
}

// Утиліта fetch
async function api(url, options = {}) {
    const res = await fetch(url, {
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        ...options
    });
    if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Błąd API");
    }
    return res.status === 204 ? null : res.json();
}
