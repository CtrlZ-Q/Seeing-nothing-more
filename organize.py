import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPORT_NAME = "file-organization-report.md"
TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".html", ".css", ".js", ".ts",
    ".py", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs", ".php",
    ".rb", ".sh", ".bat", ".ps1", ".log", ".ini", ".yaml", ".yml", ".toml",
}
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go",
    ".rs", ".php", ".rb", ".sh", ".bat", ".ps1", ".html", ".css", ".sql",
}
DOCUMENT_EXTENSIONS = {".md", ".txt", ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"}
PREVIEW_BYTES = 4096
GENERATED_FILES = {
    REPORT_NAME,
    "delete-duplicates.bat",
    "cleanup-candidates.bat",
    "file-organization-plan.md",
}
LOW_VALUE_DIRS = {
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache",
    "node_modules", "dist", "build", "coverage", ".tox", ".next", ".nuxt",
}
LOW_VALUE_FILE_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
LOW_VALUE_EXTENSIONS = {
    ".tmp", ".temp", ".bak", ".old", ".part", ".crdownload", ".download",
    ".log", ".pyc", ".pyo", ".swp",
}
MEDIUM_RISK_CLEANUP_EXTENSIONS = {".bak", ".old", ".log"}


@dataclass
class FileInfo:
    path: Path
    relative_path: str
    size: int
    extension: str
    modified_at: datetime
    sha256: str | None
    preview: str
    read_error: str | None
    category: str = "其他"
    suggested_folder: str = "其他"
    suggested_name: str | None = None
    health_score: int = 100
    health_issues: list[str] | None = None
    cleanup_kind: str | None = None
    cleanup_risk: str | None = None


@dataclass
class ActionItem:
    priority: str
    title: str
    impact: str
    suggestion: str
    files: list[FileInfo]
    action_label: str


class Classifier:
    def classify(self, file_info: FileInfo) -> tuple[str, str]:
        raise NotImplementedError


class OfflineRuleClassifier(Classifier):
    def __init__(self, scenario: str = "通用"):
        self.scenario = scenario

    def classify(self, file_info: FileInfo) -> tuple[str, str]:
        text = f"{file_info.path.name} {file_info.preview}".lower()
        ext = file_info.extension

        # 扩展名优先：精确匹配，避免被关键词误判
        if ext in CODE_EXTENSIONS:
            return "代码", "代码"
        if ext in IMAGE_EXTENSIONS:
            return self._classify_image(file_info, text)
        if ext in ARCHIVE_EXTENSIONS:
            return "压缩包", "压缩包"
        if ext in DOCUMENT_EXTENSIONS:
            return self._classify_document(file_info, text)

        # 关键词匹配：用于无明确扩展名或需要进一步细分的场景
        if contains_any(text, ["合同", "contract", "协议", "agreement"]):
            return "合同", "合同"
        if contains_any(text, ["发票", "invoice", "报销", "付款", "receipt", "收据"]):
            return "财务/发票", "财务"
        if ext == ".log" or contains_any(text, ["traceback", "error", "exception", "异常", "错误"]):
            return "日志", "日志"
        if contains_any(text, ["笔记", "notes", "课程", "学习", "study", "教程"]):
            return "学习笔记", "学习笔记"
        if contains_any(text, ["截图", "screenshot", "screen shot"]):
            return "图片/截图", "图片"
        return "其他", "其他"

    def _classify_image(self, file_info: FileInfo, text: str) -> tuple[str, str]:
        if self.scenario == "照片整理":
            # 按拍摄年份分类
            year = file_info.modified_at.year
            return f"图片/{year}年", f"照片/{year}"
        if contains_any(text, ["截图", "screenshot"]):
            return "图片/截图", "截图"
        return "图片/截图", "图片"

    def _classify_document(self, file_info: FileInfo, text: str) -> tuple[str, str]:
        if self.scenario == "工作文档":
            if contains_any(text, ["项目", "方案", "需求", "设计"]):
                return "文档/项目", "项目文档"
            if contains_any(text, ["会议", "纪要", "记录"]):
                return "文档/会议", "会议记录"
        elif self.scenario == "学习资料":
            if contains_any(text, ["课程", "教程", "lecture"]):
                return "文档/课程", "课程资料"
            if contains_any(text, ["作业", "练习", "assignment"]):
                return "文档/作业", "作业"
        return "文档", "文档"


def contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


class AIAdvisor:
    """使用 OpenAI 兼容 API 生成扫描后的整理建议。"""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1",
                 model: str = "gpt-4o-mini", scenario: str = "通用"):
        self.scenario = scenario
        self.model = model
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        except ImportError:
            raise RuntimeError("需要安装 openai 库：pip install openai")

    def generate_advice(
        self,
        files: list[FileInfo],
        duplicates: list[list[FileInfo]],
        cleanup_candidates: list[FileInfo],
        action_items: list[ActionItem],
    ) -> str:
        prompt = self._build_prompt(files, duplicates, cleanup_candidates, action_items)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=900,
            )
            text = (resp.choices[0].message.content or "").strip()
            return text or "AI 整理建议为空，请以本地扫描报告为准。"
        except Exception:
            return "AI 整理建议生成失败：请检查网络、API Key、Base URL 或模型名。未保存任何 API 配置。"

    def _build_prompt(
        self,
        files: list[FileInfo],
        duplicates: list[list[FileInfo]],
        cleanup_candidates: list[FileInfo],
        action_items: list[ActionItem],
    ) -> str:
        total_size = sum(file_info.size for file_info in files)
        category_stats: dict[str, dict[str, int]] = {}
        for file_info in files:
            stat = category_stats.setdefault(file_info.category, {"count": 0, "size": 0})
            stat["count"] += 1
            stat["size"] += file_info.size

        low_risk = [file_info for file_info in cleanup_candidates if file_info.cleanup_risk == "低"]
        medium_risk = [file_info for file_info in cleanup_candidates if file_info.cleanup_risk == "中"]
        duplicate_waste = sum((len(group) - 1) * group[0].size for group in duplicates)
        low_health = sorted([file_info for file_info in files if file_info.health_score < 70], key=lambda item: item.health_score)[:10]
        large_files = sorted(files, key=lambda item: item.size, reverse=True)[:10]

        summary = {
            "scan_scenario": self.scenario,
            "total_files": len(files),
            "total_size": format_size(total_size),
            "category_stats": [
                {"category": category, "count": stat["count"], "size": format_size(stat["size"])}
                for category, stat in sorted(category_stats.items(), key=lambda item: (-item[1]["size"], item[0]))[:12]
            ],
            "cleanup": {
                "candidate_count": len(cleanup_candidates),
                "candidate_size": format_size(sum(file_info.size for file_info in cleanup_candidates)),
                "low_risk_count": len(low_risk),
                "medium_risk_count": len(medium_risk),
            },
            "duplicates": {
                "group_count": len(duplicates),
                "estimated_waste": format_size(duplicate_waste),
            },
            "top_action_items": [
                {"priority": item.priority, "title": item.title, "impact": item.impact, "suggestion": item.suggestion}
                for item in action_items[:8]
            ],
            "problem_file_samples": [
                {
                    "file": file_info.relative_path,
                    "score": file_info.health_score,
                    "issues": file_info.health_issues or [],
                }
                for file_info in low_health
            ],
            "large_file_samples": [
                {"file": file_info.relative_path, "size": format_size(file_info.size), "category": file_info.category}
                for file_info in large_files
            ],
        }
        return (
            "你是本地文件整理顾问。请只基于下面的扫描摘要，给出实用、谨慎的整理建议。\n"
            "要求：\n"
            "1. 用简体中文输出。\n"
            "2. 不要说你看过完整文件内容，因为摘要不包含文件正文。\n"
            "3. 不要建议直接执行删除脚本；涉及删除时必须提醒先人工复核和备份。\n"
            "4. 输出四段：优先处理、重点区域、风险提醒、建议步骤。\n"
            "5. 不要提及 API Key、Base URL、模型名或任何 API 配置。\n\n"
            f"扫描摘要：\n{json.dumps(summary, ensure_ascii=False, indent=2)}"
        )


