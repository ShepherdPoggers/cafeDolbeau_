const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/CafeDolbeau/cafes.js"), "utf8");
const flush = () => new Promise(resolve => setImmediate(resolve));
const reponse = html => ({ ok: true, status: 200, json: async () => ({ promotion_html: html }) });

function page(fetch) {
    const documentEvents = {}, windowEvents = {}, formEvents = {};
    const promotion = { dataset: { url: "/succursales/2/clients/3/cafes/?partiel=promotion" }, innerHTML: "Ancienne" };
    const form = {
        action: "/succursales/2/clients/3/cafes/",
        querySelectorAll: () => [], querySelector: () => null,
        addEventListener: (nom, fn) => { formEvents[nom] = fn; },
        setAttribute() {}, reset() {},
    };
    const document = {
        hidden: false,
        getElementById: id => id === "compteur-promotion" ? promotion : null,
        querySelectorAll: () => [form], querySelector: () => null,
        addEventListener: (nom, fn) => { documentEvents[nom] = fn; },
    };
    let interval, delai;
    vm.runInNewContext(source, {
        document, fetch,
        window: { addEventListener: (nom, fn) => { windowEvents[nom] = fn; }, location: { assign() {} } },
        setInterval: (fn, ms) => { interval = fn; delai = ms; },
        clearTimeout() {}, FormData: class { set() {} },
    });
    return { promotion, document, documentEvents, windowEvents, formEvents, tick: () => interval(), delai };
}

test("actualise au chargement et toutes les 15 secondes, y compris après expiration", async () => {
    let html = "Promotion active";
    const appels = [];
    const caisse = page(async (url, options) => { appels.push({ url, options }); return reponse(html); });
    await flush();
    assert.equal(caisse.promotion.innerHTML, html);
    assert.equal(caisse.delai, 15000);
    assert.match(appels[0].url, /succursales\/2\/.+partiel=promotion/);
    assert.equal(appels[0].options.cache, "no-store");
    html = "";
    await caisse.tick();
    assert.equal(caisse.promotion.innerHTML, "");
    html = "Promotion suivante";
    await caisse.tick();
    assert.equal(caisse.promotion.innerHTML, html);
});

test("suspend les lectures en arrière-plan et rafraîchit au retour sur l’onglet", async () => {
    let lectures = 0;
    const caisse = page(async () => { lectures++; return reponse(`Version ${lectures}`); });
    await flush();
    caisse.document.hidden = true;
    await caisse.tick();
    assert.equal(lectures, 1);
    caisse.document.hidden = false;
    await caisse.documentEvents.visibilitychange();
    assert.equal(caisse.promotion.innerHTML, "Version 2");
    await caisse.windowEvents.focus();
    assert.equal(caisse.promotion.innerHTML, "Version 3");
});

test("une ancienne lecture ne remplace pas la mise à jour d’un achat", async () => {
    let terminerLecture;
    const caisse = page((url, options) => {
        if (options.method === "POST") return Promise.resolve(reponse("Après achat"));
        return new Promise(resolve => { terminerLecture = resolve; });
    });
    await caisse.formEvents.submit({ preventDefault() {}, submitter: null });
    assert.equal(caisse.promotion.innerHTML, "Après achat");
    terminerLecture(reponse("Avant achat"));
    await flush();
    assert.equal(caisse.promotion.innerHTML, "Après achat");
});

test("retente après une panne et retire l’affichage si l’accès est révoqué", async () => {
    let lectures = 0;
    const caisse = page(async () => {
        lectures++;
        if (lectures === 1) throw new Error("Réseau indisponible");
        if (lectures === 2) return reponse("Rétablie");
        return { status: 403, ok: false };
    });
    await flush();
    assert.equal(caisse.promotion.innerHTML, "Ancienne");
    await caisse.tick();
    assert.equal(caisse.promotion.innerHTML, "Rétablie");
    await caisse.tick();
    assert.equal(caisse.promotion.innerHTML, "");
});
