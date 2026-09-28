"""混合字体 v9：在 v8 基础上修正 Termux 渲染层暴露出的几类问题。

1. 行高 1430 不变，但把 lineGap 250 平分进 ascent/descent（965/-215 → 1090/-340）。
   Termux 的 TerminalRenderer 把 leading 整块放在行底，v8 的文字贴着行顶，
   选区、背景色行、光标块下能看出文字偏上。
2. 制表符 / 方块元素 / Powerline 分隔符纵向拉伸，铺满新行高，上下各多出 OVERLAP。
   v8 改了行高却没动这些字形：│ █ 只有 1400 高（行高 1430），加上 Termux 对行高 ceil() 取整，
   31px 字号下行与行之间断开约 1.6px；Powerline 箭头按原 1257 行高设计，比色块矮一截。
3. CJK 字形整体右移 CJK_SHIFT，恢复 v5 设计的左右各 50 留白。
   v7 把 lsb 改成真实 xMin 时，原先靠 lsb=50 实现的平移也一起没了，中文在 2 格里偏左。
4. advance 与 Termux 的 wcwidth 对齐（表从 NewTermux 的 WcWidth.<clinit> 字节码解出，
   存于 termux_wcwidth.json）。advance ≠ wcwidth×600 时 Termux 会整段横向缩放：
   - wcwidth=1 却按 1200 合入的半角片假名/半角符号/谚文中终声 → 收窄到单格
   - wcwidth=2 的 emoji 只有单格字形（⏰⬜☕⚡🎵🎶💩🔒🤖）→ 删映射，交给系统彩色 emoji
   - 组合用浊点/声调符号（wcwidth=0）→ advance 归零
5. 补常用符号区（✔✘★☆※℃①Ⅰ↩➜⌥⇧⏎ …）里缺的 wcwidth=1 字形，DejaVu Sans Mono 优先。
6. 补 CJK 边角区（谚文兼容字母、注音扩展、IDS、竖排/小写变体、扩展 B+）：取系统
   Noto Sans CJK SC（与更纱同为思源黑体字形），处理同 merge_font7；
   康熙部首、兼容表意补充按 NFKC 直接复用已有字形。

用法：python3 patch_v9.py   （需同目录有 SourceCodeProNerdMono-CJK8.ttf）
"""
import bisect
import json
import os
import sys
import unicodedata
import zipfile
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont

import patch_symbols8 as p8

HERE = Path(__file__).resolve().parent
V8 = HERE / "SourceCodeProNerdMono-CJK8.ttf"
OUT = HERE / "SourceCodeProNerdMono-CJK9.ttf"
WCWIDTH = HERE / "termux_wcwidth.json"
SYS_CJK = "/system/fonts/NotoSansCJK-Regular.ttc"

CELL = 600
ASC, DESC = 1090, -340      # 行高仍是 1430，只是 lineGap 挪进来让文字居中
OVERLAP = 20                # 铺满类字形上下越界量，盖住 Termux 行高 ceil() 取整留下的缝
CJK_SCALE = 1.1
CJK_SHIFT = 50              # 1.1× 后 em 框宽 1100，右移 50 居中于 1200
SYM_W, SYM_H = 560, 820     # 补入符号的墨迹上限（单格）
REF_CAP = 656               # SCP 的 H 高，补入符号按源字体大写高度对齐到它

BOX_SRC = (-400, 1000)      # SCP 制表符/方块元素的设计纵向范围（已含重叠）
PL_SRC = (-273, 984)        # Powerline 按原 SauceCodePro 行高设计

