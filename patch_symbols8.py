"""混合字体 v8：在 v7 基础上补齐 UI 符号字形（杂项技术 / 杂项符号 / 箭头 / 几何区）。

背景：Source Code Pro Nerd 的 Nerd 补丁只加私有区图标（Powerline/FontAwesome/Material），
     不含 Unicode 符号区；v7 只并了 CJK 区，于是 Claude Code 的 ⏵⏵（accept edits 标记）、
     ⏸（plan 模式）、思考转圈 ✻✢✳✶✽、⎿（工具结果树）等全渲染成空框。
v8 从 Noto Sans Symbols 系列（+ DejaVu Sans 补箭头）取字形，参数与 v7 的 CJK 处理一致：
     advance = 600（恰好 1 格）、水平居中、lsb = 字形真实 xMin（见 v7 README 坑 2）。

用法：python3 patch_symbols8.py   （需先有同目录的 SourceCodeProNerdMono-CJK7.ttf）
源字体缺失时自动下载到 ~/.cache/symbols；个别字形若只有 Android 系统字体才有，
则从 /system/fonts 的 Noto 子集兜底，兜不到会跳过并告警。
"""
import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.varLib.instancer import instantiateVariableFont

HERE = Path(__file__).resolve().parent
CACHE = Path.home() / ".cache" / "symbols"
V7 = HERE / "SourceCodeProNerdMono-CJK7.ttf"
OUT = HERE / "SourceCodeProNerdMono-CJK8.ttf"

NOTO_S2_URL = "https://github.com/google/fonts/raw/main/ofl/notosanssymbols2/NotoSansSymbols2-Regular.ttf"
NOTO_S1_URL = "https://github.com/google/fonts/raw/main/ofl/notosanssymbols/NotoSansSymbols%5Bwght%5D.ttf"
DEJAVU_URL = "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip"

# 要补的码位（Claude Code UI + 终端常用）
NEED = [
    0x2717, 0x273B, 0x2722, 0x2731, 0x2733, 0x2736, 0x273D,  # ✗ 与思考转圈 ✻✢✱✳✶✽
    0x23BF, 0x23FA, 0x23F5, 0x23F8, 0x23F0,                  # ⎿ ⏺ ⏵ ⏸ ⏰
    0x2913, 0x21B3, 0x21E5, 0x21B5,                          # ⤓ ↳ ⇥ ↵
    0x2699, 0x26A0, 0x2318, 0x2B1C,                          # ⚙ ⚠ ⌘ ⬜
]

CELL = 600        # 单格 advance（= v7 拉丁字宽）
TARGET_W = 520    # 墨迹最大宽
TARGET_H = 640    # 墨迹最大高


def fetch(url, dest):
    dest = Path(dest)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ↓ 下载 {dest.name} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "termux-zh-font-fix"})
    with urllib.request.urlopen(req, timeout=300) as r:
        dest.write_bytes(r.read())
    return dest


def ensure_sources():
    """返回 (标签, TTFont) 源字体链，按优先级排列"""
    cache = CACHE
    s2 = fetch(NOTO_S2_URL, cache / "NotoSansSymbols2-Regular.ttf")
    s1 = fetch(NOTO_S1_URL, cache / "NotoSansSymbols[wght].ttf")
    dz = fetch(DEJAVU_URL, cache / "dejavu-fonts-ttf-2.37.zip")
    dejavu = cache / "DejaVuSans.ttf"
    if not dejavu.exists():
        with zipfile.ZipFile(dz) as z:
            name = next(n for n in z.namelist() if n.endswith("DejaVuSans.ttf"))
            dejavu.write_bytes(z.read(name))

    s1f = TTFont(s1)
    if "fvar" in s1f:
        instantiateVariableFont(s1f, {"wght": 400}, inplace=True)

    chain = [("NotoSymbols2", TTFont(s2)), ("NotoSymbols", s1f), ("DejaVuSans", TTFont(dejavu))]
    # Android 系统字体兜底（部分箭头/时钟字形只有这里才有）
    for label, path in (("sysNotoSub", "/system/fonts/NotoSansSymbols-Regular-Subsetted.ttf"),
                        ("sysNotoSub2", "/system/fonts/NotoSansSymbols-Regular-Subsetted2.ttf")):
        if os.path.exists(path):
            try:
                chain.append((label, TTFont(path)))
            except Exception as e:
                print(f"  跳过系统字体 {path}: {e}")
    return chain


def rec_bounds(rec):
    """从展平后的轮廓记录里求墨迹包围盒（不依赖 BoundsPen，避免复合字形报错）"""
    xs, ys = [], []
    for op, args in rec.value:
        if op == "addComponent":
            continue
        for a in args:
            if isinstance(a, tuple) and len(a) == 2 and all(isinstance(n, (int, float)) for n in a):
                xs.append(a[0]); ys.append(a[1])
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


def main():
    if not V7.exists():
        sys.exit(f"缺 {V7.name}——请先跑 merge_font7.py（或从仓库取成品）")

    tgt = TTFont(V7)
    tgt_upem = tgt["head"].unitsPerEm
    tgt_cmap = tgt.getBestCmap()
    tgt_glyf = tgt["glyf"]
    tgt_hmtx = tgt["hmtx"]

    print("准备源字体...")
    sources = ensure_sources()

    added, skipped = [], []
    for cp in NEED:
        if cp in tgt_cmap:
            skipped.append((cp, "v7 已有"))
            continue
        hit = next(((n, f) for n, f in sources if cp in f.getBestCmap()), None)
        if not hit:
            skipped.append((cp, "无源字体"))
            continue
        srcname, src = hit
        src_cmap = src.getBestCmap()
        src_glyf = src["glyf"]
        gname = src_cmap[cp]

        k = tgt_upem / src["head"].unitsPerEm
        b = rec_bounds(draw_scaled(src_glyf, gname, k, 0, 0))
        if not b:
            skipped.append((cp, "空白字形"))
            continue
        w, h = b[2] - b[0], b[3] - b[1]
        s = k * min(1.0, TARGET_W / w if w else 1.0, TARGET_H / h if h else 1.0)
        bb = rec_bounds(draw_scaled(src_glyf, gname, s, 0, 0))
        dx = (CELL - (bb[2] - bb[0])) / 2 - bb[0]      # 水平居中到单格
        rec = draw_scaled(src_glyf, gname, s, dx, 0)   # 竖直保持源字体基线

        newname = f"sym{cp:04X}"
        tgt_glyf[newname] = to_glyph(rec)
        tgt_hmtx[newname] = (CELL, int(round(rec_bounds(rec)[0])))
        added.append((cp, srcname))

    for table in tgt["cmap"].tables:
        if table.isUnicode():
            for cp, *_ in added:
                table.cmap[cp] = f"sym{cp:04X}"
            table.cmap = {k: v for k, v in sorted(table.cmap.items())}

    tgt.save(OUT)
    print(f"v8 已保存: {OUT.name} | 补入 {len(added)} 个字形")
    for cp, srcname in added:
        print(f"  U+{cp:04X} {chr(cp)}  ← {srcname}")
    if skipped:
        print("跳过:", ", ".join(f"{chr(c)} ({r})" for c, r in skipped))


if __name__ == "__main__":
    main()
