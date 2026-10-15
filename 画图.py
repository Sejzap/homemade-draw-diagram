# -*- coding: utf-8 -*-
"""
简易画图程序（Python + Tkinter，标准库实现，无需第三方依赖）

功能：
    铅笔 / 直线 / 矩形 / 椭圆 / 橡皮擦 / 文字
    前景色、填充色、线宽可调
    撤销(Ctrl+Z) / 重做(Ctrl+Y) / 清空 / 保存图片(Ctrl+S)
    按住 Shift 可画直线 45° 吸附、正方形、正圆

保存 PNG/JPG 需要 Pillow（pip install pillow），没装则保存为 PostScript(.eps)
"""

import re
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog


class PaintApp:
    MAX_UNDO = 60

    def __init__(self, root):
        self.root = root
        root.title("画图 — Python 版")
        root.geometry("1000x680")
        root.minsize(640, 420)

        # ---------------- 状态 ----------------
        self.fg = "#000000"          # 前景色（线条 / 文字）
        self.bg = "#ffffff"          # 填充色
        self.canvas_bg = "#ffffff"   # 画布背景色        # ← 新增
        self.brush_size = 3          # 线宽
        self.tool = tk.StringVar(value="pencil")
        self.fill_shape = tk.BooleanVar(value=False)   # 是否填充图形

        self.start_x = self.start_y = None
        self.points = []             # 铅笔/橡皮的轨迹点
        self.cur_item = None         # 正在画的笔画
        self.preview = None          # 正在拖拽的图形预览

        self.undo_stack = []
        self.redo_stack = []

        self._build_ui()
        self._bind_events()
        self.push_undo()             # 初始快照（空画布）

    # ================= 界面 =================
    def _build_ui(self):
        # ---- 第一行：工具栏 ----
        bar1 = tk.Frame(self.root, bd=1, relief=tk.RAISED)
        bar1.pack(side=tk.TOP, fill=tk.X)

        for text, val in (("铅笔", "pencil"), ("直线", "line"), ("矩形", "rect"),
                          ("椭圆", "oval"), ("橡皮", "eraser"), ("文字", "text")):
            tk.Radiobutton(bar1, text=text, value=val, variable=self.tool,
                           indicatoron=False, width=6, pady=3,
                           relief=tk.RAISED, bd=1, selectcolor="#bcdcf5",
                           command=self._on_tool_change).pack(side=tk.LEFT, padx=2, pady=4)

        tk.Label(bar1, text="   粗细:").pack(side=tk.LEFT)
        self.size_var = tk.IntVar(value=self.brush_size)
        tk.Scale(bar1, from_=1, to=40, orient=tk.HORIZONTAL, length=130,
                 variable=self.size_var, command=self._on_size).pack(side=tk.LEFT)

        # 填充复选框加上 command                                 # ← 修改
        tk.Checkbutton(bar1, text="填充图形", variable=self.fill_shape,
                       selectcolor="#bcdcf5",
                       command=self._on_fill_toggle).pack(side=tk.LEFT, padx=12)

        # ---- 第二行：颜色与操作 ----
        bar2 = tk.Frame(self.root, bd=1, relief=tk.RAISED)
        bar2.pack(side=tk.TOP, fill=tk.X)

        tk.Label(bar2, text="画笔颜色:").pack(side=tk.LEFT, padx=(8, 3), pady=4)
        self.fg_btn = tk.Button(bar2, bg=self.fg, width=4, relief=tk.SUNKEN,
                                bd=2, command=self.choose_fg)
        self.fg_btn.pack(side=tk.LEFT)

        tk.Label(bar2, text="填充颜色:").pack(side=tk.LEFT, padx=(10, 3))
        self.bg_btn = tk.Button(bar2, bg=self.bg, width=4, relief=tk.SUNKEN,
                                bd=2, command=self.choose_bg)
        self.bg_btn.pack(side=tk.LEFT)

        # 几个常用快捷色
        for c in ("#000000", "#ff0000", "#00a000", "#0064ff", "#ffd200", "#ffffff"):
            tk.Button(bar2, bg=c, width=2, relief=tk.RIDGE,
                      command=lambda col=c: self._set_fg(col)).pack(side=tk.LEFT, padx=1)

        tk.Button(bar2, text="撤销", width=6, command=self.undo).pack(side=tk.LEFT, padx=(18, 2))
        tk.Button(bar2, text="恢复", width=6, command=self.redo).pack(side=tk.LEFT, padx=2)
        tk.Button(bar2, text="清空", width=6, command=self.clear).pack(side=tk.LEFT, padx=2)
        tk.Button(bar2, text="保存图片", width=9, command=self.save).pack(side=tk.LEFT, padx=2)

        # ---- 画布 ----
        self.canvas = tk.Canvas(self.root, bg=self.canvas_bg,   # ← 修改
                                highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def _bind_events(self):
        c = self.canvas
        c.bind("<Button-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_motion)
        c.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())
        self.root.bind("<Control-s>", lambda e: self.save())

    # ================= 参数回调 =================
    def _on_tool_change(self):
        t = self.tool.get()
        self.canvas.config(cursor="xterm" if t == "text" else "crosshair")

    def _on_size(self, v):
        self.brush_size = max(1, int(float(v)))

    # 下面两个方法为新增                                        # ← 新增
    def _on_fill_toggle(self):
        """勾选填充时，如果填充色和画布同色（看不见），自动改用画笔颜色。"""
        if self.fill_shape.get() and self._same_color(self.bg, self.canvas_bg):
            self.bg = self.fg
            self.bg_btn.config(bg=self.bg)

    def _same_color(self, c1, c2):
        """判断两个 Tk 颜色值是否相同，支持 'white' 和 '#ffffff' 这类写法。"""
        try:
            return self.root.winfo_rgb(c1) == self.root.winfo_rgb(c2)
        except tk.TclError:
            return str(c1).strip().lower() == str(c2).strip().lower()

    def _set_fg(self, color):
        self.fg = color
        self.fg_btn.config(bg=color)

    def choose_fg(self):
        color = colorchooser.askcolor(color=self.fg, title="选择画笔颜色")[1]
        if color:
            self._set_fg(color)

    def choose_bg(self):
        color = colorchooser.askcolor(color=self.bg, title="选择填充颜色")[1]
        if color:
            self.bg = color
            self.bg_btn.config(bg=color)

    # ================= 鼠标事件 =================
    def on_press(self, e):
        t = self.tool.get()

        if t == "text":
            self.add_text(e.x, e.y)
            return

        self.start_x, self.start_y = e.x, e.y

        if t == "pencil":
            self.points = [(e.x, e.y)]
            self.cur_item = self.canvas.create_line(
                e.x, e.y, e.x, e.y, fill=self.fg, width=self.brush_size,
                capstyle=tk.ROUND, joinstyle=tk.ROUND)

        elif t == "eraser":
            self.points = [(e.x, e.y)]
            self.cur_item = self.canvas.create_line(
                e.x, e.y, e.x, e.y, fill=self.canvas["bg"],
                width=max(8, self.brush_size * 3),
                capstyle=tk.ROUND, joinstyle=tk.ROUND)

        elif t == "line":
            self.preview = self.canvas.create_line(
                e.x, e.y, e.x, e.y, fill=self.fg, width=self.brush_size,
                capstyle=tk.ROUND)

        elif t == "rect":
            self.preview = self.canvas.create_rectangle(
                e.x, e.y, e.x, e.y, outline=self.fg, width=self.brush_size,
                fill=self.bg if self.fill_shape.get() else "")

        elif t == "oval":
            self.preview = self.canvas.create_oval(
                e.x, e.y, e.x, e.y, outline=self.fg, width=self.brush_size,
                fill=self.bg if self.fill_shape.get() else "")

    def on_motion(self, e):
        t = self.tool.get()

        # 铅笔 / 橡皮：不断追加轨迹点
        if t in ("pencil", "eraser") and self.cur_item:
            self.points.append((e.x, e.y))
            flat = [v for p in self.points for v in p]
            self.canvas.coords(self.cur_item, *flat)
            return

        # 直线 / 矩形 / 椭圆：实时预览
        if t in ("line", "rect", "oval") and self.preview and self.start_x is not None:
            x1, y1 = self.start_x, self.start_y
            x2, y2 = e.x, e.y

            if e.state & 0x0001:          # 按住 Shift 做约束
                if t == "line":
                    dx, dy = x2 - x1, y2 - y1
                    if abs(dx) > 2 * abs(dy):
                        y2 = y1
                    elif abs(dy) > 2 * abs(dx):
                        x2 = x1
                    else:
                        s = min(abs(dx), abs(dy))
                        x2 = x1 + s * (1 if dx >= 0 else -1)
                        y2 = y1 + s * (1 if dy >= 0 else -1)
                else:
                    s = max(abs(x2 - x1), abs(y2 - y1))
                    x2 = x1 + s * (1 if x2 >= x1 else -1)
                    y2 = y1 + s * (1 if y2 >= y1 else -1)

            self.canvas.coords(self.preview, x1, y1, x2, y2)

    def on_release(self, e):
        if self.start_x is None and self.cur_item is None and self.preview is None:
            return

        # 只是点了一下没拖动 -> 删除零尺寸的图形
        if self.preview is not None:
            x1, y1, x2, y2 = self.canvas.coords(self.preview)
            if abs(x2 - x1) < 1 and abs(y2 - y1) < 1:
                self.canvas.delete(self.preview)

        self.preview = None
        self.cur_item = None
        self.points = []
        self.start_x = self.start_y = None
        self.push_undo()

    # ================= 文字 =================
    def add_text(self, x, y):
        s = simpledialog.askstring("输入文字", "请输入要添加的文字：", parent=self.root)
        if not s:
            return
        size = max(12, self.brush_size * 4)
        self.canvas.create_text(x, y, text=s, fill=self.fg, anchor="nw",
                                font=("Microsoft YaHei", size))
        self.push_undo()

    # ================= 撤销 / 重做 =================
    def snapshot(self):
        """把画布上所有图元序列化成可还原的数据。"""
        items = []
        for i in self.canvas.find_all():
            t = self.canvas.type(i)
            coords = self.canvas.coords(i)
            cfg = {}
            for opt in ("fill", "outline", "width", "capstyle", "joinstyle",
                        "smooth", "text", "font", "anchor", "dash"):
                try:
                    v = self.canvas.itemcget(i, opt)
                except tk.TclError:
                    continue
                if v != "":
                    cfg[opt] = v
            items.append((t, coords, cfg))
        return items

    def restore(self, state):
        self.canvas.delete("all")
        for t, coords, cfg in state:
            try:
                getattr(self.canvas, "create_" + t)(*coords, **cfg)
            except tk.TclError:
                pass

    def push_undo(self):
        self.undo_stack.append(self.snapshot())
        if len(self.undo_stack) > self.MAX_UNDO:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if len(self.undo_stack) <= 1:
            return
        self.redo_stack.append(self.undo_stack.pop())
        self.restore(self.undo_stack[-1])

    def redo(self):
        if not self.redo_stack:
            return
        state = self.redo_stack.pop()
        self.undo_stack.append(state)
        self.restore(state)

    # ================= 清空 =================
    def clear(self):
        if messagebox.askyesno("确认", "确定要清空整张画布吗？", parent=self.root):
            self.canvas.delete("all")
            self.push_undo()

    # ================= 保存图片 =================
    def save(self):
        path = filedialog.asksaveasfilename(
            parent=self.root, title="保存图片", defaultextension=".png",
            filetypes=[("PNG 图片", "*.png"), ("JPEG 图片", "*.jpg"),
                       ("PostScript 文件", "*.eps"), ("所有文件", "*.*")])
        if not path:
            return

        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            # 没装 Pillow 时退化为 PostScript
            try:
                self.canvas.postscript(file=path)
                messagebox.showinfo(
                    "提示",
                    "未检测到 Pillow，已保存为 PostScript 文件。\n"
                    "如需保存 PNG，请先安装：pip install pillow", parent=self.root)
            except tk.TclError as ex:
                messagebox.showerror("保存失败", str(ex), parent=self.root)
            return

        self.root.update_idletasks()
        w = max(self.canvas.winfo_width(), 1)
        h = max(self.canvas.winfo_height(), 1)
        img = Image.new("RGB", (w, h), self.canvas_bg)      # ← 用画布背景色
        draw = ImageDraw.Draw(img)

        for item in self.canvas.find_all():
            try:
                self._draw_item_pil(draw, item, ImageFont)
            except Exception:
                continue

        try:
            img.save(path)
            messagebox.showinfo("成功", "图片已保存到：\n" + path, parent=self.root)
        except Exception as ex:
            messagebox.showerror("保存失败", str(ex), parent=self.root)

    def _draw_item_pil(self, draw, item, ImageFont):
        """把单个 Tk 图元绘制到 PIL 图像上。"""
        t = self.canvas.type(item)
        c = self.canvas.coords(item)
        fill = self.canvas.itemcget(item, "fill") or None
        try:
            width = max(1, int(float(self.canvas.itemcget(item, "width"))))
        except (ValueError, tk.TclError):
            width = 1

        if t == "line":
            pts = list(zip(c[0::2], c[1::2]))
            if len(pts) < 2:
                return
            color = fill or "#000000"
            draw.line(pts, fill=color, width=width, joint="curve")
            r = width / 2.0
            for (x, y) in (pts[0], pts[-1]):      # 圆头端点
                draw.ellipse([x - r, y - r, x + r, y + r], fill=color)

        elif t == "rectangle":
            outline = self.canvas.itemcget(item, "outline") or None
            try:
                draw.rectangle(c, outline=outline, fill=fill, width=width)
            except TypeError:
                draw.rectangle(c, outline=outline, fill=fill)

        elif t == "oval":
            outline = self.canvas.itemcget(item, "outline") or None
            try:
                draw.ellipse(c, outline=outline, fill=fill, width=width)
            except TypeError:
                draw.ellipse(c, outline=outline, fill=fill)

        elif t == "text":
            text = self.canvas.itemcget(item, "text")
            font = None
            fs = self.canvas.itemcget(item, "font")
            nums = re.findall(r"\d+", fs)
            size = int(nums[-1]) if nums else 18
            for name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
                try:
                    font = ImageFont.truetype(name, size)
                    break
                except Exception:
                    continue
            draw.text((c[0], c[1]), text, fill=fill or "#000000",
                      font=font, anchor="la")


if __name__ == "__main__":
    root = tk.Tk()
    app = PaintApp(root)
    root.mainloop()