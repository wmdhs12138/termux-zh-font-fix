"""从源字体构建成品：下载并校验源字体 → 三步流水线 → 宽度审计。

    python3 build/build.py              # 输出到仓库根目录的 SourceCodeProNerdMono-CJK.ttf
    python3 build/build.py -o 某处.ttf  # 调参试验时输出到别处，配合 tools/preview.py 对比

依赖 python3 + fonttools、p7zip（解更纱的 7z）；首次运行下载约 60MB，缓存在 ~/.cache/termux-zh-font-fix。
第 2、3 步有少量字形取自安卓系统字体（/system/fonts 下的 Noto Symbols 子集和 Noto Sans CJK），
换机型可能略有差别；不在安卓上时这些来源会被跳过。
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from fontTools.misc.timeTools import timestampFromString
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

import step1_merge_cjk
import step2_ui_symbols
import step3_termux_fit

ROOT = Path(__file__).resolve().parent.parent
PRODUCT = ROOT / "SourceCodeProNerdMono-CJK.ttf"
CACHE = Path.home() / ".cache" / "termux-zh-font-fix"

# 写进 head.modified 的固定时间（UTC）：同样的源字体和参数必然构建出逐字节相同的字体。发新版时改成当天。
FONT_TIMESTAMP = "Mon Sep 28 15:44:59 2026"

# 下载地址锁定到具体版本 / commit 并校验 sha256，上游更新不会悄悄改变构建结果
SOURCES = {
    "SourceCodePro.tar.xz": (
        "https://github.com/ryanoasis/nerd-fonts/releases/download/v3.5.0/SourceCodePro.tar.xz",
        "876deff02b4f21c4ba02da1dbf2c384e1d6113326ea777e7537d2a54029da3e6"),
    "SarasaTermSC-TTF-Unhinted-1.0.40.7z": (
        "https://github.com/be5invis/Sarasa-Gothic/releases/download/v1.0.40/SarasaTermSC-TTF-Unhinted-1.0.40.7z",
        "e63361966b01e91d6080009785c654922d95e7879f7e0a7db154fa5d35f64a7c"),
    "NotoSansSymbols2-Regular.ttf": (
        "https://raw.githubusercontent.com/google/fonts/7b6724ac7ececc713e9ba93af309f7520c9a80a3/"
        "ofl/notosanssymbols2/NotoSansSymbols2-Regular.ttf",
        "7d5fb73b7ca67a6798101741f5d280a3d016a56a197afcd4199dbb57b4b82a21"),
    "NotoSansSymbols[wght].ttf": (
        "https://raw.githubusercontent.com/google/fonts/caa8c83707a5797d62fd02f14301391986f21d75/"
        "ofl/notosanssymbols/NotoSansSymbols%5Bwght%5D.ttf",
        "f7e7e04b4a24b6c78893d50cbfd2b2f6cae49617ab047bfef668d252adb128f7"),
    "dejavu-fonts-ttf-2.37.zip": (
        "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip",
        "7576310b219e04159d35ff61dd4a4ec4cdba4f35c00e002a136f00e96a908b0a"),
}
SYS_FONTS = Path("/system/fonts")
SYS_SYMBOLS = ["NotoSansSymbols-Regular-Subsetted.ttf", "NotoSansSymbols-Regular-Subsetted2.ttf"]
SYS_CJK = SYS_FONTS / "NotoSansCJK-Regular.ttc"


def fetch(name):
    url, sha256 = SOURCES[name]
    path = CACHE / "src" / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"  下载 {name} ...")
        part = path.with_name(path.name + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "termux-zh-font-fix"})
        with urllib.request.urlopen(req, timeout=600) as r:
            part.write_bytes(r.read())
        part.rename(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != sha256:
        sys.exit(f"{path} 的 sha256 不符（{digest}）：删掉它重新下载；若上游确实换了文件，核对后再改 SOURCES")
    return path


def extract(archive, member):
    out = CACHE / "extracted" / member
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith(".tar.xz"):
        with tarfile.open(archive) as tf:
            out.write_bytes(tf.extractfile(member).read())
    elif archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            out.write_bytes(z.read(next(n for n in z.namelist() if n.endswith("/" + member))))
    else:
        subprocess.run(["7z", "e", str(archive), f"-o{out.parent}", member, "-y"],
                       check=True, stdout=subprocess.DEVNULL)
    return out


def symbol_sources(with_mono=False):
    """符号源字体链，按优先级排列；每步各自重新加载一份"""
    noto = TTFont(fetch("NotoSansSymbols[wght].ttf"))
    if "fvar" in noto:
        instantiateVariableFont(noto, {"wght": 400}, inplace=True)
    dejavu = fetch("dejavu-fonts-ttf-2.37.zip")
    chain = [("NotoSymbols2", TTFont(fetch("NotoSansSymbols2-Regular.ttf"))),
             ("NotoSymbols", noto),
             ("DejaVuSans", TTFont(extract(dejavu, "DejaVuSans.ttf")))]
    chain += [(f"系统{p.stem}", TTFont(p)) for p in (SYS_FONTS / n for n in SYS_SYMBOLS) if p.exists()]
    if with_mono:
        chain.insert(0, ("DejaVuSansMono", TTFont(extract(dejavu, "DejaVuSansMono.ttf"))))
    return chain


def chars(cps, limit=40):
    return "".join(chr(c) for c in cps[:limit]) + ("…" if len(cps) > limit else "")


def main():
    ap = argparse.ArgumentParser(description="从源字体构建 Termux 中文混合字体")
    ap.add_argument("-o", "--output", type=Path, default=PRODUCT, help=f"输出路径（默认 {PRODUCT.name}）")
    out = ap.parse_args().output.resolve()
    if not shutil.which("7z"):
        sys.exit("缺 7z，请先：pkg install p7zip")

    print("准备源字体...")
    scp = extract(fetch("SourceCodePro.tar.xz"), "SauceCodeProNerdFontMono-Regular.ttf")
    sarasa = extract(fetch("SarasaTermSC-TTF-Unhinted-1.0.40.7z"), "SarasaTermSC-Regular.ttf")
    started = time.time()

    with tempfile.TemporaryDirectory() as work:
        merged, symbols = Path(work) / "1-merge-cjk.ttf", Path(work) / "2-ui-symbols.ttf"

        n = step1_merge_cjk.run(scp, sarasa, merged)
        print(f"[1/3] 合入更纱 CJK 字形 {n} 个")

        added, skipped = step2_ui_symbols.run(merged, symbols, symbol_sources())
        print(f"[2/3] 补 UI 符号 {len(added)} 个：{chars([c for c, _ in added])}")
        if skipped:
            print("      跳过：" + "、".join(f"{chr(c)}（{why}）" for c, why in skipped))

        r = step3_termux_fit.run(symbols, out, symbol_sources(with_mono=True), SYS_CJK,
                                 timestampFromString(FONT_TIMESTAMP))

    fit = step3_termux_fit
    print("[3/3] 对齐 Termux 渲染器")
    print(f"      行高 ascent {fit.ASC} / descent {fit.DESC} / lineGap 0；"
          f"拉伸制表/方块 {r['box']} 个、Powerline {r['powerline']} 个")
    print(f"      收窄为单格 {len(r['narrowed'])} 个：{chars(r['narrowed'], 20)}")
    print(f"      去掉单格 emoji 映射 {len(r['dropped'])} 个：{chars(r['dropped'])}")
    print(f"      组合符号 advance 归零 {len(r['zeroed'])} 个：{' '.join(f'U+{c:04X}' for c in r['zeroed'])}")
    for label, cps in r["symbols"].items():
        print(f"      补符号 {len(cps):>4} 个 ← {label}：{chars(cps, 30)}")
    if r["cjk_extras"] is None:
        print(f"      跳过 CJK 边角字：没有 {SYS_CJK}")
    else:
        print(f"      补 CJK 边角字 {len(r['cjk_extras'])} 个 ← Noto Sans CJK SC")
    print(f"      康熙部首 / 兼容补充按 NFKC 复用 {r['nfkc_aliases']} 个")

    bad = fit.audit(out)
    glyphs = TTFont(out, lazy=True)["maxp"].numGlyphs
    print(f"完成：{out}（{glyphs} 个字形，{out.stat().st_size / 1e6:.1f}MB，用时 {time.time() - started:.0f}s）")
    if bad:
        sys.exit(f"宽度审计失败：{len(bad)} 个码位与 Termux wcwidth 不一致：{chars(bad)}")
    print("宽度审计：全部与 Termux wcwidth 一致")


if __name__ == "__main__":
    main()
