import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;

import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.Arrays;

/**
 * 用手机上真实的 Android 文字渲染（Minikin + Skia + FreeType），按 Termux TerminalRenderer 的方式排版画字，
 * 检查方块、制表符有没有缝，以及中文宽度是否恰好两格。由 tools/android_check.py 调用：
 *
 *   CLASSPATH=probe.dex app_process / Probe <font.ttf> <PNG 输出目录，或 -> <混排样例> <字号...>
 *
 * 每个字号输出一行 key=value（含义见 android_check.py）。
 */
public class Probe {
    static final String[] LOGO = {  // Claude Code 开屏形象
        " ▐▛███▜▌",
        "▝▜█████▛▘",
        "  ▘▘ ▝▝",
    };

    /**
     * app_process 不经过 zygote，系统字体表没有预加载，Typeface.createFromFile 会因默认字体为 null 而崩溃；
     * 有的机型（如 vivo）系统字体配置对应用不可读，也没法补加载。所以绕开系统回退表，直接用字体文件建 Typeface
     * 并设为默认字体（要测的字形都在字体里，用不到回退）。用了隐藏 API，Android 16 上验证过；不可用时退回公开 API。
     */
    static Typeface load(String path) throws Exception {
        try {
            android.graphics.fonts.Font font = new android.graphics.fonts.Font.Builder(new File(path)).build();
            android.graphics.fonts.FontFamily family = new android.graphics.fonts.FontFamily.Builder(font).build();
            long familyPtr = (long) family.getClass().getMethod("getNativePtr").invoke(family);
            Method create = Typeface.class.getDeclaredMethod("nativeCreateFromArray", long[].class, long.class, int.class, int.class);
            create.setAccessible(true);
            long ptr = (long) create.invoke(null, new long[]{familyPtr}, 0L, 400, 0);
            Constructor<Typeface> ctor = Typeface.class.getDeclaredConstructor(long.class, String.class);
            ctor.setAccessible(true);
            Typeface tf = ctor.newInstance(ptr, null);
            Method setDefault = Typeface.class.getDeclaredMethod("setDefault", Typeface.class);
            setDefault.setAccessible(true);
            setDefault.invoke(null, tf);
            return tf;
        } catch (ReflectiveOperationException | LinkageError e) {  // LinkageError：Android 10 以下没有 Font.Builder
            System.err.println("隐藏 API 不可用，退回 Typeface.createFromFile：" + e);
            return Typeface.createFromFile(path);
        }
    }

    /** 与 TerminalRenderer 一样按 char[] 量宽度（走 Minikin + HarfBuzz 排版，GSUB 替换会生效） */
    static float measure(Paint p, String text) {
        char[] t = text.toCharArray();
        return p.measureText(t, 0, t.length);
    }

    /** 与 TerminalRenderer 构造函数相同：只设字体、抗锯齿和字号，其余（hinting、亚像素定位）全用默认值 */
    static Paint paint(Typeface tf, int size) {
        Paint p = new Paint();
        p.setTypeface(tf);
        p.setAntiAlias(true);
        p.setTextSize(size);
        return p;
    }

    /** 按 TerminalRenderer.render / drawTextRun 的坐标，每行一个 run，从第 0 列开始画 */
    static Bitmap draw(Paint p, String[] lines, int fg, int bg) {
        int lineSpacing = (int) Math.ceil(p.getFontSpacing());
        int ascent = (int) Math.ceil(p.ascent());
        int spacingAndAscent = lineSpacing + ascent;
        float width = 0;
        for (String l : lines) width = Math.max(width, measure(p, l));
        Bitmap bm = Bitmap.createBitmap((int) Math.ceil(width) + 8,
                spacingAndAscent + lineSpacing * (lines.length + 1), Bitmap.Config.ARGB_8888);
        Canvas c = new Canvas(bm);
        c.drawColor(bg);
        p.setColor(fg);
        float heightOffset = spacingAndAscent;
        for (String line : lines) {
            heightOffset += lineSpacing;
            char[] t = line.toCharArray();
            c.drawTextRun(t, 0, t.length, 0, t.length, 0f, heightOffset - spacingAndAscent, false, p);
        }
        return bm;
    }

    static String[] repeat(char ch, int cols, int rows) {
        char[] row = new char[cols];
        Arrays.fill(row, ch);
        String[] out = new String[rows];
        Arrays.fill(out, new String(row));
        return out;
    }

