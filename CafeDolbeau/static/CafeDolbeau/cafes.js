(() => {
    const forms = [...document.querySelectorAll(".form-cafes")];
    const buttons = forms.map(form => form.querySelector("button[type=submit]"));
    const messages = document.getElementById("messages-cafes");
    let messageTimer;
    let pending = false;

    const banner = document.querySelector(".site-banner");
    const updatePosition = () => {
        messages.style.setProperty("--banner-height", `${banner.getBoundingClientRect().height}px`);
    };
    updatePosition();
    new ResizeObserver(updatePosition).observe(banner);

    function dismissLater() {
        clearTimeout(messageTimer);
        if (!messages.matches(":hover")) {
            messageTimer = setTimeout(() => messages.replaceChildren(), 2000);
        }
    }

    messages.addEventListener("mouseenter", () => clearTimeout(messageTimer));
    messages.addEventListener("mouseleave", dismissLater);
    dismissLater();

    for (const form of forms) {
        form.addEventListener("submit", async event => {
            event.preventDefault();
            if (pending) return;
            pending = true;
            const errors = form.querySelector(".erreurs-cafes");
            errors.replaceChildren();
            clearTimeout(messageTimer);
            messages.replaceChildren();
            buttons.forEach(button => { button.disabled = true; });
            form.setAttribute("aria-busy", "true");
            try {
                const response = await fetch(form.action, {
                    method: "POST",
                    body: new FormData(form),
                    headers: { "X-Requested-With": "XMLHttpRequest" },
                });
                const data = await response.json();
                if (response.status === 400 && data.erreurs) {
                    errors.textContent = Object.values(data.erreurs).flat()
                        .map(error => error.message).join(" ");
                    return;
                }
                if (!response.ok) throw new Error("Échec de l’enregistrement");
                const counters = document.getElementById("compteurs-cafes").querySelectorAll("p");
                counters[0].textContent = `Total de cafés achetés : ${data.achetes}`;
                counters[1].textContent = `Total de cafés prépayés : ${data.prepayes}`;
                const history = document.getElementById("transactions-cafes");
                history.innerHTML = data.historique;
                history.scrollTop = 0;
                for (const message of data.messages) {
                    const paragraph = document.createElement("p");
                    paragraph.setAttribute("role", "status");
                    paragraph.className = message.tags;
                    paragraph.textContent = message.texte;
                    messages.append(paragraph);
                }
                dismissLater();
                form.reset();
            } catch (error) {
                errors.textContent = "Impossible de confirmer l’enregistrement. Actualisez la page pour vérifier l’historique avant de réessayer.";
            } finally {
                pending = false;
                buttons.forEach(button => { button.disabled = false; });
                form.setAttribute("aria-busy", "false");
            }
        });
    }
})();
