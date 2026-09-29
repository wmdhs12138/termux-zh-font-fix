"""用手机上真实的 Android 渲染器检查字体在 Termux 里的效果（tools/preview.py 只是用 Pillow 离线模拟）。

按 TerminalRenderer 的排版方式逐个字号检查：
  - █ 方阵：竖条纹（列与列之间的缝）、横条纹（行与行之间的缝）
  - │ 竖线跨行、─ 横线跨列是否连续
  - 中文宽度是否恰好两格：不是的话 Termux 会把中文横向缩放
  - 中英混排的一整行宽度是否等于 wcwidth 算出的格数

用法：python3 tools/android_check.py 字体.ttf [字体2.ttf ...] [--sizes 14-60] [--labels A,B] [--png 目录]
只能在安卓上运行：用 /system/bin/app_process 加载 tools/android_render/probe.dex（源码和编译方法见同目录）。
--png 把每个字号的 Claude Code 开屏形象和混排样例存到 目录/<标签>/logo_<字号>.png、sample_<字号>.png。
结果取决于本机的 Skia / FreeType，换机型、换系统版本可能不同。
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "build"))
from termux_wcwidth import wcwidth  # noqa: E402

DEX = Path(__file__).resolve().parent / "android_render" / "probe.dex"
APP_PROCESS = "/system/bin/app_process"
SAMPLE = "│中文，English。混排ｱｲ한글「引号」１２ab│"


def parse_sizes(spec):
    sizes = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        sizes += range(int(lo), int(hi or lo) + 1)
    return sizes


def probe(font, sizes, png_dir):
    with tempfile.TemporaryDirectory() as tmp:
        dex = Path(tmp) / "probe.dex"
        shutil.copyfile(DEX, dex)
        dex.chmod(0o444)  # 新版 Android 拒绝加载可写的 dex
        r = subprocess.run(
            [APP_PROCESS, "/", "Probe", str(Path(font).resolve()), str(png_dir or "-"), SAMPLE, *map(str, sizes)],
            env={**os.environ, "CLASSPATH": str(dex)}, capture_output=True, text=True)
    rows = [{k: float(v) for k, v in (kv.split("=") for kv in line.split())}
            for line in r.stdout.splitlines() if line.startswith("size=")]
    if r.returncode or len(rows) != len(sizes):
        sys.exit(f"app_process 失败（退出码 {r.returncode}）：{r.stderr.strip()[-600:]}\n"
                 "崩溃原因：logcat -d | grep -A20 AndroidRuntime")
    return rows


def report(label, rows):
    groups = {"竖条纹": [], "横条纹": [], "竖、横都有": []}
    vbar, hbar, cjk, mixed = [], [], [], []
    cols = sum(wcwidth(ord(c)) for c in SAMPLE)
    for r in rows:
        s = f"{r['size']:.0f}"
        col, row = r["col_seams"] > 0, r["row_seams"] > 0
        if col or row:
            kind = "竖、横都有" if col and row else "竖条纹" if col else "横条纹"
            groups[kind].append(f"{s}({min(r['col_min'], r['row_min']):.0f})")
        if r["vbar_gaps"]:
            vbar.append(f"{s}({r['vbar_min']:.0f})")
        if r["hbar_gaps"]:
            hbar.append(f"{s}({r['hbar_min']:.0f})")
        if abs(r["cjk"] / r["fw"] - 2) > 0.01:  # TerminalRenderer 的判定：误差超过 1% 就缩放
            cjk.append(f"{s}({r['cjk']:g}/{2 * r['fw']:g})")
        if abs(r["mixed"] - cols * r["fw"]) > 0.01:
            mixed.append(f"{s}({r['mixed']:g}/{cols * r['fw']:g})")
    clean = len(rows) - sum(map(len, groups.values()))
    print(f"{label}")
    print(f"  █ 方块：{clean}/{len(rows)} 个字号无缝")
    for kind, xs in groups.items():
        if xs:
            print(f"    {kind}：{' '.join(xs)}")
    print(f"  │ 跨行断开：{' '.join(vbar) or '无'}")
    print(f"  ─ 跨列断开：{' '.join(hbar) or '无'}")
    print(f"  中文不是恰好两格、会被缩放：{' '.join(cjk) or '无'}")
    print(f"  混排整行宽度 ≠ {cols} 格：{' '.join(mixed) or '无'}")


def main():
    ap = argparse.ArgumentParser(description="用真实的 Android 渲染器检查字体在 Termux 里的效果")
    ap.add_argument("fonts", nargs="+")
    ap.add_argument("--sizes", default="14-60", help="字号列表，如 14-60 或 31,37,42（默认 14-60）")
    ap.add_argument("--labels", help="逗号分隔，与字体一一对应（默认用文件名）")
    ap.add_argument("--png", type=Path, help="把各字号的 Claude Code 开屏形象存成 PNG 到这个目录")
    a = ap.parse_args()
    if not os.path.exists(APP_PROCESS):
        sys.exit("只能在安卓上运行（需要 /system/bin/app_process）")
    labels = a.labels.split(",") if a.labels else [Path(p).name for p in a.fonts]
    sizes = parse_sizes(a.sizes)

    prop = lambda k: subprocess.run(["getprop", k], capture_output=True, text=True).stdout.strip()
    print(f"设备 {prop('ro.product.model')}，Android {prop('ro.build.version.release')}；"
          "括号里是缝处最暗亮度（满分 255）或 中文宽/两格宽 px\n")
    for font, label in zip(a.fonts, labels):
        png = None
        if a.png:
            png = a.png / label
            png.mkdir(parents=True, exist_ok=True)
        report(label, probe(font, sizes, png))


if __name__ == "__main__":
    main()
