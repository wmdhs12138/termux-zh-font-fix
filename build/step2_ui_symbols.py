"""第 2 步：补 Claude Code 等 TUI 常用的 20 个 UI 符号。

Nerd 补丁只往私有区加图标，不含 Unicode 符号区，于是 ⏵⏵（accept edits）、⏸（plan 模式）、
思考转圈 ✻✢✳✶✽、工具结果树 ⎿ 等都会变成空框。这里按 NEED 逐个从源字体链里取字形：
等比缩放（不放大）到 TARGET_W×TARGET_H 以内 → 水平居中到单格 → advance = CELL。
（⏰⬜ 在 Termux 里是 2 格宽的 emoji，第 3 步会统一去掉映射交给系统彩色 emoji；
其余符号区的整块补全也在第 3 步。）
"""
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

NEED = [
    0x2717, 0x273B, 0x2722, 0x2731, 0x2733, 0x2736, 0x273D,  # ✗ 与思考转圈 ✻✢✱✳✶✽
    0x23BF, 0x23FA, 0x23F5, 0x23F8, 0x23F0,                  # ⎿ ⏺ ⏵ ⏸ ⏰
    0x2913, 0x21B3, 0x21E5, 0x21B5,                          # ⤓ ↳ ⇥ ↵
    0x2699, 0x26A0, 0x2318, 0x2B1C,                          # ⚙ ⚠ ⌘ ⬜
]

CELL = 600        # 单格 advance（= SCP 拉丁字宽）
TARGET_W = 520    # 墨迹最大宽
TARGET_H = 640    # 墨迹最大高


def rec_bounds(rec):
    """从展平后的轮廓记录里求墨迹包围盒（不依赖 BoundsPen，避免复合字形报错）"""
    xs, ys = [], []
    for op, args in rec.value:
        if op == "addComponent":
            continue
        for a in args:
            if isinstance(a, tuple) and len(a) == 2 and all(isinstance(n, (int, float)) for n in a):
                xs.append(a[0])
                ys.append(a[1])
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def draw_scaled(src_glyf, gname, scale, dx, dy):
    rec = RecordingPen()
    src_glyf[gname].draw(TransformPen(rec, (scale, 0, 0, scale, dx, dy)), src_glyf)
    return rec


def round_args(args):
    """args 是点列表（RecordingPen 记录格式）；逐点取整，None（隐含点）原样保留"""
    out = []
    for a in args:
        if isinstance(a, tuple) and len(a) == 2 and all(isinstance(n, (int, float)) for n in a):
            out.append((round(a[0]), round(a[1])))
        else:
            out.append(a)
    return tuple(out)


def to_glyph(rec):
    pen = TTGlyphPen(None)
    for op, args in rec.value:
        if op == "addComponent":
            continue
        getattr(pen, op)(*round_args(args))
    return pen.glyph()


def run(in_path, out_path, sources):
    """sources：[(标签, TTFont), ...]，按优先级排列"""
    font = TTFont(in_path)
    upem = font["head"].unitsPerEm
    font_cmap, glyf, hmtx = font.getBestCmap(), font["glyf"], font["hmtx"]

    added, skipped = [], []
    for cp in NEED:
        if cp in font_cmap:
            skipped.append((cp, "已有"))
            continue
        hit = next(((label, f) for label, f in sources if cp in f.getBestCmap()), None)
        if not hit:
            skipped.append((cp, "无源字体"))
            continue
        label, src = hit
        src_glyf, gname = src["glyf"], src.getBestCmap()[cp]

        k = upem / src["head"].unitsPerEm
        b = rec_bounds(draw_scaled(src_glyf, gname, k, 0, 0))
        if not b:
            skipped.append((cp, "空白字形"))
            continue
        w, h = b[2] - b[0], b[3] - b[1]
        s = k * min(1.0, TARGET_W / w if w else 1.0, TARGET_H / h if h else 1.0)
        bb = rec_bounds(draw_scaled(src_glyf, gname, s, 0, 0))
        dx = (CELL - (bb[2] - bb[0])) / 2 - bb[0]      # 水平居中到单格
        rec = draw_scaled(src_glyf, gname, s, dx, 0)   # 竖直保持源字体基线

        name = f"sym{cp:04X}"
        glyf[name] = to_glyph(rec)
        hmtx[name] = (CELL, int(round(rec_bounds(rec)[0])))
        added.append((cp, label))

    for table in font["cmap"].tables:
        if table.isUnicode():
            for cp, _ in added:
                table.cmap[cp] = f"sym{cp:04X}"
            table.cmap = dict(sorted(table.cmap.items()))

    font.save(out_path)
    return added, skipped
