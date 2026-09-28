# 版本历史

旧版字体可以从 git 标签里取回，例如：

```bash
git show v8:SourceCodeProNerdMono-CJK8.ttf > v8.ttf
```

各标签里的文件名：`v5` → `SourceCodeProNerdMono-CJK5.ttf`，`v7` → `…-CJK7.ttf`，`v8` → `…-CJK8.ttf`，`v9` → `…-CJK9.ttf`。

## 2026-09-29 项目整理（字体内容不变）

- 构建脚本重组为 `build/` 下的三步流水线，`build/build.py` 一条命令从源字体构建到成品
- 源字体下载地址锁定到具体版本 / commit 并校验 sha256，`head.modified` 固定，构建逐字节可复现（已验证与 v9 成品完全一致）
- 成品改用不带版本号的文件名 `SourceCodeProNerdMono-CJK.ttf`，删去中间产物 v7 / v8 字体
- 演示图换成 `tools/preview.py` 离线渲染的对比图
- README 只写现状，版本历史挪到本文件

## v9（2026-09-28）对齐 Termux 渲染器

用离线模拟 TerminalRenderer 排版逐项查出 v8 的问题后修正：

- lineGap 250 被 Termux 放在行底，文字贴着行顶 → lineGap 平分进 ascent/descent（1090/−340），行高不变
- 改行高时没改制表符和方块字形，加上行高向上取整，`│`、`█` 在行与行之间断开（31px 字号下约 1.6px）→ 纵向拉满并上下各留 20 units 重叠；Powerline 分隔符同理
- v7 改 lsb 时丢了 v5 的居中平移，中文在两格里偏左（左 106 / 右 208）→ 右移 50 恢复居中
- 宽度按 Termux 自己的 wcwidth 表对齐：294 个单格字（半角假名、半角符号、谚文中终声）从两格收窄；9 个只有单格字形的 emoji（⚡☕⏰⬜🤖 等）去掉映射，交给系统彩色 emoji；6 个组合符号 advance 归零
- 补 2,184 个常用符号（✔✘★※℃①Ⅰ↩⏎⌥ 等，原先走系统回退后被挤窄）和 2,567 个 CJK 边角字（𠮷、谚文兼容字母等，原先回退后被拉宽）；康熙部首按 NFKC 复用已有字形
- `install.sh` 改为临时文件 + `mv` 原子替换：原地 `cp` 覆盖正被 mmap 的字体会让 Termux 当场闪退；下载加 `curl -f` 并校验文件头

## v8（2026-09-11）补 UI 符号

Nerd 补丁只往私有区加图标，Claude Code 的 `⏵⏵`、`⏸`、思考转圈 `✻✢✳✶✽`、工具结果树 `⎿` 等都显示成空框 → 从 Noto Sans Symbols 系列、DejaVu Sans 和系统字体补 20 个字形，单格居中。

## v7（2026-08-11）修括号左对齐

FreeType 按 `hmtx.lsb` 定位绘制起点。v5 统一设 lsb=50，把括号、标点等窄字形都推到了格子最左 → lsb 改为每个字形的真实 xMin。

## v5（2026-08-11）首个版本

Termux 发现字宽与 wcwidth 不符就横向缩放，中文宽度不是恰好两格就会被拉扁 → Source Code Pro Nerd Mono + 更纱 Term SC，中文放大 1.1 倍、advance 精确设为 1200（= 2 × 600）；lineGap 250 加大行距。