def build_viz_data(files: list[FileInfo], duplicates: list[list[FileInfo]],
                   cleanup_candidates: list[FileInfo]) -> dict:
    """生成可视化图表所需的数据结构。"""
    cat_stats: dict[str, tuple[int, int]] = {}
    for f in files:
        count, size = cat_stats.get(f.category, (0, 0))
        cat_stats[f.category] = (count + 1, size + f.size)

    health_hist = [0] * 10
    for f in files:
        bucket = min(f.health_score // 10, 9)
        health_hist[bucket] += 1

    dup_total_waste = sum((len(g) - 1) * g[0].size for g in duplicates)
    cleanup_by_risk = {"低": 0, "中": 0}
    for f in cleanup_candidates:
        cleanup_by_risk[f.cleanup_risk or "中"] += f.size

    largest = sorted(files, key=lambda f: f.size, reverse=True)[:15]

    return {
        "categories": cat_stats,
        "health_histogram": health_hist,
        "duplicate_waste": dup_total_waste,
        "duplicate_groups": len(duplicates),
        "cleanup_by_risk": cleanup_by_risk,
        "cleanup_count": len(cleanup_candidates),
        "largest_files": [(f.relative_path, f.size, f.category) for f in largest],
        "total_files": len(files),
        "total_size": sum(f.size for f in files),
    }


def scan_directory(root: Path, progress_cb=None, max_depth: int = 20) -> list[FileInfo]:
    files: list[FileInfo] = []
    for current_root, dirs, filenames in os.walk(root):
        depth = Path(current_root).relative_to(root).parts
        if len(depth) >= max_depth:
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in filenames:
            path = Path(current_root) / filename
            if path.name in GENERATED_FILES:
                continue
            files.append(build_file_info(root, path))
            if progress_cb and len(files) % 50 == 0:
                progress_cb(len(files), str(path.relative_to(root)))
    files.sort(key=lambda item: item.relative_path.lower())
    if progress_cb:
        progress_cb(len(files), "扫描完成")
    return files


def build_file_info(root: Path, path: Path) -> FileInfo:
    try:
        stat = path.stat()
        size = stat.st_size
        modified_at = datetime.fromtimestamp(stat.st_mtime)
    except OSError as exc:
        return FileInfo(
            path=path,
            relative_path=safe_relative_path(root, path),
            size=0,
            extension=path.suffix.lower(),
            modified_at=datetime.fromtimestamp(0),
            sha256=None,
            preview="",
            read_error=str(exc),
        )

    preview, read_error = read_text_preview(path)

    return FileInfo(
        path=path,
        relative_path=safe_relative_path(root, path),
        size=size,
        extension=path.suffix.lower(),
        modified_at=modified_at,
        sha256=None,
        preview=preview,
        read_error=read_error,
    )


def safe_relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def read_text_preview(path: Path) -> tuple[str, str | None]:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return "", None
    try:
        with path.open("rb") as handle:
            data = handle.read(PREVIEW_BYTES)
    except OSError as exc:
        return "", str(exc)
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding), None
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin-1"), None


