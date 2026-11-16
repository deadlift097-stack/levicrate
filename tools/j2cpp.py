"""Java bytecode -> C++ translator (the automatic part of levicrate).

Translates *pure computation*: methods whose bytecode only uses int/long/float/double (and boolean/byte/char/short),
local variables, branches/loops, static fields of translated classes, calls between translated methods and a
java.lang.Math subset. Anything else (objects, arrays, strings, instance calls, switch tables, try/catch, Minecraft
APIs) makes that one method an explicit UNSUPPORTED stub with the reason recorded. Nothing is guessed.
"""
import re
import struct
from dataclasses import dataclass, field


class Unsupported(Exception):
    pass


CT = {"I": "int32_t", "J": "int64_t", "F": "float", "D": "double"}
KIND = {"I": "I", "Z": "I", "B": "I", "C": "I", "S": "I", "J": "J", "F": "F", "D": "D"}


def sym(s):
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def parse_desc(d):
    params, i = [], 1
    while d[i] != ")":
        c = d[i]
        if c == "L":
            i = d.index(";", i) + 1
            params.append("A")
        elif c == "[":
            while d[i] == "[":
                i += 1
            i = d.index(";", i) + 1 if d[i] == "L" else i + 1
            params.append("A")
        else:
            params.append(c)
            i += 1
    r = d[i + 1]
    return params, ("A" if r in "L[" else r)


@dataclass
class Member:
    access: int
    name: str
    desc: str
    code: bytes = None
    handlers: int = 0
    const: object = None


@dataclass
class JClass:
    name: str
    cp: list
    fields: list = field(default_factory=list)
    methods: list = field(default_factory=list)


def load_class(data: bytes) -> JClass:
    if data[:4] != b"\xca\xfe\xba\xbe":
        raise ValueError("not a class file")
    pos = 8
    (n,) = struct.unpack_from(">H", data, pos); pos += 2
    cp = [None] * n
    i = 1
    while i < n:
        tag = data[pos]; pos += 1
        if tag == 1:
            (ln,) = struct.unpack_from(">H", data, pos)
            cp[i] = (1, data[pos + 2:pos + 2 + ln].decode("utf-8", "replace")); pos += 2 + ln
        elif tag == 3:
            cp[i] = (3, struct.unpack_from(">i", data, pos)[0]); pos += 4
        elif tag == 4:
            cp[i] = (4, struct.unpack_from(">f", data, pos)[0]); pos += 4
        elif tag == 5:
            cp[i] = (5, struct.unpack_from(">q", data, pos)[0]); pos += 8; i += 1
        elif tag == 6:
            cp[i] = (6, struct.unpack_from(">d", data, pos)[0]); pos += 8; i += 1
        elif tag in (7, 8, 16, 19, 20):
            cp[i] = (tag, struct.unpack_from(">H", data, pos)[0]); pos += 2
        elif tag in (9, 10, 11, 12, 17, 18):
            cp[i] = (tag,) + struct.unpack_from(">HH", data, pos); pos += 4
        elif tag == 15:
            cp[i] = (15,); pos += 3
        else:
            raise ValueError("bad constant pool tag %d" % tag)
        i += 1

    def u(idx):
        return cp[idx][1] if cp[idx] and cp[idx][0] == 1 else "?"
    def cname(idx):
        return u(cp[idx][1])

    pos += 2
    this_i, _sup = struct.unpack_from(">HH", data, pos); pos += 4
    (ni,) = struct.unpack_from(">H", data, pos); pos += 2 + 2 * ni
    jc = JClass(cname(this_i), cp)

    def members(target, with_code):
        nonlocal pos
        (cnt,) = struct.unpack_from(">H", data, pos); pos += 2
        for _ in range(cnt):
            acc, ni_, di, na = struct.unpack_from(">HHHH", data, pos); pos += 8
            m = Member(acc, u(ni_), u(di))
            for _ in range(na):
                ani, alen = struct.unpack_from(">HI", data, pos); pos += 6
                an = u(ani)
                if an == "Code" and with_code:
                    _ms, _ml, clen = struct.unpack_from(">HHI", data, pos)
                    m.code = data[pos + 8:pos + 8 + clen]
                    (ex,) = struct.unpack_from(">H", data, pos + 8 + clen)
                    m.handlers = ex
                elif an == "ConstantValue":
                    (ci,) = struct.unpack_from(">H", data, pos)
                    if cp[ci] and cp[ci][0] in (3, 4, 5, 6):
                        m.const = cp[ci]
                pos += alen
            target.append(m)
    members(jc.fields, False)
    members(jc.methods, True)
    return jc


