# Termux 中文扁字修复 — 混合字体一键安装

**Source Code Pro Nerd Mono（拉丁/Nerd 图标）+ 更纱黑体（CJK）+ Noto 符号** 三合一混合字体，为 Termux / ZeroTermux / NewTermux 定制，**当前 v9**。

## 效果

<img src="assets/screenshot.jpg" width="360" alt="ZeroTermux 实机效果" />

（ZeroTermux 实机效果：中文方正、括号/标点位置正常、Nerd 图标与 Unicode 符号（⏵⏸✻⎿ 等）完整）

## 为什么有这个字体

Termux 系终端渲染中文"扁"的根因（源码级发现）：

> `TerminalRenderer.drawTextRun` 会量每个字符的实测宽度，与 wcwidth 期望格数对比，偏差 >1% 就 `canvas.scale` 横向拉伸。CJK 字形宽度 ≠ 2×主字体 X 宽度时必被拉扁（系统 Noto 也中招）。

**解法**：把更纱 CJK 字形等比 1.1 倍、advance 精确设为 1200units（= 2×SourceCodePro X 宽 600）——渲染器实测恰 2.00 格，不触发缩放，中文保持方正。

## 字体参数（v9）

| 参数 | 值 |
|---|---|
| 拉丁/图标 | Source Code Pro Nerd Mono Regular |
| CJK 字形 | Sarasa Term SC Regular（等比 1.1×） |
| 符号字形 | Noto Sans Symbols 2 / Noto Sans Symbols / DejaVu Sans（见下） |
| CJK advance | 1200units（= 2×X 宽，骗过渲染器 scale 逻辑），字形居中、左右各 50 留白 |
| 符号 advance | 按 Termux 自己的 wcwidth 表：1 格 600 / 2 格 1200，水平居中 |
| lsb | **= 每个字形真实 xMin**（关键修复，见下） |
| 行高 | ascent 1090 / descent -340 / lineGap 0（总 1430，文字在行内垂直居中） |
| OS/2 | ulUnicodeRange 声明 CJK 位（防 Android fallback） |
| 尺寸 | 15.5MB，共 57,510 个字形（CJK 43,162 + 补入符号 2,184 + 599 个 NFKC 复用映射） |

## v8：补齐 UI 符号

Nerd 补丁只往私有区加图标（Powerline/FontAwesome/Material），**不含 Unicode 符号区**。于是 Claude Code 的 `⏵⏵`（accept edits 模式）、`⏸`（plan 模式）、思考转圈 `✻✢✳✶✽`、工具结果树 `⎿` 等全部渲染成空框——`patch_symbols8.py` 把 20 个字形补进来（源字体缺失时自动下载），个别只有 Android 系统字体才有的从 `/system/fonts/NotoSansSymbols-Regular-Subsetted*.ttf` 兜底。

处理方法与 CJK 一致：等比缩放（不放大）→ **水平居中到单格、advance 精确 = 600（1 格）** → **lsb = 字形真实 xMin**（否则窄符号会贴格子左边，见坑 2）。

补的码位：`✗ ✻ ✢ ✱ ✳ ✶ ✽ ⎿ ⏺ ⏵ ⏸ ⏰ ⤓ ↳ ⇥ ↵ ⚙ ⚠ ⌘ ⬜`

## v9：对齐 Termux 渲染器

用 `preview.py`（按 TerminalRenderer 逻辑离线模拟）对照 v8 查出的问题，`patch_v9.py` 在 v8 上逐项修正：

| 问题（v8） | 现象 | v9 处理 |
|---|---|---|
| lineGap 250 被 Termux 整块放在行底 | 选区、diff 背景色、光标块里文字贴着行顶 | lineGap 平分进 ascent/descent（1090/-340），行高不变 |
| 改了行高没改制表符/方块字形（只有 1400 高），加上行高 `ceil()` 取整 | `│` 竖线逐行断开、`█` 进度条行间黑缝，31px 下约 1.6px（16–64px 全部字号都有） | 制表符/方块/Powerline 分隔符纵向拉满新行高并上下各多 20 units 重叠 |
| v7 改 lsb=xMin 时顺带丢了 v5 的 50 units 平移 | 中文在 2 格里偏左（中：左 106 / 右 208） | CJK 整体右移 50 |
| 按 1200 合入了 wcwidth=1 的字 | 半角片假名 `ｱｲｳ`、半角符号 `｡｢｣`、谚文中终声被压成半宽 | 294 个收窄到单格 |
| Nerd/v8 自带单格的 emoji 字形 | `⚡☕⏰⬜🤖🔒` 等被横向拉宽 2 倍 | 删映射，交给系统彩色 emoji |
| 组合用浊点/声调符号 advance=1200 | 同一 run 里后续文字错位 | advance 归零 |
| 常用符号区没合入 | `✔✘★☆※℃①Ⅰ↩➜⌥⇧⏎` 等走系统回退后被挤成窄条 | 补 2,184 个（DejaVu Sans Mono 优先，其次 Noto Symbols） |
| CJK 边角区没合入 | 谚文兼容字母、注音扩展、IDS、扩展 B（𠮷）回退后被横向拉宽 1.2× | 从系统 Noto Sans CJK SC（与更纱同源思源黑体）补 2,567 个；康熙部首 `⽂` 等按 NFKC 复用已有字形 |