def calculate_sha256(path: Path) -> tuple[str | None, str | None]:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        return None, str(exc)
    return digest.hexdigest(), None


def classify_files(files: list[FileInfo], classifier: Classifier) -> None:
    for file_info in files:
        category, folder = classifier.classify(file_info)
        file_info.category = category
        file_info.suggested_folder = folder
        file_info.suggested_name = suggest_name(file_info)
        mark_cleanup_candidate(file_info)
        calculate_health_score(file_info)


def get_scenario_description(scenario: str) -> str:
    descriptions = {
        "通用": "适用于各类文件混合的场景",
        "下载整理": "📥 清理下载文件夹，识别安装包、压缩包、临时文件",
        "工作文档": "💼 整理工作文档，按项目、会议分类",
        "学习资料": "📚 整理学习资料，按课程、作业分类",
        "照片整理": "📸 整理照片，按拍摄年份分类",
    }
    return descriptions.get(scenario, "")


def calculate_health_score(file_info: FileInfo) -> None:
    score = 100
    issues = []

    # 1. 文件名质量 (-30)
    name = file_info.path.stem.lower()
    if re.search(r"[一-鿿]{10,}", name):  # 超长中文
        score -= 30
        issues.append("文件名过长")
    elif re.search(r"^(未命名|新建|副本|copy|tmp|temp|\d{8,})", name):
        score -= 20
        issues.append("文件名无意义")
    elif len(name) > 100:
        score -= 15
        issues.append("文件名过长")

    # 2. 存储位置 (-20)
    path_lower = str(file_info.path).lower()
    if any(x in path_lower for x in ["temp", "tmp", "cache", "下载", "download", "desktop", "桌面"]):
        if file_info.category in ["文档", "代码", "合同", "财务/发票"]:
            score -= 20
            issues.append("重要文件位于临时目录")

    # 3. 时间异常 (-15)
    age_days = (datetime.now() - file_info.modified_at).days
    if age_days > 730:  # 2年未修改
        score -= 15
        issues.append(f"{age_days // 365}年未访问")

    # 4. 文件完整性 (-10)
    if file_info.extension in ARCHIVE_EXTENSIONS and file_info.size < 100:
        score -= 10
        issues.append("压缩包异常小")
    if file_info.read_error:
        score -= 10
        issues.append("读取失败")

    # 5. 垃圾/缓存候选 (-15/-5)
    if file_info.cleanup_kind:
        if file_info.cleanup_risk == "低":
            score -= 15
            issues.append(f"可清理候选：{file_info.cleanup_kind}")
        else:
            score -= 5
            issues.append(f"需确认清理：{file_info.cleanup_kind}")

    file_info.health_score = max(0, score)
    file_info.health_issues = issues if issues else None


def mark_cleanup_candidate(file_info: FileInfo) -> None:
    """标记可清理候选；只做建议，不会执行删除。"""
    parts = {part.lower() for part in file_info.path.parts}
    name = file_info.path.name.lower()
    ext = file_info.extension

    matched_dirs = sorted(parts & LOW_VALUE_DIRS)
    if matched_dirs:
        file_info.cleanup_kind = f"缓存目录 {matched_dirs[0]}"
        file_info.cleanup_risk = "低"
        return

    if name in LOW_VALUE_FILE_NAMES:
        file_info.cleanup_kind = "系统索引/缩略图文件"
        file_info.cleanup_risk = "低"
        return

    if ext in LOW_VALUE_EXTENSIONS:
        file_info.cleanup_kind = "临时/缓存文件"
        file_info.cleanup_risk = "中" if ext in MEDIUM_RISK_CLEANUP_EXTENSIONS else "低"
        return


