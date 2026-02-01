document.getElementById("loginForm").onsubmit = async e => {
    e.preventDefault();
    const formData = new FormData(e.target);

    const res = await fetch("/auth/login", {
        method: "POST",
        body: formData
    });

    if (res.ok) location.href = "/";
    else alert("Blędne dane logowania");
};