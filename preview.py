"""按 Termux TerminalRenderer 的排版逻辑离线预览字体，免得每调一次参数都要重启 app。

模拟要点（与 termux-app 源码一致）：
  行高   = ceil(ascent - descent + lineGap)，基线 = 行顶 + |ceil(ascent)|，leading 落在行底
  列宽   = measureText("X")
  字宽 ≠ wcwidth×列宽（误差 >1%）时整字横向缩放到 wcwidth 格
  字体里没有的字按 cmap 走系统回退：Noto Sans CJK SC → Noto Symbols 子集；
  emoji 交给 NotoColorEmoji（COLRv1，Pillow 画不了，用黄色圆块占位，宽度按真实 advance）

用法：python3 preview.py 输出.png 字体A.ttf [字体B.ttf ...] [--size 31]
"""
import argparse
import math

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

from patch_v9 import wcwidth

BG, FG = (0, 0, 0), (220, 220, 220)
SAMPLE = [
    [("╭─ 生成中 · 5 轮 ─────────────╮", (90, 200, 220), None)],
    [("│ 模型/推理 openai · max      │", None, None)],
    [("│ 上下文/会话 64k/272k · 24%  │", None, None)],
    [("╰─────────────────────────────╯", (90, 200, 220), None)],
    [("选中行：中文 Mixed 文本 gjy。", (255, 255, 255), (60, 90, 160))],
    [("+ 新增 added line，括号（测试）", (200, 255, 200), (20, 70, 30))],
    [("█████▀▀▀▀▄▄▄▄░░▒▒▓▓██", (230, 160, 60), None)],
    [("█████▀▀▀▀▄▄▄▄░░▒▒▓▓██", (230, 160, 60), None)],
    [(" \ue0a0 main ", (0, 0, 0), (120, 180, 250)), ("\ue0b0", (120, 180, 250), (70, 70, 70)),
     (" ~/proj ", (255, 255, 255), (70, 70, 70)), ("\ue0b0", (70, 70, 70), None)],
    [("ｱｲｳｴｵ ｶﾀｶﾅ ﾃｽﾄ | ｡｢ok｣", None, None)],
    [("✔ done ✘ fail ★☆ ※ ①② ℃ Ⅳ", None, None)],
    [("➜ ↩ ⏎ ⌥⇧⌃ ◯◇ ⚡ ⏰ 🤖", None, None)],
    [("⽂档(康熙部首) 𠮷 ㅋㅋ 中文", None, None)],
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
        self.col = self.hmtx[self.cmap[ord("X")]][0] * size / upem
        self.pil = ImageFont.truetype(path, size)

    def advance(self, ch):
        return self.hmtx[self.cmap[ord(ch)]][0] * self.size / self.upem


class Fallback:
    CHAIN = [("/system/fonts/NotoSansCJK-Regular.ttc", 2),
             ("/system/fonts/NotoSansSymbols-Regular-Subsetted.ttf", 0),
             ("/system/fonts/NotoSansSymbols-Regular-Subsetted2.ttf", 0)]
    EMOJI = "/system/fonts/NotoColorEmoji.ttf"

    def __init__(self, size):
        self.size = size
        self.chain = []
        for path, idx in self.CHAIN:
            tt = TTFont(path, fontNumber=idx, lazy=True)
            self.chain.append((tt.getBestCmap(), ImageFont.truetype(path, size, index=idx)))
        emoji = TTFont(self.EMOJI, lazy=True)
        self.emoji_cmap = emoji.getBestCmap()
        self.emoji_adv = emoji["hmtx"][self.emoji_cmap[0x1F600]][0] / emoji["head"].unitsPerEm * size

    def font_for(self, ch):
        if wcwidth(ord(ch)) == 2 and ord(ch) in self.emoji_cmap:
            return None
        return next((f for cm, f in self.chain if ord(ch) in cm), self.chain[0][1])


def glyph_image(face, fb, ch, fg, frac):
    """返回 (RGBA 图, 实测宽度, 字形原点在图中的 x)；frac 是列坐标的小数部分，保留亚像素定位"""
    pad = face.size
    font = face.pil if ord(ch) in face.cmap else fb.font_for(ch)
    w = face.advance(ch) if font is face.pil else (fb.emoji_adv if font is None else font.getlength(ch))
    img = Image.new("RGBA", (int(w) + 2 * pad, face.line + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if font is None:
        r = face.size * 0.45
        cx, cy = pad + frac + w / 2, pad + face.base - face.size * 0.35
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(250, 200, 60))
    else:
        d.text((pad + frac, pad + face.base), ch, font=font, fill=fg, anchor="ls")
    return img, w, pad


def render(path, size, cols=34):
    face, fb = Face(path, size), Fallback(size)
    W, H = int(cols * face.col) + 20, face.line * (len(SAMPLE) + 1) + 20
    im = Image.new("RGBA", (W, H), BG + (255,))
    top = 10 + face.line
    title = f"{path.split('/')[-1]}  line={face.line}px col={face.col:.1f}px"
    ImageDraw.Draw(im).text((10, 10), title, font=ImageFont.truetype(path, size * 0.6), fill=(150, 150, 150))
    for row in SAMPLE:
        x_col = 0
        for text, fg, bg in row:
            fg = fg or FG
            for ch in text:
                wc = wcwidth(ord(ch))
                if wc == 0:
                    continue
                x = 10 + x_col * face.col
                if bg:
                    ImageDraw.Draw(im).rectangle([x, top, x + wc * face.col - 1, top + face.line - 1], fill=bg)
                g, measured, pad = glyph_image(face, fb, ch, fg, x - int(x))
                if abs(measured / face.col - wc) > 0.01:
                    k = wc * face.col / measured
                    g = g.resize((max(1, round(g.width * k)), g.height), Image.LANCZOS)
                    pad = round(pad * k)
                im.alpha_composite(g, (int(x) - pad, top - (g.height - face.line) // 2))
                x_col += wc
        top += face.line
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("fonts", nargs="+")
    ap.add_argument("--size", type=int, default=31)
    a = ap.parse_args()
    ims = [render(p, a.size) for p in a.fonts]
    out = Image.new("RGB", (sum(i.width for i in ims) + 10 * (len(ims) - 1), max(i.height for i in ims)), (40, 40, 40))
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.width + 10
    out.save(a.out)
    print("saved", a.out)


if __name__ == "__main__":
    main()
