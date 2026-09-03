let dmSitesCache = null;

async function getSitesForManagers() {
    if (!dmSitesCache) {
        dmSitesCache = await api("/admin/api/sites");
    }
    return dmSitesCache;
}

/**
 * Dział = site. Lista pochodzi ze słownika sites plus wartość specjalna ALL
 * (zbiorczy email). Wartość zapisywana pozostaje tekstem, więc logika
 * dopasowania działów i ALL w mailach działa bez zmian.
 *
 * currentValue, którego nie ma w słowniku (np. historyczne ECOM), jest
 * dodawany jako opcja — inaczej zapis po cichu zmieniłby przypisanie.
 */
async function loadDepartmentOptions(selectId, currentValue = null) {
    const select = document.getElementById(selectId);
    if (!select) return;

    try {
        const sites = await getSitesForManagers();
        const names = sites.filter(s => s.enabled).map(s => s.name);

        if (currentValue && currentValue.toUpperCase() !== "ALL" && !names.includes(currentValue)) {
            names.push(currentValue);
        }
        names.sort();

        select.innerHTML = '<option value="">-- wybierz --</option>';

        const allOption = document.createElement("option");
        allOption.value = "ALL";
        allOption.textContent = "ALL (zbiorczy email)";
        if (currentValue && currentValue.toUpperCase() === "ALL") allOption.selected = true;
        select.appendChild(allOption);

        for (const name of names) {
            const option = document.createElement("option");
            option.value = name;
            option.textContent = name;
            if (currentValue === name) option.selected = true;
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
        tbody.innerHTML = "";

        for (const m of managers) {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${m.department}</td>
                <td>${m.email}</td>
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
        loadDepartmentOptions("managerDepartmentSelect");
        createForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            await api("/admin/api/department-managers", {
                method: "POST",
                body: JSON.stringify({
                    department: createForm.department.value,
                    email: createForm.email.value
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
                    email: detailForm.email.value
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
    await loadDepartmentOptions("managerDepartmentSelect", m.department ?? null);
    form.email.value = m.email;
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