SYMBOL_BLOCKS = [
    (0x2010, 0x2027), (0x2030, 0x205E), (0x20A0, 0x20C0), (0x2100, 0x218B),
    (0x2190, 0x23FF), (0x2400, 0x244A), (0x2460, 0x24FF), (0x25A0, 0x27BF),
    (0x27C0, 0x27FF), (0x2900, 0x2AFF), (0x2B00, 0x2BFF),
]
CJK_EXTRA_BLOCKS = [
    (0x2FF0, 0x2FFF), (0x3130, 0x318F), (0x3190, 0x319F), (0x31A0, 0x31BF),
    (0x31F0, 0x31FF), (0xFE10, 0xFE1F), (0xFE50, 0xFE6F), (0x20000, 0x3FFFD),
]
NFKC_ALIAS_BLOCKS = [(0x2F00, 0x2FD5), (0x2F800, 0x2FA1D)]

# ---- Termux wcwidth（com.termux.terminal.WcWidth.width 的移植） ----
_ZERO, _WIDE = json.loads(WCWIDTH.read_text())
_ZERO_LO = [a for a, _ in _ZERO]
_WIDE_LO = [a for a, _ in _WIDE]


def _intable(table, starts, cp):
    i = bisect.bisect_right(starts, cp) - 1
    return i >= 0 and cp <= table[i][1]


def wcwidth(cp):
    if (cp == 0 or cp == 0x034F or 0x200B <= cp <= 0x200F or cp in (0x2028, 0x2029)
            or 0x202A <= cp <= 0x202E or 0x2060 <= cp <= 0x2063):
        return 0
    if cp < 32 or 0x7F <= cp < 0xA0:
        return 0
    if _intable(_ZERO, _ZERO_LO, cp):
        return 0
    return 2 if _intable(_WIDE, _WIDE_LO, cp) else 1


# ---- 字形工具 ----
def record(glyphset, name, m):
    rec = DecomposingRecordingPen(glyphset)
    glyphset[name].draw(rec)
    out = RecordingPen()
    rec.replay(TransformPen(out, m))
    return out


def bounds(rec):
    bp = BoundsPen(None)
    rec.replay(bp)
    return bp.bounds


def to_tt(rec, cubic=False):
    pen = TTGlyphPen(None)
    rec.replay(Cu2QuPen(pen, max_err=1.0, reverse_direction=True) if cubic else pen)
    return pen.glyph()


class Target:
    def __init__(self, path):
        self.font = TTFont(path)
        self.glyf = self.font["glyf"]
        self.hmtx = self.font["hmtx"]
        self.gs = self.font.getGlyphSet()
        self.cmap = dict(self.font.getBestCmap())

    def put(self, name, glyph, adv):
        self.glyf[name] = glyph
        glyph.recalcBounds(self.glyf)
        self.hmtx[name] = (adv, getattr(glyph, "xMin", 0))

    def redraw(self, name, m, adv=None):
        self.put(name, to_tt(record(self.gs, name, m)), self.hmtx[name][0] if adv is None else adv)

    def ink(self, name):
        return bounds(record(self.gs, name, (1, 0, 0, 1, 0, 0)))

    def map(self, cp, name):
        self.cmap[cp] = name
        for t in self.font["cmap"].tables:
            if t.isUnicode() and (t.format == 12 or cp <= 0xFFFF):
                t.cmap[cp] = name

    def unmap(self, cp):
        self.cmap.pop(cp, None)
        for t in self.font["cmap"].tables:
            t.cmap.pop(cp, None)


def stretch_matrix(src_lo, src_hi):
    """把按 [src_lo, src_hi] 设计的铺满类字形线性映射到 [DESC-OVERLAP, ASC+OVERLAP]"""
    k = (ASC - DESC + 2 * OVERLAP) / (src_hi - src_lo)
    return (1, 0, 0, k, 0, DESC - OVERLAP - src_lo * k)


def fix_metrics(t):
    h, o = t.font["hhea"], t.font["OS/2"]
    h.ascent, h.descent, h.lineGap = ASC, DESC, 0
    o.sTypoAscender, o.sTypoDescender, o.sTypoLineGap = ASC, DESC, 0
    o.usWinAscent, o.usWinDescent = ASC + OVERLAP, -DESC + OVERLAP


