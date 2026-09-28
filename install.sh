#!/usr/bin/env bash
# ============================================================
# Termux / ZeroTermux / NewTermux 中文混合字体一键安装
#   Source Code Pro Nerd Mono（拉丁/图标）+ 更纱黑体（CJK）+ 符号补全
#
# 用法:
#   ./install.sh                 # 安装仓库里的成品（本地没有就从 GitHub 下载）
#   ./install.sh --from-source   # 从源字体重新构建再安装（python3 + fonttools + p7zip）
#   ./install.sh --help
# ============================================================
set -euo pipefail

FONT_NAME="SourceCodeProNerdMono-CJK.ttf"
DEST="$HOME/.termux/font.ttf"
REPO="https://raw.githubusercontent.com/wmdhs12138/termux-zh-font-fix/main"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install_file() {
    # 必须"写临时文件 + rename"原子替换：Termux 是 mmap 着 font.ttf 渲染的，
    # cp/curl -o 原地截断重写会让正在运行的 app 读到被改掉的映射页，当场 SIGSEGV/SIGBUS 闪退。
    # rename 后旧 inode 仍被 app 持有，照常渲染，直到重启才换成新字体。
    local src="$1" tmp="$DEST.new.$$"
    mkdir -p "$(dirname "$DEST")"
    cp "$src" "$tmp"
    if [[ "$(head -c 4 "$tmp" | od -An -tx1 | tr -d ' ')" != "00010000" ]]; then
        rm -f "$tmp"
        echo "==> $src 不是 TrueType 字体，已放弃安装"
        exit 1
    fi
    mv -f "$tmp" "$DEST"
    echo "==> 已安装: $DEST ($(du -h "$DEST" | cut -f1))"
    echo "==> 字体是进程级缓存：【完全退出】Termux（最近任务里划掉）再打开才生效"
}

if [[ "${1:-}" == "--from-source" ]]; then
    echo "==> 从源字体重新构建（首次需下载约 60MB）..."
    command -v python3 >/dev/null || { echo "缺 python3"; exit 1; }
    python3 -c "import fontTools" 2>/dev/null || pip install fonttools
    python3 "$SCRIPT_DIR/build/build.py"
    install_file "$SCRIPT_DIR/$FONT_NAME"
elif [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '2,10p' "$0"
    exit 0
elif [[ -f "$SCRIPT_DIR/$FONT_NAME" ]]; then
    # 本地仓库内有成品
    install_file "$SCRIPT_DIR/$FONT_NAME"
else
    # 直接从 GitHub 下载成品（迁移场景：机器上什么都没有）
    echo "==> 本地无成品，从 GitHub 下载..."
    DL="$(mktemp)"
    trap 'rm -f "$DL"' EXIT
    curl -fsSL -m 120 -o "$DL" "$REPO/$FONT_NAME"
    install_file "$DL"
fi