宽度一律以 Termux 自己的 wcwidth 为准：`extract_wcwidth.py` 从已装 APK 的 `WcWidth.<clinit>` 字节码解出区间表（`termux_wcwidth.json`），不用 Python 的 Unicode 表（Unicode 16 改了 `☰` 等的宽度，Termux 仍是旧表）。

**字重**：Termux 系只加载一个 `~/.termux/font.ttf`，粗体是 `Paint.setFakeBoldText` 描边加粗、斜体是 `-0.35` 错切（NewTermux 同样如此，已查 dex 确认），放 Bold/Italic 字体文件也不会被读取——这是 app 的限制，字体侧无解。

## 两个渲染层坑（都踩过）

**坑 1：TerminalRenderer 的 scale 逻辑** — 实测字符宽度 ≠ wcwidth 期望格数时横向拉伸。CJK advance 必须精确 = 2×X 宽（1200 = 2×600），否则字形被拉扁（系统 Noto 也中招）。

**坑 2：freetype/Android 按 hmtx.lsb 定位字形绘制起点**（不是字形轮廓坐标！）— 统一设 LSB=50 会把窄字形（括号/标点）全部推到格子最左边，看起来"左对齐"。**lsb 必须 = 每个字形真实 xMin**（TrueType 规范本来就这样要求）。

## 安装

```bash
# 一键（本地有成品或自动从 GitHub 下载）
./install.sh

# 从源字体重新合并构建（需 python3 + fonttools + p7zip）
./install.sh --from-source
```

**安装后必须【完全退出】Termux/ZeroTermux（最近任务划掉）再重开**——字体是进程级缓存，新建会话不会重新加载。

**手动换字体别直接 `cp` 覆盖 `~/.termux/font.ttf`**：app 是 mmap 着这个文件渲染的，原地覆盖会让正在运行的 Termux 当场闪退（HarfBuzz 读字体表时 SIGSEGV/SIGBUS）。要先拷到同目录临时文件再 `mv` 过去（`install.sh` 已这样做）：

```bash
cp 新字体.ttf ~/.termux/font.ttf.new && mv -f ~/.termux/font.ttf.new ~/.termux/font.ttf
```

## 迁移到新设备

```bash
pkg install curl 2>/dev/null
curl -sL https://raw.githubusercontent.com/wmdhs12138/termux-zh-font-fix/main/install.sh | bash
# 完事！退出重开即可
```

## 调参

改 `merge_font7.py` 顶部的常量（SCALE / NEW_ADVANCE / LSB / LINEGAP）后 `./install.sh --from-source` 重新构建；符号的 CELL / TARGET_W / TARGET_H 在 `patch_symbols8.py` 顶部；v9 的行内位置（ASC / DESC）、铺满字形重叠量（OVERLAP）、CJK 平移（CJK_SHIFT）、补入符号大小（SYM_W / SYM_H）在 `patch_v9.py` 顶部（注意 ASC−DESC 决定行高，`merge_font7.py` 的 LINEGAP 会被 v9 覆盖）。

改完先离线预览再装，不用反复重启 app（需要 `pip install pillow`）：

```bash
python3 preview.py /sdcard/Download/cmp.png SourceCodeProNerdMono-CJK8.ttf SourceCodeProNerdMono-CJK9.ttf --size 31
```

```python
SCALE = 1.1        # CJK 字形等比缩放
NEW_ADVANCE = 1200 # 目标 advance（必须 = 2×X 宽）
LSB = 50           # 旧版字距参数（v7 已废弃，lsb 自动取真实 xMin）
LINEGAP = 250      # 额外行距（行高 1430）
```

## 文件

- `SourceCodeProNerdMono-CJK9.ttf` — 成品字体（直接 `cp` 到 `~/.termux/font.ttf` 也行）
- `SourceCodeProNerdMono-CJK8.ttf` — 上一版（v9 的构建输入）
- `SourceCodeProNerdMono-CJK7.ttf` — 旧版（无符号字形，v8 的构建输入）
- `merge_font7.py` — 拉丁+Nerd / CJK 合并脚本（fontTools，含 lsb=xMin 修复）
- `patch_symbols8.py` — 在 v7 上补 20 个 UI 符号字形，输出 v8（源字体自动下载）
- `patch_v9.py` — 在 v8 上做渲染层修正，输出 v9（见上表）
- `termux_wcwidth.json` / `extract_wcwidth.py` — Termux 的 wcwidth 区间表及其提取脚本（换 Termux 版本后重跑）
- `preview.py` — 按 TerminalRenderer 逻辑离线渲染对比图
- `install.sh` — 一键安装脚本

## 相关研究

- [Termux 渲染"扁"字机制](https://github.com/termux/termux-app) — TerminalRenderer.drawTextRun scale 逻辑
- 源字体：ryanoasis/nerd-fonts（SourceCodePro v3.5.0）、be5invis/Sarasa-Gothic（v1.0.40）、Google Noto Sans Symbols 2、dejavu-fonts（v2.37）
