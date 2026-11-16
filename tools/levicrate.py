#!/usr/bin/env python3
"""levicrate - Java mod -> LeviLauncher native-mod workspace, and .levipack packer.

Scope: `convert` automates metadata, assets, packaging AND translates pure-computation bytecode to C++.
Methods that touch Minecraft/Java objects cannot be mapped automatically; they become explicit stubs + a porting report.

Commands:
  inspect <jar>                         show detected metadata + classes
  convert <jar> -o <dir> [--mc V ...]   create a buildable workspace (+ PORTING.md, src/ModPort.cpp)
  build <jar> [-o <out.levipack>]       convert + compile (Android NDK) + package: Java mod -> .levipack in one step
  pack --workspace <dir> --so <lib.so>  create <id>-<version>-<abi>.levipack from a built library
"""
import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import j2cpp  # noqa: E402

MAX_FILE = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
DEFAULT_MC = ["1.26.62.1"]
ABI = "arm64-v8a"  # LeviLauncher is 64-bit ARM only; 32-bit ARM (armeabi-v7a) is not supported
ROOT = Path(__file__).resolve().parent.parent


class CrateError(Exception):
    pass


# ----------------------------------------------------------------- helpers
def sanitize_id(s: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", (s or "").lower()).strip("_")
    if not s:
        s = "mod"
    if s[0].isdigit():
        s = "mod_" + s
    return s[:48]


def safe_name(name: str):
    """Normalise a zip entry name; None if it could escape the target directory."""
    p = PurePosixPath(name.replace("\\", "/"))
    if p.is_absolute() or not p.parts or ".." in p.parts or ":" in p.parts[0]:
        return None
    return str(p)


@dataclass
class ModInfo:
    id: str = ""
    name: str = ""
    version: str = ""
    author: str = ""
    description: str = ""
    icon: str = ""
    loader: str = "unknown"


@dataclass
class ClassInfo:
    name: str
    super_name: str
    methods: list = field(default_factory=list)  # (name, descriptor)


# ----------------------------------------------------------------- metadata
def _first(v):
    if isinstance(v, list) and v:
        v = v[0]
    if isinstance(v, dict):
        v = v.get("name") or v.get("id") or ""
    return str(v) if v else ""


def _authors(v):
    if isinstance(v, list):
        names = [_first(a) for a in v]
        return ", ".join(n for n in names if n)
    return _first(v)


def parse_metadata(z: zipfile.ZipFile, fallback_name: str) -> ModInfo:
    names = set(z.namelist())

    def read(n):
        return z.read(n).decode("utf-8", "replace")

    info = ModInfo()
    try:
        if "fabric.mod.json" in names:
            d = json.loads(read("fabric.mod.json"))
            icon = d.get("icon", "")
            if isinstance(icon, dict):
                icon = icon[max(icon, key=lambda k: int(k) if str(k).isdigit() else 0)] if icon else ""
            info = ModInfo(d.get("id", ""), d.get("name", ""), str(d.get("version", "")),
                           _authors(d.get("authors")), d.get("description", ""), icon, "fabric")
        elif "quilt.mod.json" in names:
            q = json.loads(read("quilt.mod.json")).get("quilt_loader", {})
            md = q.get("metadata", {})
            contrib = md.get("contributors", {})
            author = ", ".join(contrib) if isinstance(contrib, dict) else _authors(contrib)
            info = ModInfo(q.get("id", ""), md.get("name", ""), str(q.get("version", "")),
                           author, md.get("description", ""), md.get("icon", "") if isinstance(md.get("icon"), str) else "", "quilt")
        elif "mcmod.info" in names:
            d = json.loads(read("mcmod.info"))
            if isinstance(d, dict):
                d = d.get("modList", [])
            m = d[0] if d else {}
            info = ModInfo(m.get("modid", ""), m.get("name", ""), str(m.get("version", "")),
                           _authors(m.get("authorList") or m.get("authors")), m.get("description", ""),
                           m.get("logoFile", ""), "forge-legacy")
        else:
            toml = next((n for n in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml") if n in names), None)
            yml = next((n for n in ("paper-plugin.yml", "plugin.yml") if n in names), None)
            if toml:
                t = read(toml)
                blk = re.search(r"\[\[mods\]\](.*?)(?=\n\s*\[\[|\Z)", t, re.S)
                b = blk.group(1) if blk else t

                def g(key):
                    m = re.search(r"^\s*%s\s*=\s*(?:\"([^\"]*)\"|'([^']*)')" % key, b, re.M)
                    return (m.group(1) or m.group(2)) if m else ""
                a = re.search(r"^\s*authors\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", t, re.M)
                info = ModInfo(g("modId"), g("displayName"), g("version"),
                               (a.group(1) or a.group(2)) if a else "", g("description"), g("logoFile"),
                               "neoforge" if "neoforge" in toml else "forge")
            elif yml:
                t = read(yml)

                def y(key):
                    m = re.search(r"^%s:\s*['\"]?(.+?)['\"]?\s*$" % key, t, re.M)
                    return m.group(1) if m else ""
                info = ModInfo(y("name"), y("name"), y("version"), y("author"), y("description"), "", "bukkit")
    except (ValueError, KeyError, StopIteration, IndexError, TypeError):
        info = ModInfo()  # malformed metadata: fall back to file name

    info.name = info.name or fallback_name
    info.id = sanitize_id(info.id or info.name)
    info.version = re.sub(r"[^\w.+-]", "", info.version or "") or "0.1.0"
    info.author = info.author or "unknown"
    if not info.icon:
        info.icon = next((n for n in ("pack.png", "logo.png", "icon.png") if n in names), "")
    return info


# ----------------------------------------------------------------- class files
def parse_class(data: bytes) -> ClassInfo:
    if data[:4] != b"\xca\xfe\xba\xbe":
        raise CrateError("not a class file")
    pos = 8
    (count,) = struct.unpack_from(">H", data, pos)
    pos += 2
    utf8, cls = {}, {}
    i = 1
    fixed = {3: 4, 4: 4, 9: 4, 10: 4, 11: 4, 12: 4, 17: 4, 18: 4, 15: 3, 16: 2, 8: 2, 19: 2, 20: 2}
    while i < count:
        tag = data[pos]
        pos += 1
        if tag == 1:
            (ln,) = struct.unpack_from(">H", data, pos)
            utf8[i] = data[pos + 2:pos + 2 + ln].decode("utf-8", "replace")
            pos += 2 + ln
        elif tag == 7:
            (cls[i],) = struct.unpack_from(">H", data, pos)
            pos += 2
        elif tag in (5, 6):
            pos += 8
            i += 1
        elif tag in fixed:
            pos += fixed[tag]
        else:
            raise CrateError("bad constant pool tag %d" % tag)
        i += 1
    pos += 2  # access flags
    this_i, super_i = struct.unpack_from(">HH", data, pos)
    pos += 4
    (n_if,) = struct.unpack_from(">H", data, pos)
    pos += 2 + 2 * n_if

    def members():
        nonlocal pos
        out = []
        (n,) = struct.unpack_from(">H", data, pos)
        pos += 2
        for _ in range(n):
            _acc, name_i, desc_i, n_attr = struct.unpack_from(">HHHH", data, pos)
            pos += 8
            for _ in range(n_attr):
                (alen,) = struct.unpack_from(">I", data, pos + 2)
                pos += 6 + alen
            out.append((utf8.get(name_i, "?"), utf8.get(desc_i, "?")))
        return out
    members()  # fields
    methods = members()
    return ClassInfo(utf8.get(cls.get(this_i), "?"), utf8.get(cls.get(super_i), ""), methods)


def scan(jar: Path):
    classes, bad, assets, total = [], [], [], 0
    with zipfile.ZipFile(jar) as z:
        meta = parse_metadata(z, jar.stem)
        for zi in z.infolist():
            if zi.is_dir():
                continue
            n = safe_name(zi.filename)
            total += zi.file_size
            if n is None:
                bad.append(("skipped unsafe path", zi.filename))
                continue
            if zi.file_size > MAX_FILE or total > MAX_TOTAL:
                raise CrateError("archive too large (zip bomb guard)")
            if n.endswith(".class"):
                try:
                    classes.append(parse_class(z.read(zi)))
                except (CrateError, struct.error, IndexError) as e:
                    bad.append((str(e), n))
            elif n.startswith(("assets/", "data/")) or n == "pack.mcmeta" or n == meta.icon:
                assets.append(n)
    return meta, classes, bad, assets


# ----------------------------------------------------------------- convert
def cxx_ident(s):
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def convert(jar: Path, out: Path, mc=None, author=None):
    meta, classes, bad, assets = scan(jar)
    if author:
        meta.author = author
    mc = mc or DEFAULT_MC
    out.mkdir(parents=True, exist_ok=True)
    (out / "src").mkdir(exist_ok=True)

    copied_icon = ""
    with zipfile.ZipFile(jar) as z:
        for n in assets:
            dest = out / "assets" / n
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(n))
            if n == meta.icon:
                copied_icon = n
    if copied_icon:
        (out / "icon").mkdir(exist_ok=True)
        (out / "icon" / PurePosixPath(copied_icon).name).write_bytes((out / "assets" / copied_icon).read_bytes())
        icon_rel = "icon/" + PurePosixPath(copied_icon).name
    else:
        icon_rel = ""

    ws = {"id": meta.id, "name": meta.name, "author": meta.author, "version": meta.version,
          "library": meta.id, "minecraft_versions": mc, "icon": icon_rel,
          "source_jar": jar.name, "source_loader": meta.loader}
    (out / "levicrate.json").write_text(json.dumps(ws, indent=2) + "\n")

    # ---- automatic Java -> C++ translation (pure-computation subset) ----
    jclasses = []
    with zipfile.ZipFile(jar) as z:
        for zi in z.infolist():
            n = safe_name(zi.filename)
            if n and n.endswith(".class") and not zi.is_dir():
                try:
                    jclasses.append(j2cpp.load_class(z.read(zi)))
                except (ValueError, struct.error, IndexError):
                    pass
    hpp, cpp_t, items = j2cpp.translate_classes(jclasses)
    (out / "src" / "Translated.hpp").write_text(hpp)
    (out / "src" / "Translated.cpp").write_text(cpp_t)
    ok = [i for i in items if i.ok and not i.clinit and not i.tainted]
    partial = [i for i in items if i.ok and not i.clinit and i.tainted]
    bad_items = [i for i in items if not i.ok]
    mixins = [c for c in classes if "mixin" in c.name.lower()]

    def short(i):
        return f"{i.cls}.{i.name}{i.desc}"
    rep = [f"# Porting report: {meta.name}", "",
           f"Detected loader: **{meta.loader}** | id `{meta.id}` | version `{meta.version}` | author {meta.author}", "",
           "## Result of the automatic rewrite", "",
           f"- **{len(ok)} method(s) translated to C++** (`src/Translated.cpp`) - pure computation: numbers, loops, branches, static fields, Math calls.",
           f"- **{len(bad_items) + len(partial)} method(s) need manual work** ({len(partial)} translated but depend on untranslated callees)  - untranslated ones are explicit stubs that report through `levicrate::faultHandler()` when called.",
           f"- {len(assets)} asset file(s) copied to `assets/`", "",
           "Why the rest can't be automatic: calls into Minecraft Java classes (entities, worlds, rendering) have no Bedrock-native",
           "equivalent. Each needs a hand-written hook (`pl::memory::Hook` / `Signature`) found for the target game version.", "",
           "## Translated", ""]
    rep += [f"- [x] `{short(i)}` -> `port::{i.cname}`" for i in sorted(ok, key=short)] or ["- (none)"]
    if partial:
        rep += ["", "## Translated, but call methods that were not (finish those first)", ""]
        rep += [f"- [~] `{short(i)}` - {i.tainted}" for i in sorted(partial, key=short)]
    rep += ["", "## Needs a hand-written C++ rewrite", ""]
    rep += [f"- [ ] `{short(i)}` - {i.reason}" for i in sorted(bad_items, key=short) if not i.clinit] or ["- (none)"]
    if any(i.clinit and not i.ok for i in items):
        rep += ["", "Static initialisers that failed (their fields keep default values):"]
        rep += [f"- `{i.cls}.<clinit>` - {i.reason}" for i in items if i.clinit and not i.ok]
    if mixins:
        rep += ["", "## Mixins (always need hook rewrites)", ""] + [f"- `{c.name}`" for c in mixins]
    rep += ["", "## Asset caveat", "",
            "Java-edition resources (block/item model JSON, lang files, blockstates) use different formats than Bedrock.",
            "PNG textures and sounds usually carry over; models and data files need conversion by hand.", ""]
    if bad:
        rep += ["## Skipped / unreadable entries", ""] + [f"- {why}: `{n}`" for why, n in bad] + [""]
    (out / "PORTING.md").write_text("\n".join(rep))

    runnable = [i for i in ok if i.static and i.params == 0 and i.ret == "V"][:40]
    cpp = ["// levicrate convert wrote this once; it is YOURS to edit (convert will not overwrite it).",
           '#include "crate/Menu.hpp"', '#include "Translated.hpp"', "",
           "void buildPortedMenu(levicrate::Menu& menu) {", "    port::levicratePortInit();"]
    for i in runnable:
        label = f"{i.cls.rsplit('/', 1)[-1]}.{i.name}".replace('"', "")
        cpp.append(f'    menu.action("port.{i.cname}", "{label}", [](const levicrate::Entry&) {{ port::{i.cname}(); }});')
    cpp += ["    // Wire translated functions to real game hooks here, e.g. call port::Foo_onTick() from a pl::memory::Hook."]
    cpp.append("}")
    mp = out / "src" / "ModPort.cpp"
    if not mp.exists():
        mp.write_text("\n".join(cpp) + "\n")
    return ws, len(classes), len(assets), (len(ok), len(bad_items) + len(partial))


# ----------------------------------------------------------------- pack
def build_manifest(ws: dict) -> dict:
    return {"type": "preload-native", "name": ws["name"], "author": ws["author"], "version": ws["version"],
            "entry": f"lib{ws['library']}.so", "icon": ws.get("icon", ""),
            "minecraft_versions": ws.get("minecraft_versions", DEFAULT_MC)}


def pack(workspace: Path, so: Path, abi=ABI, out=None) -> Path:
    ws = json.loads((workspace / "levicrate.json").read_text())
    if not so.is_file():
        raise CrateError(f"library not found: {so}")
    mid = ws["id"]
    out = out or workspace / f"{mid}-{ws['version']}-{abi}.levipack"
    stamp = (1980, 1, 1, 0, 0, 0)

    def put(z, arc, data):
        zi = zipfile.ZipInfo(arc, stamp)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = 0o644 << 16
        z.writestr(zi, data)

    with zipfile.ZipFile(out, "w") as z:
        put(z, f"{mid}/manifest.json", json.dumps(build_manifest(ws), indent=2) + "\n")
        put(z, f"{mid}/lib{ws['library']}.so", so.read_bytes())
        if ws.get("icon") and (workspace / ws["icon"]).is_file():
            put(z, f"{mid}/{ws['icon']}", (workspace / ws["icon"]).read_bytes())
        for f in sorted((workspace / "assets").rglob("*")) if (workspace / "assets").is_dir() else []:
            if f.is_file():
                put(z, f"{mid}/assets/{f.relative_to(workspace / 'assets').as_posix()}", f.read_bytes())
    return out



# ----------------------------------------------------------------- build (jar -> levipack)
def find_ndk(explicit=None):
    cands = [explicit] + [os.environ.get(k) for k in ("ANDROID_NDK_HOME", "ANDROID_NDK_ROOT", "ANDROID_NDK")]
    for c in cands:
        if c and (Path(c) / "build/cmake/android.toolchain.cmake").is_file():
            return Path(c)
    return None


def build(jar: Path, out=None, mc=None, author=None, ndk=None, workdir=None) -> Path:
    """Java mod -> workspace -> native library -> .levipack. Needs the Android NDK (r28c recommended), cmake, ninja."""
    ndk_path = find_ndk(ndk)
    if ndk_path is None:
        raise CrateError("Android NDK not found. Pass --ndk <path> or set ANDROID_NDK_HOME. No NDK locally? Push the jar to "
                         "mods/ in your GitHub repo: the 'convert' workflow builds the .levipack for you (see README).")
    for tool in ("cmake", "ninja"):
        if not shutil.which(tool):
            raise CrateError(f"{tool} not found on PATH")
    work = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="levicrate-"))
    ws_dir, bld = work / "workspace", work / "build"
    ws, _nc, _na, (t, u) = convert(jar, ws_dir, mc, author)
    print(f"converted: {t} method(s) translated, {u} need manual work (see {ws_dir / 'PORTING.md'})")
    cfg = ["cmake", "-S", str(ROOT), "-B", str(bld), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
           f"-DCMAKE_TOOLCHAIN_FILE={ndk_path / 'build/cmake/android.toolchain.cmake'}", f"-DANDROID_ABI={ABI}",
           "-DANDROID_PLATFORM=android-28", "-DANDROID_STL=c++_shared", f"-DCRATE_WORKSPACE={ws_dir.resolve()}"]
    for cmd in (cfg, ["cmake", "--build", str(bld), "--target", "levi_package"]):
        if subprocess.run(cmd).returncode != 0:
            raise CrateError("native build failed (see the compiler output above)")
    built = sorted(bld.glob("*.levipack"))
    if not built:
        raise CrateError("build finished but produced no .levipack")
    dest = Path(out) if out else Path.cwd() / built[0].name
    shutil.copy2(built[0], dest)
    shutil.copy2(ws_dir / "PORTING.md", dest.with_suffix(".PORTING.md"))
    return dest


