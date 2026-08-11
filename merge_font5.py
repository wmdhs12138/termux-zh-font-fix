"""混合字体 v5：v4 + CJK 缩至 1.1 倍 + 居中留白（字距）——坐标取整版"""
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.recordingPen import RecordingPen

src = TTFont("SauceCodeProNerdFontMono-Regular.ttf")
cjk = TTFont("sarasa/SarasaTermSC-Regular.ttf")

cjk_ranges = [
    (0x1100, 0x11FF), (0x2E80, 0x2EFF), (0x3000, 0x303F), (0x3040, 0x30FF),
    (0x3100, 0x312F), (0x31C0, 0x31EF), (0x3200, 0x32FF), (0x3300, 0x33FF),
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xA000, 0xA4CF), (0xAC00, 0xD7AF),
    (0xF900, 0xFAFF), (0xFE30, 0xFE4F), (0xFF00, 0xFFEF),
]
def in_ranges(cp):
    return any(lo <= cp <= hi for lo, hi in cjk_ranges)

cjk_cmap = cjk.getBestCmap()
src_cmap = src.getBestCmap()
want = [(cp, cjk_cmap[cp]) for cp in sorted(cjk_cmap) if in_ranges(cp) and cp not in src_cmap]

src_glyf = src["glyf"]
cjk_glyf = cjk["glyf"]
cjk_hmtx = cjk["hmtx"]
hmtx = src["hmtx"]

SCALE = 1.1
NEW_ADVANCE = 1200
LSB = (NEW_ADVANCE - int(1000 * SCALE)) // 2  # = 50

def round_coords(rec):
    """把 RecordingPen 的坐标全部取整"""
    out = []
    for op, args in rec.value:
        if not args:
            out.append((op, args))
        elif isinstance(args[0], tuple):  # 点列表
            out.append((op, tuple((round(x), round(y)) for x, y in args)))
        else:
            out.append((op, args))
    return out

name_map = {gname: f"cjk{cp:04X}" for cp, gname in want}
for gname, newname in name_map.items():
    rec = RecordingPen()
    transform = TransformPen(rec, (SCALE, 0, 0, SCALE, 0, 0))
    cjk_glyf[gname].draw(transform, cjk_glyf)
    pen = TTGlyphPen(None)
    for op, args in round_coords(rec):
        getattr(pen, op)(*args)
    src_glyf[newname] = pen.glyph()
    hmtx[newname] = (NEW_ADVANCE, LSB)

for table in src["cmap"].tables:
    if table.isUnicode():
        for cp, gname in want:
            table.cmap[cp] = name_map[gname]
        table.cmap = {k: v for k, v in sorted(table.cmap.items())}

LINEGAP = 250
h = src["hhea"]
h.ascent, h.descent, h.lineGap = 965, -215, LINEGAP
o = src["OS/2"]
o.sTypoAscender, o.sTypoDescender, o.sTypoLineGap = 965, -215, LINEGAP
o.usWinAscent, o.usWinDescent = 965, 215
for bit in [0, 1, 2, 3, 4, 5, 6, 7, 44, 45, 46, 47, 48, 49, 50, 51]:
    o.ulUnicodeRange1 |= (1 << bit) if bit < 32 else 0
    o.ulUnicodeRange2 |= (1 << (bit - 32)) if bit >= 32 else 0

# 手动设 hhea 整数度量（Android 渲染只用 ascent/descent/lineGap）
h.advanceWidthMax = 1200
h.minLeftSideBearing = 0
h.minRightSideBearing = 0
h.xMaxExtent = 1300
# OS/2 其余字段手动保持整数，无需 recalc

out = "SourceCodeProNerdMono-CJK5.ttf"
src.save(out)
print("✅ v5 已保存:", out, "| SCALE=1.1 LSB=50 → 字间隙 100units（8.3%）")

from fontTools.pens.boundsPen import BoundsPen
v = TTFont(out)
cm = v.getBestCmap()
glyf, hmtx2 = v["glyf"], v["hmtx"]
for cp, name in [(0x4E2D,"中"), (0x6587,"文")]:
    g = cm[cp]
    pen = BoundsPen(glyf)
    glyf[g].draw(pen, glyf)
    aw, _ = hmtx2[g]
    b = pen.bounds
    hh = b[3]-b[1] if b else 0
    print(f"  U+{cp:04X} {name}: advance={aw} 宽={b[2]-b[0]:.0f} 高={hh:.0f} 格数={aw/600:.2f} 左右留白={LSB}")
