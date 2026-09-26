(() => {
    const form = document.getElementById("form-recherche");
    const input = document.getElementById("recherche");
    const results = document.getElementById("resultats-recherche");
    const status = document.getElementById("recherche-status");
    let timer;
    let controller;
    let version = 0;

    async function search(currentVersion) {
        controller = new AbortController();
        const url = new URL(form.action);
        url.searchParams.set("q", input.value.trim());
        url.searchParams.set("partiel", "recherche");
        try {
            const response = await fetch(url, { signal: controller.signal });
            if (!response.ok) throw new Error("Recherche indisponible");
            const html = await response.text();
            if (currentVersion !== version) return;
            const documentResults = new DOMParser().parseFromString(html, "text/html");
            const newBody = documentResults.querySelector("tbody");
            const currentBody = results.querySelector("tbody");
            if (!newBody || !currentBody) throw new Error("Résultats invalides");
            if (!currentBody.isEqualNode(newBody)) {
                currentBody.replaceWith(newBody);
                results.scrollTop = 0;
            }
            status.textContent = "";
        } catch (error) {
            if (currentVersion !== version || error.name === "AbortError") return;
            status.textContent = "La recherche a échoué. Cliquez sur Rechercher pour réessayer.";
        } finally {
            if (currentVersion === version) results.setAttribute("aria-busy", "false");
        }
    }

    function schedule(delay) {
        clearTimeout(timer);
        controller?.abort();
        const currentVersion = ++version;
        status.textContent = "";
        results.setAttribute("aria-busy", "true");
        timer = setTimeout(() => search(currentVersion), delay);
    }

    input.addEventListener("input", () => schedule(250));
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        schedule(0);
    });
    document.getElementById("effacer-recherche").addEventListener("click", (event) => {
        event.preventDefault();
        input.value = "";
        schedule(0);
        input.focus();
    });
})();
