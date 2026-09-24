(() => {
    const forms = [...document.querySelectorAll(".form-cafes")];
    // On cible TOUS les boutons de TOUS les formulaires de cafés
    const allButtons = forms.flatMap(form => [...form.querySelectorAll("button")]);
    const messages = document.getElementById("messages-cafes");
    let messageTimer;
    let pending = false;

    const banner = document.querySelector(".site-banner");
    const updatePosition = () => {
        if (banner && messages) {
            messages.style.setProperty("--banner-height", `${banner.getBoundingClientRect().height}px`);
        }
    };
    updatePosition();
    if (banner) new ResizeObserver(updatePosition).observe(banner);

    function dismissLater() {
        clearTimeout(messageTimer);
        if (messages && !messages.matches(":hover")) {
            messageTimer = setTimeout(() => messages.replaceChildren(), 2000);
        }
    }

    if (messages) {
        messages.addEventListener("mouseenter", () => clearTimeout(messageTimer));
        messages.addEventListener("mouseleave", dismissLater);
        dismissLater();
    }

    for (const form of forms) {
        form.addEventListener("submit", async event => {
            event.preventDefault();
            if (pending) return;
            pending = true;

            // On récupère le bouton précis qui a été cliqué
            const submitter = event.submitter;
            const nameButton = submitter ? submitter.name : "type_transaction";
            const valButton = submitter ? submitter.value : "achat";

            const errors = form.querySelector(".erreurs-cafes");
            if (errors) errors.replaceChildren();
            clearTimeout(messageTimer);
            if (messages) messages.replaceChildren();
            
            // Désactive les boutons pendant le chargement
            allButtons.forEach(button => { button.disabled = true; });
            form.setAttribute("aria-busy", "true");

            try {
                // CORRECTION CRUCIALE : On utilise l'URL exacte du formulaire (ex: /clients/7/cafes/)
                // On ne rajoute plus "/utilise/" ou "/prepaye/" au bout de l'URL.
                const url = form.action; 

                // On prépare les données du formulaire
                const formData = new FormData(form);
                
                // On injecte explicitement le bouton cliqué dans les données du POST
                if (submitter) {
                    formData.set(nameButton, valButton);
                }

                const response = await fetch(url, {
                    method: "POST",
                    body: formData,
                    headers: { "X-Requested-With": "XMLHttpRequest" },
                });

                const data = await response.json();
                if (response.status === 400 && data.erreurs) {
                    if (errors) {
                        errors.textContent = Object.values(data.erreurs).flat()
                            .map(error => error.message).join(" ");
                    }
                    return;
                }
                if (!response.ok) throw new Error("Échec de l’enregistrement");

                const compteurs = document.getElementById("compteurs-cafes");
                if (compteurs) {
                    const counters = compteurs.querySelectorAll("p");
                    if (counters.length >= 2) {
                        counters[0].textContent = `Total de cafés achetés : ${data.achetes}`;
                        counters[1].textContent = `Total de cafés prépayés : ${data.prepayes}`;
                    }
                }

                const history = document.getElementById("transactions-cafes");
                if (history) {
                    history.innerHTML = data.historique;
                    history.scrollTop = 0;
                }

                if (messages && data.messages) {
                    for (const message of data.messages) {
                        const paragraph = document.createElement("p");
                        paragraph.setAttribute("role", "status");
                        paragraph.className = message.tags;
                        paragraph.textContent = message.texte;
                        messages.append(paragraph);
                    }
                }
                dismissLater();
                form.reset();
            } catch (error) {
                if (errors) {
                    errors.textContent = "Impossible de confirmer l’enregistrement. Actualisez la page pour vérifier l’historique avant de réessayer.";
                }
            } finally {
                pending = false;
                allButtons.forEach(button => { button.disabled = false; });
                form.setAttribute("aria-busy", "false");
            }
        });
    }
})();
