async function api(url, options = {}) {
    const res = await fetch(url, {
        credentials: "include",
        headers: {
            "Content-Type": "application/json"
        },
        ...options
    });

    if (!res.ok) {
        throw new Error(await res.text());
    }

    return res.status === 204
        ? null
        : await res.json();
}

function escapeAttr(value) {
    return String(value ?? "").replace(/"/g, "&quot;");
}


/* =========================
   LOAD
========================= */

async function loadSites() {
    const tbody = document.querySelector("#siteTable tbody");

    tbody.innerHTML = `<tr><td colspan="6">Ładowanie...</td></tr>`;

    try {
        const sites = await api("/admin/api/sites");

        tbody.innerHTML = "";

        for (const s of sites) {
            const tr = document.createElement("tr");

            tr.innerHTML = `
                <td>${s.id}</td>

                <td>
                    <input value="${escapeAttr(s.name)}" id="site-name-${s.id}">
                </td>

                <td>
                    <input value="${escapeAttr(s.description ?? "")}" id="site-desc-${s.id}">
                </td>

                <td style="text-align:center">
                    <input type="checkbox" id="site-enabled-${s.id}" ${s.enabled ? "checked" : ""}>
                </td>

                <td style="text-align:center">${s.devices_count ?? 0}</td>

                <td style="display:flex; gap:10px;">
                    <button class="btn btn-primary" onclick="updateSite(${s.id})">
                        💾 Zapisz
                    </button>

                    <button class="btn btn-danger" onclick="deleteSite(${s.id})">
                        🗑 Usuń
                    </button>
                </td>
            `;

            tbody.appendChild(tr);
        }

        if (sites.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6">Brak site</td></tr>`;
        }

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6">Błąd: ${err.message}</td></tr>`;
    }
}


/* =========================
   CREATE
========================= */

async function createSite() {
    const name = document.getElementById("siteName").value.trim();
    const description = document.getElementById("siteDesc").value.trim();

    if (!name) {
        alert("Podaj nazwę site");
        return;
    }

    try {
        await api("/admin/api/sites", {
            method: "POST",
            body: JSON.stringify({ name, description })
        });

        document.getElementById("siteName").value = "";
        document.getElementById("siteDesc").value = "";

        loadSites();

    } catch (err) {
        alert(err.message);
    }
}


/* =========================
   UPDATE
========================= */

async function updateSite(id) {
    const name = document.getElementById(`site-name-${id}`).value.trim();
    const description = document.getElementById(`site-desc-${id}`).value.trim();
    const enabled = document.getElementById(`site-enabled-${id}`).checked;

    if (!name) {
        alert("Nazwa site jest wymagana");
        return;
    }

    try {
        await api(`/admin/api/sites/${id}`, {
            method: "PUT",
            body: JSON.stringify({ name, description, enabled })
        });

        alert("Site zapisany ✅");
        loadSites();

    } catch (err) {
        alert(err.message);
    }
}


/* =========================
   DELETE
========================= */

async function deleteSite(id) {
    if (!confirm("Usunąć site?")) {
        return;
    }

    try {
        await api(`/admin/api/sites/${id}`, { method: "DELETE" });
        loadSites();

    } catch (err) {
        alert(err.message);
    }
}


/* =========================
   AUTOSTART
========================= */

document.addEventListener("DOMContentLoaded", loadSites);
