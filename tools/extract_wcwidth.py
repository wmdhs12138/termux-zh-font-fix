"""从已安装的 Termux（含 NewTermux 等 fork）APK 里解出 WcWidth 的两张区间表，写入 build/termux_wcwidth.json。

Termux 渲染时字形 advance ≠ wcwidth×列宽 就会横向缩放，所以字体的宽度必须对齐 app 自己的表，
而不是 Python/系统的 Unicode 表（版本不同，比如 Unicode 16 把 ☰ 等改成了宽字符）。
表是 D8 编进 WcWidth.<clinit> 的 filled-new-array 常量，这里直接线性解码字节码取出。

用法：python3 tools/extract_wcwidth.py [base.apk]   （缺省用 `pm path com.termux` 找）
"""
import json
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "build" / "termux_wcwidth.json"
CLASS = "Lcom/termux/terminal/WcWidth;"
# <clinit> 里会出现的指令长度（16-bit 单元）
SIZE = {0x00: 1, 0x01: 1, 0x02: 2, 0x07: 1, 0x08: 2, 0x0c: 1, 0x0e: 1, 0x12: 1, 0x13: 2, 0x14: 3,
        0x15: 2, 0x1a: 2, 0x1c: 2, 0x22: 2, 0x23: 2, 0x24: 3, 0x25: 3, 0x4b: 2, 0x4d: 2, 0x69: 2,
        0x6e: 3, 0x70: 3, 0x71: 3, 0x72: 3, 0x74: 3, 0x76: 3, 0x77: 3}


class Dex:
    def __init__(self, data):
        self.d = data

    def u2(self, o):
        return struct.unpack_from("<H", self.d, o)[0]

    def u4(self, o):
        return struct.unpack_from("<I", self.d, o)[0]

    def uleb(self, o):
        r = s = 0
        while True:
            b = self.d[o]
            o += 1
            r |= (b & 0x7f) << s
            s += 7
            if b < 0x80:
                return r, o

    def string(self, i):
        _, o = self.uleb(self.u4(self.u4(0x3C) + 4 * i))
        return self.d[o:self.d.index(b"\0", o)].decode("utf-8", "replace")

    def type_name(self, i):
        return self.string(self.u4(self.u4(0x44) + 4 * i))

    def method_name(self, i):
        return self.string(self.u4(self.u4(0x5C) + 8 * i + 4))

    def clinit(self, cls):
        for k in range(self.u4(0x60)):
            c = self.u4(0x64) + 32 * k
            if self.type_name(self.u4(c)) != cls:
                continue
            o = self.u4(c + 24)
            sf, o = self.uleb(o)
            inf, o = self.uleb(o)
            dm, o = self.uleb(o)
            _, o = self.uleb(o)
            for _ in range(2 * (sf + inf)):
                _, o = self.uleb(o)
            mi = 0
            for _ in range(dm):
                diff, o = self.uleb(o)
                _, o = self.uleb(o)
                code, o = self.uleb(o)
                mi += diff
                if self.method_name(mi) == "<clinit>":
                    return code
        return None

    def int_pair_tables(self, code):
        """按 sput-object 切分，收集每张表里 filled-new-array {a, b} 的常量对"""
        n, ins = self.u4(code + 12), code + 16
        regs, pairs, tables, pc = {}, [], [], 0
        while pc < n:
            w = self.u2(ins + 2 * pc)
            op = w & 0xff
            if op == 0x00 and w:
                break  # 到了 payload 伪指令
            if op not in SIZE:
                sys.exit(f"未知指令 {op:#x} @ {pc}，WcWidth 结构可能变了")
            if op == 0x12:
                v = w >> 12
                regs[(w >> 8) & 0xf] = v - 16 if v >= 8 else v
            elif op == 0x13:
                regs[w >> 8] = struct.unpack_from("<h", self.d, ins + 2 * pc + 2)[0]
            elif op == 0x14:
                regs[w >> 8] = struct.unpack_from("<i", self.d, ins + 2 * pc + 2)[0]
            elif op == 0x15:
                regs[w >> 8] = struct.unpack_from("<h", self.d, ins + 2 * pc + 2)[0] << 16
            elif op == 0x24 and w >> 12 == 2:
                r = self.u2(ins + 2 * pc + 4)
                pairs.append((regs[r & 0xf], regs[r >> 4 & 0xf]))
            elif op == 0x69 and pairs:
                tables.append(pairs)
                pairs = []
            pc += SIZE[op]
        return tables


def main():
    apk = sys.argv[1] if len(sys.argv) > 1 else \
        subprocess.check_output(["pm", "path", "com.termux"], text=True).split(":", 1)[1].strip()
    with zipfile.ZipFile(apk) as z:
        for name in sorted(n for n in z.namelist() if n.startswith("classes") and n.endswith(".dex")):
            dex = Dex(z.read(name))
            code = dex.clinit(CLASS)
            if code:
                break
        else:
            sys.exit(f"{apk} 里找不到 {CLASS}")
    tables = dex.int_pair_tables(code)
    if len(tables) != 2 or tables[1][0] != (0x1100, 0x115F):
        sys.exit(f"解出的表不符合预期（{len(tables)} 张），请人工检查")
    OUT.write_text(json.dumps(tables))
    print(f"{name}: 零宽 {len(tables[0])} 段、宽字符 {len(tables[1])} 段 → {OUT.name}")


if __name__ == "__main__":
    main()
