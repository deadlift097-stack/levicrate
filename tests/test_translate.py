"""End-to-end proof: real javac bytecode -> C++ -> run -> output must equal what the JVM prints."""
import shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import j2cpp

def have_java():
    if not shutil.which("java") or not shutil.which("g++"):
        return False
    return subprocess.run(["java", "--list-modules"], capture_output=True, text=True).stdout.find("jdk.compiler") >= 0


@unittest.skipUnless(have_java(), "needs java (with jdk.compiler) and g++")
class TranslateEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        src = cls.tmp / "Calc.java"
        shutil.copy(ROOT / "tests/java/Calc.java", src)
        subprocess.run(["java", "-m", "jdk.compiler/com.sun.tools.javac.Main", str(src)], check=True, cwd=cls.tmp)
        cls.expected = subprocess.run(["java", "-cp", str(cls.tmp), "Calc"], capture_output=True, text=True, check=True).stdout
        jc = j2cpp.load_class((cls.tmp / "Calc.class").read_bytes())
        hpp, cpp, cls.items = j2cpp.translate_classes([jc])
        (cls.tmp / "Translated.hpp").write_text(hpp); (cls.tmp / "Translated.cpp").write_text(cpp)

    def test_output_identical_to_jvm(self):
        exe = self.tmp / "h"
        subprocess.run(["g++", "-std=c++17", "-O1", "-Wno-unused-label", "-Wno-unused-variable", "-I", str(ROOT / "native/include"),
                        "-I", str(self.tmp), str(ROOT / "tests/java/harness.cpp"), str(self.tmp / "Translated.cpp"), "-o", str(exe)], check=True)
        got = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout
        self.assertGreater(len(self.expected.splitlines()), 90)
        self.assertEqual(got, self.expected)

    def test_unsupported_are_explicit(self):
        by = {i.name: i for i in self.items}
        for n, why in (("sw", "switch"), ("sarr", "newarray"), ("tc", "try/catch"), ("usesStr", "Integer.toString"), ("name", "String")):
            self.assertFalse(by[n].ok, n); self.assertIn(why, by[n].reason)
        self.assertTrue(by["add"].ok and by["fib"].ok)
        self.assertIn("Calc_sw", by["callsStub"].tainted)  # depends on an untranslated callee


if __name__ == "__main__":
    unittest.main()