# ----------------------------------------------------------------- cli
def main(argv=None):
    ap = argparse.ArgumentParser(prog="levicrate", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("inspect"); a.add_argument("jar", type=Path)
    c = sub.add_parser("convert"); c.add_argument("jar", type=Path); c.add_argument("-o", "--out", type=Path, required=True)
    c.add_argument("--mc", action="append", help="Minecraft version, repeatable (default 1.26.62.1)")
    c.add_argument("--author")
    b = sub.add_parser("build"); b.add_argument("jar", type=Path); b.add_argument("-o", "--out", type=Path)
    b.add_argument("--mc", action="append", help="Minecraft version, repeatable (default 1.26.62.1)")
    b.add_argument("--author"); b.add_argument("--ndk", help="Android NDK path (default: $ANDROID_NDK_HOME)")
    b.add_argument("--workdir", type=Path, help="keep workspace + build files here (default: temp dir)")
    p = sub.add_parser("pack"); p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--so", type=Path, required=True); p.add_argument("--abi", default=ABI)
    p.add_argument("-o", "--out", type=Path)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "inspect":
            meta, classes, bad, assets = scan(args.jar)
            print(json.dumps(meta.__dict__, indent=2))
            print(f"{len(classes)} classes, {len(assets)} assets, {len(bad)} skipped")
        elif args.cmd == "convert":
            ws, nc, na, (t, u) = convert(args.jar, args.out, args.mc, args.author)
            print(f"workspace: {args.out}  ({nc} classes, {na} assets)")
            print(f"auto-translated to C++: {t} method(s); need manual rewrite: {u}")
            print(f"next: python3 tools/levicrate.py build {args.jar} --ndk $ANDROID_NDK_HOME   (or see README for the manual cmake steps)")
            print(f"read {args.out / 'PORTING.md'} - it lists what was translated and what still needs a hand-written hook")
        elif args.cmd == "build":
            print(f"levipack: {build(args.jar, args.out, args.mc, args.author, args.ndk, args.workdir)}")
        else:
            print(pack(args.workspace, args.so, args.abi, args.out))
    except (CrateError, OSError, zipfile.BadZipFile, KeyError, subprocess.SubprocessError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
