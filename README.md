# Termux Mixed Font — 混合字体一键安装

**Source Code Pro Nerd Mono（拉丁/Nerd 图标）+ 更纱黑体（CJK）** 混合字体，为 Termux / ZeroTermux 定制。

## 为什么有这个字体

Termux 系终端渲染中文"扁"的根因（源码级发现）：

> `TerminalRenderer.drawTextRun` 会量每个字符的实测宽度，与 wcwidth 期望格数对比，偏差 >1% 就 `canvas.scale` 横向拉伸。CJK 字形宽度 ≠ 2×主字体 X 宽度时必被拉扁（系统 Noto 也中招）。

**解法**：把更纱 CJK 字形等比 1.1 倍、advance 精确设为 1200units（= 2×SourceCodePro X 宽 600）——渲染器实测恰 2.00 格，不触发缩放，中文保持方正。

## 字体参数（v5 最终版）

| 参数 | 值 |
|---|---|
| 拉丁/图标 | Source Code Pro Nerd Mono Regular |
| CJK 字形 | Sarasa Term SC Regular（等比 1.1×） |
| advance | 1200units（= 2×X 宽，骗过渲染器 scale 逻辑） |
| LSB | 50（字距留白 ≈ 8.3% 字宽） |
| 行高 | ascent 965 / descent -215 / lineGap 250（总 1430） |
| OS/2 | ulUnicodeRange 声明 CJK 位（防 Android fallback） |
| 尺寸 | 14.2MB，40,595 个 CJK 字形 |

## 安装

```bash
# 一键（本地有成品或自动从 GitHub 下载）
./install.sh

# 从源字体重新合并构建（需 python3 + fonttools + p7zip）
./install.sh --from-source
```

**安装后必须【完全退出】Termux/ZeroTermux（最近任务划掉）再重开**——字体是进程级缓存，新建会话不会重新加载。

## 迁移到新设备

```bash
pkg install curl 2>/dev/null
curl -sL https://raw.githubusercontent.com/wmdhs12138/termux-zh-font-fix/main/install.sh | bash
# 完事！退出重开即可
```

## 调参

改 `merge_font5.py` 顶部的常量（SCALE / NEW_ADVANCE / LSB / LINEGAP）后 `./install.sh --from-source` 重新构建。

```python
SCALE = 1.1        # CJK 字形等比缩放
NEW_ADVANCE = 1200 # 目标 advance（必须 = 2×X 宽）
LSB = 50           # 左右字距
LINEGAP = 250      # 额外行距（行高 1430）
```

## 文件

- `SourceCodeProNerdMono-CJK5.ttf` — 成品字体（直接 `cp` 到 `~/.termux/font.ttf` 也行）
- `merge_font5.py` — 字体合并脚本（fontTools）
- `install.sh` — 一键安装脚本

## 相关研究

- [Termux 渲染"扁"字机制](https://github.com/termux/termux-app) — TerminalRenderer.drawTextRun scale 逻辑
- 源字体：ryanoasis/nerd-fonts（SourceCodePro v3.5.0）、be5invis/Sarasa-Gothic（v1.0.40）
