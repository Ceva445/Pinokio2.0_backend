/* Ekran wymuszonej zmiany hasła (pierwsze logowanie).
   Jedyna reguła: minimum 4 znaki — bez wymagań co do złożoności. */

const MIN_PASSWORD_LENGTH = 4;

(async function guard() {
    // Na ten ekran wchodzi tylko zalogowany użytkownik z ustawioną flagą.
    try {
        const res = await fetch("/auth/me", { credentials: "include" });
        if (!res.ok) { location.href = "/login"; return; }
        const me = await res.json();
        if (!me.must_change_password) location.href = "/";
    } catch (e) {}
})();

document.getElementById("changePasswordForm").onsubmit = async e => {
    e.preventDefault();

    const form = e.target;
    const newPassword = form.new_password.value;
    const confirmPassword = form.confirm_password.value;

    if (newPassword.length < MIN_PASSWORD_LENGTH) {
        alert(`Hasło musi mieć co najmniej ${MIN_PASSWORD_LENGTH} znaki`);
        return;
    }

    if (newPassword !== confirmPassword) {
        alert("Hasła nie są takie same");
        return;
    }

    try {
        const res = await fetch("/auth/change-password", {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ new_password: newPassword })
        });

        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            alert(data.detail || "Nie udało się zmienić hasła");
            return;
        }

        location.href = "/";
    } catch (err) {
        alert("Nie udało się zmienić hasła");
    }
};
