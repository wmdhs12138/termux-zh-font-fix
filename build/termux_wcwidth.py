"""Termux 的 wcwidth：com.termux.terminal.WcWidth.width() 的逐行移植。

TerminalRenderer 量出的字宽 ≠ wcwidth×列宽（误差 >1%）就把整个字横向缩放，所以字形 advance
必须以 app 自己的表为准，而不是 Python/系统的 Unicode 表（版本不同，比如 Unicode 16 把 ☰ 改成了宽字符）。
区间表 termux_wcwidth.json 由 tools/extract_wcwidth.py 从已安装 APK 的字节码解出。
"""
import bisect
import json
from pathlib import Path

TABLE = Path(__file__).resolve().parent / "termux_wcwidth.json"

_ZERO, _WIDE = json.loads(TABLE.read_text())
_ZERO_LO = [a for a, _ in _ZERO]
_WIDE_LO = [a for a, _ in _WIDE]


def _intable(table, starts, cp):
    i = bisect.bisect_right(starts, cp) - 1
    return i >= 0 and cp <= table[i][1]


def wcwidth(cp):
    if (cp == 0 or cp == 0x034F or 0x200B <= cp <= 0x200F or cp in (0x2028, 0x2029)
            or 0x202A <= cp <= 0x202E or 0x2060 <= cp <= 0x2063):
        return 0
    if cp < 32 or 0x7F <= cp < 0xA0:
        return 0
    if _intable(_ZERO, _ZERO_LO, cp):
        return 0
    return 2 if _intable(_WIDE, _WIDE_LO, cp) else 1
