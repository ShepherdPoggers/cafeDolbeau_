const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");
const { adapterBornesRapport } = require("../static/CafeDolbeau/rapports.js");

test("un mois sélectionné sur une semaine devient un mois complet", () => {
    assert.deepEqual(adapterBornesRapport("mois", "2026-10-05", "2026-10-11"), {
        debut: "2026-10-01", fin: "2026-10-31",
    });
});

test("février respecte les années bissextiles", () => {
    assert.equal(adapterBornesRapport("mois", "2024-02-10", "2024-02-12").fin, "2024-02-29");
    assert.equal(adapterBornesRapport("mois", "2025-02-10", "2025-02-12").fin, "2025-02-28");
});

test("les semaines traversent les mois et les années ISO", () => {
    assert.deepEqual(adapterBornesRapport("semaine", "2020-12-31", "2021-01-01"), {
        debut: "2020-12-28", fin: "2021-01-03",
    });
    assert.deepEqual(adapterBornesRapport("semaine", "2026-10-01", "2026-10-03"), {
        debut: "2026-09-28", fin: "2026-10-04",
    });
});

test("les changements d'heure ne déplacent pas les dates du calendrier", () => {
    assert.deepEqual(adapterBornesRapport("semaine", "2026-03-08", "2026-03-08"), {
        debut: "2026-03-02", fin: "2026-03-08",
    });
    assert.deepEqual(adapterBornesRapport("semaine", "2026-11-01", "2026-11-01"), {
        debut: "2026-10-26", fin: "2026-11-01",
    });
});

test("les autres niveaux gardent les dates libres et les champs vides", () => {
    for (const niveau of ["periode", "jour", "transaction"]) {
        assert.deepEqual(adapterBornesRapport(niveau, "2026-10-05", "2026-10-11"), {
            debut: "2026-10-05", fin: "2026-10-11",
        });
    }
    assert.deepEqual(adapterBornesRapport("mois", "", ""), { debut: "", fin: "" });
});

function formulaire() {
    function champ(value) {
        return { value, evenements: {}, addEventListener(type, callback) { this.evenements[type] = callback; } };
    }
    const elements = {
        precision: champ("periode"), date_debut: champ("2026-10-05"), date_fin: champ("2026-10-11"),
    };
    const textes = {
        'label[for="id_date_debut"]': {}, 'label[for="id_date_fin"]': {},
        "periode-rapport": {}, "regle-periode": {},
    };
    const form = {
        elements, evenements: {}, querySelector(selecteur) { return textes[selecteur]; },
        addEventListener(type, callback) { this.evenements[type] = callback; },
    };
    const document = { getElementById(id) { return id === "form-rapport" ? form : textes[id]; } };
    const source = fs.readFileSync(path.join(__dirname, "../static/CafeDolbeau/rapports.js"), "utf8");
    vm.runInNewContext(source, { document, Intl, Date });
    return { elements, textes, form };
}

test("changer de niveau ajuste immédiatement les calendriers et leur description", () => {
    const { elements, textes } = formulaire();
    elements.precision.value = "mois";
    elements.precision.evenements.change();
    assert.equal(elements.date_debut.value, "2026-10-01");
    assert.equal(elements.date_fin.value, "2026-10-31");
    assert.match(textes['label[for="id_date_fin"]'].textContent, /dernier jour/);
    assert.match(textes["periode-rapport"].textContent, /31 octobre 2026/);
    elements.date_fin.value = "2026-11-05";
    elements.date_fin.evenements.change();
    assert.equal(elements.date_fin.value, "2026-11-30");
    assert.match(textes["periode-rapport"].textContent, /30 novembre 2026/);
});

test("les dates envoyées à l'affichage et à l'export sont normalisées à la soumission", () => {
    const { elements, form } = formulaire();
    elements.precision.value = "semaine";
    elements.date_debut.value = "2026-10-07";
    elements.date_fin.value = "2026-10-09";
    form.evenements.submit();
    assert.equal(elements.date_debut.value, "2026-10-05");
    assert.equal(elements.date_fin.value, "2026-10-11");
});
