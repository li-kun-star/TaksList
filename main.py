# -*- coding: utf-8 -*-
"""
FloatTask · 桌面悬浮任务清单（Windows / Tkinter）· 手绘简笔画风格

运行:   python main.py
打包:   pyinstaller --onefile --noconsole --name FloatTask ^
          --add-data "20200726060256_nuoes.jpg;." main.py
"""
import io
import json
import math
import os
import re
import sys
import ctypes
import uuid
import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk, filedialog, colorchooser

# ---------------- 常量 ----------------
APP_TITLE = "FloatTask"
MAGIC = "#010101"                     # 透明色（稀有颜色，避免误伤正常色块）
ICON_FILE = "20200726060256_nuoes.jpg"
DATA_FILE = "data.json"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "FloatTask"

# ---- 手绘风格配色（低饱和、暖色系，摒弃纯黑） ----
COL_PANEL = "#FFFBF2"        # 奶油纸面
COL_BORDER = "#E7DCC8"       # 柔和纸边
COL_PENCIL = "#B8A98F"       # 铅笔线条
COL_TEXT = "#5B4A3A"         # 暖棕正文
COL_SUB = "#A79B87"          # 暖灰辅助
COL_DONE = "#C8BCA8"         # 完成淡化
COL_ACCENT = "#8FB4D9"       # 柔和天蓝
COL_ACCENT_DARK = "#6E9AC5"
COL_INPUT_BG = "#FFFEFD"
COL_DANGER = "#DE8A7B"       # 柔和珊瑚红
COL_CHECK = "#8FBC94"        # 柔和绿（勾选）
COL_SEP = "#E4D8C2"          # 手绘分隔线
COL_ENTRY_BD = "#D8CBAF"

DOODLE_COLORS = ["#E8AEBF", "#9CC7A5", "#EAC78A",
                 "#A9B8DE", "#D3AEDE", "#EDBE9C"]   # 低饱和涂鸦色

WEEK_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

try:
    from PIL import Image, ImageDraw
except ImportError:                    # 打包后 PIL 会被 PyInstaller 收进去；开发环境缺库时降级
    Image = None


def _hex_rgb(c: str):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(round(max(0, min(255, v)))) for v in rgb)


def _lum(c: str) -> float:
    """感知亮度 0-255：判断文字该往浅还是往深淡化"""
    r, g, b = _hex_rgb(c)
    return 0.299 * r + 0.587 * g + 0.114 * b


