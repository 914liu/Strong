"""
剪映 AI 自动剪辑 — 桌面启动器
双击 jy-launcher.bat 运行
"""

import os
import sys
import subprocess
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from pathlib import Path

# ── 路径配置 ──────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent
FFMPEG_DIR = r"C:\Users\Administrator.SCPC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin"
PYTHON = r"C:\Users\Administrator.SCPC\AppData\Local\Programs\Python\Python311\python.exe"
LOG_FILE = PROJECT_DIR / "launcher.log"

# 剪映路径 — 支持自定义安装位置
JIANYING_EXE = r"E:\剪映\JianyingPro\JianyingPro.exe"
JIANYING_DIR = r"E:\剪映\JianyingPro"
LOCAL_APP_DATA = os.environ.get("LOCALAPPDATA", r"C:\Users\Administrator.SCPC\AppData\Local")
JIANYING_DRAFT_DIR = LOCAL_APP_DATA + r"\JianyingPro\User Data\Projects\com.lveditor.draft"

# 设置环境变量
os.environ["PATH"] = FFMPEG_DIR + ";" + os.environ.get("PATH", "")
os.environ["PYTHONIOENCODING"] = "utf-8"


def log(msg):
    """写日志到文件"""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("剪映 AI 自动剪辑")
        self.root.geometry("750x580")
        self.root.resizable(True, True)
        self.root.configure(bg="#f5f5f5")

        self._build_ui()

        # 启动后自动检查环境
        self.root.after(500, self._auto_check)

    def _build_ui(self):
        # ── 标题 ──
        title = tk.Label(
            self.root, text="剪映 AI 自动剪辑",
            font=("Microsoft YaHei", 18, "bold"),
            bg="#f5f5f5", fg="#333",
        )
        title.pack(pady=(12, 2))

        subtitle = tk.Label(
            self.root, text="AI 全自动视频剪辑 → 直接导入剪映",
            font=("Microsoft YaHei", 10), bg="#f5f5f5", fg="#888",
        )
        subtitle.pack(pady=(0, 8))

        # ── 文件选择 ──
        file_frame = tk.LabelFrame(
            self.root, text=" 视频文件 ",
            font=("Microsoft YaHei", 10), bg="#f5f5f5", padx=10, pady=8,
        )
        file_frame.pack(fill="x", padx=15, pady=4)

        self.file_path_var = tk.StringVar()
        entry = tk.Entry(
            file_frame, textvariable=self.file_path_var,
            font=("Consolas", 9), width=55,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = tk.Button(
            file_frame, text="浏览...", command=self._browse_file,
            font=("Microsoft YaHei", 9),
        )
        browse_btn.pack(side="right")

        # ── 功能按钮 ──
        btn_frame = tk.LabelFrame(
            self.root, text=" 功能 ",
            font=("Microsoft YaHei", 10), bg="#f5f5f5", padx=10, pady=10,
        )
        btn_frame.pack(fill="x", padx=15, pady=4)

        buttons = [
            ("环境检查", self._run_check, "#4CAF50"),
            ("自动字幕", self._run_subtitle, "#2196F3"),
            ("智能剪辑", self._run_smart_cut, "#FF9800"),
            ("长转短", self._run_long_to_short, "#9C27B0"),
            ("全自动流水线", self._run_full_pipeline, "#E53935"),
        ]

        for i, (text, cmd, color) in enumerate(buttons):
            btn = tk.Button(
                btn_frame, text=text, command=cmd,
                font=("Microsoft YaHei", 10, "bold"),
                bg=color, fg="white", activebackground=color,
                activeforeground="white",
                relief="flat", cursor="hand2", width=12, height=1,
            )
            btn.grid(row=0, column=i, padx=3, pady=2)

        # ── 剪映操作 ──
        jy_frame = tk.LabelFrame(
            self.root, text=" 剪映 ",
            font=("Microsoft YaHei", 10), bg="#f5f5f5", padx=10, pady=8,
        )
        jy_frame.pack(fill="x", padx=15, pady=4)

        jy_btns = [
            ("打开剪映", self._open_jianying, "#1565C0"),
            ("打开草稿目录", self._open_draft_dir, "#00695C"),
            ("在剪映中打开草稿", self._open_draft_in_jianying, "#AD1457"),
        ]
        for i, (text, cmd, color) in enumerate(jy_btns):
            btn = tk.Button(
                jy_frame, text=text, command=cmd,
                font=("Microsoft YaHei", 10, "bold"),
                bg=color, fg="white", activebackground=color,
                activeforeground="white",
                relief="flat", cursor="hand2", width=16, height=1,
            )
            btn.grid(row=0, column=i, padx=6, pady=2)

        # ── 输出区域 ──
        out_frame = tk.LabelFrame(
            self.root, text=" 运行输出 ",
            font=("Microsoft YaHei", 10), bg="#f5f5f5", padx=5, pady=5,
        )
        out_frame.pack(fill="both", expand=True, padx=15, pady=4)

        self.output = scrolledtext.ScrolledText(
            out_frame, font=("Consolas", 9),
            bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white", wrap="word", state="disabled",
        )
        self.output.pack(fill="both", expand=True)

        # ── 状态栏 ──
        self.status_var = tk.StringVar(value="就绪")
        status_bar = tk.Label(
            self.root, textvariable=self.status_var,
            font=("Microsoft YaHei", 9), bg="#e0e0e0",
            anchor="w", padx=10,
        )
        status_bar.pack(fill="x", side="bottom")

        # ── 欢迎信息 ──
        self._append(
            "欢迎使用剪映 AI 自动剪辑!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  1. 点击 [浏览] 选择视频文件\n"
            "  2. 选择功能按钮开始处理\n"
            "  3. 处理完成后可直接在剪映中打开结果\n"
            "\n"
            f"剪映路径: {JIANYING_DIR}\n"
            f"草稿目录: {JIANYING_DRAFT_DIR}\n"
        )

    # ── 输出 ──────────────────────────────────────────────────────

    def _append(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    # ── 文件选择 ──────────────────────────────────────────────────

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.file_path_var.set(path)

    # ── 命令执行 ──────────────────────────────────────────────────

    def _run_cmd(self, args, label, need_video=True):
        """在后台线程运行 CLI 命令"""
        video = self.file_path_var.get().strip()
        if need_video and not video:
            self._append("\n[错误] 请先选择视频文件!\n")
            return

        self.status_var.set(f"正在执行: {label} ...")
        self._append(f"\n{'='*50}\n>>> {label}\n{'='*50}\n")

        cmd = [PYTHON, "-m", "jy_auto_editor"] + list(args)
        if video and need_video:
            cmd.append(video)

        log(f"Running: {' '.join(cmd)}")

        def _worker():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(PROJECT_DIR),
                    env=os.environ.copy(),
                    encoding="utf-8",
                    errors="replace",
                )
                for line in proc.stdout:
                    self.root.after(0, lambda l=line: self._append(l))
                proc.wait()
                code = proc.returncode
                self.root.after(0, lambda: self.status_var.set(
                    f"完成 (退出码: {code})"
                ))
                if code == 0:
                    self.root.after(0, lambda: self._append(
                        f"\n>>> {label} 完成!\n"
                    ))
                else:
                    self.root.after(0, lambda: self._append(
                        f"\n>>> {label} 失败 (退出码: {code})\n"
                    ))
                log(f"Exit code: {code}")
            except Exception as e:
                err = f"执行失败: {e}"
                log(f"ERROR: {err}\n{traceback.format_exc()}")
                self.root.after(0, lambda: self._append(f"\n{err}\n"))
                self.root.after(0, lambda: self.status_var.set("执行失败"))

        threading.Thread(target=_worker, daemon=True).start()

    # ── 功能按钮 ──────────────────────────────────────────────────

    def _auto_check(self):
        """启动时自动检查环境"""
        self._run_cmd(["check"], "环境检查", need_video=False)

    def _run_check(self):
        self._run_cmd(["check"], "环境检查", need_video=False)

    def _run_subtitle(self):
        self._run_cmd(["subtitle"], "自动字幕")

    def _run_smart_cut(self):
        self._run_cmd(["smart_cut"], "智能剪辑")

    def _run_long_to_short(self):
        self._run_cmd(["long_to_short"], "长转短")

    def _run_full_pipeline(self):
        self._run_cmd(["run"], "全自动流水线")

    # ── 剪映操作 ──────────────────────────────────────────────────

    def _open_jianying(self):
        """打开剪映"""
        # 查找剪映可执行文件
        jy_exe = self._find_jianying_exe()
        if jy_exe:
            self._append(f"\n>>> 正在打开剪映: {jy_exe}\n")
            try:
                subprocess.Popen([jy_exe], cwd=os.path.dirname(jy_exe))
                self.status_var.set("剪映已启动")
            except Exception as e:
                self._append(f"[错误] 无法启动剪映: {e}\n")
        else:
            # 尝试通过开始菜单启动
            self._append("\n>>> 未找到剪映可执行文件，尝试通过系统启动...\n")
            try:
                os.startfile("jianyingpro:")  # URI scheme
                self.status_var.set("剪映已启动")
            except Exception:
                self._append(
                    "[提示] 无法自动启动剪映，请手动打开。\n"
                    f"剪映数据目录: {JIANYING_DIR}\n"
                )

    def _open_draft_dir(self):
        """打开剪映草稿目录"""
        draft_dir = JIANYING_DRAFT_DIR
        if os.path.isdir(draft_dir):
            os.startfile(draft_dir)
            self._append(f"\n>>> 已打开草稿目录: {draft_dir}\n")
            self.status_var.set("草稿目录已打开")
        else:
            self._append(f"\n[提示] 草稿目录不存在: {draft_dir}\n")
            # 尝试打开上级目录
            if os.path.isdir(JIANYING_DIR):
                os.startfile(JIANYING_DIR)
                self._append(f">>> 已打开剪映目录: {JIANYING_DIR}\n")

    def _open_draft_in_jianying(self):
        """在剪映中打开最近的草稿"""
        draft_dir = JIANYING_DRAFT_DIR
        if not os.path.isdir(draft_dir):
            self._append(f"\n[提示] 草稿目录不存在: {draft_dir}\n")
            return

        # 查找最近的草稿
        drafts = []
        try:
            for entry in os.scandir(draft_dir):
                if entry.is_dir():
                    # 检查是否是有效的草稿目录
                    draft_json = os.path.join(entry.path, "draft_content.json")
                    if os.path.isfile(draft_json):
                        mtime = os.path.getmtime(draft_json)
                        drafts.append((mtime, entry.path, entry.name))
        except Exception as e:
            self._append(f"\n[错误] 读取草稿目录失败: {e}\n")
            return

        if not drafts:
            self._append("\n[提示] 没有找到任何草稿文件。\n")
            self._open_draft_dir()
            return

        # 按修改时间排序，打开最新的
        drafts.sort(reverse=True)
        latest = drafts[0]
        self._append(f"\n>>> 找到草稿: {latest[2]}\n")
        self._append(f">>> 路径: {latest[1]}\n")

        # 先打开剪映，然后打开草稿
        jy_exe = self._find_jianying_exe()
        if jy_exe:
            # 剪映支持通过命令行打开草稿
            draft_content = os.path.join(latest[1], "draft_content.json")
            try:
                subprocess.Popen([jy_exe, draft_content], cwd=os.path.dirname(jy_exe))
                self._append(">>> 已在剪映中打开草稿!\n")
                self.status_var.set("草稿已在剪映中打开")
            except Exception as e:
                self._append(f"[错误] 打开草稿失败: {e}\n")
                # 退而求其次，打开目录
                os.startfile(latest[1])
                self._append(">>> 已打开草稿目录，请手动在剪映中打开\n")
        else:
            # 直接打开草稿目录
            os.startfile(latest[1])
            self._append(
                ">>> 已打开草稿目录。\n"
                "    请在剪映中点击此草稿即可打开。\n"
            )

    def _find_jianying_exe(self):
        """查找剪映可执行文件"""
        # 已知路径（优先）
        if os.path.isfile(JIANYING_EXE):
            return JIANYING_EXE

        # 常见路径
        candidates = [
            os.path.join(JIANYING_DIR, "JianyingPro.exe"),
            os.path.join(LOCAL_APP_DATA, "JianyingPro", "JianyingPro.exe"),
            os.path.join(LOCAL_APP_DATA, "JianyingPro", "Apps", "JianyingPro.exe"),
        ]

        # 搜索 Apps 子目录
        apps_dir = os.path.join(JIANYING_DIR, "Apps")
        if os.path.isdir(apps_dir):
            try:
                for root, dirs, files in os.walk(apps_dir):
                    for f in files:
                        if f.lower() == "jianyingpro.exe":
                            candidates.append(os.path.join(root, f))
            except Exception:
                pass

        for path in candidates:
            if os.path.isfile(path):
                return path

        return None


# ── 主入口 ────────────────────────────────────────────────────────

def main():
    log("=" * 50)
    log(f"Launcher started at {__import__('datetime').datetime.now()}")
    log(f"Python: {sys.executable}")
    log(f"Project: {PROJECT_DIR}")

    try:
        root = tk.Tk()
        app = LauncherApp(root)
        root.mainloop()
    except Exception as e:
        log(f"FATAL: {e}\n{traceback.format_exc()}")
        # 写一个错误文件让用户能看到
        error_file = PROJECT_DIR / "launcher_error.txt"
        with open(error_file, "w", encoding="utf-8") as f:
            f.write(f"启动器出错:\n\n{e}\n\n{traceback.format_exc()}")
        messagebox.showerror("错误", f"启动器出错，详见 launcher_error.txt:\n{e}")


if __name__ == "__main__":
    main()
