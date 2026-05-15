import argparse
import random
import sys
import time
import tkinter as tk
from datetime import datetime, timedelta

try:
    import winsound
except ImportError:
    winsound = None


DEFAULT_PROMPTS = [
    "回到当前这一页，继续看下一行。",
    "检查一下：现在是在主动学习，还是在滑走？",
    "把刚才的内容用一句话复述出来。",
    "眼睛离开屏幕 5 秒，回来继续。",
    "把注意力放回手上的题目或材料。",
    "写下当前小目标：接下来 8 分钟完成什么？",
    "如果卡住了，先标记问题，再继续推进。",
    "保持坐姿，喝一口水，然后继续。",
]


class StudyReminder:
    def __init__(self, args):
        self.args = args
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("学习提示")
        self.is_windows = sys.platform.startswith("win")

    def run(self):
        cycle_index = 1
        try:
            while self.args.cycles == 0 or cycle_index <= self.args.cycles:
                self.run_cycle(cycle_index)
                cycle_index += 1
        except KeyboardInterrupt:
            self.notify("已停止", "学习计时器已手动停止。", tone="end")
        finally:
            self.root.destroy()

    def run_cycle(self, cycle_index):
        start = time.monotonic()
        unit = self.args.unit_seconds
        focus_end = self.args.focus_minutes * unit
        rest_start = self.args.rest_start_minutes * unit
        cycle_end = self.args.cycle_minutes * unit

        self.notify(
            "开始学习",
            f"第 {cycle_index} 轮开始。前 {self.args.focus_minutes} 分钟会每 "
            f"{self.args.nudge_min}-{self.args.nudge_max} 分钟随机提示一次。",
            tone="start",
        )

        next_nudge = self.next_nudge_time(start)
        focus_end_sent = False
        rest_sent = False

        while True:
            now = time.monotonic()
            elapsed = now - start

            if elapsed >= cycle_end:
                self.notify("休息结束", "110 分钟周期结束，回到学习状态。", tone="start")
                return

            if not focus_end_sent and elapsed >= focus_end:
                self.notify("80 分钟提示", "已经学习 80 分钟。收束当前任务，准备进入休息前缓冲。", tone="stage")
                focus_end_sent = True

            if not rest_sent and elapsed >= rest_start:
                self.notify("开始休息", "已经到 90 分钟。现在休息 20 分钟，离开学习材料。", tone="rest")
                rest_sent = True

            if elapsed < focus_end and now >= next_nudge:
                self.notify("随机学习提示", random.choice(DEFAULT_PROMPTS), tone="nudge")
                next_nudge = self.next_nudge_time(now)

            self.pump_ui()
            time.sleep(0.2)

    def next_nudge_time(self, base_time):
        minutes = random.uniform(self.args.nudge_min, self.args.nudge_max)
        return base_time + minutes * self.args.unit_seconds

    def notify(self, title, message, tone):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {title} - {message}", flush=True)
        self.play_sound(tone)
        if not self.args.no_window:
            self.show_window(title, message, tone)

    def play_sound(self, tone):
        if self.args.no_sound:
            return

        if winsound is None:
            try:
                self.root.bell()
            except tk.TclError:
                pass
            return

        if tone == "nudge":
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        elif tone == "rest":
            winsound.Beep(660, 180)
            winsound.Beep(520, 220)
        elif tone == "end":
            winsound.MessageBeep(winsound.MB_ICONHAND)
        else:
            winsound.Beep(880, 160)
            winsound.Beep(1040, 160)

    def show_window(self, title, message, tone):
        colors = {
            "start": ("#0f766e", "#ecfeff"),
            "stage": ("#b45309", "#fffbeb"),
            "rest": ("#2563eb", "#eff6ff"),
            "nudge": ("#4f46e5", "#eef2ff"),
            "end": ("#525252", "#f5f5f5"),
        }
        accent, bg = colors.get(tone, colors["nudge"])

        window = tk.Toplevel(self.root)
        window.title(title)
        window.configure(bg=bg)
        window.attributes("-topmost", True)
        window.resizable(False, False)

        frame = tk.Frame(window, bg=bg, padx=28, pady=24)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text=title,
            fg=accent,
            bg=bg,
            font=("Microsoft YaHei UI", 20, "bold"),
        ).pack(anchor="w")

        tk.Label(
            frame,
            text=message,
            fg="#171717",
            bg=bg,
            justify="left",
            wraplength=420,
            font=("Microsoft YaHei UI", 12),
        ).pack(anchor="w", pady=(12, 18))

        deadline = datetime.now() + timedelta(seconds=self.args.window_seconds)
        countdown = tk.StringVar()

        button = tk.Button(
            frame,
            textvariable=countdown,
            command=window.destroy,
            relief="flat",
            bg=accent,
            fg="white",
            activebackground=accent,
            activeforeground="white",
            padx=18,
            pady=8,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        button.pack(anchor="e")

        def update_countdown():
            remaining = max(0, int((deadline - datetime.now()).total_seconds()))
            countdown.set(f"知道了 ({remaining}s)")
            if remaining <= 0:
                window.destroy()
            else:
                window.after(250, update_countdown)

        self.center_window(window, 520, 230)
        update_countdown()

    def center_window(self, window, width, height):
        window.update_idletasks()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 3
        window.geometry(f"{width}x{height}+{x}+{y}")

    def pump_ui(self):
        try:
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            pass


def positive_number(value):
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return number


def build_parser():
    parser = argparse.ArgumentParser(description="110 分钟学习周期随机提示器")
    parser.add_argument("--focus-minutes", type=positive_number, default=80)
    parser.add_argument("--rest-start-minutes", type=positive_number, default=90)
    parser.add_argument("--cycle-minutes", type=positive_number, default=110)
    parser.add_argument("--nudge-min", type=positive_number, default=8)
    parser.add_argument("--nudge-max", type=positive_number, default=10)
    parser.add_argument("--cycles", type=int, default=0, help="运行轮数，0 表示无限循环")
    parser.add_argument("--window-seconds", type=positive_number, default=12)
    parser.add_argument("--unit", choices=["minutes", "seconds"], default="minutes")
    parser.add_argument("--no-window", action="store_true")
    parser.add_argument("--no-sound", action="store_true")
    return parser


def validate_args(args):
    if args.nudge_min > args.nudge_max:
        raise SystemExit("--nudge-min 不能大于 --nudge-max")
    if not args.focus_minutes < args.rest_start_minutes < args.cycle_minutes:
        raise SystemExit("必须满足 focus < rest-start < cycle")
    args.unit_seconds = 1 if args.unit == "seconds" else 60
    return args


if __name__ == "__main__":
    parsed_args = validate_args(build_parser().parse_args())
    StudyReminder(parsed_args).run()
