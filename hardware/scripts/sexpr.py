"""Tiny S-expression reader/writer for KiCad files."""
import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))')


class Sym(str):
    """Unquoted atom (keyword or number) as opposed to a quoted string."""


def parse(text):
    stack, cur = [], []
    pos = 0
    while True:
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        lp, rp, qs, atom = m.groups()
        if lp:
            stack.append(cur)
            cur = []
        elif rp:
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif qs is not None:
            cur.append(bytes(qs[1:-1], "utf-8").decode("unicode_escape") if "\\" in qs else qs[1:-1])
        else:
            cur.append(Sym(atom))
    return cur[0] if len(cur) == 1 else cur


def _atom(x):
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, float)):
        return f"{x:.6g}" if isinstance(x, float) else str(x)
    s = str(x).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{s}"'


def dumps(node, indent=0):
    if not isinstance(node, list):
        return _atom(node)
    if not any(isinstance(c, list) for c in node):
        return "(" + " ".join(_atom(c) for c in node) + ")"
    pad = "  " * (indent + 1)
    parts = [_atom(c) if not isinstance(c, list) else None for c in node]
    head = []
    rest = []
    for c, p in zip(node, parts):
        if p is not None and not rest:
            head.append(p)
        else:
            rest.append(c)
    out = "(" + " ".join(head)
    for c in rest:
        out += "\n" + pad + dumps(c, indent + 1)
    return out + "\n" + "  " * indent + ")"


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def find1(node, key):
    r = find(node, key)
    return r[0] if r else None


def load_lib_symbol(lib_path, name):
    """Return a symbol definition from a .kicad_sym file with any `extends` flattened."""
    lib = parse(open(lib_path, encoding="utf-8").read())
    table = {s[1]: s for s in find(lib, "symbol")}
    sym = table[name]
    ext = find1(sym, "extends")
    if not ext:
        return sym
    parent = load_lib_symbol(lib_path, ext[1])
    merged = [Sym("symbol"), name]
    own_props = {p[1]: p for p in find(sym, "property")}
    for c in parent[2:]:
        if isinstance(c, list) and c[0] == "property" and c[1] in own_props:
            merged.append(own_props.pop(c[1]))
        elif isinstance(c, list) and c[0] == "symbol":
            merged.append([Sym("symbol"), c[1].replace(parent[1], name, 1)] + c[2:])
        else:
            merged.append(c)
    merged[2:2] = []
    for p in own_props.values():
        merged.append(p)
    for c in sym[2:]:
        if isinstance(c, list) and c[0] not in ("property", "extends"):
            merged.append(c)
    return merged


def symbol_pins(sym):
    """[(unit, number, name, type, x, y, angle, length)] for a flattened lib symbol."""
    pins = []
    for sub in find(sym, "symbol"):
        m = re.search(r"_(\d+)_(\d+)$", sub[1])
        unit = int(m.group(1)) if m else 0
        if m and int(m.group(2)) > 1:  # skip De Morgan alternate body styles
            continue
        for p in find(sub, "pin"):
            at = find1(p, "at")
            num = find1(p, "number")[1]
            nm = find1(p, "name")[1]
            ln = float(find1(p, "length")[1])
            pins.append((unit, num, nm, str(p[1]), float(at[1]), float(at[2]),
                         float(at[3]) if len(at) > 3 else 0.0, ln))
    return pins
