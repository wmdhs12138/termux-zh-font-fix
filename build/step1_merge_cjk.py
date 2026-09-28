"""第 1 步：Source Code Pro Nerd Mono（拉丁 / Nerd 图标）+ 更纱 Term SC（CJK）。

Termux 的 TerminalRenderer 会量每个字的实际宽度，和 wcwidth 期望格数差 >1% 就横向缩放——
CJK 字宽只要不是恰好 2×X 宽（2×600），中文就被拉扁。所以只补 SCP 没有的 CJK 码位，并且：
  - 字形等比放大 SCALE 倍，advance 精确设为 ADVANCE（= 2×600）
  - 放大后 em 框宽 1100，整体右移 MARGIN 居中于 1200，左右各留 50
  - lsb 必须等于字形真实 xMin：FreeType 按 hmtx.lsb 定位绘制起点，填错会把窄标点推到格子最左
行高、半角字收窄、符号补全等与渲染器对齐的处理都在第 3 步。
"""
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

SCALE = 1.1
ADVANCE = 1200
MARGIN = (ADVANCE - round(1000 * SCALE)) // 2  # 50

CJK_RANGES = [
    (0x1100, 0x11FF), (0x2E80, 0x2EFF), (0x3000, 0x303F), (0x3040, 0x30FF),
    (0x3100, 0x312F), (0x31C0, 0x31EF), (0x3200, 0x32FF), (0x3300, 0x33FF),
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xA000, 0xA4CF), (0xAC00, 0xD7AF),
    (0xF900, 0xFAFF), (0xFE30, 0xFE4F), (0xFF00, 0xFFEF),
]
# OS/2 ulUnicodeRange 里要声明的位（CJK 相关区块）
UNICODE_RANGE_BITS = [0, 1, 2, 3, 4, 5, 6, 7, 44, 45, 46, 47, 48, 49, 50, 51]


def in_cjk_ranges(cp):
    return any(lo <= cp <= hi for lo, hi in CJK_RANGES)


def round_coords(rec):
    """把 RecordingPen 记录的点坐标全部取整"""
    out = []
    for op, args in rec.value:
        if args and isinstance(args[0], tuple):
            out.append((op, tuple((round(x), round(y)) for x, y in args)))
        else:
            out.append((op, args))
    return out


def run(scp_path, sarasa_path, out_path):
    font = TTFont(scp_path)
    cjk = TTFont(sarasa_path)
    font_cmap, cjk_cmap = font.getBestCmap(), cjk.getBestCmap()
    glyf, hmtx, cjk_glyf = font["glyf"], font["hmtx"], cjk["glyf"]

    want = [(cp, cjk_cmap[cp]) for cp in sorted(cjk_cmap) if in_cjk_ranges(cp) and cp not in font_cmap]
    new_name = {gname: f"cjk{cp:04X}" for cp, gname in want}  # 多个码位共用一个更纱字形时只合入一份
    for gname, name in new_name.items():
        rec = RecordingPen()
        cjk_glyf[gname].draw(TransformPen(rec, (SCALE, 0, 0, SCALE, 0, 0)), cjk_glyf)
        pen = TTGlyphPen(None)
        for op, args in round_coords(rec):
            getattr(pen, op)(*args)
        glyph = pen.glyph()
        glyph.coordinates.translate((MARGIN, 0))  # 取整之后再平移，避免浮点误差改变舍入
        glyph.recalcBounds(glyf)
        glyf[name] = glyph
        hmtx[name] = (ADVANCE, glyph.xMin if glyph.numberOfContours else MARGIN)

    for table in font["cmap"].tables:
        if table.isUnicode():
            for cp, gname in want:
                table.cmap[cp] = new_name[gname]
            table.cmap = dict(sorted(table.cmap.items()))

    os2 = font["OS/2"]
    for bit in UNICODE_RANGE_BITS:
        if bit < 32:
            os2.ulUnicodeRange1 |= 1 << bit
        else:
            os2.ulUnicodeRange2 |= 1 << (bit - 32)

    font.save(out_path)
    return len(new_name)
