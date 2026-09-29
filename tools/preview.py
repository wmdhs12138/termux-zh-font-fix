"""按 Termux TerminalRenderer 的排版逻辑离线渲染字体，调参时不用反复重启 app；README 的演示图也由它生成。

模拟要点（与 termux-app 源码一致）：
  行高 = ceil(ascent - descent + lineGap)，基线 = 行顶 + |ceil(ascent)|，leading 落在行底
  列宽 = measureText("X")；Android 默认开 hinting，每个字形的 advance 各自取整到整像素
  （本字体的双格字形经 GSUB 拆成 单格字形 + 单格空白，宽度按两个取整后的单格算）
  字宽 ≠ wcwidth×列宽（误差 >1%）时整字横向缩放到 wcwidth 格
这里只是模拟；要看真机渲染器的实际结果（方块缝隙、中文宽度），用 tools/android_check.py。
  字体里没有的字按 cmap 走系统回退：Noto Sans CJK SC → Noto Symbols 子集；
  emoji 交给 NotoColorEmoji（COLRv1，Pillow 画不了，用黄色圆块占位，宽度按真实 advance）

用法：python3 tools/preview.py 输出.png 字体A.ttf [字体B.ttf ...] [--labels 标签A,标签B] [--size 31]
多个字体上下排列；Termux 不装字体时用的是 /system/fonts/DroidSansMono.ttf。
需要 Pillow（pip install pillow）。
"""
import argparse
import math
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "build"))
from step3_termux_fit import CELL, split_glyphs  # noqa: E402
from termux_wcwidth import wcwidth  # noqa: E402

COLS = 40
BG, FG, DIM = (0, 0, 0), (215, 215, 215), (130, 130, 130)
CYAN, GREEN, RED, ORANGE = (95, 200, 220), (120, 210, 120), (235, 110, 110), (230, 160, 60)
MAGENTA, BLUE, GREY = (205, 130, 225), (120, 180, 250), (70, 70, 70)
FALLBACK_CJK = "/system/fonts/NotoSansCJK-Regular.ttc"


def width(text):
    return sum(wcwidth(ord(c)) for c in text)


def boxed(lines, title):
    """圆角方框；每行是 [(文字, 前景色), ...]"""
    top = f"╭─ {title} "
    rows = [[(top + "─" * (COLS - 1 - width(top)) + "╮", CYAN)]]
    for segs in lines:
        used = sum(width(t) for t, _ in segs)
        rows.append([("│ ", CYAN), *segs, (" " * (COLS - 3 - used), None), ("│", CYAN)])
    rows.append([("╰" + "─" * (COLS - 2) + "╯", CYAN)])
    return rows


def filled(text, fg, bg, indent="", indent_fg=None):
    """整行铺底色（diff、选区）"""
    return [(indent, indent_fg), (text + " " * (COLS - width(indent + text)), fg, bg)]


SAMPLE = [
    *boxed([[("> 帮我把 Termux 的中文字体修一下", FG)],
            [("  顺便把演示图也更新了", FG)]], "✻ 思考中… (12s · esc 中断)"),
    [("⏺ ", GREEN), ("读取 README.md（第 1–120 行）", FG)],
    [("  ⎿  ", DIM), ("已读取，发现 4 处问题", DIM)],
    [("⏺ ", GREEN), ("修改 install.sh：原子替换字体", FG)],
    filled('- cp "$src" "$DEST"', (255, 200, 200), (90, 25, 25), "  ⎿  ", DIM),
    filled('+ mv -f "$tmp" "$DEST"  # 防闪退', (200, 255, 200), (20, 70, 30), "     "),
    [("def ", MAGENTA), ("渲染", ORANGE), ("(文字: ", FG), ("str", CYAN), (") -> ", FG), ("None", CYAN), (":", FG)],
    [("✔", GREEN), (" 通过 3/3  ", FG), ("✘", RED), (" 失败 0  ★ ① ※ ℃ ↩ ⏎ ⌥", FG)],
    [("进度 ", FG), ("██████████▓▒░", ORANGE), ("░░░░", GREY), (" 62%", FG)],
    [("半角ｱｲｳ 全角ＡＢＣ 康熙⽂ 𠮷 ㅋㅋ", FG)],
    filled("选中的一行：中文 English 混排。", (255, 255, 255), (60, 90, 160)),
    [("  main ", (0, 0, 0), BLUE), ("", BLUE, GREY), (" ~/projects/字体 ", (255, 255, 255), GREY),
     ("", GREY), (" ❯", GREEN)],
    [("⏵⏵ accept edits on", MAGENTA), (" (shift+tab 切换)", DIM)],
]


