"""Roemische Zahlen im Sprechtext (REGELN_V 5, 23.11.2026)."""
import unittest

from pipeline import sprechtext as st

FAELLE = [
    ("de", "s", "Ludwig XIV. regierte lange.", "Ludwig der Vierzehnte regierte lange."),
    ("de", "s", "Unter Ludwig XIV. und Heinrich VIII. war es so.", "Unter Ludwig dem Vierzehnten und Heinrich dem Achten war es so."),
    ("de", "s", "Die Zeit Ludwigs XIV. war prächtig.", "Die Zeit Ludwigs des Vierzehnten war prächtig."),
    ("de", "s", "Unter König Ludwig XIV. blühte Paris.", "Unter König Ludwig dem Vierzehnten blühte Paris."),
    ("de", "s", "Papst Johannes XXIII. starb.", "Papst Johannes der Dreiundzwanzigste starb."),
    ("de", "s", "Ein Brief für Heinrich VIII. kam an.", "Ein Brief für Heinrich den Achten kam an."),
    ("de", "s", "Für Karl V. oder Philipp II. sprach viel.", "Für Karl den Fünften oder Philipp den Zweiten sprach viel."),
    ("de", "s", "Im XIX. Jahrhundert lebte er.", "Im neunzehnten Jahrhundert lebte er."),
    ("de", "s", "Der XIX. Band erschien.", "Der neunzehnte Band erschien."),
    ("de", "h", "Suntzu: I. Einleitende Gedanken", "Suntzu: Eins. Einleitende Gedanken"),
    ("en", "h", "Sun Tzu: I. Introductory Thoughts", "Sun Tzu: One. Introductory Thoughts"),
    ("de", "h", "Teil 2 – IV", "Teil 2 – Vier"),
    ("de", "h", "IX. Der Nimmervogel", "Neun. Der Nimmervogel"),
    ("de", "h", "Kapitel IV", "Kapitel vier"),
    ("en", "h", "Note: I went home", "Note: I went home"),
    ("en", "s", "Then I went home.", "Then I went home."),
    ("en", "s", "Louis XIV ruled.", "Louis the Fourteenth ruled."),
    ("de", "s", "Die meisten kamen in Klasse III, aber er in Klasse IV.", "Die meisten kamen in Klasse drei, aber er in Klasse vier."),
    ("de", "s", "seit Franz’ I. Niederlage bei Pavia", "seit Franz’ des Ersten Niederlage bei Pavia"),
    ("de", "s", "Arnim, Hans V., „Epictetos“", "Arnim, Hans V., „Epictetos“"),
    ("en", "s", "At 3 p.m. he left; see p. 12.", "At 3 p.m. he left; see page twelve."),
]


class TRoemisch(unittest.TestCase):
    def test_faelle(self):
        for lg, typ, ein, soll in FAELLE:
            with self.subTest(ein=ein):
                self.assertEqual(st.sprechtext(ein, lg, typ), soll)

    def test_gate_ruhig(self):
        for lg, typ, ein, _ in FAELLE:
            with self.subTest(ein=ein):
                self.assertEqual(st.roemisch_offen(st.sprechtext(ein, lg, typ), typ == "h"), [])

    def test_abbildung(self):
        t = "Unter Ludwig XIV. lebte er."
        sp, abb = st.sprechtext_abb(t, "de", "s")
        i = sp.index("dem Vierzehnten")
        self.assertEqual(t[slice(*st.lesespan(abb, i, i + len("dem Vierzehnten"), len(sp)))].strip(), "XIV.")


if __name__ == "__main__":
    unittest.main()