def find_cleanup_candidates(files: list[FileInfo]) -> list[FileInfo]:
    return sorted(
        [file_info for file_info in files if file_info.cleanup_kind],
        key=lambda item: (item.cleanup_risk != "低", -item.size, item.relative_path.lower()),
    )


def build_action_items(files: list[FileInfo], duplicates: list[list[FileInfo]], cleanup_candidates: list[FileInfo]) -> list[ActionItem]:
    items: list[ActionItem] = []

    duplicate_files: list[FileInfo] = []
    for group in duplicates:
        duplicate_files.extend(file_info for file_info, _, _ in rank_duplicate_files(group)[1:])
    if duplicate_files:
        total_waste = sum(file_info.size for file_info in duplicate_files)
        items.append(ActionItem(
            priority="高",
            title=f"处理 {len(duplicates)} 组重复文件",
            impact=f"预计可释放 {format_size(total_waste)}",
            suggestion="先保留每组评分最高的文件，其余副本逐个确认后再删除。",
            files=duplicate_files[:20],
            action_label="检查重复文件",
        ))

    low_risk_cleanup = [file_info for file_info in cleanup_candidates if file_info.cleanup_risk == "低"]
    if low_risk_cleanup:
        total_cleanup = sum(file_info.size for file_info in low_risk_cleanup)
        items.append(ActionItem(
            priority="高",
            title=f"清理 {len(low_risk_cleanup)} 个低风险缓存/临时文件",
            impact=f"预计可释放 {format_size(total_cleanup)}",
            suggestion="这些通常是缓存、编译产物或系统缩略图，建议确认没有正在使用后清理。",
            files=low_risk_cleanup[:20],
            action_label="检查低风险清理候选",
        ))

    medium_risk_cleanup = [file_info for file_info in cleanup_candidates if file_info.cleanup_risk == "中"]
    if medium_risk_cleanup:
        total_cleanup = sum(file_info.size for file_info in medium_risk_cleanup)
        items.append(ActionItem(
            priority="中",
            title=f"复核 {len(medium_risk_cleanup)} 个中风险清理候选",
            impact=f"可能释放 {format_size(total_cleanup)}",
            suggestion=".bak、.old、.log 可能有追溯价值，不建议批量删除；先打开所在位置确认。",
            files=medium_risk_cleanup[:20],
            action_label="人工复核",
        ))

    low_health_files = sorted(
        [file_info for file_info in files if file_info.health_score < 70 and not file_info.cleanup_kind],
        key=lambda item: item.health_score,
    )
    if low_health_files:
        items.append(ActionItem(
            priority="中",
            title=f"处理 {len(low_health_files)} 个低健康分文件",
            impact="降低误删、丢失和难以查找的风险",
            suggestion="优先检查文件名、存放位置、读取失败和长期未整理问题。",
            files=low_health_files[:20],
            action_label="查看问题文件",
        ))

    rename_files = [file_info for file_info in files if file_info.suggested_name and not file_info.cleanup_kind]
    if rename_files:
        items.append(ActionItem(
            priority="低",
            title=f"规范 {len(rename_files)} 个文件名",
            impact="让文件更容易搜索和排序",
            suggestion="这只是命名建议，不会自动重命名；建议只处理你确认有价值的文件。",
            files=rename_files[:20],
            action_label="检查命名建议",
        ))

    return items


def suggest_name(file_info: FileInfo) -> str | None:
    stem = file_info.path.stem.strip()
    normalized = re.sub(r"[\s_]+", "-", stem)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        normalized = "未命名文件"
    if normalized == stem:
        return None
    return f"{normalized}{file_info.path.suffix.lower()}"


def find_duplicates(files: list[FileInfo]) -> list[list[FileInfo]]:
    EMPTY_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    by_size: dict[int, list[FileInfo]] = {}
    for file_info in files:
        by_size.setdefault(file_info.size, []).append(file_info)

    by_hash: dict[tuple[int, str], list[FileInfo]] = {}
    for same_size_files in by_size.values():
        if len(same_size_files) < 2:
            continue
        for file_info in same_size_files:
            if file_info.size == 0:
                file_info.sha256 = EMPTY_HASH
                key = (0, EMPTY_HASH)
            else:
                sha256, hash_error = calculate_sha256(file_info.path)
                file_info.sha256 = sha256
                if hash_error and not file_info.read_error:
                    file_info.read_error = hash_error
                if not sha256:
                    continue
                key = (file_info.size, sha256)
            by_hash.setdefault(key, []).append(file_info)

    duplicates = [group for group in by_hash.values() if len(group) > 1]

    # 标记重复文件的健康分数
    for group in duplicates:
        for file_info in group:
            file_info.health_score = max(0, file_info.health_score - 25)
            if file_info.health_issues is None:
                file_info.health_issues = []
            file_info.health_issues.append("文件重复")

    return duplicates


