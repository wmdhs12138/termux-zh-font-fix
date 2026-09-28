"""第 3 步：让字形与 Termux 的 TerminalRenderer 严丝合缝（前两步的产物在 Termux 里仍有这些问题）。

1. 行高：总高 1430，全部放进 ascent/descent（1090/-340）、lineGap 为 0。
   TerminalRenderer 把 leading 整块放在行底，lineGap 非 0 时文字会贴着行顶。
2. 制表符 / 方块元素 / Powerline 分隔符纵向拉伸铺满行高，上下各多出 OVERLAP。
   Termux 行高是 ceil() 取整的，字形只"刚好铺满"也会在行与行之间留下亚像素缝。
3. advance 对齐 Termux 的 wcwidth（见 termux_wcwidth.py），不一致就会被整字横向缩放：
   - wcwidth=1 却按 2 格合入的半角片假名 / 半角符号 / 谚文中终声 → 收窄到单格
   - wcwidth=2 却只有单格字形的 emoji（⏰⬜☕⚡🎵🎶💩🔒🤖）→ 删映射，交给系统彩色 emoji
   - 组合用浊点 / 声调符号（wcwidth=0）→ advance 归零
4. 补齐常用符号区里缺的 wcwidth=1 字形（✔✘★☆※℃①Ⅰ↩➜⌥⇧⏎ …），DejaVu Sans Mono 优先。
5. 补 CJK 边角区（谚文兼容字母、注音扩展、IDS、竖排 / 小写变体、扩展 B+）：取系统
   Noto Sans CJK SC（与更纱同为思源黑体字形），缩放和居中与第 1 步相同；
   康熙部首、兼容表意补充按 NFKC 直接复用已有字形。
"""
import os
import unicodedata

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont

from step1_merge_cjk import MARGIN as CJK_MARGIN, SCALE as CJK_SCALE
from termux_wcwidth import wcwidth

CELL = 600
ASC, DESC = 1090, -340      # 行高 = ASC - DESC = 1430；想调行距改这里
OVERLAP = 20                # 铺满类字形上下越界量，盖住 Termux 行高 ceil() 取整留下的缝
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


def add_cjk_extras(t, sys_cjk):
    if not os.path.exists(sys_cjk):
        return None
    sc = next(f for f in TTCollection(sys_cjk, lazy=True).fonts if "SC" in f["name"].getDebugName(4))
    cm, gs = sc.getBestCmap(), sc.getGlyphSet()
    m = (CJK_SCALE, 0, 0, CJK_SCALE, CJK_MARGIN, 0)
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


def run(in_path, out_path, symbol_sources, sys_cjk, timestamp):
    """symbol_sources：[(标签, TTFont), ...] 按优先级；sys_cjk：系统 Noto Sans CJK 的 ttc 路径；
    timestamp：写入 head.modified 的固定值，让同样的输入构建出逐字节相同的字体"""
    t = Target(in_path)
    fix_metrics(t)
    box, pl = fix_cell_fillers(t)
    narrowed, dropped, zeroed = fix_widths(t)
    symbols = add_symbols(t, symbol_sources)
    extras = add_cjk_extras(t, sys_cjk)
    aliases = add_nfkc_aliases(t)

    for tb in t.font["cmap"].tables:
        tb.cmap = dict(sorted(tb.cmap.items()))
    t.font.recalcTimestamp = False
    t.font["head"].modified = timestamp
    t.font.save(out_path)
    return dict(box=box, powerline=pl, narrowed=narrowed, dropped=dropped, zeroed=zeroed,
                symbols=symbols, cjk_extras=extras, nfkc_aliases=aliases)


def audit(path):
    """返回 advance 与 Termux wcwidth 不一致的码位"""
    t = Target(path)
    bad = []
    for cp, name in t.cmap.items():
        if cp < 0x20 or 0x300 <= cp <= 0x36F:
            continue
        w, adv = wcwidth(cp), t.hmtx[name][0]
        if (w == 0 and adv) or (w and abs(adv - w * CELL) > 6):
            bad.append(cp)
    return bad
