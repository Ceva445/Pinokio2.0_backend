// Причина вилогування з ?reason= (напр. авто-вилогування за простій)
(function showLogoutNotice() {
    const el = document.getElementById("loginNotice");
    if (!el) return;
    const reason = new URLSearchParams(location.search).get("reason");
    if (!reason) return;
    el.textContent = reason === "idle"
        ? "Zostałeś wylogowany z powodu bezczynności."
        : "Zostałeś wylogowany.";
    el.style.display = "block";
})();

// Заповнити список ESP (тільки онлайн); зайняті — disabled з іменем того, хто слідкує
async function loadEsps() {
    const sel = document.getElementById("deviceSelect");
    if (!sel) return;
    try {
        const res = await fetch("/auth/available-esps");
        const list = await res.json();
        for (const d of list) {
            const opt = document.createElement("option");
            if (d.watched_by) {
                opt.disabled = true;
                opt.textContent = `${d.name} — śledzi: ${d.watched_by}`;
            } else {
                opt.value = d.id;
                opt.textContent = d.name;
            }
            sel.appendChild(opt);
        }
    } catch (e) {
        // список недоступний — лишиться лише опція admin
    }
}
loadEsps();

document.getElementById("loginForm").onsubmit = async e => {
    e.preventDefault();
    const formData = new FormData(e.target);

    const res = await fetch("/auth/login", {
        method: "POST",
        body: formData
    });

    if (res.ok) {
        location.href = "/";
        return;
    }

    let msg = "Błędne dane logowania";
    try {
        const j = await res.json();
        if (j && j.detail) msg = j.detail;
    } catch (e) {}
    alert(msg);
};