def write_report(
    root: Path,
    files: list[FileInfo],
    duplicates: list[list[FileInfo]],
    cleanup_candidates: list[FileInfo],
    action_items: list[ActionItem],
    scenario: str = "通用",
    ai_advice: str | None = None,
) -> Path:
    report_path = root / REPORT_NAME
    lines: list[str] = []
    total_size = sum(file_info.size for file_info in files)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("# 文件整理建议报告")
    lines.append("")
    lines.append("## 扫描概览")
    lines.append("")
    lines.append(f"- 扫描路径：`{root}`")
    lines.append(f"- 生成时间：{generated_at}")
    lines.append(f"- 扫描场景：**{scenario}** — {get_scenario_description(scenario)}")
    lines.append(f"- 文件数量：{len(files)}")
    lines.append(f"- 文件总大小：{format_size(total_size)}")
    lines.append("")
    lines.append("## 安全说明")
    lines.append("")
    lines.append("本工具只生成整理建议报告、整理计划和可检查脚本；没有移动、删除、重命名任何原文件。")
    lines.append("生成的 `.bat` 脚本也不会自动执行，必须由你检查后手动运行。")
    lines.append("")

    append_ai_advice(lines, ai_advice)
    append_action_items(lines, action_items)
    append_cleanup_candidates(lines, cleanup_candidates)
    append_health_summary(lines, files)
    append_category_summary(lines, files)
    append_large_files(lines, files)
    append_move_suggestions(lines, files)
    append_rename_suggestions(lines, files)
    append_duplicates(lines, duplicates)
    append_read_errors(lines, files)
    append_file_details(lines, files)

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def append_ai_advice(lines: list[str], ai_advice: str | None) -> None:
    if not ai_advice:
        return
    lines.append("## AI 整理建议")
    lines.append("")
    lines.extend(ai_advice.strip().splitlines())
    lines.append("")


def append_action_items(lines: list[str], action_items: list[ActionItem]) -> None:
    lines.append("## 待处理任务清单")
    lines.append("")
    if not action_items:
        lines.append("暂未发现需要优先处理的任务。")
        lines.append("")
        return

    lines.append("下面按优先级列出最值得处理的事项。所有操作都只是建议，不会自动改动原文件。")
    lines.append("")
    for index, item in enumerate(action_items, start=1):
        lines.append(f"### {index}. 【{item.priority}】{item.title}")
        lines.append("")
        lines.append(f"- 影响：{item.impact}")
        lines.append(f"- 建议动作：{item.suggestion}")
        lines.append(f"- 操作入口：{item.action_label}")
        lines.append("")
        if item.files:
            lines.append("| 文件 | 大小 | 问题/类型 |")
            lines.append("|---|---:|---|")
            for file_info in item.files[:10]:
                issues = "、".join(file_info.health_issues or []) or file_info.cleanup_kind or file_info.category
                lines.append(f"| `{file_info.relative_path}` | {format_size(file_info.size)} | {escape_table_text(issues)} |")
            if len(item.files) > 10:
                lines.append(f"| …… | …… | 还有 {len(item.files) - 10} 个候选未展开 |")
            lines.append("")


def append_cleanup_candidates(lines: list[str], cleanup_candidates: list[FileInfo]) -> None:
    lines.append("## 垃圾/缓存候选")
    lines.append("")
    if not cleanup_candidates:
        lines.append("未发现明显的缓存、临时文件或低价值生成物。")
        lines.append("")
        return

    total_size = sum(file_info.size for file_info in cleanup_candidates)
    low_risk = [file_info for file_info in cleanup_candidates if file_info.cleanup_risk == "低"]
    medium_risk = [file_info for file_info in cleanup_candidates if file_info.cleanup_risk == "中"]
    lines.append(f"发现 **{len(cleanup_candidates)}** 个清理候选，合计 **{format_size(total_size)}**。")
    lines.append(f"其中低风险 {len(low_risk)} 个，中风险 {len(medium_risk)} 个。")
    lines.append("")
    lines.append("| 文件 | 类型 | 风险 | 大小 |")
    lines.append("|---|---|---|---:|")
    for file_info in cleanup_candidates[:30]:
        lines.append(
            f"| `{file_info.relative_path}` | {file_info.cleanup_kind or ''} | {file_info.cleanup_risk or ''} | {format_size(file_info.size)} |"
        )
    if len(cleanup_candidates) > 30:
        lines.append(f"| …… | …… | …… | 还有 {len(cleanup_candidates) - 30} 个候选未展开 |")
    lines.append("")


