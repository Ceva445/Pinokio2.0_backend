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
    form.department.value = m.department;
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