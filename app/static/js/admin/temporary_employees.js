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

/* ================================
   LOAD UNUSED GUESTS
================================ */
async function loadGuests() {
    const guestSelect = document.getElementById("guestSelect");
    if (!guestSelect) return;

    try {
        const guests = await api("/admin/api/guests");
        
        // Clear existing options except the first one
        while (guestSelect.options.length > 1) {
            guestSelect.remove(1);
        }

        // Add guest options
        for (const guest of guests) {
            const option = document.createElement("option");
            option.value = guest.id;
            option.textContent = `${guest.name} (RFID: ${guest.rfid})`;
            guestSelect.appendChild(option);
        }

        if (guests.length === 0) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "Brak dostępnych gości";
            option.disabled = true;
            guestSelect.appendChild(option);
        }
    } catch (err) {
        console.error("❌ Error loading guests:", err);
        showError("Nie udało się załadować listy gości: " + err.message);
    }
}

/* ================================
   FORM INITIALIZATION
================================ */
document.addEventListener("DOMContentLoaded", () => {
    // Load guests when page loads
    loadGuests();

    const form = document.getElementById("temporaryEmployeeCreateForm");
    if (!form) return;

    const guestSelect = document.getElementById("guestSelect");
    const rfidDisplay = form.rfid_display;

    // When guest is selected, update the RFID display
    if (guestSelect) {
        guestSelect.addEventListener("change", () => {
            const selectedOption = guestSelect.options[guestSelect.selectedIndex];
            if (selectedOption.value) {
                // Extract RFID from the option text: "name (RFID: value)"
                const rfidMatch = selectedOption.textContent.match(/RFID: (.+)\)$/);
                if (rfidMatch) {
                    rfidDisplay.value = rfidMatch[1];
                }
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
            const result = await api("/admin/api/temporary-employees", {
                method: "POST",
                body: JSON.stringify({
                    guest_id: parseInt(guestSelect.value),
                    wms_login: form.wms_login.value || null,
                    first_name: form.first_name.value,
                    last_name: form.last_name.value,
                    company: form.company.value,
                    department: form.department.value || null
                })
            });

            showSuccess("Pracownik tymczasowy został utworzony ✅");
            setTimeout(() => {
                window.location.href = "/admin/employees";
            }, 1500);
        } catch (err) {
            showError(err.message);
        }
    });
});
