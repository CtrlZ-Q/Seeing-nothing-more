import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
from pathlib import Path
import threading

from organize import (
    generate_report, format_size, get_scenario_description,
    rank_duplicate_files, AIAdvisor, build_viz_data,
)

try:
    import matplotlib
    matplotlib.use("TkAgg")
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("不会动文件的 AI 扫描器")
        self.root.geometry("1100x750")
        self.root.configure(bg="#faf8f5")

        # 顶部：标题和说明
        header = tk.Frame(root, bg="#faf8f5", padx=25, pady=20)
        header.pack(fill=tk.X)

        tk.Label(header, text="不会动文件的 AI 扫描器",
                font=("Georgia", 22), bg="#faf8f5", fg="#2d2520").pack(anchor=tk.W)
        tk.Label(header, text="扫描文件夹，生成整理建议。只写报告，不移动、不删除、不重命名原文件。",
                font=("微软雅黑", 10), bg="#faf8f5", fg="#8b7d6b").pack(anchor=tk.W, pady=(5, 0))

        # 输入区
        input_frame = tk.Frame(root, bg="#fffefb", padx=25, pady=20)
        input_frame.pack(fill=tk.X, padx=20, pady=(0, 15))

        tk.Label(input_frame, text="文件夹路径", font=("微软雅黑", 11, "bold"),
                bg="#fffefb", fg="#2d2520").pack(anchor=tk.W, pady=(0, 8))

        path_row = tk.Frame(input_frame, bg="#fffefb")
        path_row.pack(fill=tk.X)

        self.path_entry = tk.Entry(path_row, font=("微软雅黑", 11), relief=tk.SOLID,
                                   bd=2, highlightthickness=0, highlightbackground="#e8dfd5",
                                   highlightcolor="#c17145")
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)

        # 拖放支持
        self.path_entry.drop_target_register(DND_FILES)
        self.path_entry.dnd_bind('<<Drop>>', self.on_drop)

        btn_frame = tk.Frame(path_row, bg="#fffefb")
        btn_frame.pack(side=tk.LEFT, padx=(10, 0))

        tk.Button(btn_frame, text="选择", command=self.select_folder,
                 bg="#f5ebe0", fg="#2d2520", font=("微软雅黑", 10, "bold"),
                 relief=tk.FLAT, padx=18, pady=7, cursor="hand2").pack(side=tk.LEFT, padx=(0, 8))

        self.scan_btn = tk.Button(btn_frame, text="开始扫描", command=self.start_scan,
                                  bg="#c17145", fg="white", font=("微软雅黑", 10, "bold"),
                                  relief=tk.FLAT, padx=22, pady=7, cursor="hand2")
        self.scan_btn.pack(side=tk.LEFT)

        self.cancel_btn = tk.Button(btn_frame, text="取消", command=self.cancel_scan,
                                    bg="#d04a2e", fg="white", font=("微软雅黑", 10),
                                    relief=tk.FLAT, padx=14, pady=7, cursor="hand2",
                                    state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.viz_btn = tk.Button(btn_frame, text="📊 可视化", command=self.show_charts,
                                 bg="#5a8c3e", fg="white", font=("微软雅黑", 10, "bold"),
                                 relief=tk.FLAT, padx=14, pady=7, cursor="hand2",
                                 state=tk.DISABLED)
        self.viz_btn.pack(side=tk.LEFT, padx=(8, 0))

        # 场景选择
        scenario_frame = tk.Frame(input_frame, bg="#fffefb")
        scenario_frame.pack(fill=tk.X, pady=(15, 0))

        tk.Label(scenario_frame, text="扫描场景", font=("微软雅黑", 11, "bold"),
                bg="#fffefb", fg="#2d2520").pack(side=tk.LEFT, padx=(0, 10))

        self.scenario_var = tk.StringVar(value="通用")
        scenarios = ["通用", "下载整理", "工作文档", "学习资料", "照片整理"]

        for scenario in scenarios:
            desc = get_scenario_description(scenario)
            tooltip = f"{scenario}: {desc}" if desc else scenario
            rb = tk.Radiobutton(scenario_frame, text=scenario, variable=self.scenario_var,
                               value=scenario, bg="#fffefb", fg="#2d2520",
                               font=("微软雅黑", 10), selectcolor="#faf8f5",
                               activebackground="#fffefb", cursor="hand2")
            rb.pack(side=tk.LEFT, padx=(0, 15))

        # AI 整理顾问配置
        ai_frame = tk.Frame(input_frame, bg="#fffefb")
        ai_frame.pack(fill=tk.X, pady=(12, 0))

        self.ai_var = tk.BooleanVar(value=False)
        ai_check = tk.Checkbutton(ai_frame, text="生成 AI 整理建议", variable=self.ai_var,
                                   bg="#fffefb", fg="#2d2520", font=("微软雅黑", 10),
                                   selectcolor="#faf8f5", activebackground="#fffefb",
                                   cursor="hand2", command=self.toggle_ai_config)
        ai_check.pack(side=tk.LEFT)

        self.ai_config_frame = tk.Frame(ai_frame, bg="#fffefb")

        tk.Label(self.ai_config_frame, text="API Key", font=("微软雅黑", 9),
                 bg="#fffefb", fg="#6b5640").pack(side=tk.LEFT, padx=(15, 4))
        self.api_key_entry = tk.Entry(self.ai_config_frame, font=("微软雅黑", 9),
                                       show="*", width=24, relief=tk.SOLID, bd=1)
        self.api_key_entry.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(self.ai_config_frame, text="Base URL", font=("微软雅黑", 9),
                 bg="#fffefb", fg="#6b5640").pack(side=tk.LEFT, padx=(0, 4))
        self.base_url_entry = tk.Entry(self.ai_config_frame, font=("微软雅黑", 9),
                                        width=28, relief=tk.SOLID, bd=1)
        self.base_url_entry.insert(0, "https://api.openai.com/v1")
        self.base_url_entry.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(self.ai_config_frame, text="模型", font=("微软雅黑", 9),
                 bg="#fffefb", fg="#6b5640").pack(side=tk.LEFT, padx=(0, 4))
        self.model_entry = tk.Entry(self.ai_config_frame, font=("微软雅黑", 9),
                                     width=14, relief=tk.SOLID, bd=1)
        self.model_entry.insert(0, "gpt-4o-mini")
        self.model_entry.pack(side=tk.LEFT)

        # 统计卡片区
        self.stats_frame = tk.Frame(root, bg="#faf8f5", padx=20)
        self.stats_frame.pack(fill=tk.X, pady=(0, 15))

        # 进度条
        self.progress_frame = tk.Frame(root, bg="#faf8f5", padx=20)
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode="indeterminate", length=400)
        self.progress_label = tk.Label(self.progress_frame, text="", bg="#faf8f5",
                                        font=("微软雅黑", 9), fg="#8b7d6b")
        self.progress_bar.pack(fill=tk.X, pady=(0, 2))
        self.progress_label.pack(anchor=tk.W)

        self.cancel_flag = threading.Event()
        self._viz_data = None

        # 手风琴结果区
        self.result_container = tk.Frame(root, bg="#faf8f5")
        self.result_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))

        self.accordion_sections = {}
        self.accordion_bodies = {}
        self.create_empty_result_view()

        # 状态栏
        self.status_label = tk.Label(root, text="就绪", anchor=tk.W, bg="#f5ebe0",
                                     font=("微软雅黑", 10), fg="#6b5640", padx=25, pady=10)
        self.status_label.pack(fill=tk.X, side=tk.BOTTOM)

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, folder)

    def on_drop(self, event):
        # 拖放的路径格式：{C:/path/to/folder} 或 {path1} {path2}
        raw = event.data.strip()
        # 移除首尾的大括号对
        if raw.startswith('{') and raw.endswith('}'):
            path = raw[1:-1]
        elif raw.startswith('{'):
            # 多个路径：{path1} {path2}，取第一个
            path = raw.split('}')[0][1:]
        else:
            path = raw
        if path:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, path)
        return event.action

    def toggle_ai_config(self):
        if self.ai_var.get():
            self.ai_config_frame.pack(fill=tk.X, pady=(8, 0))
        else:
            self.ai_config_frame.pack_forget()

    def start_scan(self):
        folder = self.path_entry.get().strip()
        if not folder:
            self.status_label.config(text="⚠ 请输入文件夹路径", fg="#d04a2e")
            return

        root = Path(folder)
        if not root.exists():
            self.status_label.config(text="⚠ 路径不存在", fg="#d04a2e")
            return
        if not root.is_dir():
            self.status_label.config(text="⚠ 不是文件夹", fg="#d04a2e")
            return

        # AI 整理顾问校验
        advisor = None
        if self.ai_var.get():
            api_key = self.api_key_entry.get().strip()
            if not api_key:
                self.status_label.config(text="⚠ 请输入 API Key", fg="#d04a2e")
                return
            try:
                advisor = AIAdvisor(
                    api_key=api_key,
                    base_url=self.base_url_entry.get().strip(),
                    model=self.model_entry.get().strip(),
                    scenario=self.scenario_var.get(),
                )
            except Exception as exc:
                self.status_label.config(text=f"⚠ AI 初始化失败：{exc}", fg="#d04a2e")
                return

        self.cancel_flag.clear()
        self.scan_btn.config(state=tk.DISABLED, text="扫描中...", bg="#8b7d6b")
        self.cancel_btn.config(state=tk.NORMAL)
        self.viz_btn.config(state=tk.DISABLED)
        self.status_label.config(text="🔍 正在扫描，请稍候...", fg="#c17145")
        self.progress_frame.pack(fill=tk.X, padx=20, pady=(0, 5))
        self.progress_bar.start(15)
        self.clear_result_view()

        for widget in self.stats_frame.winfo_children():
            widget.destroy()

        threading.Thread(target=self.run_scan, args=(root, advisor), daemon=True).start()

    def update_progress(self, count, current_file):
        self.root.after(0, self._update_progress_ui, count, current_file)

    def _update_progress_ui(self, count, current_file):
        self.progress_label.config(text=f"已扫描 {count} 个文件：{current_file[:60]}")

    def cancel_scan(self):
        self.cancel_flag.set()
        self.status_label.config(text="⏹ 正在取消...", fg="#d97845")

    def run_scan(self, root, advisor):
        try:
            scenario = self.scenario_var.get()

            def progress_cb(count, path):
                if self.cancel_flag.is_set():
                    raise InterruptedError("用户取消扫描")
                self.update_progress(count, path)

            report_path, files, duplicates, cleanup_candidates, action_items, ai_advice = generate_report(
                root, scenario, advisor=advisor, progress_cb=progress_cb,
            )
            report = report_path.read_text(encoding="utf-8")

            total_size = sum(f.size for f in files)
            read_errors = sum(1 for f in files if f.read_error)
            avg_health = sum(f.health_score for f in files) // len(files) if files else 0

            viz_data = build_viz_data(files, duplicates, cleanup_candidates)

            self.root.after(0, self.show_result, report, files, duplicates, cleanup_candidates, action_items,
                          len(files), total_size, len(duplicates), read_errors, avg_health, str(report_path), viz_data, ai_advice)
        except InterruptedError:
            self.root.after(0, self.show_cancelled)
        except Exception as e:
            self.root.after(0, self.show_error, str(e))

    def show_result(self, report, files, duplicates, cleanup_candidates, action_items, file_count, total_size, dup_groups, errors, avg_health, report_path, viz_data=None, ai_advice=None):
        # 显示统计卡片
        stats = [
            ("📁 文件数量", str(file_count), "#c17145"),
            ("💾 总大小", format_size(total_size), "#a25a32"),
            ("✅ 待办项", str(len(action_items)), "#d97845"),
            ("🧹 清理候选", str(len(cleanup_candidates)), "#b45f3c"),
            ("💯 健康分", str(avg_health), "#5a8c3e"),
            ("🔄 重复组", str(dup_groups), "#d97845"),
            ("⚠️ 读取问题", str(errors), "#d04a2e")
        ]

        for label, value, color in stats:
            card = tk.Frame(self.stats_frame, bg="#fffefb", relief=tk.FLAT)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=5)

            tk.Label(card, text=value, font=("Georgia", 24),
                    bg="#fffefb", fg=color).pack(pady=(15, 5))
            tk.Label(card, text=label, font=("微软雅黑", 10),
                    fg="#8b7d6b", bg="#fffefb").pack(pady=(0, 15))

        self.clear_result_view()
        self.create_result_scroll_view()

        todo_body = self.add_accordion_section(
            "todo", "✅ 待办清单", f"{len(action_items)} 个建议动作，先处理高优先级", True
        )
        self.fill_todo_section(todo_body, action_items)

        cleanup_body = self.add_accordion_section(
            "cleanup", "🧹 垃圾/缓存", f"发现 {len(cleanup_candidates)} 个清理候选", True
        )
        self.fill_cleanup_section(cleanup_body, cleanup_candidates)

        if ai_advice:
            ai_body = self.add_accordion_section(
                "ai_advice", "🤖 AI 整理建议", "基于扫描摘要生成，不包含 API 配置", True
            )
            self.fill_ai_advice_section(ai_body, ai_advice)

        health_body = self.add_accordion_section(
            "health", "💯 健康评分", f"平均 {avg_health}/100，优先查看低分文件", False
        )
        self.fill_health_section(health_body, files, avg_health)

        category_body = self.add_accordion_section(
            "category", "📊 分类统计", "查看文件按类型分布", False
        )
        self.fill_category_section(category_body, files)

        duplicate_body = self.add_accordion_section(
            "duplicates", "🔄 重复文件", f"发现 {dup_groups} 组重复文件", True
        )
        self.fill_duplicate_section(duplicate_body, duplicates)

        move_body = self.add_accordion_section(
            "moves", "🧭 整理建议", "按建议文件夹查看移动方向", False
        )
        self.fill_move_section(move_body, files)

        full_body = self.add_accordion_section(
            "full", "📄 完整 Markdown", "保留完整原始报告，需要时展开", False
        )
        self.fill_full_report_section(full_body, report, report_path)

        self._viz_data = viz_data
        self.scan_btn.config(state=tk.NORMAL, text="开始扫描", bg="#c17145")
        self.cancel_btn.config(state=tk.DISABLED)
        self.viz_btn.config(state=tk.NORMAL if viz_data else tk.DISABLED)
        self.progress_bar.stop()
        self.progress_frame.pack_forget()
        self.status_label.config(text=f"✓ 扫描完成！报告已保存：{report_path}", fg="#6b5640")

    def show_cancelled(self):
        self.scan_btn.config(state=tk.NORMAL, text="开始扫描", bg="#c17145")
        self.cancel_btn.config(state=tk.DISABLED)
        self.progress_bar.stop()
        self.progress_frame.pack_forget()
        self.status_label.config(text="⏹ 扫描已取消", fg="#d97845")

    def clear_result_view(self):
        for widget in self.result_container.winfo_children():
            widget.destroy()
        self.accordion_sections = {}
        self.accordion_bodies = {}

    def create_empty_result_view(self):
        self.clear_result_view()
        placeholder = tk.Frame(self.result_container, bg="#faf8f5", padx=30, pady=35)
        placeholder.pack(fill=tk.BOTH, expand=True)
        tk.Label(placeholder, text="扫描后，这里会按区块展示结果",
                 font=("微软雅黑", 16, "bold"), bg="#faf8f5", fg="#2d2520").pack(anchor=tk.W)
        tk.Label(placeholder, text="默认展开待办清单、垃圾缓存和重复文件；完整 Markdown 报告会收起，页面更清爽。",
                 font=("微软雅黑", 11), bg="#faf8f5", fg="#8b7d6b").pack(anchor=tk.W, pady=(8, 0))

    def create_result_scroll_view(self):
        canvas = tk.Canvas(self.result_container, bg="#faf8f5", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.result_container, orient=tk.VERTICAL, command=canvas.yview)
        self.result_content = tk.Frame(canvas, bg="#faf8f5")
        window_id = canvas.create_window((0, 0), window=self.result_content, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def stretch_content(event):
            canvas.itemconfigure(window_id, width=event.width)

        def on_mousewheel(event):
            if getattr(event, "num", None) == 4:
                canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(3, "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def bind_mousewheel(_event=None):
            canvas.bind_all("<MouseWheel>", on_mousewheel)
            canvas.bind_all("<Button-4>", on_mousewheel)
            canvas.bind_all("<Button-5>", on_mousewheel)

        def unbind_mousewheel(_event=None):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        self.result_content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", stretch_content)
        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)
        self.result_content.bind("<Enter>", bind_mousewheel)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def add_accordion_section(self, key, title, summary, expanded):
        section = tk.Frame(self.result_content, bg="#faf8f5")
        section.pack(fill=tk.X, pady=(0, 10))

        header = tk.Frame(section, bg="#fff3e8", padx=16, pady=12, cursor="hand2")
        header.pack(fill=tk.X)

        arrow = tk.Label(header, text="▼" if expanded else "▶", font=("微软雅黑", 12, "bold"),
                         bg="#fff3e8", fg="#c17145")
        arrow.pack(side=tk.LEFT, padx=(0, 10))

        title_label = tk.Label(header, text=title, font=("微软雅黑", 13, "bold"),
                               bg="#fff3e8", fg="#2d2520")
        title_label.pack(side=tk.LEFT)

        summary_label = tk.Label(header, text=summary, font=("微软雅黑", 10),
                                 bg="#fff3e8", fg="#8b7d6b")
        summary_label.pack(side=tk.RIGHT)

        body = tk.Frame(section, bg="#fffefb", padx=18, pady=14)
        if expanded:
            body.pack(fill=tk.X)

        self.accordion_sections[key] = {"body": body, "arrow": arrow, "expanded": expanded}
        self.accordion_bodies[key] = body

        def toggle(_event=None):
            info = self.accordion_sections[key]
            if info["expanded"]:
                info["body"].pack_forget()
                info["arrow"].config(text="▶")
            else:
                info["body"].pack(fill=tk.X)
                info["arrow"].config(text="▼")
            info["expanded"] = not info["expanded"]

        for widget in (header, arrow, title_label, summary_label):
            widget.bind("<Button-1>", toggle)

        return body

    def fill_ai_advice_section(self, body, ai_advice):
        self.add_plain_line(body, "AI 只基于扫描摘要生成建议；API Key、Base URL、模型名不会写入报告。", "#8b7d6b")
        for line in ai_advice.strip().splitlines():
            self.add_plain_line(body, line or " ", "#2d2520")

    def fill_todo_section(self, body, action_items):
        if not action_items:
            self.add_plain_line(body, "暂未发现必须优先处理的事项。", "#5a8c3e")
            return

        self.add_plain_line(body, "按优先级处理这些事项，比直接看完整报告更省时间。", "#2d2520", bold=True)
        for index, item in enumerate(action_items, start=1):
            color = "#d04a2e" if item.priority == "高" else "#d97845" if item.priority == "中" else "#8b7d6b"
            self.add_plain_line(body, f"{index}. 【{item.priority}】{item.title}", color, bold=True)
            self.add_plain_line(body, f"   影响：{item.impact}", "#6b5640")
            self.add_plain_line(body, f"   建议：{item.suggestion}", "#6b5640")
            for file_info in item.files[:5]:
                issues = "、".join(file_info.health_issues or []) or file_info.cleanup_kind or file_info.category
                self.add_file_action_row(body, file_info, issues)
            if len(item.files) > 5:
                self.add_plain_line(body, f"   还有 {len(item.files) - 5} 个候选，请查看完整报告或整理计划。", "#8b7d6b")

    def fill_cleanup_section(self, body, cleanup_candidates):
        if not cleanup_candidates:
            self.add_plain_line(body, "未发现明显的缓存、临时文件或低价值生成物。", "#5a8c3e")
            return

        total_size = sum(file_info.size for file_info in cleanup_candidates)
        low_risk = [file_info for file_info in cleanup_candidates if file_info.cleanup_risk == "低"]
        medium_risk = [file_info for file_info in cleanup_candidates if file_info.cleanup_risk == "中"]
        self.add_plain_line(
            body,
            f"发现 {len(cleanup_candidates)} 个候选，合计 {format_size(total_size)}；低风险 {len(low_risk)} 个，中风险 {len(medium_risk)} 个。",
            "#2d2520",
            bold=True,
        )
        self.add_plain_line(body, "工具只生成建议和脚本，不会自动删除。中风险文件建议人工打开位置确认。", "#8b7d6b")
        self.add_table_header(body, ["文件", "风险", "类型"])
        for file_info in cleanup_candidates[:20]:
            self.add_file_action_row(body, file_info, f"{file_info.cleanup_risk or ''}｜{file_info.cleanup_kind or ''}")
        if len(cleanup_candidates) > 20:
            self.add_plain_line(body, f"还有 {len(cleanup_candidates) - 20} 个候选，请查看完整报告。", "#8b7d6b")

    def fill_health_section(self, body, files, avg_health):
        score_color = "#5a8c3e" if avg_health >= 80 else "#d97845" if avg_health >= 60 else "#d04a2e"
        top = tk.Frame(body, bg="#fffefb")
        top.pack(fill=tk.X, pady=(0, 10))
        tk.Label(top, text=str(avg_health), font=("Georgia", 34), bg="#fffefb", fg=score_color).pack(side=tk.LEFT)
        tk.Label(top, text="/100\n平均健康分", justify=tk.LEFT, font=("微软雅黑", 11),
                 bg="#fffefb", fg="#8b7d6b").pack(side=tk.LEFT, padx=(8, 0))

        problem_files = sorted([f for f in files if f.health_score < 70], key=lambda item: item.health_score)
        if not problem_files:
            self.add_plain_line(body, "没有低于 70 分的问题文件。", "#5a8c3e")
            return

        self.add_plain_line(body, f"需要关注 {len(problem_files)} 个低分文件：", "#2d2520", bold=True)
        self.add_table_header(body, ["文件", "分数", "问题"])
        for file_info in problem_files[:15]:
            issues = "、".join(file_info.health_issues or [])
            self.add_file_action_row(body, file_info, f"{file_info.health_score}｜{issues}")
        if len(problem_files) > 15:
            self.add_plain_line(body, f"还有 {len(problem_files) - 15} 个低分文件，请在完整报告中查看。", "#8b7d6b")

    def fill_category_section(self, body, files):
        if not files:
            self.add_plain_line(body, "没有可统计的文件。", "#8b7d6b")
            return
        stats = {}
        for file_info in files:
            count, size = stats.get(file_info.category, (0, 0))
            stats[file_info.category] = (count + 1, size + file_info.size)

        self.add_table_header(body, ["分类", "数量", "大小"])
        for category, (count, size) in sorted(stats.items(), key=lambda item: (-item[1][0], item[0])):
            self.add_table_row(body, [category, str(count), format_size(size)])

    def fill_duplicate_section(self, body, duplicates):
        if not duplicates:
            self.add_plain_line(body, "未发现 SHA256 完全相同的重复文件。", "#5a8c3e")
            return

        total_waste = sum((len(group) - 1) * group[0].size for group in duplicates)
        self.add_plain_line(body, f"删除冗余副本预计可释放 {format_size(total_waste)}。", "#2d2520", bold=True)
        for index, group in enumerate(duplicates[:8], start=1):
            self.add_plain_line(body, f"重复组 {index}", "#c17145", bold=True)
            self.add_table_header(body, ["文件", "评分/建议", "操作"])
            for file_info, quality_score, action in rank_duplicate_files(group):
                self.add_file_action_row(body, file_info, f"{quality_score}｜{action}")
        if len(duplicates) > 8:
            self.add_plain_line(body, f"还有 {len(duplicates) - 8} 组重复文件，请在完整报告中查看。", "#8b7d6b")

    def fill_move_section(self, body, files):
        folders = {}
        for file_info in files:
            if file_info.cleanup_kind:
                continue
            folders.setdefault(file_info.suggested_folder, []).append(file_info)
        if not folders:
            self.add_plain_line(body, "暂未发现可整理的文件。", "#8b7d6b")
            return

        for folder in sorted(folders):
            group = folders[folder]
            self.add_plain_line(body, f"建议放入：{folder}（{len(group)} 个）", "#c17145", bold=True)
            for file_info in group[:8]:
                self.add_file_action_row(body, file_info, f"{file_info.category}｜{format_size(file_info.size)}")
            if len(group) > 8:
                self.add_plain_line(body, f"  还有 {len(group) - 8} 个文件未显示。", "#8b7d6b")

    def fill_full_report_section(self, body, report, report_path):
        self.add_plain_line(body, f"完整报告已保存：{report_path}", "#8b7d6b")
        report_text = scrolledtext.ScrolledText(body, wrap=tk.WORD, height=16,
                                                font=("Consolas", 10), bg="#fffefb",
                                                fg="#2d2520", relief=tk.FLAT,
                                                bd=0, highlightthickness=0,
                                                padx=0, pady=8)
        report_text.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        report_text.insert(1.0, report)
        report_text.config(state=tk.DISABLED)

    def add_plain_line(self, parent, text, color, bold=False):
        font = ("微软雅黑", 10, "bold") if bold else ("微软雅黑", 10)
        tk.Label(parent, text=text, font=font, bg="#fffefb", fg=color,
                 anchor=tk.W, justify=tk.LEFT, wraplength=980).pack(fill=tk.X, pady=2)

    def add_table_header(self, parent, values):
        row = tk.Frame(parent, bg="#f5ebe0", padx=8, pady=6)
        row.pack(fill=tk.X, pady=(8, 2))
        for index, value in enumerate(values):
            tk.Label(row, text=value, font=("微软雅黑", 10, "bold"), bg="#f5ebe0",
                     fg="#6b5640", anchor=tk.W).grid(row=0, column=index, sticky="ew", padx=6)
            row.columnconfigure(index, weight=3 if index == 0 else 1)

    def add_table_row(self, parent, values):
        row = tk.Frame(parent, bg="#fffefb", padx=8, pady=5)
        row.pack(fill=tk.X)
        for index, value in enumerate(values):
            tk.Label(row, text=value, font=("微软雅黑", 9), bg="#fffefb", fg="#2d2520",
                     anchor=tk.W, justify=tk.LEFT, wraplength=620 if index == 0 else 260).grid(
                row=0, column=index, sticky="ew", padx=6
            )
            row.columnconfigure(index, weight=3 if index == 0 else 1)

    def add_file_action_row(self, parent, file_info, detail):
        row = tk.Frame(parent, bg="#fffefb", padx=8, pady=5)
        row.pack(fill=tk.X)

        file_text = f"{file_info.relative_path}（{format_size(file_info.size)}）"
        tk.Label(row, text=file_text, font=("微软雅黑", 9), bg="#fffefb", fg="#2d2520",
                 anchor=tk.W, justify=tk.LEFT, wraplength=560).grid(row=0, column=0, sticky="ew", padx=6)
        tk.Label(row, text=detail, font=("微软雅黑", 9), bg="#fffefb", fg="#6b5640",
                 anchor=tk.W, justify=tk.LEFT, wraplength=260).grid(row=0, column=1, sticky="ew", padx=6)

        action_box = tk.Frame(row, bg="#fffefb")
        action_box.grid(row=0, column=2, sticky="e", padx=6)
        tk.Button(action_box, text="打开位置", command=lambda p=file_info.path: self.open_file_location(p),
                  bg="#f5ebe0", fg="#2d2520", font=("微软雅黑", 9), relief=tk.FLAT,
                  padx=8, pady=3, cursor="hand2").pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(action_box, text="复制路径", command=lambda p=file_info.path: self.copy_path(p),
                  bg="#fff3e8", fg="#2d2520", font=("微软雅黑", 9), relief=tk.FLAT,
                  padx=8, pady=3, cursor="hand2").pack(side=tk.LEFT)

        row.columnconfigure(0, weight=4)
        row.columnconfigure(1, weight=2)
        row.columnconfigure(2, weight=1)

    def open_file_location(self, path):
        try:
            if os.name == "nt":
                subprocess.run(["explorer", "/select,", str(path)], check=False)
            else:
                os.startfile(path.parent)
            self.status_label.config(text=f"已打开位置：{path.parent}", fg="#6b5640")
        except Exception as exc:
            self.status_label.config(text=f"打开位置失败：{exc}", fg="#d04a2e")

    def copy_path(self, path):
        self.root.clipboard_clear()
        self.root.clipboard_append(str(path))
        self.root.update_idletasks()
        self.status_label.config(text=f"已复制路径：{path}", fg="#6b5640")

    def show_error(self, error):
        self.scan_btn.config(state=tk.NORMAL, text="开始扫描", bg="#c17145")
        self.cancel_btn.config(state=tk.DISABLED)
        self.progress_bar.stop()
        self.progress_frame.pack_forget()
        self.status_label.config(text=f"✗ 扫描失败：{error}", fg="#d04a2e")

    def show_charts(self):
        if not self._viz_data:
            messagebox.showinfo("提示", "请先扫描文件夹，再查看可视化图表。")
            return
        if not HAS_MATPLOTLIB:
            messagebox.showwarning("缺少依赖", "需要安装 matplotlib：pip install matplotlib")
            return

        data = self._viz_data
        win = tk.Toplevel(self.root)
        win.title("📊 扫描结果可视化")
        win.geometry("960x720")
        win.configure(bg="#faf8f5")

        fig = Figure(figsize=(9.4, 6.8), dpi=100, facecolor="#faf8f5")
        fig.suptitle("文件扫描结果总览", fontsize=15, fontweight="bold", y=0.98)

        # 1. 分类饼图
        ax1 = fig.add_subplot(221)
        cats = data["categories"]
        if cats:
            labels = list(cats.keys())
            sizes = [v[0] for v in cats.values()]
            ax1.pie(sizes, labels=labels, autopct="%1.0f%%", startangle=90,
                    textprops={"fontsize": 8})
            ax1.set_title(f"文件分类分布（共 {data['total_files']} 个）", fontsize=10)
        else:
            ax1.text(0.5, 0.5, "无数据", ha="center", va="center")

        # 2. 分类大小柱状图
        ax2 = fig.add_subplot(222)
        if cats:
            names = list(cats.keys())
            mb_sizes = [v[1] / (1024 * 1024) for v in cats.values()]
            colors = ["#c17145", "#a25a32", "#d97845", "#5a8c3e", "#8b7d6b",
                       "#b45f3c", "#6b5640", "#d04a2e"][:len(names)]
            ax2.barh(names, mb_sizes, color=colors)
            ax2.set_xlabel("MB")
            ax2.set_title("各分类占用空间", fontsize=10)
            ax2.tick_params(axis="y", labelsize=8)

        # 3. 健康分分布
        ax3 = fig.add_subplot(223)
        hist = data["health_histogram"]
        labels3 = [f"{i*10}-{i*10+9}" for i in range(10)]
        bar_colors = ["#d04a2e" if i < 7 else "#5a8c3e" for i in range(10)]
        ax3.bar(labels3, hist, color=bar_colors)
        ax3.set_xlabel("分数段")
        ax3.set_ylabel("文件数")
        ax3.set_title("健康评分分布", fontsize=10)
        ax3.tick_params(axis="x", labelsize=7, rotation=30)

        # 4. 重复/清理统计
        ax4 = fig.add_subplot(224)
        dup_waste_mb = data["duplicate_waste"] / (1024 * 1024)
        cleanup_mb = data["cleanup_by_risk"].get("低", 0) / (1024 * 1024)
        cleanup_med_mb = data["cleanup_by_risk"].get("中", 0) / (1024 * 1024)
        bars = ax4.bar(
            [f"重复文件\n({data['duplicate_groups']}组)",
             f"低风险清理\n({data['cleanup_count']}个)",
             f"中风险清理"],
            [dup_waste_mb, cleanup_mb, cleanup_med_mb],
            color=["#d97845", "#5a8c3e", "#b45f3c"],
        )
        ax4.set_ylabel("MB")
        ax4.set_title("可释放空间", fontsize=10)
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax4.annotate(f"{h:.1f}MB", xy=(bar.get_x() + bar.get_width() / 2, h),
                             xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8)

        fig.tight_layout(rect=[0, 0, 1, 0.95])

        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        tk.Button(win, text="关闭", command=win.destroy,
                  bg="#f5ebe0", fg="#2d2520", font=("微软雅黑", 10),
                  relief=tk.FLAT, padx=20, pady=6, cursor="hand2").pack(pady=10)


def main():
    root = TkinterDnD.Tk()
    app = ScannerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