# ------------------------------------------------------------------------------------------------
def ilit(v):
    return "(-2147483647-1)" if v == -2147483648 else str(v)

def llit(v):
    return "(-INT64_C(9223372036854775807)-1)" if v == -9223372036854775808 else f"INT64_C({v})"

def flit(v, kind):
    t = "float" if kind == "F" else "double"
    if v != v:
        return f"std::numeric_limits<{t}>::quiet_NaN()"
    if v in (float("inf"), float("-inf")):
        return f"{'-' if v < 0 else ''}std::numeric_limits<{t}>::infinity()"
    return v.hex() + ("f" if kind == "F" else "")

def const_lit(c):
    tag, v = c
    return {3: lambda: ilit(v), 4: lambda: flit(v, "F"), 5: lambda: llit(v), 6: lambda: flit(v, "D")}[tag]()


BIN = {}
for base, k in ((96, "I"), (97, "J")):
    BIN[base] = (k, k, k, "levicrate::jadd({a}, {b})")
    BIN[base + 4] = (k, k, k, "levicrate::jsub({a}, {b})")
    BIN[base + 8] = (k, k, k, "levicrate::jmul({a}, {b})")
    BIN[base + 12] = (k, k, k, "levicrate::jdiv({a}, {b})")
    BIN[base + 16] = (k, k, k, "levicrate::jrem({a}, {b})")
for base, k in ((98, "F"), (99, "D")):
    BIN[base] = (k, k, k, "{a} + {b}")
    BIN[base + 4] = (k, k, k, "{a} - {b}")
    BIN[base + 8] = (k, k, k, "{a} * {b}")
    BIN[base + 12] = (k, k, k, "{a} / {b}")
    BIN[base + 16] = (k, k, k, "std::fmod({a}, {b})")
BIN.update({120: ("I", "I", "I", "levicrate::jshl({a}, {b})"), 121: ("J", "I", "J", "levicrate::jshl({a}, {b})"),
            122: ("I", "I", "I", "levicrate::jshr({a}, {b})"), 123: ("J", "I", "J", "levicrate::jshr({a}, {b})"),
            124: ("I", "I", "I", "levicrate::jushr({a}, {b})"), 125: ("J", "I", "J", "levicrate::jushr({a}, {b})"),
            126: ("I", "I", "I", "{a} & {b}"), 127: ("J", "J", "J", "{a} & {b}"),
            128: ("I", "I", "I", "{a} | {b}"), 129: ("J", "J", "J", "{a} | {b}"),
            130: ("I", "I", "I", "{a} ^ {b}"), 131: ("J", "J", "J", "{a} ^ {b}"),
            148: ("J", "J", "I", "levicrate::jcmp({a}, {b})"),
            149: ("F", "F", "I", "levicrate::jfcmpl({a}, {b})"), 150: ("F", "F", "I", "levicrate::jfcmpg({a}, {b})"),
            151: ("D", "D", "I", "levicrate::jfcmpl({a}, {b})"), 152: ("D", "D", "I", "levicrate::jfcmpg({a}, {b})")})
