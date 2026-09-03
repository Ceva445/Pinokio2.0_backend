let dmSitesCache = null;

async function getSitesForManagers() {
    if (!dmSitesCache) {
        dmSitesCache = await api("/admin/api/sites");
    }
    return dmSitesCache;
}

async function loadManagerSiteOptions(selectId, selectedId = null) {
    const select = document.getElementById(selectId);
    if (!select) return;

    try {
        const sites = await getSitesForManagers();

        select.innerHTML = '<option value="">-- brak site --</option>';

        for (const s of sites) {
            if (!s.enabled && Number(selectedId) !== Number(s.id)) continue;
            const option = document.createElement("option");
            option.value = s.id;
            option.textContent = s.name;
            if (selectedId !== null && Number(selectedId) === Number(s.id)) {
                option.selected = true;
            }
            select.appendChild(option);
        }
    } catch (err) {
        console.error(err);
    }
}


async function loadDepartmentManagers() {
    const tbody = document.querySelector("#managersTable tbody");
    const q = document.getElementById("search")?.value ?? "";
    if (!tbody) return;

    tbody.innerHTML = "<tr><td colspan='3'>Ładowanie...</td></tr>";

    try {
        const url = q
            ? `/admin/api/department-managers?q=${encodeURIComponent(q)}`
            : "/admin/api/department-managers";

        const managers = await api(url);
        const siteNames = new Map((await getSitesForManagers()).map(s => [s.id, s.name]));
        tbody.innerHTML = "";

        for (const m of managers) {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${m.department}</td>
                <td>${m.email}</td>
                <td>${siteNames.get(m.site_id) ?? ""}</td>
                <td><a href="/admin/department-managers/${m.id}">✏️</a></td>
            `;
            tbody.appendChild(tr);
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="3">Błąd: ${err.message}</td></tr>`;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const listTable = document.querySelector("#managersTable");
    if (listTable) {
        loadDepartmentManagers();
        const searchInput = document.getElementById("search");
        if (searchInput) {
            let timeout;
            searchInput.addEventListener("input", () => {
                clearTimeout(timeout);
                timeout = setTimeout(loadDepartmentManagers, 300);
            });
        }
    }

    const createForm = document.getElementById("managerCreateForm");
    if (createForm) {
        loadManagerSiteOptions("managerSiteSelect");
        createForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            await api("/admin/api/department-managers", {
                method: "POST",
                body: JSON.stringify({
                    department: createForm.department.value,
                    email: createForm.email.value,
                    site_id: createForm.site_id.value ? parseInt(createForm.site_id.value) : null
                })
            });
            alert("Manager stworzono ✅");
            window.location.href = "/admin/department-managers";
        });
    }

    const detailForm = document.getElementById("managerForm");
    if (detailForm && typeof managerId !== "undefined") {
        loadManagerDetail(managerId);

        detailForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            await api(`/admin/api/department-managers/${managerId}`, {
                method: "PUT",
                body: JSON.stringify({
                    department: detailForm.department.value,
                    email: detailForm.email.value,
                    site_id: detailForm.site_id.value ? parseInt(detailForm.site_id.value) : null
                })
            });
            alert("Zapisano ✅");
        });

        const deleteBtn = document.getElementById("deleteBtn");
        deleteBtn?.addEventListener("click", async () => {
            if (!confirm("Czy usunąć managera?")) return;
            await api(`/admin/api/department-managers/${managerId}`, { method: "DELETE" });
            window.location.href = "/admin/department-managers";
        });
    }
});

async function loadManagerDetail(id) {
    const form = document.getElementById("managerForm");
    if (!form) return;

    const m = await api(`/admin/api/department-managers/${id}`);
    form.department.value = m.department;
    form.email.value = m.email;
    await loadManagerSiteOptions("managerSiteSelect", m.site_id ?? null);
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