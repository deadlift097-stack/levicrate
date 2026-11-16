import io, json, struct, sys, tempfile, unittest, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import levicrate as lc


def make_class(name="com/x/Foo", sup="java/lang/Object", methods=(("run", "()V"), ("<init>", "()V"))):
    cp, idx = [], {}
    def utf(s):
        if s not in idx:
            b = s.encode(); cp.append(b"\x01" + struct.pack(">H", len(b)) + b); idx[s] = len(cp)
        return idx[s]
    def klass(s):
        u = utf(s); cp.append(b"\x07" + struct.pack(">H", u)); return len(cp)
    t, s = klass(name), klass(sup)
    ms = b"".join(struct.pack(">HHHH", 1, utf(n), utf(d), 0) for n, d in methods)
    return (b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 65, len(cp) + 1) + b"".join(cp) +
            struct.pack(">HHHH", 1, t, s, 0) + struct.pack(">H", 0) + struct.pack(">H", len(methods)) + ms + struct.pack(">H", 0))


def make_jar(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)


FABRIC = json.dumps({"id": "Cool-Mod", "name": "Cool Mod", "version": "1.2.3", "authors": ["Ann", {"name": "Bob"}],
                     "icon": "assets/cool/icon.png"})


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def jar(self, extra=None):
        files = {"fabric.mod.json": FABRIC, "com/x/Foo.class": make_class(),
                 "com/x/mixin/FooMixin.class": make_class("com/x/mixin/FooMixin"),
                 "assets/cool/icon.png": b"PNG", "assets/cool/lang/en.json": "{}", "data/x.json": "{}",
                 "../evil.txt": "x", "/abs.txt": "x", "META-INF/MANIFEST.MF": "m"}
        files.update(extra or {})
        p = self.tmp / "cool.jar"; make_jar(p, files); return p

    def test_class_parser(self):
        c = lc.parse_class(make_class())
        self.assertEqual(c.name, "com/x/Foo"); self.assertEqual(c.super_name, "java/lang/Object")
        self.assertIn(("run", "()V"), c.methods)
        with self.assertRaises(lc.CrateError): lc.parse_class(b"nope")

    def test_fabric_metadata(self):
        meta, classes, bad, assets = lc.scan(self.jar())
        self.assertEqual((meta.id, meta.name, meta.version, meta.author), ("cool_mod", "Cool Mod", "1.2.3", "Ann, Bob"))
        self.assertEqual(len(classes), 2)
        self.assertEqual(len(bad), 2)  # ../evil.txt and /abs.txt
        self.assertIn("assets/cool/lang/en.json", assets)

    def test_forge_and_bukkit_and_fallback(self):
        toml = 'modLoader="javafml"\n[[mods]]\nmodId="forgy"\nversion="2.0"\ndisplayName="Forgy"\n[[dependencies.forgy]]\nmodId="forge"\n'
        p = self.tmp / "a.jar"; make_jar(p, {"META-INF/mods.toml": toml})
        m = lc.scan(p)[0]; self.assertEqual((m.id, m.name, m.version, m.loader), ("forgy", "Forgy", "2.0", "forge"))
        p = self.tmp / "b.jar"; make_jar(p, {"plugin.yml": "name: Plug\nversion: 3.1\nauthor: Zed\n"})
        m = lc.scan(p)[0]; self.assertEqual((m.id, m.author, m.loader), ("plug", "Zed", "bukkit"))
        p = self.tmp / "9weird name.jar"; make_jar(p, {"fabric.mod.json": "{broken"})
        m = lc.scan(p)[0]; self.assertEqual(m.id, "mod_9weird_name")

    def test_convert_and_pack(self):
        out = self.tmp / "ws"
        ws, nc, na, counts = lc.convert(self.jar(), out, ["1.21.*", "1.22.*"])
        self.assertEqual(ws["library"], "cool_mod")
        self.assertTrue((out / "assets/assets/cool/lang/en.json").is_file())
        self.assertTrue((out / "icon/icon.png").is_file())
        self.assertFalse((out.parent / "evil.txt").exists())
        rep = (out / "PORTING.md").read_text()
        self.assertIn("Mixins", rep); self.assertIn("automatic rewrite", rep); self.assertIn("Asset caveat", rep)
        cpp = (out / "src/ModPort.cpp").read_text()
        self.assertIn("void buildPortedMenu", cpp); self.assertIn("levicratePortInit", cpp)
        self.assertTrue((out / "src/Translated.cpp").is_file() and (out / "src/Translated.hpp").is_file())
        so = self.tmp / "libcool_mod.so"; so.write_bytes(b"\x7fELF")
        pk = lc.pack(out, so)
        with zipfile.ZipFile(pk) as z:
            names = z.namelist()
            self.assertIn("cool_mod/libcool_mod.so", names)
            self.assertIn("cool_mod/assets/assets/cool/lang/en.json", names)
            self.assertIn("cool_mod/icon/icon.png", names)
            man = json.loads(z.read("cool_mod/manifest.json"))
        self.assertEqual(man["type"], "preload-native"); self.assertEqual(man["entry"], "libcool_mod.so")
        self.assertEqual(man["minecraft_versions"], ["1.21.*", "1.22.*"])
        self.assertEqual(pk.read_bytes(), lc.pack(out, so, out=self.tmp / "again.levipack").read_bytes())  # reproducible

    def test_cli_errors(self):
        self.assertEqual(lc.main(["pack", "--workspace", str(self.tmp), "--so", "missing.so"]), 1)
        bad = self.tmp / "notzip.jar"; bad.write_bytes(b"x")
        self.assertEqual(lc.main(["inspect", str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
