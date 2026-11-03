// AP 710c: App-Loader (taella-app/src/lib/loader.js) gegen ein Paket aus Stage 710 (Schema 2) und ein Altpaket.
// Aufruf: node tools/test_loader_710c.mjs <public-ordner mit 710-Paket> <slug> [<altwerk-ordner>]
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { pathToFileURL } from "node:url";

const [pub, slug, altBase] = process.argv.slice(2);
const appLoader = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..", "..", "taella-app", "src", "lib", "loader.js");
const src = fs.readFileSync(appLoader, "utf8")
  .replace(/^import \{ setSprecherGeschlecht \}.*$/m, "const setSprecherGeschlecht = () => {};");
const tmp = path.join(os.tmpdir(), `loader_710c_${process.pid}.mjs`);
fs.writeFileSync(tmp, src);
const { loadWork, schemaPruefen } = await import(pathToFileURL(tmp).href);

let root = pub;
globalThis.fetch = async (url) => {
  const p = path.join(root, decodeURIComponent(url));
  const ok = fs.existsSync(p);
  return { ok, headers: { get: () => (url.endsWith(".json") ? "application/json" : "") },
           json: async () => JSON.parse(fs.readFileSync(p, "utf8")) };
};
let fehler = 0;
const pruef = (ok, text) => { console.log(`${ok ? "ok " : "X  "} ${text}`); if (!ok) fehler++; };

const kat = JSON.parse(fs.readFileSync(path.join(pub, "demo", "katalog.json"), "utf8"));
const e = kat.werke.find((w) => w.slug === slug);
pruef(!!e, `Katalogeintrag ${slug} (schema ${kat.schema})`);
const w = await loadWork(`/demo/${slug}`, { sprachen: e.sprachen, downloads: e.downloads });
pruef(w.meta.schema === 2, `Schema ${w.meta.schema}`);
pruef(JSON.stringify(w.meta.sprachen) === JSON.stringify(e.sprachen), `Sprachen ${w.meta.sprachen}`);
pruef(w.meta.quellsprache === "en" && w.meta.zielsprache === "de", `Paar ${w.meta.quellsprache}->${w.meta.zielsprache}`);
const n = w.nodes.find((x) => x.tag_id === "c001_00002_s");
pruef(n.en.text === "One dollar." && n.de.text === "Ein Dollar.", "Texte je Sprache");
pruef(n.de.audio === `/demo/${slug}/audio/de/c001_00002_s.mp3`, `Audio ${n.de.audio}`);
pruef(n.de.audio_hs === `/demo/${slug}/audio_hoerspiel/de/c001_00002_s.mp3`, `Hoerspiel aus Manifest ${n.de.audio_hs}`);
pruef(n.de.sprecher_hs === "Buck", `Hoerspiel-Sprecher ${n.de.sprecher_hs}`);
pruef(n.align && n.align[0].t, "Anker align_de mit Wortzeit");
pruef(w.meta.hoerspiel.de === true && w.meta.hoerspiel.en === false, "Hoerspiel je Sprache");
pruef(Array.isArray(w.wordtimes.de?.c001_00002_s), "Wortzeiten de");
pruef(Array.isArray(w.wordtimesHs.de?.c001_00002_s), "Wortzeiten Hoerspiel de");
pruef(w.coverSrc("de") === `/demo/${slug}/cover_de.jpg`, `Cover ${w.coverSrc("de")}`);
pruef(w.meta.teaser.de === `/demo/${slug}/teaser/de`, `Teaser ${w.meta.teaser.de}`);
pruef(w.meta.downloads.en?.text === `/demo/${slug}/download/${slug}_en.epub`, `Download ${w.meta.downloads.en?.text}`);
pruef(w.kapitel.length === 1 && w.kapitel[0].titel_je.de === "Kapitel eins", "Kapitel je Sprache");
let wurf = null;
try { schemaPruefen({ schema: 3 }, "en"); } catch (x) { wurf = x.message; }
pruef(!!wurf, `Schema 3 abgelehnt: ${wurf}`);

if (altBase) {
  root = path.dirname(path.dirname(altBase));
  const a = await loadWork(`/demo/${path.basename(altBase)}`, {});
  pruef(a.meta.schema === 1 && a.nodes.length > 0, `Altpaket ${path.basename(altBase)}: Schema 1, ${a.nodes.length} Knoten, Sprachen ${a.meta.sprachen}`);
  const h = a.nodes.find((x) => x.de.audio_hs || x.en.audio_hs);
  if (h) pruef(/\.wav$/.test(h.de.audio_hs || h.en.audio_hs), `Altpaket Hoerspiel .wav ${h.de.audio_hs || h.en.audio_hs}`);
}
fs.unlinkSync(tmp);
console.log(fehler ? `FEHLER: ${fehler}` : "ALLES OK");
process.exit(fehler ? 1 : 0);