UN = {116: ("I", "levicrate::jneg({a})"), 117: ("J", "levicrate::jneg({a})"), 118: ("F", "-{a}"), 119: ("D", "-{a}")}
CONV = {133: ("I", "J", "static_cast<int64_t>({a})"), 134: ("I", "F", "static_cast<float>({a})"),
        135: ("I", "D", "static_cast<double>({a})"), 136: ("J", "I", "levicrate::jl2i({a})"),
        137: ("J", "F", "static_cast<float>({a})"), 138: ("J", "D", "static_cast<double>({a})"),
        139: ("F", "I", "levicrate::jf2i<int32_t, float>({a})"), 140: ("F", "J", "levicrate::jf2i<int64_t, float>({a})"),
        141: ("F", "D", "static_cast<double>({a})"), 142: ("D", "I", "levicrate::jf2i<int32_t, double>({a})"),
        143: ("D", "J", "levicrate::jf2i<int64_t, double>({a})"), 144: ("D", "F", "static_cast<float>({a})"),
        145: ("I", "I", "static_cast<int32_t>(static_cast<int8_t>({a}))"),
        146: ("I", "I", "static_cast<int32_t>(static_cast<uint16_t>({a}))"),
        147: ("I", "I", "static_cast<int32_t>(static_cast<int16_t>({a}))")}
CMP_OPS = ["==", "!=", "<", ">=", ">", "<="]

MATH = {}
for n, ds in {"abs": ["(I)I", "(J)J", "(F)F", "(D)D"], "max": ["(II)I", "(JJ)J", "(FF)F", "(DD)D"],
              "min": ["(II)I", "(JJ)J", "(FF)F", "(DD)D"]}.items():
    for d in ds:
        MATH[(n, d)] = f"levicrate::j{n}"