class Face:
    def __init__(self, path, size):
        tt = TTFont(path, lazy=True)
        upem = tt["head"].unitsPerEm
        o, h = tt["OS/2"], tt["hhea"]
        if o.fsSelection & (1 << 7):
            asc, desc, gap = o.sTypoAscender, o.sTypoDescender, o.sTypoLineGap
        else:
            asc, desc, gap = h.ascent, h.descent, h.lineGap
        self.cmap = tt.getBestCmap()
        self.hmtx = tt["hmtx"]
        self.upem, self.size = upem, size
        self.line = math.ceil((asc - desc + gap) * size / upem)
        self.base = -math.ceil(-asc * size / upem)
        self.split = split_glyphs(tt)
        self.col = self.px(self.hmtx[self.cmap[ord("X")]][0])
        self.pil = ImageFont.truetype(path, size)

    def px(self, units):
        """advance 换算成像素并四舍五入到整数，与真机 hinting 后的结果一致"""
        return math.floor(units * self.size / self.upem + 0.5)

    def advance(self, ch):
        name = self.cmap[ord(ch)]
        return self.px(self.hmtx[name][0]) + (self.px(CELL) if name in self.split else 0)


class Fallback:
    CHAIN = [(FALLBACK_CJK, 2),
             ("/system/fonts/NotoSansSymbols-Regular-Subsetted.ttf", 0),
             ("/system/fonts/NotoSansSymbols-Regular-Subsetted2.ttf", 0)]
    EMOJI = "/system/fonts/NotoColorEmoji.ttf"

    def __init__(self, size):
        self.chain = []
        for path, idx in self.CHAIN:
            tt = TTFont(path, fontNumber=idx, lazy=True)
            self.chain.append((tt.getBestCmap(), ImageFont.truetype(path, size, index=idx)))
        emoji = TTFont(self.EMOJI, lazy=True)
        self.emoji_cmap = emoji.getBestCmap()
        self.emoji_adv = round(emoji["hmtx"][self.emoji_cmap[0x1F600]][0] / emoji["head"].unitsPerEm * size)

    def font_for(self, ch):
        if wcwidth(ord(ch)) == 2 and ord(ch) in self.emoji_cmap:
            return None
        return next((f for cm, f in self.chain if ord(ch) in cm), self.chain[0][1])


def glyph_image(face, fb, ch, fg, frac):
    """返回 (RGBA 图, 实测宽度, 字形原点在图中的 x)；frac 是列坐标的小数部分，保留亚像素定位"""
    pad = face.size
    font = face.pil if ord(ch) in face.cmap else fb.font_for(ch)
    w = face.advance(ch) if font is face.pil else (fb.emoji_adv if font is None else round(font.getlength(ch)))
    img = Image.new("RGBA", (int(w) + 2 * pad, face.line + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if font is None:
        r = face.size * 0.45
        cx, cy = pad + frac + w / 2, pad + face.base - face.size * 0.35
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(250, 200, 60))
    else:
        d.text((pad + frac, pad + face.base), ch, font=font, fill=fg, anchor="ls")
    return img, w, pad


def render(path, size, label):
    face, fb = Face(path, size), Fallback(size)
    title_font = ImageFont.truetype(FALLBACK_CJK, round(size * 0.6), index=2)
    W, H = int(COLS * face.col) + 20, face.line * (len(SAMPLE) + 1) + 20
    im = Image.new("RGBA", (W, H), BG + (255,))
    ImageDraw.Draw(im).text((10, 10), f"{label}  ·  行高 {face.line}px  列宽 {face.col:.1f}px",
                            font=title_font, fill=DIM)
    top = 10 + face.line
    for row in SAMPLE:
        x_col = 0
        for text, fg, *bg in row:
            bg = bg[0] if bg else None
            for ch in text:
                wc = wcwidth(ord(ch))
                if wc == 0:
                    continue
                x = 10 + x_col * face.col
                if bg:
                    ImageDraw.Draw(im).rectangle([x, top, x + wc * face.col - 1, top + face.line - 1], fill=bg)
                if ch != " ":
                    g, measured, pad = glyph_image(face, fb, ch, fg or FG, x - int(x))
                    if abs(measured / face.col - wc) > 0.01:
                        k = wc * face.col / measured
                        g = g.resize((max(1, round(g.width * k)), g.height), Image.LANCZOS)
                        pad = round(pad * k)
                    im.alpha_composite(g, (int(x) - pad, top - (g.height - face.line) // 2))
                x_col += wc
        top += face.line
    return im


def main():
    ap = argparse.ArgumentParser(description="按 Termux 排版逻辑离线渲染字体")
    ap.add_argument("out")
    ap.add_argument("fonts", nargs="+")
    ap.add_argument("--labels", help="逗号分隔，与字体一一对应（默认用文件名）")
    ap.add_argument("--size", type=int, default=31, help="字号 px（Termux 设置里的 fontsize，默认 31）")
    a = ap.parse_args()
    labels = a.labels.split(",") if a.labels else [Path(p).name for p in a.fonts]
    ims = [render(p, a.size, label) for p, label in zip(a.fonts, labels)]
    out = Image.new("RGB", (max(i.width for i in ims), sum(i.height for i in ims) + 6 * (len(ims) - 1)), (45, 45, 45))
    y = 0
    for i in ims:
        out.paste(i, (0, y))
        y += i.height + 6
    out.save(a.out)
    print("已保存", a.out)


if __name__ == "__main__":
    main()