    /** 墨迹包围盒向内收 2px（避开外轮廓的抗锯齿边），细线只沿线的方向收：{x0, y0, x1, y1} */
    static int[] interior(Bitmap g, boolean shrinkX, boolean shrinkY) {
        int x0 = g.getWidth(), y0 = g.getHeight(), x1 = -1, y1 = -1;
        for (int y = 0; y < g.getHeight(); y++)
            for (int x = 0; x < g.getWidth(); x++)
                if ((g.getPixel(x, y) & 0xff) > 0) {
                    x0 = Math.min(x0, x); x1 = Math.max(x1, x);
                    y0 = Math.min(y0, y); y1 = Math.max(y1, y);
                }
        int dx = shrinkX ? 2 : 0, dy = shrinkY ? 2 : 0;
        return new int[]{x0 + dx, y0 + dy, x1 - dx, y1 - dy};
    }

    /**
     * 逐行 / 逐列算一个值，比基准暗 5 以上就算缝，返回 {缝的条数（相邻的算一条）, 最暗值}。
     * 实心方阵（line=false）取中位数、基准 255：中位数不受另一方向上那几条缝的影响。
     * 细线（line=true）取最亮值、基准为全线的中位数：细线在小字号下落在半像素上，本身就不是全亮，
     * 而上下两个字形重叠的地方反而更亮，所以不能拿最亮处当基准。
     */
    static int[] scan(Bitmap g, int[] r, boolean alongX, boolean line) {
        int outerLo = alongX ? r[0] : r[1], outerHi = alongX ? r[2] : r[3];
        int innerLo = alongX ? r[1] : r[0], innerHi = alongX ? r[3] : r[2];
        int[] vals = new int[outerHi - outerLo + 1];
        for (int o = outerLo; o <= outerHi; o++) {
            int[] px = new int[innerHi - innerLo + 1];
            for (int i = innerLo; i <= innerHi; i++)
                px[i - innerLo] = (alongX ? g.getPixel(o, i) : g.getPixel(i, o)) & 0xff;
            Arrays.sort(px);
            vals[o - outerLo] = line ? px[px.length - 1] : px[px.length / 2];
        }
        int[] sorted = vals.clone();
        Arrays.sort(sorted);
        int ref = line ? sorted[sorted.length / 2] : 255, n = 0, worst = 255;
        boolean inGap = false;
        for (int v : vals) {
            if (v < ref - 5 && !inGap) n++;
            inGap = v < ref - 5;
            worst = Math.min(worst, v);
        }
        return new int[]{n, worst};
    }

    public static void main(String[] a) throws Exception {
        Typeface tf = load(a[0]);
        String pngDir = a[1], sample = a[2];
        for (int i = 3; i < a.length; i++) {
            int size = Integer.parseInt(a[i]);
            Paint p = paint(tf, size);

            // 4 行 × 12 列 █：某一列整体偏暗 = 竖条纹，某一行整体偏暗 = 横条纹
            Bitmap g = draw(p, repeat('█', 12, 4), Color.WHITE, Color.BLACK);
            int[] r = interior(g, true, true);
            int[] cols = scan(g, r, true, false), rows = scan(g, r, false, false);
            // 4 行 │：沿竖线每一行取最亮值，偏暗 = 断开
            Bitmap v = draw(p, repeat('│', 1, 4), Color.WHITE, Color.BLACK);
            int[] vbar = scan(v, interior(v, false, true), false, true);
            // 12 列 ─：沿横线每一列取最亮值
            Bitmap h = draw(p, repeat('─', 12, 1), Color.WHITE, Color.BLACK);
            int[] hbar = scan(h, interior(h, true, false), true, true);

            System.out.printf("size=%d fw=%.4f cjk=%.4f mixed=%.4f line=%d col_seams=%d col_min=%d row_seams=%d row_min=%d"
                    + " vbar_gaps=%d vbar_min=%d hbar_gaps=%d hbar_min=%d%n",
                size, measure(p, "X"), measure(p, "中"), measure(p, sample), (int) Math.ceil(p.getFontSpacing()),
                cols[0], cols[1], rows[0], rows[1], vbar[0], vbar[1], hbar[0], hbar[1]);

            if (!pngDir.equals("-")) {
                Bitmap logo = draw(p, LOGO, Color.rgb(215, 119, 87), Color.rgb(30, 30, 30));
                try (FileOutputStream f = new FileOutputStream(new File(pngDir, "logo_" + size + ".png"))) {
                    logo.compress(Bitmap.CompressFormat.PNG, 100, f);
                }
                Bitmap text = draw(p, new String[]{sample}, Color.rgb(215, 215, 215), Color.BLACK);
                try (FileOutputStream f = new FileOutputStream(new File(pngDir, "sample_" + size + ".png"))) {
                    text.compress(Bitmap.CompressFormat.PNG, 100, f);
                }
            }
        }
    }
}