for n in ("sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "exp", "log", "log10", "floor", "ceil", "cbrt"):
    MATH[(n, "(D)D")] = f"std::{n}"
for n in ("pow", "atan2", "hypot"):
    MATH[(n, "(DD)D")] = f"std::{n}"
MATH[("round", "(D)J")] = "levicrate::jround"
MATH[("round", "(F)I")] = "levicrate::jroundf"

NAMES = {42: "aload", 25: "aload", 58: "astore", 50: "aaload", 83: "aastore", 187: "new", 188: "newarray", 189: "anewarray",
         190: "arraylength", 191: "athrow", 192: "checkcast", 193: "instanceof", 194: "monitorenter", 170: "tableswitch/switch",
         171: "lookupswitch/switch on a value", 198: "ifnull", 199: "ifnonnull", 165: "if_acmpeq", 166: "if_acmpne",
         176: "areturn", 1: "aconst_null", 196: "wide", 169: "ret", 168: "jsr"}


class MethodTranslator:
    def __init__(self, jc, m, names, fields):
        self.jc, self.m, self.names, self.fields = jc, m, names, fields
        self.params, self.ret = parse_desc(m.desc)
        self.calls = set()
        self.static = bool(m.access & 0x8)

    # --- constant pool helpers
    def _u(self, i):
        return self.jc.cp[i][1]
    def _ref(self, idx):
        e = self.jc.cp[idx]
        owner = self._u(self.jc.cp[e[1]][1])
        nat = self.jc.cp[e[2]]
        return owner, self._u(nat[1]), self._u(nat[2])

    def signature(self, cname):
        if any(p == "A" for p in self.params) or self.ret == "A":
            raise Unsupported("uses object/array/String types in its signature")
        slot = 0 if self.static else 1
        args = []
        for p in self.params:
            k = KIND[p]
            args.append(f"{CT[k]} l{slot}{k}")
            slot += 2 if k in "JD" else 1
        rt = "void" if self.ret == "V" else CT[KIND[self.ret]]
        return rt, args

    def translate(self, cname):
        rt, args = self.signature(cname)
        m = self.m
        if m.handlers:
            raise Unsupported("contains try/catch")
        code = m.code
        self.svars, self.lvars, self.targets = set(), set(), set()
        self.out, self.states = {}, {}
        work = [(0, [])]
        while work:
            pc, st = work.pop()
            while True:
                if pc in self.states:
                    if self.states[pc] != st:
                        raise Unsupported("inconsistent stack shape at a branch join")
                    break
                if pc >= len(code):
                    raise Unsupported("falls off the end of the code")
                self.states[pc] = list(st)
                lines = []
                nxt, st, tg = self.step(code, pc, list(st), lines)
                self.out[pc] = lines
                for t, ts in tg:
                    self.targets.add(t)
                    work.append((t, list(ts)))
                if nxt is None:
                    break
                pc = nxt
        body = []
        for pc in sorted(self.out):
            if pc in self.targets:
                body.append(f"L{pc}:;")
            body += ["    " + l for l in self.out[pc]]
        param_names = {a.split()[-1] for a in args}
        decl = [f"{CT[k]} {n} = {'0' if k in 'IJ' else '0'};" for n, k in sorted(self.svars)]
        decl += [f"{CT[k]} {n} = 0;" for n, k in sorted(self.lvars) if n not in param_names]
        head = f"{rt} {cname}({', '.join(args)}) {{"
        return "\n".join([head] + ["    " + d for d in decl] + body + ["}"])

    # --- one instruction
    def step(self, code, pc, st, lines):
        op = code[pc]
        svars = self.svars

        def pop(k=None):
            if not st:
                raise Unsupported("stack underflow")
            kind = st.pop()
            if k and kind != k:
                raise Unsupported("type mismatch on stack")
            return f"s{len(st)}{kind}", kind
        def push(k):
            n = f"s{len(st)}{k}"
            st.append(k)
            svars.add((n, k))
            return n
        def local(slot, k):
            n = f"l{slot}{k}"
            self.lvars.add((n, k))
            return n
        def s16(p):
            return struct.unpack_from(">h", code, p)[0]
        nxt = pc + 1
        targets = []

        if op == 0:
            pass
        elif 2 <= op <= 8:
            lines.append(f"{push('I')} = {ilit(op - 3)};")
        elif op in (9, 10):
            lines.append(f"{push('J')} = {llit(op - 9)};")
        elif 11 <= op <= 13:
            lines.append(f"{push('F')} = {flit(float(op - 11), 'F')};")
        elif op in (14, 15):
            lines.append(f"{push('D')} = {flit(float(op - 14), 'D')};")
        elif op == 16:
            lines.append(f"{push('I')} = {ilit(struct.unpack_from('>b', code, pc + 1)[0])};"); nxt = pc + 2
        elif op == 17:
            lines.append(f"{push('I')} = {ilit(s16(pc + 1))};"); nxt = pc + 3
        elif op in (18, 19, 20):
            if op == 18:
                idx, nxt = code[pc + 1], pc + 2
            else:
                idx, nxt = struct.unpack_from(">H", code, pc + 1)[0], pc + 3
            c = self.jc.cp[idx]
            if c[0] not in (3, 4, 5, 6):
                raise Unsupported("uses a String/class constant")
            k = {3: "I", 4: "F", 5: "J", 6: "D"}[c[0]]
            lines.append(f"{push(k)} = {const_lit(c)};")
        elif op in (21, 22, 23, 24, 54, 55, 56, 57):
            k = "IJFD"[(op - 21) % 33 if op < 54 else op - 54]
            slot, nxt = code[pc + 1], pc + 2
            if op < 54:
                lines.append(f"{push(k)} = {local(slot, k)};")
            else:
                v, _ = pop(k); lines.append(f"{local(slot, k)} = {v};")
        elif 26 <= op <= 41:
            k, slot = "IJFD"[(op - 26) // 4], (op - 26) % 4
            lines.append(f"{push(k)} = {local(slot, k)};")
        elif 59 <= op <= 74:
            k, slot = "IJFD"[(op - 59) // 4], (op - 59) % 4
            v, _ = pop(k); lines.append(f"{local(slot, k)} = {v};")
        elif op == 87:
            if st and st[-1] in "JD": raise Unsupported("pop of a 2-slot value")
            pop()
        elif op == 88:
            if st and st[-1] in "JD": pop()
            else: pop(); pop()
        elif op == 89:
            if not st or st[-1] in "JD": raise Unsupported("dup of a 2-slot value")
            a, k = st[-1], st[-1]; n = push(k); lines.append(f"{n} = s{len(st) - 2}{k};")
        elif op == 92:
            if not st: raise Unsupported("stack underflow")
            if st[-1] in "JD":
                k = st[-1]; src = f"s{len(st) - 1}{k}"; lines.append(f"{push(k)} = {src};")
            else:
                if len(st) < 2 or st[-2] in "JD": raise Unsupported("unusual dup2")
                k1, k2 = st[-2], st[-1]; n = len(st)
                lines.append(f"{push(k1)} = s{n - 2}{k1};"); lines.append(f"{push(k2)} = s{n - 1}{k2};")
        elif op == 95:
            if len(st) < 2 or any(x in "JD" for x in st[-2:]): raise Unsupported("unusual swap")
            n = len(st); ka, kb = st[-2], st[-1]
            raise Unsupported("swap is not translated")
        elif op in BIN:
            ka, kb, kr, fmt = BIN[op]
            b, _ = pop(kb); a, _ = pop(ka)
            lines.append(f"{push(kr)} = {fmt.format(a=a, b=b)};")
        elif op in UN:
            k, fmt = UN[op]
            a, _ = pop(k); lines.append(f"{push(k)} = {fmt.format(a=a)};")
        elif op in CONV:
            kf, kt, fmt = CONV[op]
            a, _ = pop(kf); lines.append(f"{push(kt)} = {fmt.format(a=a)};")
        elif op == 132:
            slot, c = code[pc + 1], struct.unpack_from(">b", code, pc + 2)[0]
            n = local(slot, "I"); lines.append(f"{n} = levicrate::jadd<int32_t>({n}, {ilit(c)});"); nxt = pc + 3
        elif 153 <= op <= 158:
            a, _ = pop("I"); t = pc + s16(pc + 1)
            lines.append(f"if ({a} {CMP_OPS[op - 153]} 0) goto L{t};"); targets.append((t, list(st))); nxt = pc + 3
        elif 159 <= op <= 164:
            b, _ = pop("I"); a, _ = pop("I"); t = pc + s16(pc + 1)
            lines.append(f"if ({a} {CMP_OPS[op - 159]} {b}) goto L{t};"); targets.append((t, list(st))); nxt = pc + 3
        elif op == 167:
            t = pc + s16(pc + 1); lines.append(f"goto L{t};"); targets.append((t, list(st))); nxt = None
        elif op in (172, 173, 174, 175):
            k = "IJFD"[op - 172]
            if self.ret == "V" or KIND.get(self.ret) != k: raise Unsupported("return type mismatch")
            v, _ = pop(k); lines.append(f"return {v};"); nxt = None
        elif op == 177:
            lines.append("return;"); nxt = None
        elif op in (178, 179):
            owner, name, desc = self._ref(struct.unpack_from(">H", code, pc + 1)[0]); nxt = pc + 3
            g = self.fields.get((owner, name, desc))
            if g is None: raise Unsupported(f"accesses static field {owner.rsplit('/', 1)[-1]}.{name}")
            k = KIND[desc]
            if op == 178: lines.append(f"{push(k)} = {g};")
            else:
                v, _ = pop(k); lines.append(f"{g} = {v};")
        elif op == 184:
            owner, name, desc = self._ref(struct.unpack_from(">H", code, pc + 1)[0]); nxt = pc + 3
            ps, r = parse_desc(desc)
            if owner == "java/lang/Math" and (name, desc) in MATH: fn = MATH[(name, desc)]
            elif (owner, name, desc) in self.names: fn = self.names[(owner, name, desc)]
            else: raise Unsupported(f"calls {owner.rsplit('/', 1)[-1]}.{name}")
            if any(p == "A" for p in ps) or r == "A": raise Unsupported(f"calls {name} with object types")
            if (owner, name, desc) in self.names: self.calls.add(fn)
            args = [pop(KIND[p])[0] for p in reversed(ps)][::-1]
            call = f"{fn}({', '.join(args)})"
            lines.append(f"{push(KIND[r])} = {call};" if r != "V" else f"{call};")
        elif op in (180, 181, 182, 183, 185):
            owner, name, _d = self._ref(struct.unpack_from(">H", code, pc + 1)[0])
            what = "instance field" if op in (180, 181) else "instance/interface method"
            raise Unsupported(f"uses {what} {owner.rsplit('/', 1)[-1]}.{name}")
        elif op == 186:
            raise Unsupported("uses invokedynamic (lambda/string concat)")
        else:
            raise Unsupported(f"uses unsupported opcode {NAMES.get(op, op)}")
        return nxt, st, targets


@dataclass
class Item:
    cls: str
    name: str
    desc: str
    cname: str
    ok: bool
    reason: str = ""
    static: bool = True
    params: int = 0
    ret: str = "V"
    clinit: bool = False
    calls: set = field(default_factory=set)
    tainted: str = ""


def translate_classes(classes):
    names, fields, items = {}, {}, []
    used = set()
    for jc in classes:
        for m in jc.methods:
            if m.code is None or m.name == "<init>":
                continue
            base = sym(jc.name) + "_" + sym("clinit" if m.name == "<clinit>" else m.name)
            n, i = base, 2
            while n in used:
                n, i = f"{base}_{i}", i + 1
            used.add(n)
            names[(jc.name, m.name, m.desc)] = n
        for f in jc.fields:
            if f.access & 0x8 and f.desc in KIND:
                fields[(jc.name, f.name, f.desc)] = "g_" + sym(jc.name) + "_" + sym(f.name)

    defs, protos = [], []
    for jc in classes:
        for m in jc.methods:
            key = (jc.name, m.name, m.desc)
            if key not in names:
                continue
            cn = names[key]
            mt = MethodTranslator(jc, m, names, fields)
            ps, r = parse_desc(m.desc)
            it = Item(jc.name, m.name, m.desc, cn, False, static=mt.static, params=len(ps), ret=r, clinit=m.name == "<clinit>")
            try:
                body = mt.translate(cn)
                it.ok = True
                it.calls = mt.calls
                defs.append(body)
                rt, args = mt.signature(cn)
                protos.append(f"{rt} {cn}({', '.join(args)});")
            except Unsupported as e:
                it.reason = str(e)
                try:
                    rt, args = mt.signature(cn)
                    sig = ", ".join(a.split()[0] + " /*unused*/" for a in args)
                    zero = "" if rt == "void" else " return 0;"
                    defs.append(f"// UNSUPPORTED: {it.reason}\n{rt} {cn}({sig}) {{ levicrate::junsupported(\"{jc.name}.{m.name}\");{zero} }}")
                    protos.append(f"{rt} {cn}({', '.join(a.split()[0] for a in args)});")
                except Unsupported:
                    pass  # not expressible in C++ at all; callers will be unsupported too
            except (IndexError, struct.error, KeyError) as e:
                it.reason = f"malformed or unusual bytecode ({type(e).__name__})"
            items.append(it)

    # a translated method that calls an untranslated one is only as good as its callee
    bad = {i.cname for i in items if not i.ok}
    changed = True
    while changed:
        changed = False
        for i in items:
            dead = sorted(c for c in i.calls if c in bad)
            if i.ok and dead and not i.tainted:
                i.tainted = "calls untranslated " + ", ".join(dead)
                changed = True

    gl = []
    for jc in classes:
        for f in jc.fields:
            g = fields.get((jc.name, f.name, f.desc))
            if g:
                k = KIND[f.desc]
                init = const_lit(f.const) if f.const and f.const[0] in (3, 4, 5, 6) else "0"
                gl.append(f"static {CT[k]} {g} = {init};")
    clinits = [i.cname for i in items if i.clinit and i.ok]
    init = ["void levicratePortInit() {", *[f"    {c}();" for c in clinits], "}"]

    hpp = ["// Generated by levicrate convert - do not edit; regenerate instead.", "#pragma once", "#include <cstdint>",
           "namespace port {", *protos, "void levicratePortInit();", "}  // namespace port", ""]
    cpp = ['// Generated by levicrate convert from Java bytecode - do not edit; regenerate instead.',
           '#include "Translated.hpp"', '#include <cmath>', '#include <limits>', '#include "crate/JavaOps.hpp"', "",
           "namespace port {", "", *gl, "", *[d + "\n" for d in defs], *init, "", "}  // namespace port", ""]
    return "\n".join(hpp), "\n".join(cpp), items
