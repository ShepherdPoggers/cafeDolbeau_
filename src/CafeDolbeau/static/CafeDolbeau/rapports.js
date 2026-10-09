function adapterBornesRapport(precision, debut, fin) {
    function adapter(valeur, derniere) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(valeur)) return valeur;
        const date = new Date(`${valeur}T00:00:00Z`);
        if (Number.isNaN(date.getTime())) return valeur;
        if (precision === "semaine") {
            const decalage = (date.getUTCDay() + 6) % 7;
            date.setUTCDate(date.getUTCDate() - decalage + (derniere ? 6 : 0));
        } else if (precision === "mois") {
            if (derniere) date.setUTCMonth(date.getUTCMonth() + 1, 0);
            else date.setUTCDate(1);
        }
        return `${String(date.getUTCFullYear()).padStart(4, "0")}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
    }
    return { debut: adapter(debut, false), fin: adapter(fin, true) };
}

if (typeof module !== "undefined") module.exports = { adapterBornesRapport };

if (typeof document !== "undefined") {
    const form = document.getElementById("form-rapport");
    if (form) {
        const precision = form.elements.precision;
        const debut = form.elements.date_debut;
        const fin = form.elements.date_fin;
        const description = document.getElementById("periode-rapport");
        const regle = document.getElementById("regle-periode");
        const formatDate = new Intl.DateTimeFormat("fr-CA", { dateStyle: "long", timeZone: "UTC" });

        function actualiser(adapter) {
            if (adapter) {
                const bornes = adapterBornesRapport(precision.value, debut.value, fin.value);
                debut.value = bornes.debut;
                fin.value = bornes.fin;
            }
            const semaine = precision.value === "semaine";
            const mois = precision.value === "mois";
            form.querySelector('label[for="id_date_debut"]').textContent = semaine ? "Semaine de début — lundi" : mois ? "Mois de début — premier jour" : "Date de début";
            form.querySelector('label[for="id_date_fin"]').textContent = semaine ? "Semaine de fin — dimanche" : mois ? "Mois de fin — dernier jour" : "Date de fin";
            regle.textContent = semaine
                ? "Sélectionnez une date dans chaque semaine souhaitée. Les bornes seront ajustées du lundi au dimanche."
                : mois
                    ? "Sélectionnez une date dans chaque mois souhaité. Les mois seront inclus en entier."
                    : "Les dates de début et de fin sont incluses.";
            description.textContent = debut.value && fin.value
                ? `Période sélectionnée : du ${formatDate.format(new Date(`${debut.value}T00:00:00Z`))} au ${formatDate.format(new Date(`${fin.value}T00:00:00Z`))}.`
                : "Choisissez le début et la fin de la période.";
        }
        precision.addEventListener("change", () => actualiser(true));
        debut.addEventListener("change", () => actualiser(true));
        fin.addEventListener("change", () => actualiser(true));
        form.addEventListener("submit", () => actualiser(true));
        actualiser(false);
    }
}
