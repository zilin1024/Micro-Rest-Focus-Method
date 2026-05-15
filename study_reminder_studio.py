import argparse
import math
import random
import sys
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime

try:
    import winsound
except ImportError:
    winsound = None


PROMPTS = [
    "闭眼 10 秒。把刚才看的内容在脑子里过一遍。",
    "检查一下：你还在原任务上吗？",
    "用一句话复述刚才学到的东西。",
    "松开肩膀，慢慢呼吸一次，然后继续。",
    "如果卡住了，先做标记，不要切走。",
    "把注意力放回当前这一行、这一题、这一页。",
    "你又完成了一小段。停 10 秒，再回来。",
    "不要换任务。提示音只是让你短暂停一下。",
]


THEMES = {
    "focus": {
        "bg_top": "#162235",
        "bg_bottom": "#0b1020",
        "panel": "#101827",
        "panel_2": "#172234",
        "line": "#2a3952",
        "text": "#f7fbff",
        "muted": "#93a4bb",
        "focus": "#65d6c3",
        "stage": "#f1b65d",
        "rest": "#8fb8ff",
        "danger": "#ff8a8a",
        "shadow": "#070b14",
    },
    "paper": {
        "bg_top": "#f6efe3",
        "bg_bottom": "#e7dccd",
        "panel": "#fffaf0",
        "panel_2": "#f3eadc",
        "line": "#b9aa98",
        "text": "#2f2a24",
        "muted": "#74685e",
        "focus": "#4f9b91",
        "stage": "#b98242",
        "rest": "#5f82bd",
        "danger": "#c9685b",
        "shadow": "#d3c5b6",
    },
}


@dataclass
class Config:
    focus_minutes: float = 80
    rest_start_minutes: float = 90
    cycle_minutes: float = 110
    nudge_min: float = 8
    nudge_max: float = 10
    cycles: int = 0
    window_seconds: float = 12
    unit_seconds: int = 60
    no_sound: bool = False
    theme: str = "focus"
    auto_close_seconds: float = 0

    @property
    def focus_end(self):
        return self.focus_minutes * self.unit_seconds

    @property
    def rest_start(self):
        return self.rest_start_minutes * self.unit_seconds

    @property
    def cycle_end(self):
        return self.cycle_minutes * self.unit_seconds

    def next_nudge_elapsed(self, elapsed):
        return elapsed + random.uniform(self.nudge_min, self.nudge_max) * self.unit_seconds