def normalize_color(raw) -> str:
    """校验 #RRGGBB / #RGB；空或非法返回 ""（表示使用内置默认色）"""
    c = str(raw or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
        return c.upper()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", c):
        return "#" + "".join(ch * 2 for ch in c[1:]).upper()
    return ""


def mix_color(a: str, b: str, t: float) -> str:
    """a、b 间线性插值（t=0→a，t=1→b），用于从正文色推导辅助/完成态色"""
    t = max(0.0, min(1.0, float(t)))
    ra, ga, ba = _hex_rgb(a)
    rb, gb, bb = _hex_rgb(b)
    return _rgb_hex((ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t))


def text_color_palette(main: str):
    """正文色 → (正文, 辅助, 完成态)。淡色文字往深色淡化，深色文字往纸色淡化。"""
    main = normalize_color(main) or COL_TEXT
    mate = "#241C14" if _lum(main) > 150 else COL_PANEL
    return main, mix_color(main, mate, 0.40), mix_color(main, mate, 0.62)


# ---------------- 路径 ----------------
def data_dir() -> Path:
    """数据目录：exe 所在目录（打包后）或脚本目录（开发时）"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else data_dir()


def die_msgbox(msg: str):
    ctypes.windll.user32.MessageBoxW(None, msg, APP_TITLE, 0x10)
    sys.exit(1)


# ---------------- 系统：DPI / 单实例 ----------------
def setup_dpi() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    dpi = 0
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
    except Exception:
        pass
    if not dpi:
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, hdc)
        except Exception:
            dpi = 96
    return max(int(dpi), 96)


def ensure_single_instance():
    """命名互斥体防止多开；重复启动时聚焦已有胶囊窗口"""
    k32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    k32.CreateMutexW(None, False, "FloatTask_InstanceMutex")
    if ctypes.get_last_error() == 183:            # ERROR_ALREADY_EXISTS
        u32 = ctypes.windll.user32
        hwnd = u32.FindWindowW(None, APP_TITLE)
        if hwnd:
            u32.ShowWindow(hwnd, 9)               # SW_RESTORE
            u32.SetForegroundWindow(hwnd)
        sys.exit(0)


def _noactivate(win):
    """给窗口加 WS_EX_NOACTIVATE：永不抢键盘焦点（背景衬底窗口用）"""
    try:
        import ctypes.wintypes as wt
        u32 = ctypes.windll.user32
        hwnd = wt.HWND(int(win.wm_frame(), 16))
        u32.GetWindowLongW.restype = wt.LONG
        u32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
        u32.SetWindowLongW.argtypes = [wt.HWND, ctypes.c_int, wt.LONG]
        GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = -20, 0x08000000, 0x80
        ex = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                           ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    except Exception:
        pass


# ---------------- 开机自启（注册表 HKCU\\...\\Run） ----------------
def _autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    script = Path(__file__).resolve()
    return f'"{exe}" "{script}"'


def autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_VALUE)
            return True
    except OSError:
        return False


def set_autostart(on: bool):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if on:
            winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_VALUE)
            except FileNotFoundError:
                pass


# ---------------- 时间输入归一化 ----------------
def normalize_time(raw):
    """"9:30"/"0930" -> "09:30"；空 -> ""；非法 -> None"""
    s = (raw or "").strip().replace("：", ":").replace(" ", "")
    if not s:
        return ""
    m = re.fullmatch(r"(\d{1,2}):(\d{1,2})", s)
    if m:
        hh, mm = m.group(1), m.group(2)
    elif re.fullmatch(r"\d{3,4}", s):
        hh, mm = s[:-2], s[-2:]
    else:
        return None
    h, mi = int(hh), int(mm)
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return f"{h:02d}:{mi:02d}"
    return None


# ---------------- 数据层 ----------------
class TaskStore:
    """data.json 读写；变更即落盘；损坏自动备份重建"""

    DEFAULT_SETTINGS = {"autoStart": False, "bgImage": "",
                        "iconImage": "", "capSize": 48, "textColor": ""}

    def __init__(self, path: Path):
        self.path = path
        self.tasks = []
        self.settings = dict(self.DEFAULT_SETTINGS)
        self.corrupted = False
        self.save_error = None
        self._load()

    @staticmethod
    def _norm_task(t: dict) -> dict:
        return {
            "id": str(t.get("id") or uuid.uuid4().hex[:8]),
            "text": str(t.get("text") or ""),
            "time": str(t.get("time") or ""),
            "date": str(t.get("date") or date.today().isoformat()),
            "done": bool(t.get("done", False)),
            "completedAt": t.get("completedAt") or None,
        }

    def _load(self):
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
                tasks = data.get("tasks", [])
                if not isinstance(tasks, list):
                    tasks = []
                self.tasks = [self._norm_task(t) for t in tasks if isinstance(t, dict)]
                st = data.get("settings", {})
                self.settings = dict(self.DEFAULT_SETTINGS)
                if isinstance(st, dict):
                    self.settings["autoStart"] = bool(st.get("autoStart", False))
                    self.settings["bgImage"] = str(st.get("bgImage") or "")
                    self.settings["iconImage"] = str(st.get("iconImage") or "")
                    self.settings["textColor"] = normalize_color(st.get("textColor"))
                    try:
                        self.settings["capSize"] = min(96, max(24,
                                                       int(st.get("capSize", 48))))
                    except (TypeError, ValueError):
                        self.settings["capSize"] = 48
            else:
                self._save()                      # 文件不存在则创建默认结构
        except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError):
            self._recover()

    def _recover(self):
        """备份为 data.json.bak 并重建空数据"""
        try:
            if self.path.exists():
                os.replace(self.path, self.path.parent / (self.path.name + ".bak"))
        except OSError:
            pass
        self.tasks = []
        self.settings = dict(self.DEFAULT_SETTINGS)
        self.corrupted = True
        self._save()

    def _save(self):
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp.write_text(
                json.dumps({"tasks": self.tasks, "settings": self.settings},
                           ensure_ascii=False, indent=2),
                encoding="utf-8")
            os.replace(tmp, self.path)
            self.save_error = None
        except OSError as e:
            self.save_error = str(e)

    # ---- 操作 ----
    def add(self, text: str, time_str: str, day_offset: int = 0) -> dict:
        t = {
            "id": uuid.uuid4().hex[:8],
            "text": text,
            "time": time_str,
            "date": (date.today() + timedelta(days=day_offset)).isoformat(),
            "done": False,
            "completedAt": None,
        }
        self.tasks.append(t)
        self._save()
        return t

    def toggle(self, tid: str):
        for t in self.tasks:
            if t["id"] == tid:
                t["done"] = not t["done"]
                t["completedAt"] = (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S") if t["done"] else None
                )
                break
        self._save()

    def delete(self, tid: str):
        self.tasks = [t for t in self.tasks if t["id"] != tid]
        self._save()

    def update(self, tid: str, text: str, time_str: str):
        for t in self.tasks:
            if t["id"] == tid:
                t["text"] = text
                t["time"] = time_str
                break
        self._save()

    def today_view(self, today_iso: str):
        """未完成任务（自动顺延，未来日期的除外）+ 今日完成的（沉底）"""
        undone = [t for t in self.tasks
                  if not t["done"] and t["date"] <= today_iso]
        done_today = [t for t in self.tasks
                      if t["done"] and t["date"] <= today_iso
                      and (t.get("completedAt") or "")[:10] == today_iso]
        done_today.sort(key=lambda t: t.get("completedAt") or "")
        return undone, done_today

    def day_view(self, day_iso: str):
        """未来某天（如明天）视图：该日期未完成 + 该日期已完成（沉底）"""
        undone = [t for t in self.tasks if not t["done"] and t["date"] == day_iso]
        done = [t for t in self.tasks if t["done"] and t["date"] == day_iso]
        done.sort(key=lambda t: t.get("completedAt") or "")
        return undone, done


# ---------------- 圆形胶囊图片 ----------------
def make_capsule_photo(path: Path, size: int):
    """JPG -> 圆形裁剪 + 白色描边 -> PNG bytes -> PhotoImage"""
    ss = size * 4
    img = Image.open(path).convert("RGBA").resize((ss, ss), Image.LANCZOS)
    mask = Image.new("L", (ss, ss), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, ss - 1, ss - 1), fill=255)
    img.putalpha(mask)
    ImageDraw.Draw(img).ellipse(
        (2, 2, ss - 3, ss - 3),
        outline=(255, 255, 255, 235), width=max(2, ss // 40))
    img = img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return tk.PhotoImage(data=buf.getvalue())


def rounded_rect_pts(x1, y1, x2, y2, r, seg=6):
    pts = []
    for cx, cy, a0, a1 in [
        (x2 - r, y1 + r, 270, 360),
        (x2 - r, y2 - r, 0, 90),
        (x1 + r, y2 - r, 90, 180),
        (x1 + r, y1 + r, 180, 270),
    ]:
        for i in range(seg + 1):
            a = math.radians(a0 + (a1 - a0) * i / seg)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return pts


# ---------------- 手绘笔触（Canvas 抖线，确定性抖动不闪烁） ----------------
def _j(v, i, amp):
    return v + math.sin(i * 2.41 + v * 0.37) * amp


def sketch_line(cv, x1, y1, x2, y2, color, width=1.5, amp=1.0):
    """带轻微抖动的折线，模拟铅笔手绘感"""
    dist = math.hypot(x2 - x1, y2 - y1)
    n = max(2, int(dist / 7))
    nx, ny = (y2 - y1) / (dist or 1), -(x2 - x1) / (dist or 1)
    pts = []
    for i in range(n + 1):
        t = i / n
        x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        off = math.sin(i * 2.13 + x1 * 0.11 + y1 * 0.07) * amp
        pts += [x + nx * off, y + ny * off]
    return cv.create_line(*pts, fill=color, width=width,
                          capstyle="round", joinstyle="round", smooth=True)


def sketch_rect(cv, x1, y1, x2, y2, color, width=1.5, amp=0.8):
    pts = rounded_rect_pts(x1, y1, x2, y2, r=min(4, (x2 - x1) / 3), seg=2)
    j = []
    for i, (x, y) in enumerate(zip(pts[0::2], pts[1::2])):
        j += [_j(x, i, amp), _j(y, i + 50, amp)]
    j += j[:2]
    return cv.create_line(*j, fill=color, width=width,
                          capstyle="round", joinstyle="round", smooth=True)


def sketch_check(cv, cx, cy, r, color, width=2.0):
    pts = [(cx - r * 0.75, cy + r * 0.02),
           (cx - r * 0.18, cy + r * 0.55),
           (cx + r * 0.8, cy - r * 0.55)]
    j = []
    for i, (px, py) in enumerate(pts):
        j += [_j(px, i + 9, 0.5), _j(py, i + 29, 0.5)]
    return cv.create_line(*j, fill=color, width=width,
                          capstyle="round", joinstyle="round", smooth=True)


def sketch_circle(cv, cx, cy, r, outline, width=1.5, fill="", amp=0.7):
    pts = []
    n = 16
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        rr = r + math.sin(i * 2.7 + cx * 0.13 + cy * 0.07) * amp
        pts += [cx + rr * math.cos(a), cy + rr * math.sin(a)]
    return cv.create_polygon(*pts, fill=fill, outline=outline,
                             width=width, smooth=True)


# ---------------- 手绘背景（PIL 渲染：纸面/自定义图片 + 涂鸦相框） ----------------
def _jitter_rect_pts(x1, y1, x2, y2, r, seed, amp, seg=5):
    pts = rounded_rect_pts(x1, y1, x2, y2, r, seg)
    out = []
    for i, (x, y) in enumerate(zip(pts[0::2], pts[1::2])):
        j = math.sin(i * 1.7 + seed * 2.3) * amp
        ang = math.atan2(2 * y - (y1 + y2), 2 * x - (x1 + x2))
        out += [x + math.cos(ang) * j, y + math.sin(ang) * j]
    return out


def _doodle(d, kind, cx, cy, r, col, w):
    """简笔画小涂鸦：星星/爱心/太阳/云朵/对勾/音符/纸飞机/小花"""
    if kind == "star":
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.45
            pts += [cx + rr * math.cos(a), cy + rr * math.sin(a)]
        d.line(pts + pts[:2], fill=col, width=w, joint="curve")
    elif kind == "heart":
        pts = []
        for i in range(25):
            t = 2 * math.pi * i / 24
            x = 16 * math.sin(t) ** 3
            y = -(13 * math.cos(t) - 5 * math.cos(2 * t)
                  - 2 * math.cos(3 * t) - math.cos(4 * t))
            pts += [cx + x * r / 17, cy + y * r / 17]
        d.line(pts, fill=col, width=w, joint="curve")
    elif kind == "sun":
        d.ellipse((cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55),
                  outline=col, width=w)
        for i in range(8):
            a = i * math.pi / 4
            d.line((cx + r * 0.78 * math.cos(a), cy + r * 0.78 * math.sin(a),
                    cx + r * 1.15 * math.cos(a), cy + r * 1.15 * math.sin(a)),
                   fill=col, width=w)
    elif kind == "cloud":
        d.arc((cx - r, cy - r * 0.45, cx - r * 0.1, cy + r * 0.55),
              90, 270, fill=col, width=w)
        d.arc((cx - r * 0.45, cy - r * 0.85, cx + r * 0.45, cy + r * 0.35),
              0, 180, fill=col, width=w)
        d.arc((cx + r * 0.1, cy - r * 0.45, cx + r, cy + r * 0.55),
              270, 90, fill=col, width=w)
        d.line((cx - r * 0.5, cy + r * 0.55, cx + r * 0.55, cy + r * 0.55),
               fill=col, width=w)
    elif kind == "check":
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=w)
        d.line((cx - r * 0.5, cy, cx - r * 0.12, cy + r * 0.4,
                cx + r * 0.55, cy - r * 0.42), fill=col, width=w, joint="curve")
    elif kind == "note":
        d.ellipse((cx - r * 0.65, cy + r * 0.25, cx + r * 0.05, cy + r * 0.85),
                  outline=col, width=w)
        d.line((cx + r * 0.05, cy + r * 0.55, cx + r * 0.05, cy - r * 0.8),
               fill=col, width=w)
        d.line((cx + r * 0.05, cy - r * 0.8, cx + r * 0.75, cy - r * 0.55),
               fill=col, width=w)
    elif kind == "plane":
        d.line((cx - r, cy + r * 0.5, cx + r, cy - r * 0.7,
                cx - r * 0.15, cy + r * 0.85), fill=col, width=w, joint="curve")
        d.line((cx + r, cy - r * 0.7, cx - r * 0.05, cy + r * 0.05),
               fill=col, width=w)
    elif kind == "flower":
        for i in range(5):
            a = i * 2 * math.pi / 5 - math.pi / 2
            px, py = cx + r * 0.5 * math.cos(a), cy + r * 0.5 * math.sin(a)
            d.ellipse((px - r * 0.38, py - r * 0.38,
                       px + r * 0.38, py + r * 0.38), outline=col, width=w)
        d.ellipse((cx - r * 0.18, cy - r * 0.18,
                   cx + r * 0.18, cy + r * 0.18), fill=col)


def _tape(img, cx, cy, w, h, angle, color):
    """半透明和纸胶带（旋转贴到面板上沿）"""
    tile = Image.new("RGBA", (max(2, int(w)), max(2, int(h))), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    td.rectangle((0, 0, tile.width - 1, tile.height - 1), fill=color)
    td.line((0, 1, tile.width, 1), fill=(0, 0, 0, 16))
    rot = tile.rotate(angle, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(rot, (int(cx - rot.width / 2), int(cy - rot.height / 2)))


def render_panel_bg(w, h, s, image_path="", doodles=True, seed=11):
    """渲染手绘面板背景：奶油纸或自定义图片 + 铅笔抖线边框 + 简笔画相框。
    四角透明（配合 -transparentcolor）；无 PIL 时返回 None 由调用方降级。"""
    if Image is None:
        return None
    SS = 3                                          # 超采样抗锯齿
    W, H = int(w * SS), int(h * SS)
    pad = int(22 * s)
    try:
        # ---- 底：自定义图片（居中裁剪铺满，完整不挖洞）或奶油纸 ----
        img = None
        if image_path:
            p = Path(image_path)
            if p.exists():
                im = Image.open(p).convert("RGB")
                sc = max(W / im.width, H / im.height)
                im = im.resize((max(1, int(im.width * sc + .5)),
                                max(1, int(im.height * sc + .5))), Image.LANCZOS)
                x, y = (im.width - W) // 2, (im.height - H) // 2
                img = im.crop((x, y, x + W, y + H)).convert("RGBA")
        if img is None:
            img = Image.new("RGBA", (W, H), (*_hex_rgb(COL_PANEL), 255))

        d = ImageDraw.Draw(img)
        pc = _hex_rgb(COL_PENCIL)

        # ---- 内框（卡片边缘手绘线） ----
        inset = int((pad - 6 * s) * SS)
        if inset > 6 * SS:
            pts = _jitter_rect_pts(inset, inset, W - 1 - inset, H - 1 - inset,
                                   int(10 * s * SS), seed + 5, amp=1.1 * SS)
            d.line(pts + pts[:2], fill=(*pc, 150),
                   width=max(1, int(1.2 * SS)), joint="curve")

        # ---- 环形相框里的简笔画涂鸦 ----
        if doodles:
            r = 6.0 * s * SS
            c = 9.5 * s * SS
            wd = max(1, int(1.5 * SS))
            items = [
                (W * 0.30, c, "star"), (W * 0.56, c, "heart"), (W * 0.80, c, "note"),
                (W * 0.24, H - c, "plane"), (W * 0.52, H - c, "flower"),
                (W * 0.78, H - c, "check"),
                (c, H * 0.30, "sun"), (c, H * 0.62, "star"),
                (W - c, H * 0.33, "cloud"), (W - c, H * 0.66, "heart"),
            ]
            for i, (x, y, kind) in enumerate(items):
                col = (*_hex_rgb(DOODLE_COLORS[i % len(DOODLE_COLORS)]), 235)
                _doodle(d, kind, x, y, r, col, wd)
            _tape(img, W * 0.15, 4 * s * SS, 38 * s * SS, 13 * s * SS, -28,
                  (246, 216, 168, 150))
            _tape(img, W * 0.87, 4 * s * SS, 38 * s * SS, 13 * s * SS, 24,
                  (184, 210, 230, 150))

        # ---- 外框铅笔抖线（两遍，深浅叠出手绘感） ----
        for k, alpha in ((0, 200), (1, 110)):
            pts = _jitter_rect_pts(2 * SS, 2 * SS, W - 1 - 2 * SS, H - 1 - 2 * SS,
                                   int(14 * s * SS), seed + k, amp=1.3 * SS)
            d.line(pts + pts[:2], fill=(*pc, alpha),
                   width=max(2, int(1.6 * SS)), joint="curve")

        # ---- 圆角透明（仅窗口四角，让整个 panel 浮起） ----
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, W - 1, H - 1), radius=int(14 * s * SS), fill=255)
        img.putalpha(mask)

        img = img.resize((w, h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return tk.PhotoImage(data=buf.getvalue())
    except Exception:
        return None


# ---------------- UI ----------------
class App:
    def __init__(self, root: tk.Tk, store: TaskStore, scale: float, icon_path: Path):
        self.root = root
        self.store = store
        self.s = scale
        self.today = date.today().isoformat()
        self.tomorrow_mode = False    # 明天模式：写第二天任务
        self._panel_open = False
        self._suppress = 0            # 弹窗打开时抑制 FocusOut 收起
        self._collapse_job = None
        self._hint_job = None
        self._edit_dlg = None
        self._settings_dlg = None
        self._err_shown = False

        fams = set(tkfont.families(root))
        self.F_CUTE = "幼圆" if "幼圆" in fams else "Microsoft YaHei UI"
        self.F_BODY = "Microsoft YaHei UI"
        self._refresh_text_colors()   # 任务区文字配色（可在设置里改正文色）

        self.pw = int(340 * scale)
        self.ph = int(560 * scale)

        self._build_capsule(icon_path)
        self._build_panel()

        if store.corrupted:
            root.after(200, lambda: messagebox.showwarning(
                APP_TITLE, "data.json 已损坏，已自动备份为 data.json.bak 并重建空数据。"))

        root.after(30000, self._tick)

    # ---------- 胶囊（折叠态，圆形） ----------
    def _build_capsule(self, icon_path: Path):
        self._icon_fallback = icon_path
        r = self.root
        r.configure(bg=MAGIC)
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        try:
            r.attributes("-transparentcolor", MAGIC)
        except tk.TclError:
            pass
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        cap = int(self.store.settings.get("capSize", 48) * self.s)
        self.cap_size = cap
        self.cap_x, self.cap_y = sw - cap - 8, (sh - cap) // 2
        r.geometry(f"{cap}x{cap}+{self.cap_x}+{self.cap_y}")

        cv = tk.Canvas(r, bg=MAGIC, highlightthickness=0, bd=0)
        cv.pack(fill="both", expand=True)
        self.cap_cv = cv
        self._draw_capsule()
        cv.bind("<ButtonPress-1>", self._cap_press)
        cv.bind("<B1-Motion>", self._cap_move)
        cv.bind("<ButtonRelease-1>", self._cap_release)

    def _draw_capsule(self):
        """按当前设置重绘胶囊（图标或大小变化时调用）"""
        s = self.s
        cap = int(self.store.settings.get("capSize", 48) * s)
        old = getattr(self, "cap_size", cap)
        r = self.root
        # 尺寸变化时保持中心不动
        self.cap_x += (old - cap) // 2
        self.cap_y += (old - cap) // 2
        self.cap_x = min(max(0, self.cap_x), r.winfo_screenwidth() - cap)
        self.cap_y = min(max(0, self.cap_y), r.winfo_screenheight() - cap)
        self.cap_size = cap
        r.geometry(f"{cap}x{cap}+{self.cap_x}+{self.cap_y}")
        cv = self.cap_cv
        cv.delete("all")
        self._cap_photo = None
        p = self.store.settings.get("iconImage") or ""
        ipath = Path(p) if p and Path(p).exists() else self._icon_fallback
        if Image is not None and ipath.exists():
            try:
                self._cap_photo = make_capsule_photo(ipath, cap)
                cv.create_image(cap // 2, cap // 2, image=self._cap_photo)
            except Exception:
                self._cap_photo = None
        if self._cap_photo is None:                      # 兜底：手绘圆
            sketch_circle(cv, cap / 2, cap / 2, cap / 2 - 3,
                          outline=COL_ACCENT_DARK, width=2,
                          fill=COL_ACCENT, amp=1.2)
            cv.create_text(cap // 2, cap // 2, text="单", fill="white",
                           font=(self.F_CUTE, max(6, int(cap * 0.34)), "bold"))

    # ---------- 胶囊拖动（位移>4px 视为拖动，否则视为点击） ----------
    def _cap_press(self, e):
        self._drag = [e.x_root, e.y_root, self.cap_x, self.cap_y, False]

    def _cap_move(self, e):
        d = getattr(self, "_drag", None)
        if not d:
            return
        dx, dy = e.x_root - d[0], e.y_root - d[1]
        if abs(dx) + abs(dy) > 4:
            d[4] = True
        if d[4]:
            r = self.root
            nx = min(max(0, d[2] + dx), r.winfo_screenwidth() - self.cap_size)
            ny = min(max(0, d[3] + dy), r.winfo_screenheight() - self.cap_size)
            r.geometry(f"+{nx}+{ny}")
            self._drag_pos = (nx, ny)

    def _cap_release(self, _e):
        d = getattr(self, "_drag", None)
        self._drag = None
        moved = bool(d and d[4])
        if moved:
            self.cap_x, self.cap_y = getattr(self, "_drag_pos",
                                             (self.cap_x, self.cap_y))
            if self._panel_open:      # 拖动胶囊时收起面板，避免位置错位
                self.collapse()
        else:
            self._on_capsule_click()

    def _on_capsule_click(self, _e=None):
        self._cancel_collapse()
        if self._panel_open:
            self.collapse()
        else:
            self.expand()

    # ---------- 面板相框拖动 ----------
    def _pan_press(self, e):
        self._pdrag = (e.x_root, e.y_root,
                       self.panel.winfo_x(), self.panel.winfo_y())

    def _pan_move(self, e):
        d = getattr(self, "_pdrag", None)
        if not d:
            return
        p = self.panel
        nx = min(max(0, d[2] + e.x_root - d[0]),
                 p.winfo_screenwidth() - self.pw)
        ny = min(max(0, d[3] + e.y_root - d[1]),
                 p.winfo_screenheight() - self.ph)
        p.geometry(f"+{nx}+{ny}")
        self._sync_bg_win(f"+{nx}+{ny}")

    # ---------- 任务面板（展开态） ----------
    def _build_panel(self):
        s = self.s
        p = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.configure(bg=MAGIC)
        p.attributes("-topmost", True)
        try:
            p.attributes("-transparentcolor", MAGIC)
        except tk.TclError:
            pass
        p.withdraw()
        self.panel = p

        pad = int(22 * s)                  # 加宽边距，留出手绘相框一圈
        radius = int(14 * s)
        cv = tk.Canvas(p, bg=MAGIC, highlightthickness=0, bd=0)
        cv.pack(fill="both", expand=True)
        self.panel_cv = cv

        bg_path = self.store.settings.get("bgImage", "")
        # 手绘背景（自定义图片完整铺满 / 奶油纸 + 涂鸦相框）
        self._bg_photo = render_panel_bg(self.pw, self.ph, s, bg_path)
        if self._bg_photo is not None:
            self._bg_item = cv.create_image(0, 0, anchor="nw", image=self._bg_photo)
        else:
            self._bg_item = cv.create_polygon(
                rounded_rect_pts(0, 0, self.pw - 1, self.ph - 1, radius),
                fill=COL_PANEL, outline=COL_BORDER, width=1)
        cv.tag_lower(self._bg_item)

        # 自定义背景图：任务区纸面用透明色"挖洞"，露出垫在下面的背景衬底窗口。
        # 注意：-transparentcolor 是按窗口最终像素生效的，图片若画在同一窗口里
        # 会被连同洞一起抠掉（露出桌面），所以图片必须单独放一层窗口。
        self._bg_live = bool(bg_path) and self._bg_photo is not None
        self._build_bg_win()

        # 边缘相框拖动面板（内容区被 inner 覆盖，只有相框圈响应）
        cv.bind("<ButtonPress-1>", self._pan_press)
        cv.bind("<B1-Motion>", self._pan_move)

        # panel_bg：有自定义背景图时 inner 区需透明 → 用 MAGIC；否则用奶油纸
        self.panel_bg = MAGIC if self._bg_live else COL_PANEL

        inner = tk.Frame(cv, bg=self.panel_bg)
        cv.create_window((pad, pad), window=inner, anchor="nw",
                         width=self.pw - 2 * pad, height=self.ph - 2 * pad)

        header_h = int(42 * s)
        input_h = int(46 * s)
        hint_h = int(22 * s)
        gap = int(8 * s)
        list_h = self.ph - 2 * pad - header_h - input_h - hint_h - 3 * gap

        # -- 头部：小太阳涂鸦 + 日期 + 设置 --
        header = tk.Frame(inner, bg=self.panel_bg, height=header_h)
        header.pack(fill="x", pady=(0, gap))
        header.pack_propagate(False)
        sun = tk.Canvas(header, width=int(22 * s), height=int(22 * s),
                        bg=self.panel_bg, highlightthickness=0, bd=0)
        sun.pack(side="left", padx=(0, int(4 * s)))
        self.sun_cv = sun
        self._draw_sun(sun, int(22 * s))
        self.date_lbl = tk.Label(header, bg=self.panel_bg, fg=self.col_text,
                                 font=(self.F_CUTE, 12, "bold"))
        self.date_lbl.pack(side="left", pady=int(2 * s))
        gear = tk.Label(header, text="⚙", bg=self.panel_bg, fg=self.col_sub,
                        font=(self.F_CUTE, 14), cursor="hand2")
        gear.pack(side="right", padx=(6, 2))
        gear.bind("<Button-1>", lambda e: self.open_settings())
        gear.bind("<Enter>", lambda e: gear.config(fg=COL_ACCENT_DARK))
        gear.bind("<Leave>", lambda e: gear.config(fg=self.col_sub))

        # -- 明天切换按钮（写第二天任务） --
        self.day_btn_wh = (int(58 * s), int(24 * s))
        self.btn_day = tk.Canvas(header, width=self.day_btn_wh[0],
                                 height=self.day_btn_wh[1], bg=self.panel_bg,
                                 highlightthickness=0, bd=0, cursor="hand2")
        self.btn_day.pack(side="right", padx=(0, int(4 * s)))
        self.btn_day.bind("<Button-1>", lambda e: self.toggle_day_view())
        self.btn_day.bind("<Enter>", lambda e: self._draw_day_toggle(hover=True))
        self.btn_day.bind("<Leave>", lambda e: self._draw_day_toggle())

        # -- 输入行 --
        irow = tk.Frame(inner, bg=self.panel_bg, height=input_h)
        irow.pack(fill="x", pady=(0, gap))
        irow.pack_propagate(False)
        style = ttk.Style(irow)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TEntry", fieldbackground=COL_INPUT_BG,
                        bordercolor=COL_ENTRY_BD, lightcolor=COL_BORDER,
                        darkcolor=COL_BORDER, borderwidth=1)
        self._panel_style = style                        # 存引用便于后续刷新
        style.configure("TCheckbutton", background=self.panel_bg,
                        foreground=COL_TEXT)
        style.map("TCheckbutton", background=[("active", self.panel_bg)])
        self.entry_text = ttk.Entry(irow, font=(self.F_BODY, 10))
        self.entry_text.pack(side="left", fill="x", expand=True, ipady=int(5 * s))
        self.entry_time = ttk.Entry(irow, font=(self.F_BODY, 10), width=6,
                                    justify="center")
        self.entry_time.pack(side="left", padx=int(6 * s), ipady=int(5 * s))

        # 手绘圆形"＋"按钮
        bs = int(32 * s)
        self.btn_add = tk.Canvas(irow, width=bs, height=bs, bg=self.panel_bg,
                                 highlightthickness=0, bd=0, cursor="hand2")
        self.btn_add.pack(side="left")
        self._draw_add_btn(self.btn_add, bs, hover=False)
        self.btn_add.bind("<Button-1>", lambda e: self.add_from_input())
        self.btn_add.bind("<Enter>", lambda e: self._draw_add_btn(self.btn_add, bs, True))
        self.btn_add.bind("<Leave>", lambda e: self._draw_add_btn(self.btn_add, bs, False))
        self.entry_text.bind("<Return>", lambda e: self.add_from_input())
        self.entry_time.bind("<Return>", lambda e: self.add_from_input())

        # -- 提示行 --
        self.hint_lbl = tk.Label(inner, text="", bg=self.panel_bg, fg=COL_DANGER,
                                 font=(self.F_BODY, 9), height=1, anchor="w")
        self.hint_lbl.pack(fill="x", pady=(0, 2))

        # -- 任务列表 --
        lwrap = tk.Frame(inner, bg=self.panel_bg, height=list_h)
        lwrap.pack(fill="both", expand=True)
        lwrap.pack_propagate(False)
        self.list_canvas = tk.Canvas(lwrap, bg=self.panel_bg, highlightthickness=0, bd=0)
        sb = tk.Scrollbar(lwrap, orient="vertical", command=self.list_canvas.yview,
                          width=int(10 * s))
        self.list_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.list_canvas.pack(side="left", fill="both", expand=True)
        self.rows = tk.Frame(self.list_canvas, bg=self.panel_bg)
        self._list_win = self.list_canvas.create_window((0, 0), window=self.rows,
                                                        anchor="nw")
        self.rows.bind("<Configure>", lambda e: self.list_canvas.configure(
            scrollregion=self.list_canvas.bbox("all")))
        self.list_canvas.bind("<Configure>", lambda e: self.list_canvas.itemconfigure(
            self._list_win, width=e.width))
        self.root.bind_all("<MouseWheel>", self._on_wheel)

        p.bind("<FocusOut>", self._panel_focus_out)
        p.bind("<FocusIn>", lambda e: self._cancel_collapse())
        self.refresh_header()

    # ---------- 手绘小部件 ----------
    def _draw_sun(self, cv, size):
        c = size / 2
        sketch_circle(cv, c, c, size * 0.26, outline="#EAC78A",
                      width=max(1, 1.4 * self.s), fill="#FCE9C0", amp=0.5)
        for i in range(8):
            a = i * math.pi / 4
            sketch_line(cv, c + size * 0.36 * math.cos(a), c + size * 0.36 * math.sin(a),
                        c + size * 0.46 * math.cos(a), c + size * 0.46 * math.sin(a),
                        "#EAC78A", width=max(1, 1.2 * self.s), amp=0.2)

    def _mini_sun(self, cv, cx, cy, r):
        sketch_circle(cv, cx, cy, r, outline="#EAC78A",
                      width=max(1, self.s), fill="#FCE9C0", amp=0.3)
        for i in range(8):
            a = i * math.pi / 4
            sketch_line(cv, cx + r * 1.35 * math.cos(a), cy + r * 1.35 * math.sin(a),
                        cx + r * 1.8 * math.cos(a), cy + r * 1.8 * math.sin(a),
                        "#EAC78A", width=max(1, self.s), amp=0.15)

    def _mini_moon(self, cv, cx, cy, r, bite=None):
        """手绘小月牙：圆 + 底色圆咬掉一角；bite 缺省用面板底色"""
        bite = self.panel_bg if bite is None else bite
        sketch_circle(cv, cx, cy, r, outline="#A9B8DE",
                      width=max(1, self.s), fill="#DCE4F7", amp=0.3)
        cv.create_oval(cx + r * 0.25 - r * 0.95, cy - r * 0.45 - r * 0.95,
                       cx + r * 0.25 + r * 0.95, cy - r * 0.45 + r * 0.95,
                       fill=bite, outline="")

    def _draw_header_orb(self, cv, size):
        """头部小涂鸦：今天画太阳，明天模式画月亮 + 小星星"""
        cv.delete("all")
        if not self.tomorrow_mode:
            self._draw_sun(cv, size)
            return
        c = size / 2
        r = size * 0.30
        sketch_circle(cv, c, c, r, outline="#A9B8DE",
                      width=max(1, 1.4 * self.s), fill="#DCE4F7", amp=0.5)
        cv.create_oval(c + r * 0.2 - r * 0.95, c - r * 0.45 - r * 0.95,
                       c + r * 0.2 + r * 0.95, c - r * 0.45 + r * 0.95,
                       fill=self.panel_bg, outline="")
        sx, sy, sr = c + r * 1.05, c - r * 0.95, r * 0.28
        cv.create_line(sx - sr, sy, sx + sr, sy, fill="#EAC78A",
                       width=max(1, self.s), capstyle="round")
        cv.create_line(sx, sy - sr, sx, sy + sr, fill="#EAC78A",
                       width=max(1, self.s), capstyle="round")

    def _draw_day_toggle(self, hover=False):
        """明天/今天切换小胶囊：今天视图时显示"明天"，明天视图时高亮显示"今天" """
        cv = self.btn_day
        s = self.s
        w, h = self.day_btn_wh
        cv.delete("all")
        x1, y1, x2, y2 = 1.5 * s, 1.5 * s, w - 1.5 * s, h - 1.5 * s
        active = self.tomorrow_mode
        if active:
            cv.create_polygon(
                rounded_rect_pts(x1, y1, x2, y2, (y2 - y1) / 2),
                fill=COL_ACCENT_DARK if hover else COL_ACCENT, outline="")
        sketch_rect(cv, x1, y1, x2, y2,
                    COL_ACCENT_DARK if (active or hover) else COL_PENCIL,
                    width=max(1, 1.3 * s), amp=0.6)
        if active:
            self._mini_sun(cv, 13 * s, h / 2, 4.2 * s)
            cv.create_text(w - 17 * s, h / 2, text="今天", fill="white",
                           font=(self.F_CUTE, int(10 * s), "bold"))
        else:
            self._mini_moon(cv, 13 * s, h / 2, 4.2 * s)
            cv.create_text(w - 17 * s, h / 2, text="明天", fill=self.col_text,
                           font=(self.F_CUTE, int(10 * s), "bold"))

    def _draw_add_btn(self, cv, size, hover):
        cv.delete("all")
        fill = COL_ACCENT_DARK if hover else COL_ACCENT
        cv.create_oval(2, 2, size - 2, size - 2, fill=self.panel_bg, outline="")
        sketch_circle(cv, size / 2, size / 2, size / 2 - 2.5 * self.s,
                      outline=COL_ACCENT_DARK, width=max(1, 1.5 * self.s),
                      fill=fill, amp=0.9)
        cv.create_text(size / 2, size / 2 - self.s, text="＋", fill="white",
                       font=(self.F_CUTE, int(14 * self.s), "bold"))

    def _draw_checkbox(self, cv, done):
        s = self.s
        size = int(18 * s)
        cv.delete("all")
        m = 2.5 * s
        sketch_rect(cv, m, m, size - m, size - m,
                    COL_CHECK if done else COL_PENCIL,
                    width=max(1, 1.5 * s), amp=0.6 * s)
        if done:
            sketch_check(cv, size / 2, size / 2, 5.5 * s,
                         COL_CHECK, width=max(1.5, 2.2 * s))

    def _draw_sep(self, cv):
        cv.delete("all")
        w = cv.winfo_width()
        if w < 4:
            return
        h = int(5 * self.s)
        sketch_line(cv, int(6 * self.s), h / 2, w - int(6 * self.s), h / 2,
                    COL_SEP, width=max(1, 1.1 * self.s), amp=0.9)

    def _draw_empty_doodle(self, cv, w, h):
        """空列表：便签纸 + 铅笔 + 星星"""
        cv.delete("all")
        s = self.s
        cx, cy = w / 2, h / 2 - 4 * s
        hw, hh = 26 * s, 22 * s
        sketch_rect(cv, cx - hw, cy - hh, cx + hw, cy + hh,
                    COL_PENCIL, width=max(1, 1.5 * s), amp=1.0)
        for i in range(3):
            y = cy - hh + (10 + i * 9) * s
            sketch_line(cv, cx - hw + 7 * s, y, cx + hw - 7 * s, y,
                        "#D9CDB6", width=max(1, 1.1 * s), amp=0.5)
        # 铅笔
        px, py = cx + hw + 6 * s, cy + hh - 2 * s
        sketch_line(cv, px, py, px + 13 * s, py - 18 * s,
                    "#EAC78A", width=max(2, 3 * s), amp=0.3)
        sketch_line(cv, px + 13 * s, py - 18 * s, px + 16 * s, py - 22 * s,
                    self.col_sub, width=max(1, 1.6 * s), amp=0.2)
        # 两颗小星星
        for sx, sy, sr, col in ((cx - hw - 14 * s, cy - hh + 2 * s, 5 * s, "#E8AEBF"),
                                (cx + hw + 18 * s, cy - hh - 6 * s, 4 * s, "#A9B8DE")):
            pts = []
            for i in range(10):
                a = -math.pi / 2 + i * math.pi / 5
                rr = sr if i % 2 == 0 else sr * 0.45
                pts += [sx + rr * math.cos(a), sy + rr * math.sin(a)]
            cv.create_line(*pts, pts[0], pts[1], fill=col,
                           width=max(1, 1.3 * s), capstyle="round",
                           joinstyle="round", smooth=True)

    # ---------- 展开 / 收起 ----------
    def expand(self):
        if self._panel_open:
            return
        self.refresh_header()
        self.refresh_list()
        px = self.cap_x - 6 - self.pw
        py = max(0, self.cap_y + (self.cap_size - self.ph) // 2)
        geom = f"{self.pw}x{self.ph}+{max(px, 0)}+{py}"
        self._panel_open = True
        self._sync_bg_win(geom)          # 衬底层先就位，面板再盖上去
        self.panel.geometry(geom)
        self.panel.deiconify()
        self.panel.lift()
        try:
            self.panel.focus_force()
        except tk.TclError:
            pass
        self.entry_text.focus_set()
        self._cancel_hover_poll()
        self._hover_poll()                 # 启动悬停轮询兜底

    def collapse(self):
        self._cancel_collapse()
        if not self._panel_open:
            return
        self._cancel_hover_poll()
        self.panel.withdraw()
        self._panel_open = False
        self._hover = None
        self._grab = None
        self._b1_last = None
        self._press_focus = None
        self._sync_bg_win()

    # ---------- 背景衬底层（自定义背景图专用） ----------
    def _build_bg_win(self):
        """与面板同形同位的衬底窗口，永远垫在面板下方。
        任务区透明色挖洞后露出的就是这层图片，而不是桌面。"""
        bw = tk.Toplevel(self.root)
        bw.overrideredirect(True)
        bw.configure(bg=MAGIC)
        bw.attributes("-topmost", True)
        try:
            bw.attributes("-transparentcolor", MAGIC)
        except tk.TclError:
            pass
        bw.withdraw()
        bcv = tk.Canvas(bw, bg=MAGIC, highlightthickness=0, bd=0)
        bcv.pack(fill="both", expand=True)
        self._bg_win_item = None
        if self._bg_photo is not None:
            self._bg_win_item = bcv.create_image(0, 0, anchor="nw",
                                                 image=self._bg_photo)
        self.bg_win, self.bg_cv = bw, bcv
        self._apply_noactivate()         # 构建时先应用一次
        # Tk 在窗口每次映射（deiconify）时会按内部状态重写扩展样式，
        # 手动加的 WS_EX_NOACTIVATE 会被抹掉，必须在 <Map> 后重新应用。
        bw.bind("<Map>", lambda e: self._apply_noactivate(), add="+")

        # 透明像素不接收鼠标输入，点击会落到这层图片窗口上。
        # 把这些事件按坐标转发给面板上的控件，保证按钮整块区域都能点。
        self._hover = None
        self._grab = None
        self._press_focus = None
        self._b1_last = None             # 透明区多击判定的上次按下
        for seq in ("<Button-1>", "<Double-Button-1>", "<Triple-Button-1>",
                    "<ButtonRelease-1>", "<B1-Motion>"):
            bcv.bind(seq, lambda e, s=seq: self._bg_proxy(e, s))
        # Enter 也要绑：指针首次移入衬底层时 Tk 可能只派发 Enter 没有 Motion；
        # 另有 after 轮询兜底（点击抓取结束后的第一次移动也可能丢 Motion）
        bcv.bind("<Motion>", lambda e: self._hover_sync())
        bcv.bind("<Enter>", lambda e: self._hover_sync())
        bcv.bind("<Leave>", lambda e: self.panel.after_idle(self._hover_sync))
        self._hover_poll_job = None

    def _apply_noactivate(self):
        """重新给衬底窗口加 WS_EX_NOACTIVATE（被 Tk 重写样式后补救）"""
        bw = getattr(self, "bg_win", None)
        if bw is not None:
            _noactivate(bw)

    def _hwnd_of(self, w):
        try:
            return int(w.wm_frame(), 16)
        except (tk.TclError, AttributeError):
            return 0

    def _foreground_is_own(self):
        """前台窗口是否仍属于本应用（面板 / 衬底层 / 胶囊）"""
        try:
            fg = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            return False
        own = {self._hwnd_of(self.panel), self._hwnd_of(self.root)}
        bw = getattr(self, "bg_win", None)
        if bw is not None:
            own.add(self._hwnd_of(bw))
        return fg in own

    def _widget_at(self, rootx, rooty):
        """找面板上屏幕坐标 (rootx, rooty) 处最深的可见控件"""
        def walk(w):
            hit = None
            for c in w.winfo_children():
                try:
                    if not c.winfo_ismapped():
                        continue
                    x, y = c.winfo_rootx(), c.winfo_rooty()
                    if (x <= rootx < x + c.winfo_width() and
                            y <= rooty < y + c.winfo_height()):
                        hit = walk(c) or c
                except tk.TclError:
                    continue
            return hit
        return walk(self.panel)

    def _gen(self, w, seq, x=0, y=0, rootx=0, rooty=0, when="tail", **kw):
        try:
            w.event_generate(seq, x=x, y=y, rootx=rootx, rooty=rooty,
                             when=when, **kw)
        except tk.TclError:
            pass

    @staticmethod
    def _alive(w):
        try:
            return bool(w.winfo_exists())
        except tk.TclError:
            return False

    def _bg_proxy(self, e, seq):
        """把图片层收到的鼠标事件转发给面板上对应的控件。
        不转发的话按钮就只有画出来的线条/色块能点（要点得很准、易误触），
        而且穿透点击会让面板失焦自动收起。事件必须 when=now 同步派发：
        Tk 禁止 event_generate 合成 Double，双击/三击全靠 Tk 对同一控件上
        时间连续的 Button-1 自行识别，tail 排队会打断这一判定。"""
        if not self._panel_open or self._suppress > 0:
            return
        # 平台若直接把第二次按下报成 Double/Triple，统一按一次按下处理
        if seq in ("<Double-Button-1>", "<Triple-Button-1>"):
            seq = "<Button-1>"
        if seq in ("<B1-Motion>", "<ButtonRelease-1>") \
                and self._grab is not None and self._alive(self._grab):
            w = self._grab                 # 模拟 Tk 的隐式鼠标抓取：拖动跟随按下时的控件
        else:
            w = self._widget_at(e.x_root, e.y_root) or self.panel
        if not self._alive(w):
            w = self.panel
        ev = dict(x=e.x_root - w.winfo_rootx(),
                  y=e.y_root - w.winfo_rooty(), rootx=e.x_root, rooty=e.y_root,
                  button=getattr(e, "num", 1), state=getattr(e, "state", 0))
        if seq == "<Button-1>":
            self._grab = w
            # 记录可输入目标，供焦点抖动后把键盘焦点还给它
            self._press_focus = w if self._is_editable(w) else None
            self._dispatch_press(w, e, ev)
        else:
            self._gen(w, seq, when="now", **ev)
        if seq == "<ButtonRelease-1>":
            self._grab = None
        self._cancel_collapse()
        self.panel.after_idle(self._keep_focus)

    def _dispatch_press(self, w, e, ev):
        """转发按下并让 Tk 正确识别多击。物理按下先落在衬底层窗口，
        Tk 的跨窗口多击计数会被它反复冲掉，所以第二/三击时先静默补发
        count-1 个按下（临时摘掉 widget 级 Button-1 脚本，只重建计数、
        不产生单击副作用），再正式派发——此时 Tk 会同时命中
        Button-1 / Double-Button-1(/Triple) 序列，副作用次数与原生一致。"""
        try:
            now_ms = int(getattr(e, "time", 0) or
                         ctypes.windll.kernel32.GetTickCount())
            u32 = ctypes.windll.user32
            last = getattr(self, "_b1_last", None)
            dbl_t = u32.GetDoubleClickTime()
            mx = max(2, u32.GetSystemMetrics(36) // 2)   # SM_CXDOUBLECLK
            my = max(2, u32.GetSystemMetrics(37) // 2)   # SM_CYDOUBLECLK
            if (last is not None and last[0] is w
                    and 0 <= now_ms - last[1] <= dbl_t
                    and abs(e.x_root - last[2]) <= mx
                    and abs(e.y_root - last[3]) <= my):
                count = min(3, last[4] + 1)
            else:
                count = 1
            self._b1_last = (w, now_ms, e.x_root, e.y_root, count)
        except Exception:
            count = 1
            self._b1_last = None

        if count <= 1:
            self._gen(w, "<Button-1>", when="now", **ev)
            return
        try:
            saved = w.bind("<Button-1>")
            w.bind("<Button-1>", "")
            for _ in range(count - 1):
                self._gen(w, "<Button-1>", when="now", **ev)
            w.bind("<Button-1>", saved)
        except tk.TclError:
            pass
        self._gen(w, "<Button-1>", when="now", **ev)

    @staticmethod
    def _is_editable(w):
        try:
            return w.winfo_class() in ("Entry", "TEntry", "Text", "TText",
                                       "Spinbox", "TSpinbox", "Combobox",
                                       "TCombobox")
        except tk.TclError:
            return False

    def _restore_press_focus(self):
        """把键盘焦点还给最近一次点击的输入框（幂等，可被多次调用）"""
        target = getattr(self, "_press_focus", None)
        if target is not None and self._alive(target):
            try:
                target.focus_set()
            except tk.TclError:
                pass

    def _keep_focus(self):
        """点击落在透明区时焦点会在衬底层/面板间抖动，这里做最终校正：
        点的是输入框就把键盘焦点还给它，其余情况确保焦点留在面板内，避免误收起"""
        self._cancel_collapse()
        target = getattr(self, "_press_focus", None)
        if target is not None and self._alive(target):
            try:
                target.focus_set()
                return
            except tk.TclError:
                pass
        fw = self.root.focus_get()
        panel = str(self.panel)
        if fw is not None and (fw is self.panel or str(fw).startswith(panel + ".")):
            return
        try:
            self.panel.focus_force()
        except tk.TclError:
            pass

    def _hover_sync(self):
        """光标在透明区时按位置合成 <Enter>/<Leave>，悬停高亮与不透明区一致"""
        if not self._panel_open or self._suppress > 0:
            return
        try:
            x, y = self.root.winfo_pointerxy()
        except tk.TclError:
            return
        w = self._widget_at(x, y)
        # 即使悬停目标没变，也要保证衬底层光标与之一致（首次进入/重绘后）
        self._sync_proxy_cursor(w)
        if w is self._hover:
            return
        old, self._hover = self._hover, w
        if old is not None:
            self._gen(old, "<Leave>", rootx=x, rooty=y)
        if w is not None:
            self._gen(w, "<Enter>", rootx=x, rooty=y)

    def _cursor_of(self, w):
        """控件声明的光标；ttk.Entry 自身未声明时补 IBeam"""
        try:
            cur = str(w.cget("cursor"))
        except tk.TclError:
            return ""
        if cur:
            return cur
        try:
            if w.winfo_class() == "TEntry":
                return "xterm"
        except tk.TclError:
            pass
        return ""

    def _sync_proxy_cursor(self, w):
        """透明区实际命中的是衬底窗口：按面板上命中控件的光标设置衬底层光标，
        否则只有压中手绘笔画像素时才显示手型。"""
        cur = self._cursor_of(w) if w is not None else ""
        bcv = getattr(self, "bg_cv", None)
        if bcv is None:
            return
        try:
            if str(bcv.cget("cursor")) != cur:
                bcv.configure(cursor=cur)
        except tk.TclError:
            pass

    def _cancel_hover_poll(self):
        job = getattr(self, "_hover_poll_job", None)
        if job is not None:
            try:
                self.panel.after_cancel(job)
            except tk.TclError:
                pass
        self._hover_poll_job = None

    def _hover_poll(self):
        """定时轮询指针位置同步悬停态。只依赖 Enter/Motion 在两种场景会丢事件：
        指针首次进入衬底层、一次点击抓取结束后的首次移动。"""
        self._hover_poll_job = None
        if self._panel_open:
            if self._suppress == 0:
                self._hover_sync()
            self._hover_poll_job = self.panel.after(70, self._hover_poll)

    def _sync_bg_win(self, geom=""):
        """跟随面板移动/显隐；图片层始终压在面板下方"""
        bw = getattr(self, "bg_win", None)
        if bw is None:
            return
        if geom:
            bw.geometry(geom)
        if self._bg_live and self._panel_open:
            if bw.state() != "normal":
                bw.deiconify()
                bw.lift()
                self.panel.lift()
                self._apply_noactivate()
                # <Map> 回调之外再兜底一次，确保映射完成后样式仍在
                self.panel.after_idle(self._apply_noactivate)
        else:
            bw.withdraw()

    def _cancel_collapse(self):
        if self._collapse_job:
            try:
                self.panel.after_cancel(self._collapse_job)
            except Exception:
                pass
            self._collapse_job = None

    def _panel_focus_out(self, e):
        if getattr(e, "detail", "") == "NotifyInferior":
            return
        if self._suppress > 0:
            return
        # 点击穿透到衬底窗口时 Tk 会报 detail 为空的 FocusOut；
        # 只要前台仍是本应用的窗口（衬底层/胶囊），就不是真正失焦，不收起
        if self._foreground_is_own():
            # 本应用窗口间的焦点抖动可能把键盘焦点带离刚点中的输入框，
            # 在本轮 Windows 消息处理完后校正回去
            target = getattr(self, "_press_focus", None)
            if target is not None and self._alive(target):
                self.panel.after_idle(self._restore_press_focus)
            return
        self._cancel_collapse()
        self._collapse_job = self.panel.after(120, self.collapse)

    def _on_wheel(self, e):
        if not self._panel_open:
            return
        self.list_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    # ---------- 任务区文字颜色 ----------
    def _refresh_text_colors(self):
        """从设置取正文色，推导辅助/完成态/高亮色；未设置时沿用内置暖棕"""
        self.col_text, self.col_sub, self.col_done = text_color_palette(
            self.store.settings.get("textColor"))
        # 浅色文字配浅一档的蓝，深色文字配深一档（明天视图的日期高亮）
        self.col_accent = (COL_ACCENT if _lum(self.col_text) > 150
                           else COL_ACCENT_DARK)

    # ---------- 头部 / 列表 ----------
    def refresh_header(self):
        d = date.today()
        if self.tomorrow_mode:
            tm = d + timedelta(days=1)
            self.date_lbl.config(
                text=f"明天 {tm.month}月{tm.day}日 {WEEK_CN[tm.weekday()]}",
                fg=self.col_accent)
        else:
            self.date_lbl.config(
                text=f"{d.year}年{d.month}月{d.day}日 {WEEK_CN[d.weekday()]}",
                fg=self.col_text)
        self._draw_header_orb(self.sun_cv, int(22 * self.s))
        self._draw_day_toggle()

    def refresh_list(self):
        for w in self.rows.winfo_children():
            w.destroy()
        if self.tomorrow_mode:
            tm = (date.today() + timedelta(days=1)).isoformat()
            undone, done_list = self.store.day_view(tm)
            empty_txt = "明天还没有任务，先规划一条吧 ~"
        else:
            undone, done_list = self.store.today_view(self.today)
            empty_txt = "今天没有任务，写一条吧 ~"
        if not undone and not done_list:
            cv = tk.Canvas(self.rows, bg=self.panel_bg, highlightthickness=0, bd=0,
                           height=int(100 * self.s))
            cv.pack(fill="x", pady=(int(26 * self.s), int(2 * self.s)))
            cv.bind("<Configure>",
                    lambda e, c=cv: self._draw_empty_doodle(c, e.width, e.height))
            tk.Label(self.rows, text=empty_txt, bg=self.panel_bg,
                     fg=self.col_sub, font=(self.F_CUTE, 11)).pack(fill="x")
        else:
            for i, t in enumerate(undone + done_list):
                self._make_row(t)
                if i < len(undone) + len(done_list) - 1:
                    sep = tk.Canvas(self.rows, bg=self.panel_bg, highlightthickness=0,
                                    bd=0, height=int(5 * self.s))
                    sep.pack(fill="x")
                    sep.bind("<Configure>", lambda e, c=sep: self._draw_sep(c))
        self.list_canvas.update_idletasks()
        self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all"))
        self.list_canvas.yview_moveto(0)

    def _make_row(self, t: dict):
        s = self.s
        row = tk.Frame(self.rows, bg=self.panel_bg)
        row.pack(fill="x", pady=int(3 * s))
        done = t["done"]
        font = (self.F_BODY, 10, "overstrike") if done else (self.F_BODY, 10)
        fg = self.col_done if done else self.col_text

        # 手绘勾选框
        box = tk.Canvas(row, width=int(18 * s), height=int(18 * s), bg=self.panel_bg,
                        highlightthickness=0, bd=0, cursor="hand2")
        box.pack(side="left", padx=(int(2 * s), int(8 * s)))
        self._draw_checkbox(box, done)
        box.bind("<Button-1>", lambda e: self.on_toggle(t["id"]))

        lbl = tk.Label(row, text=t["text"], bg=self.panel_bg, fg=fg, font=font,
                       anchor="w", justify="left", wraplength=int(178 * s),
                       cursor="hand2")
        lbl.pack(side="left", fill="x", expand=True)
        tmlbl = tk.Label(row, text=t["time"], bg=self.panel_bg,
                         fg=self.col_done if done else self.col_sub,
                         font=(self.F_BODY, 9), width=5, anchor="e")
        tmlbl.pack(side="right", padx=int(4 * s))
        dlbl = tk.Label(row, text="✕", bg=self.panel_bg, fg=self.col_sub,
                        font=(self.F_BODY, 10), cursor="hand2",
                        padx=int(2 * s))
        dlbl.pack(side="right")
        dlbl.bind("<Button-1>", lambda e: self.on_delete(t["id"]))
        dlbl.bind("<Enter>", lambda e: dlbl.config(fg=COL_DANGER))
        dlbl.bind("<Leave>", lambda e: dlbl.config(fg=self.col_sub))
        for w in (lbl, tmlbl):
            w.bind("<Double-Button-1>", lambda e, tid=t["id"]: self.open_edit(tid))

    # ---------- 任务操作 ----------
    def toggle_day_view(self):
        """今天 ⇄ 明天 视图切换：明天模式下新增的任务记到明天"""
        self.tomorrow_mode = not self.tomorrow_mode
        self.hint_lbl.config(text="")
        self.refresh_header()
        self.refresh_list()
        self.entry_text.focus_set()

    def add_from_input(self):
        text = self.entry_text.get().strip()
        if not text:
            self._hint("请先输入任务内容")
            return
        t = normalize_time(self.entry_time.get())
        if t is None:
            self._hint("时间格式：HH:MM，可留空")
            return
        self.store.add(text, t, day_offset=1 if self.tomorrow_mode else 0)
        self.entry_text.delete(0, "end")
        self.entry_time.delete(0, "end")
        self.entry_text.focus_set()
        self.refresh_list()
        if self.tomorrow_mode:
            self._hint("已加入明天的清单 ✓", COL_CHECK)
        self._check_save_error()

    def on_toggle(self, tid):
        self.store.toggle(tid)
        self.refresh_list()
        self._check_save_error()

    def on_delete(self, tid):
        self.store.delete(tid)
        self.refresh_list()
        self._check_save_error()

    def _hint(self, text, color=COL_DANGER):
        self.hint_lbl.config(text=text, fg=color)
        if self._hint_job:
            try:
                self.root.after_cancel(self._hint_job)
            except Exception:
                pass
        self._hint_job = self.root.after(
            2500, lambda: self.hint_lbl.config(text=""))

    def _check_save_error(self):
        if self.store.save_error and not self._err_shown:
            self._err_shown = True
            messagebox.showerror(APP_TITLE,
                                 "保存 data.json 失败：\n" + self.store.save_error)
        elif not self.store.save_error:
            self._err_shown = False

    # ---------- 弹窗通用 ----------
    def _popup(self, w, h):
        s = self.s
        dlg = tk.Toplevel(self.panel)
        dlg.overrideredirect(True)
        dlg.configure(bg=MAGIC)
        dlg.attributes("-topmost", True)
        try:
            dlg.attributes("-transparentcolor", MAGIC)
        except tk.TclError:
            pass
        cv = tk.Canvas(dlg, bg=MAGIC, highlightthickness=0, bd=0)
        cv.pack(fill="both", expand=True)
        photo = render_panel_bg(w, h, s, "", doodles=False, seed=23)
        if photo is not None:
            dlg._bg = photo
            it = cv.create_image(0, 0, anchor="nw", image=photo)
            cv.tag_lower(it)
        else:
            cv.create_polygon(rounded_rect_pts(0, 0, w - 1, h - 1, int(12 * s)),
                              fill=COL_PANEL, outline=COL_BORDER, width=1)
        pad = int(16 * s)
        inner = tk.Frame(cv, bg=COL_PANEL)
        cv.create_window((pad, pad), window=inner, anchor="nw",
                         width=w - 2 * pad, height=h - 2 * pad)
        # 右上角手绘关闭按钮：inner 的子控件，永远不会被遮挡
        cr = int(9 * s)
        ccv = tk.Canvas(inner, width=2 * cr + int(6 * s),
                        height=2 * cr + int(6 * s), bg=COL_PANEL,
                        highlightthickness=0, bd=0, cursor="hand2")
        ccv.place(relx=1.0, x=0, y=0, anchor="ne")
        self._close_cv_draw(ccv, cr, COL_TEXT)
        ccv.bind("<Button-1>", lambda e: self._close_popup(dlg))
        ccv.bind("<Enter>", lambda e: self._close_cv_draw(ccv, cr, COL_DANGER))
        ccv.bind("<Leave>", lambda e: self._close_cv_draw(ccv, cr, COL_TEXT))
        x = self.panel.winfo_rootx() + (self.pw - w) // 2
        y = self.panel.winfo_rooty() + (self.ph - h) // 2
        dlg.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
        dlg.grab_set()
        try:
            dlg.focus_force()          # grab 只抢鼠标；键盘焦点也要抢，ESC 才有效
        except tk.TclError:
            pass
        self._suppress += 1
        return dlg, inner

    def _close_cv_draw(self, cv, r, color):
        """在独立小画布上画手绘"×"，整体可点，变色直接重绘（控件级 Enter/Leave 不会循环）"""
        cv.delete("all")
        s = self.s
        w = max(1.5, 1.8 * s)
        c = r + 3 * s
        sketch_circle(cv, c, c, r, outline=color, width=w, amp=0.5)
        sketch_line(cv, c - r * 0.42, c - r * 0.42,
                    c + r * 0.42, c + r * 0.42, color, width=w, amp=0.3)
        sketch_line(cv, c - r * 0.42, c + r * 0.42,
                    c + r * 0.42, c - r * 0.42, color, width=w, amp=0.3)

    def _close_popup(self, dlg):
        dlg.grab_release()
        dlg.destroy()
        self._suppress = max(0, self._suppress - 1)
        try:
            self.panel.focus_force()
        except tk.TclError:
            pass

    # ---------- 编辑任务 ----------
    def open_edit(self, tid):
        if self._edit_dlg is not None and self._edit_dlg.winfo_exists():
            self._edit_dlg.lift()
            return
        task = next((t for t in self.store.tasks if t["id"] == tid), None)
        if not task:
            return
        s = self.s
        w, h = int(300 * s), int(196 * s)
        dlg, inner = self._popup(w, h)
        self._edit_dlg = dlg

        tk.Label(inner, text="编辑任务 ✎", bg=COL_PANEL, fg=COL_TEXT,
                 font=(self.F_CUTE, 12, "bold")).pack(anchor="w",
                                                      pady=(0, int(8 * s)))
        e_text = ttk.Entry(inner, font=(self.F_BODY, 10))
        e_text.insert(0, task["text"])
        e_text.pack(fill="x", ipady=int(5 * s))
        trow = tk.Frame(inner, bg=COL_PANEL)
        trow.pack(fill="x", pady=(int(8 * s), 0))
        e_time = ttk.Entry(trow, font=(self.F_BODY, 10), width=6,
                           justify="center")
        e_time.insert(0, task["time"])
        e_time.pack(side="left", ipady=int(5 * s))
        tk.Label(trow, text="计划时间，可留空", bg=COL_PANEL, fg=COL_SUB,
                 font=(self.F_BODY, 9)).pack(side="left", padx=int(8 * s))

        brow = tk.Frame(inner, bg=COL_PANEL)
        brow.pack(fill="x", side="bottom", pady=(int(10 * s), 0))

        def save(_e=None):
            text = e_text.get().strip()
            if not text:
                return
            t = normalize_time(e_time.get())
            if t is None:
                return
            self.store.update(tid, text, t)
            self.refresh_list()
            self._check_save_error()
            self._close_popup(dlg)

        def cancel(_e=None):
            self._close_popup(dlg)

        tk.Button(brow, text="取消", command=cancel, bg=COL_INPUT_BG, fg=COL_TEXT,
                  activebackground=COL_BORDER, relief="flat", bd=0, cursor="hand2",
                  font=(self.F_CUTE, 10), padx=int(14 * s),
                  pady=int(4 * s)).pack(side="right")
        tk.Button(brow, text="保存", command=save, bg=COL_ACCENT, fg="white",
                  activebackground=COL_ACCENT_DARK, activeforeground="white",
                  relief="flat", bd=0, cursor="hand2",
                  font=(self.F_CUTE, 10, "bold"), padx=int(14 * s),
                  pady=int(4 * s)).pack(side="right", padx=(0, int(8 * s)))
        e_text.bind("<Return>", save)
        e_time.bind("<Return>", save)
        dlg.bind("<Escape>", cancel)
        dlg.protocol("WM_DELETE_WINDOW", cancel)
        e_text.focus_set()
        e_text.select_range(0, "end")

    # ---------- 设置 ----------
    def _reload_bg(self):
        img_path = self.store.settings.get("bgImage", "")
        photo = render_panel_bg(self.pw, self.ph, self.s, img_path)
        # 只有图片确实渲染成功才启用透明任务区；否则回退奶油纸，不能挖洞露桌面
        self._bg_live = bool(img_path) and photo is not None
        if photo is None:
            photo = render_panel_bg(self.pw, self.ph, self.s, "")
        if photo is not None:
            self._bg_photo = photo
            self.panel_cv.delete(self._bg_item)
            self._bg_item = self.panel_cv.create_image(0, 0, anchor="nw",
                                                       image=self._bg_photo)
            self.panel_cv.tag_lower(self._bg_item)
            if getattr(self, "bg_cv", None) is not None:
                self.bg_cv.delete("all")
                self.bg_cv.create_image(0, 0, anchor="nw", image=photo)

        # panel_bg 切换 + 递归刷新 inner 所有子控件 bg
        old_bg = self.panel_bg
        self.panel_bg = MAGIC if self._bg_live else COL_PANEL
        new_bg = self.panel_bg
        if old_bg != new_bg:
            # 只改 inner 子树，panel_cv 自身 bg 必须保持 MAGIC
            # inner 是 panel_cv 里唯一的 window 项
            for item in self.panel_cv.find_all():
                if self.panel_cv.type(item) == "window":
                    w = self.panel_cv.itemcget(item, "window")
                    self._set_tree_bg(self.root.nametowidget(w), new_bg)
            # ttk Style 同步
            if getattr(self, "_panel_style", None) is not None:
                self._panel_style.configure("TCheckbutton", background=new_bg)
                self._panel_style.map("TCheckbutton", background=[("active", new_bg)])
            # 重绘按钮/列表（它们内部画了 bg 色填充）
            self.refresh_list()
            # btn_add 重绘（它内部有 fill=panel_bg 的圆形底）
            bs = int(32 * self.s)
            self.btn_add.configure(bg=self.panel_bg)
            self._draw_add_btn(self.btn_add, bs, hover=False)
            # 头部太阳/月亮与明天按钮重绘（月牙咬口用了 panel_bg 色）
            self.refresh_header()
        # 衬底窗口显隐同步（清除背景图时立即消失，恢复原样）
        self._sync_bg_win(self.panel.geometry())

    def _set_tree_bg(self, widget, bg):
        """递归把一个容器及其所有后代的 bg 设为指定色（仅处理 Frame/Canvas/Label 等有 bg 的）"""
        try:
            try:
                widget.configure(bg=bg)
            except tk.TclError:
                pass
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._set_tree_bg(child, bg)

    def open_settings(self):
        if self._settings_dlg is not None and self._settings_dlg.winfo_exists():
            self._settings_dlg.lift()
            return
        s = self.s
        w, h = int(300 * s), int(540 * s)      # 高度需容纳"文字颜色"一段
        dlg, inner = self._popup(w, h)
        self._settings_dlg = dlg

        tk.Label(inner, text="设置 ⚙", bg=COL_PANEL, fg=COL_TEXT,
                 font=(self.F_CUTE, 12, "bold")).pack(anchor="w",
                                                      pady=(0, int(8 * s)))
        self.auto_var = tk.BooleanVar(value=autostart_enabled())

        def _toggle():
            on = self.auto_var.get()
            try:
                set_autostart(on)
                self.store.settings["autoStart"] = on
                self.store._save()
                reg_hint.config(text="")
            except OSError as e:
                self.auto_var.set(not on)
                reg_hint.config(text="写入注册表失败：" + str(e))

        self._toggle_autostart = _toggle
        ttk.Checkbutton(inner, text="开机自动启动", variable=self.auto_var,
                        command=self._toggle_autostart).pack(anchor="w")
        tk.Label(inner, text="开关写入注册表 HKCU\\...\\CurrentVersion\\Run",
                 bg=COL_PANEL, fg=COL_SUB,
                 font=(self.F_BODY, 8)).pack(anchor="w", pady=(int(2 * s), 0))
        reg_hint = tk.Label(inner, text="", bg=COL_PANEL, fg=COL_DANGER,
                            font=(self.F_BODY, 9), wraplength=w - 40)
        reg_hint.pack(anchor="w")

        # -- 背景图片 --
        sketch_line_frame = tk.Canvas(inner, height=int(8 * s), bg=COL_PANEL,
                                      highlightthickness=0, bd=0)
        sketch_line_frame.pack(fill="x", pady=(int(10 * s), int(6 * s)))
        sketch_line_frame.bind("<Configure>", lambda e: (
            e.widget.delete("all"),
            sketch_line(e.widget, 2, 4, e.width - 2, 4, COL_SEP,
                        width=max(1, 1.1 * s), amp=1.0)))

        tk.Label(inner, text="背景图片 ✿", bg=COL_PANEL, fg=COL_TEXT,
                 font=(self.F_CUTE, 11, "bold")).pack(anchor="w")
        bg_row = tk.Frame(inner, bg=COL_PANEL)
        bg_row.pack(fill="x", pady=(int(4 * s), 0))
        tk.Button(bg_row, text="选择图片…", command=lambda: self._choose_bg(name_lbl),
                  bg=COL_ACCENT, fg="white", activebackground=COL_ACCENT_DARK,
                  activeforeground="white", relief="flat", bd=0, cursor="hand2",
                  font=(self.F_CUTE, 10, "bold"), padx=int(12 * s),
                  pady=int(3 * s)).pack(side="left")
        tk.Button(bg_row, text="清除", command=lambda: self._clear_bg(name_lbl),
                  bg=COL_INPUT_BG, fg=COL_TEXT, activebackground=COL_BORDER,
                  relief="flat", bd=0, cursor="hand2", font=(self.F_CUTE, 10),
                  padx=int(12 * s), pady=int(3 * s)).pack(side="left",
                                                         padx=(int(8 * s), 0))
        cur = self.store.settings.get("bgImage") or ""
        name_lbl = tk.Label(inner, text=("当前：" + Path(cur).name) if cur
                            else "未设置（默认手绘奶油纸）",
                            bg=COL_PANEL, fg=COL_SUB, font=(self.F_BODY, 8),
                            anchor="w", wraplength=w - 40, justify="left")
        name_lbl.pack(fill="x", pady=(int(3 * s), 0))
        tk.Label(inner, text="图片铺满整个面板，任务区白色纸面透出背景图",
                 bg=COL_PANEL, fg=COL_SUB,
                 font=(self.F_BODY, 8)).pack(anchor="w")

        # -- 任务文字颜色（背景图较暗/花哨时用来救可读性） --
        sep_tc = tk.Canvas(inner, height=int(8 * s), bg=COL_PANEL,
                           highlightthickness=0, bd=0)
        sep_tc.pack(fill="x", pady=(int(10 * s), int(6 * s)))
        sep_tc.bind("<Configure>", lambda e: (
            e.widget.delete("all"),
            sketch_line(e.widget, 2, 4, e.width - 2, 4, COL_SEP,
                        width=max(1, 1.1 * s), amp=1.0)))

        tk.Label(inner, text="任务文字颜色 ✎", bg=COL_PANEL, fg=COL_TEXT,
                 font=(self.F_CUTE, 11, "bold")).pack(anchor="w")
        tc_row = tk.Frame(inner, bg=COL_PANEL)
        tc_row.pack(fill="x", pady=(int(4 * s), 0))
        swatch = tk.Canvas(tc_row, width=int(44 * s), height=int(22 * s),
                           bg=COL_PANEL, highlightthickness=0, bd=0)
        swatch.pack(side="left")
        color_cur_lbl = tk.Label(inner, text="", bg=COL_PANEL, fg=COL_SUB,
                                 font=(self.F_BODY, 8), anchor="w")
        color_cur_lbl.pack(fill="x", pady=(int(3 * s), 0))
        tk.Label(inner, text="文字压在背景图上时调浅或调深，避免看不清",
                 bg=COL_PANEL, fg=COL_SUB,
                 font=(self.F_BODY, 8)).pack(anchor="w")

        def _draw_swatch():
            """色板预览：正文色 Aa + 完成态色 ✓"""
            main, _sub, done = text_color_palette(
                self.store.settings.get("textColor"))
            swatch.delete("all")
            swatch.create_rectangle(1, 1, int(43 * s), int(21 * s),
                                    fill=COL_INPUT_BG, outline=COL_ENTRY_BD)
            swatch.create_text(int(11 * s), int(11 * s), text="Aa",
                               fill=main, font=(self.F_BODY, 10, "bold"))
            swatch.create_text(int(28 * s), int(11 * s), text="✓",
                               fill=done, font=(self.F_BODY, 10, "bold"))
            cur = normalize_color(self.store.settings.get("textColor"))
            color_cur_lbl.config(
                text=f"当前：{cur}" if cur else "当前：默认暖棕（跟随内置配色）")

        def _apply_text_color(raw):
            self.store.settings["textColor"] = normalize_color(raw)
            self.store._save()
            self._refresh_text_colors()
            self.refresh_header()
            self.refresh_list()
            _draw_swatch()
            self._check_save_error()

        def _pick_text_color():
            cur = self.store.settings.get("textColor") or COL_TEXT
            _rgb, hx = colorchooser.askcolor(
                color=cur, parent=dlg, title="选择任务文字颜色")
            if hx:
                _apply_text_color(hx)

        def _reset_text_color():
            _apply_text_color("")

        tk.Button(tc_row, text="选择颜色…", command=_pick_text_color,
                  bg=COL_ACCENT, fg="white", activebackground=COL_ACCENT_DARK,
                  activeforeground="white", relief="flat", bd=0, cursor="hand2",
                  font=(self.F_CUTE, 10, "bold"), padx=int(10 * s),
                  pady=int(3 * s)).pack(side="left", padx=(int(8 * s), 0))
        tk.Button(tc_row, text="恢复默认", command=_reset_text_color,
                  bg=COL_INPUT_BG, fg=COL_TEXT, activebackground=COL_BORDER,
                  relief="flat", bd=0, cursor="hand2", font=(self.F_CUTE, 10),
                  padx=int(10 * s), pady=int(3 * s)).pack(
                      side="left", padx=(int(6 * s), 0))
        _draw_swatch()

        # -- 悬浮图标 --
        sep2 = tk.Canvas(inner, height=int(8 * s), bg=COL_PANEL,
                         highlightthickness=0, bd=0)
        sep2.pack(fill="x", pady=(int(10 * s), int(6 * s)))
        sep2.bind("<Configure>", lambda e: (
            e.widget.delete("all"),
            sketch_line(e.widget, 2, 4, e.width - 2, 4, COL_SEP,
                        width=max(1, 1.1 * s), amp=1.0)))

        tk.Label(inner, text="悬浮图标 ◎", bg=COL_PANEL, fg=COL_TEXT,
                 font=(self.F_CUTE, 11, "bold")).pack(anchor="w")
        ic_row = tk.Frame(inner, bg=COL_PANEL)
        ic_row.pack(fill="x", pady=(int(4 * s), 0))
        tk.Button(ic_row, text="选择图标…",
                  command=lambda: self._choose_icon(icon_name_lbl),
                  bg=COL_ACCENT, fg="white", activebackground=COL_ACCENT_DARK,
                  activeforeground="white", relief="flat", bd=0, cursor="hand2",
                  font=(self.F_CUTE, 10, "bold"), padx=int(12 * s),
                  pady=int(3 * s)).pack(side="left")
        tk.Button(ic_row, text="清除",
                  command=lambda: self._clear_icon(icon_name_lbl),
                  bg=COL_INPUT_BG, fg=COL_TEXT, activebackground=COL_BORDER,
                  relief="flat", bd=0, cursor="hand2", font=(self.F_CUTE, 10),
                  padx=int(12 * s), pady=int(3 * s)).pack(side="left",
                                                         padx=(int(8 * s), 0))
        cur_ic = self.store.settings.get("iconImage") or ""
        icon_name_lbl = tk.Label(inner, text=("当前：" + Path(cur_ic).name)
                                 if cur_ic else "未设置（内置默认图标）",
                                 bg=COL_PANEL, fg=COL_SUB, font=(self.F_BODY, 8),
                                 anchor="w", wraplength=w - 40, justify="left")
        icon_name_lbl.pack(fill="x", pady=(int(3 * s), 0))

        # 图标大小自调节滑杆
        size_row = tk.Frame(inner, bg=COL_PANEL)
        size_row.pack(fill="x", pady=(int(6 * s), 0))
        tk.Label(size_row, text="大小", bg=COL_PANEL, fg=COL_TEXT,
                 font=(self.F_BODY, 9)).pack(side="left")
        cur_sz = int(self.store.settings.get("capSize", 48))
        size_val = tk.Label(size_row, text=str(cur_sz), bg=COL_PANEL,
                            fg=COL_SUB, font=(self.F_BODY, 9), width=3)
        size_val.pack(side="right")
        scale = ttk.Scale(size_row, from_=24, to=96, orient="horizontal",
                          command=lambda v: self._on_cap_size(v, size_val))
        scale.set(cur_sz)
        scale.pack(side="left", fill="x", expand=True, padx=int(6 * s))
        scale.bind("<ButtonRelease-1>", lambda e: self.store._save())

        def exit_app():
            self.root.destroy()

        tk.Button(inner, text="退出 FloatTask", command=exit_app,
                  bg=COL_INPUT_BG, fg=COL_TEXT, activebackground=COL_BORDER,
                  relief="flat", bd=0, cursor="hand2",
                  font=(self.F_CUTE, 10),
                  pady=int(4 * s)).pack(fill="x", side="bottom")
        dlg.bind("<Escape>", lambda e: self._close_popup(dlg))
        dlg.protocol("WM_DELETE_WINDOW", lambda: self._close_popup(dlg))

    def _choose_bg(self, name_lbl):
        path = filedialog.askopenfilename(
            parent=self._settings_dlg, title="选择背景图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                       ("所有文件", "*.*")])
        if not path:
            return
        self.store.settings["bgImage"] = path
        self.store._save()
        self._reload_bg()
        name_lbl.config(text="当前：" + Path(path).name)
        self._check_save_error()

    def _clear_bg(self, name_lbl):
        self.store.settings["bgImage"] = ""
        self.store._save()
        self._reload_bg()
        name_lbl.config(text="未设置（默认手绘奶油纸）")

    def _choose_icon(self, name_lbl):
        path = filedialog.askopenfilename(
            parent=self._settings_dlg, title="选择悬浮图标",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                       ("所有文件", "*.*")])
        if not path:
            return
        self.store.settings["iconImage"] = path
        self.store._save()
        self._draw_capsule()
        name_lbl.config(text="当前：" + Path(path).name)
        self._check_save_error()

    def _clear_icon(self, name_lbl):
        self.store.settings["iconImage"] = ""
        self.store._save()
        self._draw_capsule()
        name_lbl.config(text="未设置（内置默认图标）")

    def _on_cap_size(self, v, val_lbl):
        """滑杆实时调整胶囊大小；落盘在 ButtonRelease 时做"""
        n = int(round(float(v)))
        val_lbl.config(text=str(n))
        if self.store.settings.get("capSize") != n:
            self.store.settings["capSize"] = n
            self._draw_capsule()

    # ---------- 跨零点刷新 ----------
    def _tick(self):
        d = date.today().isoformat()
        if d != self.today:
            self.today = d
            self.tomorrow_mode = False     # 跨天：昨天的"明天"已成为今天
            self.refresh_header()
            self.refresh_list()
        self.root.after(30000, self._tick)


# ---------------- 自检（无 GUI） ----------------
def selftest():
    import tempfile
    d = Path(tempfile.gettempdir()) / "floattask_selftest"
    d.mkdir(exist_ok=True)
    p = d / DATA_FILE
    bak = d / (DATA_FILE + ".bak")
    for f in (p, bak):
        if f.exists():
            f.unlink()

    assert normalize_time("9:30") == "09:30"
    assert normalize_time("1430") == "14:30"
    assert normalize_time("25:00") is None
    assert normalize_time("abc") is None
    assert normalize_time("") == ""

    # 文字颜色：校验 / 默认配色 / 浅深自适应淡化
    assert normalize_color("#5b4a3a") == "#5B4A3A"
    assert normalize_color("#abc") == "#AABBCC"
    assert normalize_color(" abc") == "" and normalize_color("abc") == ""
    assert normalize_color("#12345") == "" and normalize_color(None) == ""
    d_main, d_sub, d_done = text_color_palette("")
    assert d_main == COL_TEXT and text_color_palette("oops")[0] == COL_TEXT
    assert _lum(d_main) < _lum(d_sub) < _lum(d_done)      # 默认逐级淡化
    l_main, l_sub, l_done = text_color_palette("#F2EDE4")  # 浅色文字往深色淡化
    assert _lum(l_done) < _lum(l_sub) < _lum(l_main)
    assert mix_color("#000000", "#FFFFFF", 0.5) == "#808080"

    s = TaskStore(p)
    a = s.add("写周报", "09:30")
    b = s.add("买咖啡", "")
    c = s.add("明天的事", "", day_offset=1)
    assert c["date"] == (date.today() + timedelta(days=1)).isoformat()
    s.toggle(a["id"])
    today_iso = date.today().isoformat()
    undone, done = s.today_view(today_iso)
    assert [t["id"] for t in undone] == [b["id"]] and len(done) == 1
    undone_tm, done_tm = s.day_view(c["date"])
    assert [t["id"] for t in undone_tm] == [c["id"]] and done_tm == []
    s.update(b["id"], "买两杯咖啡", "15:05")

    s2 = TaskStore(p)                       # 重启恢复
    assert len(s2.tasks) == 3
    assert s2.tasks[0]["done"] and s2.tasks[0]["completedAt"]
    assert s2.tasks[1]["text"] == "买两杯咖啡" and s2.tasks[1]["time"] == "15:05"
    assert s2.settings["textColor"] == ""            # 旧文件无此键 → 默认色

    s2.settings["textColor"] = "#F2EDE4"             # 文字颜色落盘 / 重读
    s2._save()
    assert TaskStore(p).settings["textColor"] == "#F2EDE4"
    raw = json.loads(p.read_text(encoding="utf-8"))  # 非法值容错 → 回退默认
    raw["settings"]["textColor"] = "not-a-color"
    p.write_text(json.dumps(raw), encoding="utf-8")
    assert TaskStore(p).settings["textColor"] == ""

    p.write_text("{oops", encoding="utf-8")  # 损坏容错
    s3 = TaskStore(p)
    assert s3.corrupted and s3.tasks == [] and bak.exists()

    print("SELFTEST OK")


# ---------------- 入口 ----------------
def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    ensure_single_instance()
    dpi = setup_dpi()
    store = TaskStore(data_dir() / DATA_FILE)
    root = tk.Tk()
    root.title(APP_TITLE)
    try:
        root.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        pass
    App(root, store, dpi / 96.0, resource_dir() / ICON_FILE)
    root.mainloop()


if __name__ == "__main__":
    main()