def append_health_summary(lines: list[str], files: list[FileInfo]) -> None:
    lines.append("## 健康评分")
    lines.append("")
    if not files:
        lines.append("没有可评分的文件。")
        lines.append("")
        return

    avg_score = sum(f.health_score for f in files) // len(files)
    problem_files = [f for f in files if f.health_score < 70]

    lines.append(f"- 平均健康分：**{avg_score}/100**")
    lines.append(f"- 问题文件数：**{len(problem_files)}** 个（评分 < 70）")
    lines.append("")

    if problem_files:
        lines.append("### 需要关注的文件")
        lines.append("")
        lines.append("| 文件 | 评分 | 问题 |")
        lines.append("|---|---:|---|")
        for f in sorted(problem_files, key=lambda x: x.health_score)[:20]:
            issues = "、".join(f.health_issues) if f.health_issues else "无"
            lines.append(f"| `{f.relative_path}` | {f.health_score} | {issues} |")
        lines.append("")


def append_category_summary(lines: list[str], files: list[FileInfo]) -> None:
    lines.append("## 分类统计")
    lines.append("")
    if not files:
        lines.append("没有可统计的文件。")
        lines.append("")
        return

    stats: dict[str, tuple[int, int]] = {}
    for file_info in files:
        count, size = stats.get(file_info.category, (0, 0))
        stats[file_info.category] = (count + 1, size + file_info.size)

    lines.append("| 分类 | 文件数量 | 总大小 |")
    lines.append("|---|---:|---:|")
    for category, (count, size) in sorted(stats.items(), key=lambda item: (-item[1][0], item[0])):
        lines.append(f"| {category} | {count} | {format_size(size)} |")
    lines.append("")


def append_large_files(lines: list[str], files: list[FileInfo], limit: int = 10) -> None:
    lines.append("## 大文件清单")
    lines.append("")
    largest = sorted(files, key=lambda item: item.size, reverse=True)[:limit]
    if not largest:
        lines.append("没有可统计的大文件。")
        lines.append("")
        return

    lines.append(f"列出体积最大的前 {len(largest)} 个文件，方便优先整理。")
    lines.append("")
    lines.append("| 文件 | 分类 | 大小 |")
    lines.append("|---|---|---:|")
    for file_info in largest:
        lines.append(f"| `{file_info.relative_path}` | {file_info.category} | {format_size(file_info.size)} |")
    lines.append("")


def append_move_suggestions(lines: list[str], files: list[FileInfo]) -> None:
    lines.append("## 建议移动")
    lines.append("")
    categories: dict[str, list[FileInfo]] = {}
    for file_info in files:
        if file_info.cleanup_kind:
            continue
        categories.setdefault(file_info.suggested_folder, []).append(file_info)

    if not categories:
        lines.append("未发现可整理的文件。")
        lines.append("")
        return

    for folder in sorted(categories):
        lines.append(f"### 建议放入 `{folder}`")
        lines.append("")
        for file_info in categories[folder]:
            lines.append(f"- `{file_info.relative_path}`（{file_info.category}，{format_size(file_info.size)}）")
        lines.append("")


def append_rename_suggestions(lines: list[str], files: list[FileInfo]) -> None:
    lines.append("## 建议重命名")
    lines.append("")
    suggestions = [file_info for file_info in files if file_info.suggested_name and not file_info.cleanup_kind]
    if not suggestions:
        lines.append("暂未发现明显需要规整命名的文件。")
        lines.append("")
        return

    lines.append("| 原文件 | 建议文件名 |")
    lines.append("|---|---|")
    for file_info in suggestions:
        lines.append(f"| `{file_info.relative_path}` | `{file_info.suggested_name}` |")
    lines.append("")


def append_duplicates(lines: list[str], duplicates: list[list[FileInfo]]) -> None:
    lines.append("## 可能重复")
    lines.append("")
    if not duplicates:
        lines.append("未发现 SHA256 完全相同的重复文件。")
        lines.append("")
        return

    total_waste = sum((len(group) - 1) * group[0].size for group in duplicates)
    lines.append(f"发现 **{len(duplicates)}** 组重复文件，删除冗余副本可释放 **{format_size(total_waste)}** 空间。")
    lines.append("")

    for index, group in enumerate(duplicates, start=1):
        ranked = rank_duplicate_files(group)
        lines.append(f"### 重复组 {index}")
        lines.append("")
        lines.append("| 文件 | 质量评分 | 建议 |")
        lines.append("|---|---:|---|")
        for file_info, quality_score, action in ranked:
            lines.append(f"| `{file_info.relative_path}` | {quality_score} | {action} |")
        lines.append("")