class StudyReminderStudio:
    def __init__(self, config):
        self.config = config
        self.colors = THEMES[config.theme]
        self.root = tk.Tk()
        self.root.title("学习节奏 Studio")
        self.root.geometry("1040x720")
        self.root.minsize(980, 660)
        self.root.configure(bg=self.colors["bg_bottom"])

        self.running = False
        self.paused = False
        self.started_at = None
        self.paused_at = None
        self.pause_total = 0.0
        self.elapsed_before_pause = 0.0
        self.cycle_index = 1
        self.next_nudge = None
        self.focus_sent = False
        self.rest_sent = False
        self.notice_windows = []
        self.pulse = 0
        self.last_second = -1

        self._build_ui()
        self._draw()
        if self.config.auto_close_seconds:
            self.root.after(int(self.config.auto_close_seconds * 1000), self.root.destroy)
        self.root.after(250, self._tick)

    def run(self):
        self.root.mainloop()

    def _build_ui(self):
        c = self.colors
        self.canvas = tk.Canvas(
            self.root,
            highlightthickness=0,
            bg=c["bg_bottom"],
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw())

        self.start_button = self._make_button("开始", self.start, c["focus"])
        self.pause_button = self._make_button("暂停", self.toggle_pause, c["stage"])
        self.reset_button = self._make_button("重置", self.reset, c["danger"])

        self.vars = {
            "focus": tk.StringVar(value=str(self.config.focus_minutes)),
            "rest_start": tk.StringVar(value=str(self.config.rest_start_minutes)),
            "cycle": tk.StringVar(value=str(self.config.cycle_minutes)),
            "nudge_min": tk.StringVar(value=str(self.config.nudge_min)),
            "nudge_max": tk.StringVar(value=str(self.config.nudge_max)),
        }
        self.unit_var = tk.StringVar(value="秒" if self.config.unit_seconds == 1 else "分钟")
        self.sound_var = tk.BooleanVar(value=not self.config.no_sound)

        self.entries = []
        for key in ("focus", "rest_start", "cycle", "nudge_min", "nudge_max"):
            entry = tk.Entry(
                self.root,
                textvariable=self.vars[key],
                width=7,
                relief="flat",
                justify="center",
                bg=c["panel_2"],
                fg=c["text"],
                insertbackground=c["text"],
                font=("Microsoft YaHei UI", 11, "bold"),
            )
            self.entries.append((key, entry))

        self.unit_menu = tk.OptionMenu(self.root, self.unit_var, "分钟", "秒")
        self.unit_menu.configure(
            relief="flat",
            highlightthickness=0,
            bg=c["panel_2"],
            fg=c["text"],
            activebackground=c["panel_2"],
            activeforeground=c["text"],
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.unit_menu["menu"].configure(
            bg=c["panel_2"],
            fg=c["text"],
            activebackground=c["focus"],
            activeforeground="#071014",
        )

        self.sound_check = tk.Checkbutton(
            self.root,
            text="提示音",
            variable=self.sound_var,
            relief="flat",
            borderwidth=0,
            bg=c["panel"],
            fg=c["text"],
            activebackground=c["panel"],
            activeforeground=c["text"],
            selectcolor=c["panel_2"],
            font=("Microsoft YaHei UI", 10, "bold"),
            command=self.apply_settings,
        )

        self.apply_button = self._make_button("应用设置", self.apply_settings, c["rest"])

    def _make_button(self, text, command, color):
        return tk.Button(
            self.root,
            text=text,
            command=command,
            relief="flat",
            bg=color,
            fg="#071014",
            activebackground=color,
            activeforeground="#071014",
            padx=18,
            pady=9,
            cursor="hand2",
            font=("Microsoft YaHei UI", 11, "bold"),
        )

    def start(self):
        if self.running and self.paused:
            self.toggle_pause()
            return
        if self.running:
            return
        if not self.apply_settings(silent=True):
            return
        self.running = True
        self.paused = False
        self.started_at = time.monotonic()
        self.pause_total = 0.0
        self.elapsed_before_pause = 0.0
        self.cycle_index = 1
        self._prepare_cycle(announce=True)
        self._draw()

    def toggle_pause(self):
        if not self.running:
            return
        if not self.paused:
            self.paused = True
            self.paused_at = time.monotonic()
            self.elapsed_before_pause = self.elapsed()
            self.pause_button.configure(text="继续")
            self._toast("已暂停", "当前学习周期已暂停。", "stage")
        else:
            self.paused = False
            self.pause_total += time.monotonic() - self.paused_at
            self.paused_at = None
            self.pause_button.configure(text="暂停")
            self._toast("继续", "回到当前学习周期。", "focus")
        self._draw()

    def reset(self):
        self.running = False
        self.paused = False
        self.started_at = None
        self.paused_at = None
        self.pause_total = 0.0
        self.elapsed_before_pause = 0.0
        self.cycle_index = 1
        self.next_nudge = None
        self.focus_sent = False
        self.rest_sent = False
        self.pause_button.configure(text="暂停")
        self._draw()

    def apply_settings(self, silent=False):
        try:
            focus = positive_number(self.vars["focus"].get())
            rest_start = positive_number(self.vars["rest_start"].get())
            cycle = positive_number(self.vars["cycle"].get())
            nudge_min = positive_number(self.vars["nudge_min"].get())
            nudge_max = positive_number(self.vars["nudge_max"].get())
        except ValueError:
            self._toast("设置有误", "所有时间都必须是大于 0 的数字。", "danger")
            return False
        if nudge_min > nudge_max:
            self._toast("设置有误", "随机提示的最小值不能大于最大值。", "danger")
            return False
        if not focus < rest_start < cycle:
            self._toast("设置有误", "必须满足：学习提示 < 休息开始 < 周期结束。", "danger")
            return False

        self.config.focus_minutes = focus
        self.config.rest_start_minutes = rest_start
        self.config.cycle_minutes = cycle
        self.config.nudge_min = nudge_min
        self.config.nudge_max = nudge_max
        self.config.unit_seconds = 1 if self.unit_var.get() == "秒" else 60
        self.config.no_sound = not self.sound_var.get()
        if not silent:
            self._toast("设置已应用", "新的学习节奏会在下一次开始时生效。", "focus")
        self._draw()
        return True

    def _prepare_cycle(self, announce=False):
        self.focus_sent = False
        self.rest_sent = False
        self.next_nudge = self.config.next_nudge_elapsed(0)
        self.last_second = -1
        if announce:
            self._toast(
                "开始学习",
                f"第 {self.cycle_index} 轮。前 {fmt_number(self.config.focus_minutes)} 分钟按随机提示短暂停顿。",
                "focus",
            )

    def elapsed(self):
        if not self.running or self.started_at is None:
            return 0.0
        if self.paused:
            return self.elapsed_before_pause
        return max(0.0, time.monotonic() - self.started_at - self.pause_total)

    def stage(self, elapsed):
        if not self.running:
            return "idle", "准备开始", self.colors["muted"]
        if self.paused:
            return "paused", "暂停中", self.colors["stage"]
        if elapsed < self.config.focus_end:
            return "focus", "学习中", self.colors["focus"]
        if elapsed < self.config.rest_start:
            return "buffer", "收束中", self.colors["stage"]
        if elapsed < self.config.cycle_end:
            return "rest", "休息中", self.colors["rest"]
        return "done", "切换中", self.colors["focus"]

    def _tick(self):
        if self.running and not self.paused:
            elapsed = self.elapsed()
            second = int(elapsed)
            if second != self.last_second:
                self.last_second = second
                self._check_events(elapsed)
        self.pulse = (self.pulse + 1) % 120
        self._draw()
        self.root.after(250, self._tick)

    def _check_events(self, elapsed):
        if elapsed >= self.config.cycle_end:
            self._toast("休息结束", "110 分钟周期结束，回到学习。", "focus")
            self.cycle_index += 1
            if self.config.cycles and self.cycle_index > self.config.cycles:
                self.running = False
                self._toast("完成", "设定轮数已经完成。", "focus")
                return
            self.started_at = time.monotonic()
            self.pause_total = 0.0
            self._prepare_cycle(announce=True)
            return

        if not self.focus_sent and elapsed >= self.config.focus_end:
            self.focus_sent = True
            self._toast("80 分钟提醒", "收束当前任务，准备进入休息前缓冲。", "stage")

        if not self.rest_sent and elapsed >= self.config.rest_start:
            self.rest_sent = True
            self._toast("开始休息", "现在休息 20 分钟。离开学习材料，别刷短内容。", "rest")

        if elapsed < self.config.focus_end and self.next_nudge is not None and elapsed >= self.next_nudge:
            self._toast("随机提示", random.choice(PROMPTS), "focus")
            self.next_nudge = self.config.next_nudge_elapsed(elapsed)

    def _draw(self):
        canvas = self.canvas
        width = max(canvas.winfo_width(), 980)
        height = max(canvas.winfo_height(), 660)
        canvas.delete("all")
        self._draw_background(width, height)
        self._draw_header(width)
        self._draw_ring(52, 126, 500, 470)
        self._draw_side_panel(584, 126, width - 52, 470)
        self._draw_timeline(52, 510, width - 52, 640)
        self._place_widgets(width)

    def _draw_background(self, width, height):
        c = self.colors
        steps = 80
        for i in range(steps):
            ratio = i / max(steps - 1, 1)
            color = blend(c["bg_top"], c["bg_bottom"], ratio)
            y1 = int(height * i / steps)
            y2 = int(height * (i + 1) / steps) + 1
            self.canvas.create_rectangle(0, y1, width, y2, outline="", fill=color)

        for x in range(30, width, 40):
            self.canvas.create_line(x, 0, x, height, fill=with_alpha(c["line"], 0.26), width=1)
        for y in range(28, height, 40):
            self.canvas.create_line(0, y, width, y, fill=with_alpha(c["line"], 0.24), width=1)

    def _draw_header(self, width):
        c = self.colors
        self.canvas.create_text(
            52,
            42,
            anchor="nw",
            text="学习节奏 Studio",
            fill=c["text"],
            font=("Microsoft YaHei UI", 28, "bold"),
        )
        self.canvas.create_text(
            52,
            84,
            anchor="nw",
            text="随机提示音 + 10 秒闭眼 + 90/20 循环",
            fill=c["muted"],
            font=("Microsoft YaHei UI", 12),
        )
        self._rounded_rect(width - 244, 42, width - 52, 88, 18, c["panel"], c["line"])
        self.canvas.create_text(
            width - 148,
            66,
            text=f"第 {self.cycle_index} 轮",
            fill=c["text"],
            font=("Microsoft YaHei UI", 14, "bold"),
        )

    def _draw_ring(self, x1, y1, x2, y2):
        c = self.colors
        self._panel(x1, y1, x2, y2)
        elapsed = self.elapsed()
        _stage_key, stage_text, stage_color = self.stage(elapsed)
        progress = clamp(elapsed / self.config.cycle_end, 0, 1) if self.running else 0
        remaining = max(0.0, self.config.cycle_end - elapsed)

        cx = (x1 + x2) / 2
        cy = y1 + 176
        radius = 122
        self.canvas.create_oval(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            outline=c["line"],
            width=20,
        )
        if progress > 0:
            self.canvas.create_arc(
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius,
                start=90,
                extent=-progress * 360,
                style="arc",
                outline=stage_color,
                width=20,
            )

        pulse_radius = 7 + math.sin(self.pulse / 10) * 2
        self.canvas.create_oval(
            cx - pulse_radius,
            cy - radius - 42 - pulse_radius,
            cx + pulse_radius,
            cy - radius - 42 + pulse_radius,
            fill=stage_color,
            outline="",
        )

        self.canvas.create_text(
            cx,
            cy - 36,
            text=stage_text,
            fill=stage_color,
            font=("Microsoft YaHei UI", 22, "bold"),
        )
        self.canvas.create_text(
            cx,
            cy + 12,
            text=format_clock(remaining),
            fill=c["text"],
            font=("Consolas", 40, "bold"),
        )
        self.canvas.create_text(
            cx,
            cy + 58,
            text="距离本轮结束",
            fill=c["muted"],
            font=("Microsoft YaHei UI", 12),
        )

        self._mini_metric(x1 + 34, y2 - 92, "已过", format_clock(elapsed), c["focus"])
        self._mini_metric(x1 + 184, y2 - 92, "下次提示", self.next_nudge_text(elapsed), c["stage"])
        self._mini_metric(x1 + 334, y2 - 92, "周期", f"{fmt_number(self.config.cycle_minutes)}m", c["rest"])

    def _mini_metric(self, x, y, label, value, color):
        c = self.colors
        self._rounded_rect(x, y, x + 120, y + 58, 16, c["panel_2"], c["line"])
        self.canvas.create_text(x + 16, y + 14, anchor="nw", text=label, fill=c["muted"], font=("Microsoft YaHei UI", 9))
        self.canvas.create_text(x + 16, y + 32, anchor="nw", text=value, fill=color, font=("Consolas", 14, "bold"))

    def next_nudge_text(self, elapsed):
        if not self.running:
            return "--:--"
        if elapsed >= self.config.focus_end or self.next_nudge is None:
            return "无"
        return format_clock(max(0, self.next_nudge - elapsed))

    def _draw_side_panel(self, x1, y1, x2, y2):
        c = self.colors
        self._panel(x1, y1, x2, y2)
        self.canvas.create_text(x1 + 28, y1 + 26, anchor="nw", text="控制台", fill=c["text"], font=("Microsoft YaHei UI", 22, "bold"))
        self.canvas.create_text(
            x1 + 28,
            y1 + 64,
            anchor="nw",
            text="开始后窗口可以放在旁边，当作你的学习仪表盘。",
            fill=c["muted"],
            font=("Microsoft YaHei UI", 11),
        )

        labels = [
            ("focus", "80 分钟提示"),
            ("rest_start", "90 分钟休息"),
            ("cycle", "110 分钟周期"),
            ("nudge_min", "随机最小"),
            ("nudge_max", "随机最大"),
        ]
        y = y1 + 118
        for i, (key, label) in enumerate(labels):
            col = i % 2
            row = i // 2
            lx = x1 + 28 + col * 180
            ly = y + row * 62
            self.canvas.create_text(lx, ly, anchor="nw", text=label, fill=c["muted"], font=("Microsoft YaHei UI", 10))
            self.canvas.create_window(lx, ly + 22, anchor="nw", width=82, height=30, window=dict(self.entries)[key])

        self.canvas.create_text(x1 + 28, y + 190, anchor="nw", text="单位", fill=c["muted"], font=("Microsoft YaHei UI", 10))
        self.canvas.create_window(x1 + 28, y + 214, anchor="nw", width=96, height=34, window=self.unit_menu)
        self.canvas.create_window(x1 + 144, y + 214, anchor="nw", width=92, height=34, window=self.sound_check)
        self.canvas.create_window(x1 + 260, y + 214, anchor="nw", width=118, height=34, window=self.apply_button)

    def _draw_timeline(self, x1, y1, x2, y2):
        c = self.colors
        self._panel(x1, y1, x2, y2)
        self.canvas.create_text(x1 + 26, y1 + 22, anchor="nw", text="本轮时间线", fill=c["text"], font=("Microsoft YaHei UI", 18, "bold"))
        axis_x1 = x1 + 78
        axis_x2 = x2 - 78
        axis_y = y1 + 78
        self.canvas.create_line(axis_x1, axis_y, axis_x2, axis_y, fill=c["line"], width=10, capstyle="round")

        def pos(value):
            return axis_x1 + (axis_x2 - axis_x1) * clamp(value / self.config.cycle_end, 0, 1)

        segments = [
            (0, self.config.focus_end, c["focus"], "学习"),
            (self.config.focus_end, self.config.rest_start, c["stage"], "收束"),
            (self.config.rest_start, self.config.cycle_end, c["rest"], "休息"),
        ]
        for start, end, color, label in segments:
            self.canvas.create_line(pos(start), axis_y, pos(end), axis_y, fill=color, width=10, capstyle="round")
            self.canvas.create_text((pos(start) + pos(end)) / 2, axis_y + 30, text=label, fill=color, font=("Microsoft YaHei UI", 11, "bold"))

        markers = [
            (0, "0"),
            (self.config.focus_end, f"{fmt_number(self.config.focus_minutes)}"),
            (self.config.rest_start, f"{fmt_number(self.config.rest_start_minutes)}"),
            (self.config.cycle_end, f"{fmt_number(self.config.cycle_minutes)}"),
        ]
        for value, label in markers:
            px = pos(value)
            self.canvas.create_oval(px - 10, axis_y - 10, px + 10, axis_y + 10, fill=c["panel"], outline=c["text"], width=2)
            self.canvas.create_text(px, axis_y - 28, text=label, fill=c["text"], font=("Consolas", 12, "bold"))

        elapsed = self.elapsed()
        if self.running:
            px = pos(elapsed)
            self.canvas.create_oval(px - 13, axis_y - 13, px + 13, axis_y + 13, fill="#ffffff", outline=self.stage(elapsed)[2], width=4)

    def _place_widgets(self, width):
        y = 42
        self.canvas.create_window(width - 486, y, anchor="nw", width=92, height=44, window=self.start_button)
        self.canvas.create_window(width - 386, y, anchor="nw", width=92, height=44, window=self.pause_button)
        self.canvas.create_window(width - 286, y, anchor="nw", width=92, height=44, window=self.reset_button)

    def _panel(self, x1, y1, x2, y2):
        c = self.colors
        self._rounded_rect(x1 + 8, y1 + 10, x2 + 8, y2 + 10, 28, c["shadow"], "")
        self._rounded_rect(x1, y1, x2, y2, 28, c["panel"], c["line"])

    def _rounded_rect(self, x1, y1, x2, y2, radius, fill, outline):
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        self.canvas.create_polygon(points, smooth=True, fill=fill, outline=outline, width=1.5 if outline else 0)

    def _toast(self, title, message, tone):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {title} - {message}", flush=True)
        self._play_sound(tone)
        self._notice(title, message, tone)

    def _play_sound(self, tone):
        if self.config.no_sound:
            return
        if winsound is None:
            try:
                self.root.bell()
            except tk.TclError:
                pass
            return
        if tone == "focus":
            winsound.Beep(880, 110)
            winsound.Beep(1175, 130)
        elif tone == "stage":
            winsound.Beep(784, 120)
            winsound.Beep(659, 160)
        elif tone == "rest":
            winsound.Beep(523, 160)
            winsound.Beep(392, 220)
        else:
            winsound.MessageBeep(winsound.MB_ICONHAND)

    def _notice(self, title, message, tone):
        c = self.colors
        accent = {
            "focus": c["focus"],
            "stage": c["stage"],
            "rest": c["rest"],
            "danger": c["danger"],
        }.get(tone, c["focus"])

        win = tk.Toplevel(self.root)
        win.title(title)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.configure(bg=c["bg_bottom"])

        canvas = tk.Canvas(win, width=560, height=260, highlightthickness=0, bg=c["bg_bottom"])
        canvas.pack(fill="both", expand=True)
        self._draw_notice_card(canvas, title, message, accent)

        close_after = int(max(1, self.config.window_seconds) * 1000)
        win.after(close_after, lambda: self._safe_destroy(win))
        self._center(win, 560, 260)
        self.notice_windows.append(win)

    def _draw_notice_card(self, canvas, title, message, accent):
        c = self.colors
        canvas.create_rectangle(0, 0, 560, 260, fill=c["bg_bottom"], outline="")
        for i in range(44):
            x = 24 + i * 13
            canvas.create_line(x, 0, x - 64, 260, fill=with_alpha(c["line"], 0.22), width=1)
        canvas.create_oval(392, -78, 620, 150, fill=with_alpha(accent, 0.28), outline="")
        canvas.create_oval(-64, 176, 120, 360, fill=with_alpha(accent, 0.18), outline="")
        rounded_rect_on(canvas, 34, 34, 526, 226, 28, c["panel"], c["line"])
        canvas.create_rectangle(58, 58, 92, 64, fill=accent, outline="")
        canvas.create_text(58, 82, anchor="nw", text=title, fill=c["text"], font=("Microsoft YaHei UI", 24, "bold"))
        canvas.create_text(
            58,
            126,
            anchor="nw",
            text=message,
            fill=c["muted"],
            width=430,
            font=("Microsoft YaHei UI", 13),
        )
        canvas.create_text(466, 198, text="自动关闭", fill=accent, font=("Microsoft YaHei UI", 10, "bold"))

    def _safe_destroy(self, win):
        try:
            win.destroy()
        except tk.TclError:
            pass

    def _center(self, win, width, height):
        win.update_idletasks()
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 3
        win.geometry(f"{width}x{height}+{x}+{y}")


def rounded_rect_on(canvas, x1, y1, x2, y2, radius, fill, outline):
    points = [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]
    canvas.create_polygon(points, smooth=True, fill=fill, outline=outline, width=1.5)


def positive_number(value):
    number = float(value)
    if number <= 0:
        raise ValueError("value must be greater than 0")
    return number


def validate_config(config):
    if config.nudge_min > config.nudge_max:
        raise SystemExit("--nudge-min 不能大于 --nudge-max")
    if not config.focus_minutes < config.rest_start_minutes < config.cycle_minutes:
        raise SystemExit("必须满足 focus < rest-start < cycle")
    return config


def format_clock(seconds):
    seconds = max(0, int(round(seconds)))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def fmt_number(value):
    if int(value) == value:
        return str(int(value))
    return f"{value:g}"


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def blend(hex_a, hex_b, ratio):
    a = hex_to_rgb(hex_a)
    b = hex_to_rgb(hex_b)
    mixed = tuple(int(a[i] + (b[i] - a[i]) * ratio) for i in range(3))
    return rgb_to_hex(mixed)


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def with_alpha(hex_color, alpha):
    # Tkinter does not support alpha colors, so blend against the focus theme's dark base.
    base = hex_to_rgb("#0b1020")
    color = hex_to_rgb(hex_color)
    mixed = tuple(int(base[i] + (color[i] - base[i]) * alpha) for i in range(3))
    return rgb_to_hex(mixed)


def build_parser():
    parser = argparse.ArgumentParser(description="精美可视化版 110 分钟学习周期提示器")
    parser.add_argument("--focus-minutes", type=positive_number, default=80)
    parser.add_argument("--rest-start-minutes", type=positive_number, default=90)
    parser.add_argument("--cycle-minutes", type=positive_number, default=110)
    parser.add_argument("--nudge-min", type=positive_number, default=8)
    parser.add_argument("--nudge-max", type=positive_number, default=10)
    parser.add_argument("--cycles", type=int, default=0, help="运行轮数，0 表示无限循环")
    parser.add_argument("--window-seconds", type=positive_number, default=10)
    parser.add_argument("--unit", choices=["minutes", "seconds"], default="minutes")
    parser.add_argument("--theme", choices=sorted(THEMES), default="focus")
    parser.add_argument("--no-sound", action="store_true")
    parser.add_argument("--auto-close-seconds", type=positive_number, default=0)
    parser.add_argument("--self-test", action="store_true", help="只验证参数和核心时间计算，不打开窗口")
    return parser


def config_from_args(args):
    return validate_config(
        Config(
            focus_minutes=args.focus_minutes,
            rest_start_minutes=args.rest_start_minutes,
            cycle_minutes=args.cycle_minutes,
            nudge_min=args.nudge_min,
            nudge_max=args.nudge_max,
            cycles=args.cycles,
            window_seconds=args.window_seconds,
            unit_seconds=1 if args.unit == "seconds" else 60,
            no_sound=args.no_sound,
            theme=args.theme,
            auto_close_seconds=args.auto_close_seconds,
        )
    )


def run_self_test(config):
    random.seed(7)
    samples = [round(config.next_nudge_elapsed(0), 3) for _ in range(5)]
    assert all(config.nudge_min * config.unit_seconds <= item <= config.nudge_max * config.unit_seconds for item in samples)
    assert config.focus_end < config.rest_start < config.cycle_end
    print("self-test ok")
    print(f"focus_end={config.focus_end}")
    print(f"rest_start={config.rest_start}")
    print(f"cycle_end={config.cycle_end}")
    print(f"nudge_samples={samples}")


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    cfg = config_from_args(parsed)
    if parsed.self_test:
        run_self_test(cfg)
        sys.exit(0)
    StudyReminderStudio(cfg).run()
