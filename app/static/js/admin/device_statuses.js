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


/* =========================
   LOAD
========================= */

async function loadStatuses() {
    const tbody = document.querySelector("#statusTable tbody");

    tbody.innerHTML = `
        <tr>
            <td colspan="4">Ładowanie...</td>
        </tr>
    `;

    try {
        const statuses = await api("/admin/api/device-statuses");

        tbody.innerHTML = "";

        for (const s of statuses) {
            const tr = document.createElement("tr");

            tr.innerHTML = `
                <td>${s.id}</td>

                <td>
                    <input
                        value="${s.name}"
                        id="name-${s.id}"
                    >
                </td>

                <td>
                    <input
                        value="${s.description ?? ""}"
                        id="desc-${s.id}"
                    >
                </td>

                <td style="display:flex; gap:10px;">
                    <button
                        class="btn btn-primary"
                        onclick="updateStatus(${s.id})"
                    >
                        💾 Zapisz
                    </button>

                    <button
                        class="btn btn-danger"
                        onclick="deleteStatus(${s.id})"
                    >
                        🗑 Usuń
                    </button>
                </td>
            `;

            tbody.appendChild(tr);
        }

    } catch (err) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4">
                    Błąd: ${err.message}
                </td>
            </tr>
        `;
    }
}


/* =========================
   CREATE
========================= */

async function createStatus() {
    const name = document.getElementById("statusName").value.trim();
    const description = document.getElementById("statusDesc").value.trim();

    if (!name) {
        alert("Podaj nazwę statusu");
        return;
    }

    try {
        await api("/admin/api/device-statuses", {
            method: "POST",
            body: JSON.stringify({
                name,
                description
            })
        });

        document.getElementById("statusName").value = "";
        document.getElementById("statusDesc").value = "";

        loadStatuses();

    } catch (err) {
        alert(err.message);
    }
}


/* =========================
   UPDATE
========================= */

async function updateStatus(id) {
    const name = document
        .getElementById(`name-${id}`)
        .value
        .trim();

    const description = document
        .getElementById(`desc-${id}`)
        .value
        .trim();

    if (!name) {
        alert("Nazwa statusu jest wymagana");
        return;
    }

    try {
        await api(`/admin/api/device-statuses/${id}`, {
            method: "PUT",
            body: JSON.stringify({
                name,
                description
            })
        });

        alert("Status zapisany ✅");

    } catch (err) {
        alert(err.message);
    }
}


/* =========================
   DELETE
========================= */

async function deleteStatus(id) {
    if (!confirm("Usunąć status?")) {
        return;
    }

    try {
        await api(`/admin/api/device-statuses/${id}`, {
            method: "DELETE"
        });

        loadStatuses();

    } catch (err) {
        alert(err.message);
    }
}


/* =========================
   AUTOSTART
========================= */

document.addEventListener(
    "DOMContentLoaded",
    loadStatuses
);