def rank_duplicate_files(group: list[FileInfo]) -> list[tuple[FileInfo, int, str]]:
    """为重复文件组排序，返回 (file_info, quality_score, action)"""
    scored = []
    for f in group:
        score = 0
        # 文件名质量：无意义命名扣分
        name = f.path.stem.lower()
        if not re.search(r"(副本|copy|tmp|temp|\d{8,})", name):
            score += 30
        # 路径深度：越浅越好
        depth = len(f.path.parts)
        score += max(0, 20 - depth)
        # 修改时间：越新越好
        age_days = max(0, (datetime.now() - f.modified_at).days)
        score += max(0, 50 - age_days // 30)
        scored.append((f, score, ""))

    scored.sort(key=lambda x: x[1], reverse=True)
    result = []
    for i, (f, score, _) in enumerate(scored):
        action = "✅ 保留" if i == 0 else "❌ 可删除"
        result.append((f, score, action))
    return result


def append_read_errors(lines: list[str], files: list[FileInfo]) -> None:
    lines.append("## 读取失败")
    lines.append("")
    failed = [file_info for file_info in files if file_info.read_error]
    if not failed:
        lines.append("没有记录到读取失败的文件。")
        lines.append("")
        return

    lines.append("| 文件 | 原因 |")
    lines.append("|---|---|")
    for file_info in failed:
        lines.append(f"| `{file_info.relative_path}` | {escape_table_text(file_info.read_error or '')} |")
    lines.append("")


def append_file_details(lines: list[str], files: list[FileInfo]) -> None:
    lines.append("## 文件明细")
    lines.append("")
    if not files:
        lines.append("目标文件夹中没有可扫描的文件。")
        lines.append("")
        return

    lines.append("| 文件 | 分类 | 大小 | 修改时间 |")
    lines.append("|---|---|---:|---|")
    for file_info in files:
        modified_at = file_info.modified_at.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(
            f"| `{file_info.relative_path}` | {file_info.category} | {format_size(file_info.size)} | {modified_at} |"
        )
    lines.append("")


def escape_table_text(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def generate_report(root: Path, scenario: str = "通用", advisor=None,
                    progress_cb=None) -> tuple[Path, list[FileInfo], list[list[FileInfo]], list[FileInfo], list[ActionItem], str | None]:
    files = scan_directory(root, progress_cb=progress_cb)
    classify_files(files, OfflineRuleClassifier(scenario))
    duplicates = find_duplicates(files)
    cleanup_candidates = find_cleanup_candidates(files)
    action_items = build_action_items(files, duplicates, cleanup_candidates)
    ai_advice = advisor.generate_advice(files, duplicates, cleanup_candidates, action_items) if advisor else None
    report_path = write_report(root, files, duplicates, cleanup_candidates, action_items, scenario, ai_advice)
    generate_duplicate_cleanup_script(root, duplicates)
    generate_cleanup_candidates_script(root, cleanup_candidates)
    write_organization_plan(root, action_items, cleanup_candidates, duplicates, scenario)
    return report_path, files, duplicates, cleanup_candidates, action_items, ai_advice


def generate_duplicate_cleanup_script(root: Path, duplicates: list[list[FileInfo]]) -> None:
    """生成删除冗余重复文件的 .bat 脚本；只生成，不执行。"""
    script_path = root / "delete-duplicates.bat"
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "echo 重复文件清理脚本",
        "echo.",
        "echo 安全提醒：此脚本由工具生成，但不会自动执行。",
        "echo 请先逐行检查，确认无误后再继续。",
        "echo.",
    ]

    if not duplicates:
        lines.extend(["echo 当前扫描未发现重复文件。", "pause"])
        script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    lines.extend(["echo 此脚本将删除以下重复副本：", "echo."])
    total_waste = 0
    for group in duplicates:
        ranked = rank_duplicate_files(group)
        for file_info, _, _ in ranked[1:]:  # 跳过第一个（保留）
            lines.append(f'echo   {file_info.relative_path}')
            total_waste += file_info.size

    lines.extend([
        "echo.",
        f"echo 预计释放空间：{format_size(total_waste)}",
        "echo.",
        "pause",
        "echo.",
        "echo 开始删除重复副本...",
        "echo.",
    ])

    for group in duplicates:
        ranked = rank_duplicate_files(group)
        for file_info, _, _ in ranked[1:]:
            abs_path = file_info.path.absolute()
            lines.append(f'del /f /q "{abs_path}"')
            lines.append(f'if exist "{abs_path}" (echo 失败: {file_info.relative_path}) else (echo 已删除: {file_info.relative_path})')

    lines.extend(["echo.", "echo 清理完成！", "pause"])
    script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_cleanup_candidates_script(root: Path, cleanup_candidates: list[FileInfo]) -> None:
    """生成低风险缓存清理脚本；中风险文件只列出，不自动写删除命令。"""
    script_path = root / "cleanup-candidates.bat"
    low_risk = [file_info for file_info in cleanup_candidates if file_info.cleanup_risk == "低"]
    medium_risk = [file_info for file_info in cleanup_candidates if file_info.cleanup_risk == "中"]

    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "echo 垃圾/缓存候选清理脚本",
        "echo.",
        "echo 安全提醒：此脚本不会由工具自动执行。",
        "echo 建议先检查 file-organization-plan.md 和 file-organization-report.md。",
        "echo.",
    ]

    if not cleanup_candidates:
        lines.extend(["echo 当前扫描未发现垃圾/缓存候选。", "pause"])
        script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    lines.extend([
        f"echo 低风险候选：{len(low_risk)} 个",
        f"echo 中风险候选：{len(medium_risk)} 个（只提示，不自动删除）",
        "echo.",
    ])

    if low_risk:
        lines.append("echo 将删除以下低风险候选：")
        for file_info in low_risk:
            lines.append(f'echo   {file_info.relative_path}')
        lines.extend(["echo.", f"echo 预计释放空间：{format_size(sum(f.size for f in low_risk))}", "pause", "echo."])
        for file_info in low_risk:
            abs_path = file_info.path.absolute()
            lines.append(f'del /f /q "{abs_path}"')
            lines.append(f'if exist "{abs_path}" (echo 失败: {file_info.relative_path}) else (echo 已删除: {file_info.relative_path})')
    else:
        lines.append("echo 没有低风险候选可写入删除命令。")

    if medium_risk:
        lines.extend(["echo.", "echo 以下中风险候选需要人工复核，本脚本不会删除："])
        for file_info in medium_risk:
            lines.append(f'echo   {file_info.relative_path}')

    lines.extend(["echo.", "echo 脚本结束。", "pause"])
    script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_organization_plan(
    root: Path,
    action_items: list[ActionItem],
    cleanup_candidates: list[FileInfo],
    duplicates: list[list[FileInfo]],
    scenario: str,
) -> Path:
    plan_path = root / "file-organization-plan.md"
    lines: list[str] = []
    lines.append("# 文件整理执行计划")
    lines.append("")
    lines.append(f"- 扫描路径：`{root}`")
    lines.append(f"- 扫描场景：**{scenario}** — {get_scenario_description(scenario)}")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("## 安全边界")
    lines.append("")
    lines.append("- 本计划只告诉你建议处理什么，不会移动、删除、重命名原文件。")
    lines.append("- `delete-duplicates.bat` 和 `cleanup-candidates.bat` 只是可检查脚本，不会自动运行。")
    lines.append("- 真正执行前，请先备份重要文件，并逐行检查脚本内容。")
    lines.append("")
    lines.append("## 推荐处理顺序")
    lines.append("")

    if not action_items:
        lines.append("暂未发现必须优先处理的事项。")
        lines.append("")
    else:
        for index, item in enumerate(action_items, start=1):
            lines.append(f"{index}. **【{item.priority}】{item.title}**")
            lines.append(f"   - 影响：{item.impact}")
            lines.append(f"   - 建议：{item.suggestion}")
            lines.append("")

    lines.append("## 已生成文件")
    lines.append("")
    lines.append("- `file-organization-report.md`：完整扫描报告。")
    lines.append("- `file-organization-plan.md`：这份可执行整理计划。")
    lines.append("- `delete-duplicates.bat`：重复副本清理脚本；无重复时只显示提示。")
    lines.append("- `cleanup-candidates.bat`：低风险缓存/临时文件清理脚本；中风险只列出不删除。")
    lines.append("")
    lines.append("## 本次重点数字")
    lines.append("")
    lines.append(f"- 重复文件组：{len(duplicates)} 组")
    lines.append(f"- 垃圾/缓存候选：{len(cleanup_candidates)} 个")
    lines.append(f"- 候选释放空间：{format_size(sum(file_info.size for file_info in cleanup_candidates))}")
    lines.append("")

    if cleanup_candidates:
        lines.append("## 清理候选预览")
        lines.append("")
        lines.append("| 文件 | 类型 | 风险 | 大小 |")
        lines.append("|---|---|---|---:|")
        for file_info in cleanup_candidates[:30]:
            lines.append(
                f"| `{file_info.relative_path}` | {file_info.cleanup_kind or ''} | {file_info.cleanup_risk or ''} | {format_size(file_info.size)} |"
            )
        if len(cleanup_candidates) > 30:
            lines.append(f"| …… | …… | …… | 还有 {len(cleanup_candidates) - 30} 个候选未展开 |")
        lines.append("")

    plan_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return plan_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="扫描文件夹并生成不会改动原文件的整理建议报告。")
    parser.add_argument("folder", help="要扫描的文件夹路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.folder).expanduser().resolve()
    if not root.exists():
        print(f"错误：路径不存在：{root}", file=sys.stderr)
        return 1
    if not root.is_dir():
        print(f"错误：目标不是文件夹：{root}", file=sys.stderr)
        return 1

    report_path, *_ = generate_report(root)
    print(f"已生成报告：{report_path}")
    print("安全确认：没有移动、删除、重命名任何原文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
