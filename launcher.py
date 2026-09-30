"""
剪映 AI 自动剪辑 — 桌面启动器
双击即可运行，提供图形界面操作
"""

import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
from pathlib import Path

# 项目根目录
PROJECT_DIR = Path(__file__).parent
FFMPEG_DIR = r"C:\Users\Administrator.SCPC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin"
PYTHON = sys.executable


class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("剪映 AI 自动剪辑")
        self.root.geometry("700x520")
        self.root.resizable(True, True)
        self.root.configure(bg="#f0f0f0")

        # 设置环境变量
        env = os.environ.copy()
        env["PATH"] = FFMPEG_DIR + ";" + env.get("PATH", "")
        self.env = env

        self._build_ui()
        self._check_env()

    def _build_ui(self):
        # ── 标题 ──
        title = tk.Label(
            self.root, text="剪映 AI 自动剪辑", font=("Microsoft YaHei", 18, "bold"),
            bg="#f0f0f0", fg="#333"
        )
        title.pack(pady=(15, 5))

        subtitle = tk.Label(
            self.root, text="基于 AI 的全自动视频剪辑工具",
            font=("Microsoft YaHei", 10), bg="#f0f0f0", fg="#666"
        )
        subtitle.pack(pady=(0, 10))

        # ── 文件选择 ──
        file_frame = tk.LabelFrame(
            self.root, text=" 选择视频文件 ", font=("Microsoft YaHei", 10),
            bg="#f0f0f0", padx=10, pady=8
        )
        file_frame.pack(fill="x", padx=20, pady=5)

        self.file_path_var = tk.StringVar()
        file_entry = tk.Entry(
            file_frame, textvariable=self.file_path_var,
            font=("Consolas", 9), width=55
        )
        file_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = tk.Button(
            file_frame, text="浏览...", command=self._browse_file,
            font=("Microsoft YaHei", 9)
        )
        browse_btn.pack(side="right")

        # ── 功能按钮 ──
        btn_frame = tk.LabelFrame(
            self.root, text=" 功能 ", font=("Microsoft YaHei", 10),
            bg="#f0f0f0", padx=10, pady=10
        )
        btn_frame.pack(fill="x", padx=20, pady=5)

        buttons = [
            ("环境检查", self._run_check, "#4CAF50"),
            ("自动字幕", self._run_subtitle, "#2196F3"),
            ("智能剪辑", self._run_smart_cut, "#FF9800"),
            ("长转短", self._run_long_to_short, "#9C27B0"),
            ("全自动流水线", self._run_full_pipeline, "#F44336"),
        ]

        for i, (text, cmd, color) in enumerate(buttons):
            btn = tk.Button(
                btn_frame, text=text, command=cmd,
                font=("Microsoft YaHei", 10, "bold"),
                bg=color, fg="white", activebackground=color,
                relief="flat", cursor="hand2", width=12, height=1
            )
            btn.grid(row=0, column=i, padx=4, pady=2)

        # ── 输出区域 ──
        out_frame = tk.LabelFrame(
            self.root, text=" 运行输出 ", font=("Microsoft YaHei", 10),
            bg="#f0f0f0", padx=5, pady=5
        )
        out_frame.pack(fill="both", expand=True, padx=20, pady=5)

        self.output = scrolledtext.ScrolledText(
            out_frame, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white", wrap="word", state="disabled"
        )
        self.output.pack(fill="both", expand=True)

        # ── 状态栏 ──
        self.status_var = tk.StringVar(value="就绪")
        status_bar = tk.Label(
            self.root, textvariable=self.status_var,
            font=("Microsoft YaHei", 9), bg="#e0e0e0",
            anchor="w", padx=10
        )
        status_bar.pack(fill="x", side="bottom")

        # ── 提示 ──
        self._append_output(
            "欢迎使用剪映 AI 自动剪辑!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "使用方法:\n"
            "  1. 点击 [浏览] 选择视频文件\n"
            "  2. 选择功能按钮开始处理\n"
            "  3. 首次使用请先点击 [环境检查]\n"
            "\n"
            "提示: 请先编辑 .env 文件设置 API Key\n"
            f"  路径: {PROJECT_DIR / '.env'}\n"
        )

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm"),
                ("所有文件", "*.*"),
            ]
        )
        if path:
            self.file_path_var.set(path)

    def _append_output(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _check_env(self):
        """后台检查环境"""
        def _do_check():
            try:
                result = subprocess.run(
                    [PYTHON, "-m", "jy_auto_editor", "check"],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(PROJECT_DIR), env=self.env
                )
                self.root.after(0, lambda: self._append_output(
                    f"\n--- 环境检查 ---\n{result.stdout}\n"
                ))
            except Exception as e:
                self.root.after(0, lambda: self._append_output(
                    f"\n环境检查失败: {e}\n"
                ))
        threading.Thread(target=_do_check, daemon=True).start()

    def _run_command(self, args, label):
        """在后台线程运行命令"""
        video = self.file_path_var.get().strip()
        if not video and "check" not in args:
            self._append_output("\n[错误] 请先选择视频文件!\n")
            return

        self.status_var.set(f"正在执行: {label}...")
        self._append_output(f"\n{'='*40}\n>>> {label}\n{'='*40}\n")

        cmd = [PYTHON, "-m", "jy_auto_editor"] + args
        if video and "check" not in args:
            cmd.append(video)

        def _run():
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=str(PROJECT_DIR), env=self.env
                )
                for line in proc.stdout:
                    self.root.after(0, lambda l=line: self._append_output(l))
                proc.wait()
                self.root.after(0, lambda: self.status_var.set(
                    f"完成 (退出码: {proc.returncode})"
                ))
            except Exception as e:
                self.root.after(0, lambda: self._append_output(f"\n执行失败: {e}\n"))
                self.root.after(0, lambda: self.status_var.set("执行失败"))

        threading.Thread(target=_run, daemon=True).start()

    def _run_check(self):
        self._run_command(["check"], "环境检查")

    def _run_subtitle(self):
        self._run_command(["subtitle"], "自动字幕")

    def _run_smart_cut(self):
        self._run_command(["smart_cut"], "智能剪辑")

    def _run_long_to_short(self):
        self._run_command(["long_to_short"], "长转短")

    def _run_full_pipeline(self):
        self._run_command(["run"], "全自动流水线")


def main():
    root = tk.Tk()
    app = LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
