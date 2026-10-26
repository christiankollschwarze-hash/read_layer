// AP 54c: Prueft die Wort+Gegenwort-Hervorhebung (taella-app/src/lib/wortpaar.js) an einem Demo-Werk ohne Browser.
// Aufruf: node tools/test_wortpaar_54c.mjs [slug] [anzahl] [kapitel,kapitel,...]
// Ausgabe: work/_54c/stichprobe.tsv (je Wort: Sprache, Satz, Zeit, gehoertes Wort, markiertes Gegenwort,
//          Abweichung Ankerzeit vs. Stage-520-Tokenzeit in ms) + Kennzahlen auf der Konsole.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
const app = path.resolve("../taella-app");
const { wortpaarZustand } = await import(pathToFileURL(path.join(app, "src/lib/wortpaar.js")));
const slug = process.argv[2] || "call-of-the-wild", n = +(process.argv[3] || 20);
const kapWahl = (process.argv[4] || "c001,c004,c007").split(",");
const d = path.join(app, "public/demo", slug);
const J = (f) => JSON.parse(fs.readFileSync(path.join(d, f), "utf8"));
const en = J("manifest_en.json"), deM = J("manifest_de.json");
const wt = { en: J("wordtimes_en.json").tags, de: J("wordtimes_de.json").tags };
const deById = Object.fromEntries(deM.saetze.map((s) => [s.tag_id, s]));
let seed = 54; const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
const txt = (t, st, v) => { let o = "", last = -2; for (let c = 0; c < st.length; c++) if (st[c] === v) { o += (c === last + 1 ? "" : (o ? " … " : "")) + t[c]; last = c; } return o; };
const tokAt = (t, c) => { const m = [...t.matchAll(/\S+/g)]; return m.findIndex((x) => c >= x.index && c < x.index + x[0].length); };
const rows = [["lang", "tag_id", "zeit_s", "gehoert", "gegenwort", "abw_ms", "satz_en", "satz_de"]];
const stat = { en: { n: 0, mitG: 0, abw: [] }, de: { n: 0, mitG: 0, abw: [] } };
for (const s of en.saetze) {
  if (!s.align || !kapWahl.some((k) => s.tag_id.startsWith(k))) continue;
  const node = { tag_id: s.tag_id, align: s.align, en: { text: s.text }, de: { text: deById[s.tag_id]?.text || "" } };
  for (const lang of ["en", "de"]) {
    const other = lang === "en" ? "de" : "en";
    for (const a of s.align) {
      const wins = lang === "en" ? (a.t ? [a.t] : []) : (a.tz || []);
      for (const w of wins) {
        stat[lang].n++;
        const z = wortpaarZustand(node, lang, w[0] + 0.03, "en", node[lang].text.length, node[other].text.length);
        const h = txt(node[lang].text, z.heard, 2), g = txt(node[other].text, z.other, 2);
        if (g) stat[lang].mitG++;
        const c = z.heard.indexOf(2), ti = c >= 0 ? tokAt(node[lang].text, c) : -1;
        const t520 = ti >= 0 ? wt[lang][s.tag_id]?.[ti] : null;
        const abw = t520 != null ? Math.round((w[0] - t520) * 1000) : null;
        if (abw != null) stat[lang].abw.push(Math.abs(abw));
        if (rnd() < 0.02) rows.push([lang, s.tag_id, w[0].toFixed(2), h, g, abw ?? "", node.en.text, node.de.text]);
      }
    }
  }
}
const out = path.resolve("authors/london-j/books", slug, "work/_54c");
fs.mkdirSync(out, { recursive: true });
fs.writeFileSync(path.join(out, "stichprobe_alle.tsv"), rows.map((r) => r.join("\t")).join("\n"));
for (const l of ["en", "de"]) {
  const a = stat[l].abw.sort((x, y) => x - y);
  console.log(l, "Woerter", stat[l].n, "mit Gegenwort", (100 * stat[l].mitG / stat[l].n).toFixed(1) + "%",
    "Abw. Anker/520 Median", a[a.length >> 1], "ms, P95", a[Math.floor(a.length * 0.95)], "ms, >150ms", (100 * a.filter((x) => x > 150).length / a.length).toFixed(1) + "%");
}
console.log("Kandidaten:", rows.length - 1, "->", out);