def fix_cell_fillers(t):
    names = set()
    box = [c for c in list(range(0x2500, 0x25A0)) + [0x2320, 0x2321] if c in t.cmap]
    m = stretch_matrix(*BOX_SRC)
    for cp in box:
        if t.cmap[cp] not in names:
            names.add(t.cmap[cp])
            t.redraw(t.cmap[cp], m)
    pl = 0
    m = stretch_matrix(*PL_SRC)
    for cp in range(0xE0B0, 0xE0D8):
        name = t.cmap.get(cp)
        b = name and t.ink(name)
        if b and b[3] - b[1] >= 1200 and name not in names:  # 只拉满高分隔符，跳过小图标
            names.add(name)
            t.redraw(name, m)
            pl += 1
    return len(box), pl


def shift_cjk(t):
    n = 0
    for name in t.font.getGlyphOrder():
        if name.startswith("cjk"):
            g = t.glyf[name]
            if g.numberOfContours > 0:
                g.coordinates.translate((CJK_SHIFT, 0))
                g.recalcBounds(t.glyf)
                t.hmtx[name] = (t.hmtx[name][0], g.xMin)
                n += 1
    return n


def fix_widths(t):
    narrowed, dropped, zeroed = [], [], []
    for cp, name in sorted(t.cmap.items()):
        if cp < 0x20:
            continue
        w, adv = wcwidth(cp), t.hmtx[name][0]
        if w == 1 and adv == 2 * CELL:
            b = t.ink(name)
            if b:
                s = min(1.0, SYM_W / (b[2] - b[0]))
                cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
                t.redraw(name, (s, 0, 0, s, CELL / 2 - cx * s, cy - cy * s), CELL)
            else:
                t.hmtx[name] = (CELL, 0)
            narrowed.append(cp)
        elif w == 2 and adv == CELL:
            t.unmap(cp)
            dropped.append(cp)
        elif w == 0 and adv and not 0x300 <= cp <= 0x36F:
            t.hmtx[name] = (0, t.hmtx[name][1])
            zeroed.append(cp)
    return narrowed, dropped, zeroed


def symbol_sources():
    cache = p8.CACHE
    chain = [(label, f) for label, f in p8.ensure_sources()]
    mono = cache / "DejaVuSansMono.ttf"
    if not mono.exists():
        with zipfile.ZipFile(cache / "dejavu-fonts-ttf-2.37.zip") as z:
            mono.write_bytes(z.read(next(n for n in z.namelist() if n.endswith("/DejaVuSansMono.ttf"))))
    chain.insert(0, ("DejaVuSansMono", TTFont(mono)))
    return chain


def cap_scale(src):
    upem = src["head"].unitsPerEm
    h = src.getBestCmap().get(ord("H"))
    cap = bounds(record(src.getGlyphSet(), h, (1, 0, 0, 1, 0, 0)))[3] if h else 0.7 * upem
    return REF_CAP / cap


def add_symbols(t, chain):
    srcs = [(label, f, f.getBestCmap(), f.getGlyphSet(), cap_scale(f), "CFF " in f) for label, f in chain]
    added = {}
    for lo, hi in SYMBOL_BLOCKS:
        for cp in range(lo, hi + 1):
            if cp in t.cmap or wcwidth(cp) != 1 or unicodedata.category(chr(cp)) in ("Cn", "Zs", "Cf"):
                continue
            hit = next((s for s in srcs if cp in s[2]), None)
            if not hit:
                continue
            label, _, cm, gs, k, cubic = hit
            b = bounds(record(gs, cm[cp], (k, 0, 0, k, 0, 0)))
            if not b:
                continue
            w, h = b[2] - b[0], b[3] - b[1]
            s = k * min(1.0, SYM_W / w if w else 1.0, SYM_H / h if h else 1.0)
            b = bounds(record(gs, cm[cp], (s, 0, 0, s, 0, 0)))
            dx = (CELL - (b[2] - b[0])) / 2 - b[0]
            name = f"sym{cp:04X}"
            t.put(name, to_tt(record(gs, cm[cp], (s, 0, 0, s, dx, 0)), cubic), CELL)
            t.map(cp, name)
            added.setdefault(label, []).append(cp)
    return added


