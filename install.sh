#!/usr/bin/env bash
# ============================================================
# Termux / ZeroTermux 混合字体一键安装
#   Source Code Pro Nerd Mono（拉丁/图标）+ 更纱黑体（CJK）
#   v8 最终版：v7（CJK 1.1x / advance 1200 / lineGap 250）+ 20 个 UI 符号字形
#
# 用法:
#   ./install.sh                 # 用仓库内成品字体安装
#   ./install.sh --from-source   # 从源字体重新合并构建（需 python3+fonttools）
#   ./install.sh --help
# ============================================================
set -euo pipefail

FONT_NAME="SourceCodeProNerdMono-CJK8.ttf"
DEST="$HOME/.termux/font.ttf"
REPO="https://raw.githubusercontent.com/wmdhs12138/termux-zh-font-fix/main"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> 目标: $DEST"
mkdir -p "$(dirname "$DEST")"

install_file() {
    local src="$1"
    cp "$src" "$DEST"
    echo "==> 已安装: $DEST ($(du -h "$DEST" | cut -f1))"
    echo "==> 请【完全退出】Termux/ZeroTermux（最近任务划掉）后重新打开生效"
    echo "==> 注意：更换字体后若中文变扁/行距异常，重启 app 即可（进程级字体缓存）"
}

if [[ "${1:-}" == "--from-source" ]]; then
    echo "==> 从源字体重新构建（需要网络 + python3 + fonttools + p7zip）..."
    command -v python3 >/dev/null || { echo "缺 python3"; exit 1; }
    python3 -c "import fontTools" 2>/dev/null || pip install fonttools
    command -v 7z >/dev/null || { echo "缺 7z，请先: pkg install p7zip"; exit 1; }
    cd "$SCRIPT_DIR"
    # 注意：Termux 下 /tmp 属 shell:shell 不可写，必须走 TMPDIR（= $PREFIX/tmp）
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    echo "==> 临时目录: $TMP"
    curl -sL -m 300 -o "$TMP/scp.tar.xz" https://github.com/ryanoasis/nerd-fonts/releases/download/v3.5.0/SourceCodePro.tar.xz
    curl -sL -m 300 -o "$TMP/sarasa.7z" https://github.com/be5invis/Sarasa-Gothic/releases/download/v1.0.40/SarasaTermSC-TTF-Unhinted-1.0.40.7z
    tar xJf "$TMP/scp.tar.xz" -C "$TMP" SauceCodeProNerdFontMono-Regular.ttf
    7z e "$TMP/sarasa.7z" -o"$TMP/sarasa" "SarasaTermSC-Regular.ttf" -y >/dev/null
    python3 merge_font7.py "$TMP/SauceCodeProNerdFontMono-Regular.ttf" "$TMP/sarasa/SarasaTermSC-Regular.ttf"
    python3 patch_symbols8.py
    install_file "SourceCodeProNerdMono-CJK8.ttf"
elif [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '1,12p' "$0"
    exit 0
elif [[ -f "$SCRIPT_DIR/$FONT_NAME" ]]; then
    # 本地仓库内有成品
    install_file "$SCRIPT_DIR/$FONT_NAME"
else
    # 直接从 GitHub 下载成品（迁移场景：机器上什么都没有）
    echo "==> 本地无成品，从 GitHub 下载..."
    curl -sL -m 120 -o "$DEST" "$REPO/$FONT_NAME"
    echo "==> 已下载安装: $DEST ($(du -h "$DEST" | cut -f1))"
    echo "==> 请【完全退出】Termux/ZeroTermux 后重新打开生效"
fi