def add_cjk_extras(t):
    if not os.path.exists(SYS_CJK):
        print(f"  跳过 CJK 补字：没有 {SYS_CJK}")
        return []
    sc = next(f for f in TTCollection(SYS_CJK, lazy=True).fonts if "SC" in f["name"].getDebugName(4))
    cm, gs = sc.getBestCmap(), sc.getGlyphSet()
    m = (CJK_SCALE, 0, 0, CJK_SCALE, CJK_SHIFT, 0)
    added = []
    for lo, hi in CJK_EXTRA_BLOCKS:
        for cp in range(lo, hi + 1):
            if cp in cm and cp not in t.cmap and wcwidth(cp) == 2:
                name = f"cjk{cp:04X}"
                t.put(name, to_tt(record(gs, cm[cp], m), cubic=True), 2 * CELL)
                t.map(cp, name)
                added.append(cp)
    return added


def add_nfkc_aliases(t):
    n = 0
    for lo, hi in NFKC_ALIAS_BLOCKS:
        for cp in range(lo, hi + 1):
            s = unicodedata.normalize("NFKC", chr(cp))
            if cp not in t.cmap and len(s) == 1 and s != chr(cp) and ord(s) in t.cmap:
                t.map(cp, t.cmap[ord(s)])
                n += 1
    return n


def audit(t):
    bad = []
    for cp, name in t.cmap.items():
        if cp < 0x20 or 0x300 <= cp <= 0x36F:
            continue
        w, adv = wcwidth(cp), t.hmtx[name][0]
        if (w == 0 and adv) or (w and abs(adv - w * CELL) > 6):
            bad.append(cp)
    return bad


def main():
    if not V8.exists():
        sys.exit(f"缺 {V8.name}——请先跑 patch_symbols8.py（或从仓库取成品）")
    t = Target(V8)
    print("准备源字体...")
    chain = symbol_sources()

    fix_metrics(t)
    box, pl = fix_cell_fillers(t)
    print(f"行高度量 → ascent {ASC} / descent {DESC} / lineGap 0；拉伸制表/方块 {box} 个、Powerline {pl} 个")
    print(f"CJK 右移 {CJK_SHIFT}：{shift_cjk(t)} 个字形")

    narrowed, dropped, zeroed = fix_widths(t)
    print(f"收窄为单格 {len(narrowed)} 个：{''.join(chr(c) for c in narrowed[:40])}…")
    print(f"去掉单格 emoji 映射 {len(dropped)} 个：{''.join(chr(c) for c in dropped)}")
    print(f"组合符号 advance 归零 {len(zeroed)} 个：{' '.join(f'U+{c:04X}' for c in zeroed)}")

    added = add_symbols(t, chain)
    for label, cps in added.items():
        print(f"补符号 {len(cps):>4} 个 ← {label}: {''.join(chr(c) for c in cps[:50])}{'…' if len(cps) > 50 else ''}")
    extras = add_cjk_extras(t)
    print(f"补 CJK 边角字 {len(extras)} 个 ← Noto Sans CJK SC")
    print(f"康熙部首/兼容补充按 NFKC 复用 {add_nfkc_aliases(t)} 个")

    for tb in t.font["cmap"].tables:
        tb.cmap = dict(sorted(tb.cmap.items()))
    t.font.save(OUT)

    bad = audit(Target(OUT))
    print(f"v9 已保存: {OUT.name} | 字形 {len(t.font.getGlyphOrder())} | {OUT.stat().st_size / 1e6:.1f}MB")
    print("宽度审计:", "全部与 Termux wcwidth 一致" if not bad else f"仍有 {len(bad)} 个不一致: {bad[:20]}")


if __name__ == "__main__":
    main()
