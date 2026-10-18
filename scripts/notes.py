"""Private local Markdown notes; no model calls or Zotero writes."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading
import uuid

LOCK = threading.RLock()
MAX_BODY = 200_000
TEMPLATES = [
    {"id": "quick", "name": "快速摘记", "description": "记住要点、原文位置和接下来要问的问题。", "body": "## 一句话理解\n\n\n## 原文摘录与位置\n\n> 摘录：\n\nPDF 页码 / 图号 / 公式编号：\n\n## 我的理解\n\n\n## 还没想通的问题\n\n- \n"},
    {"id": "paper", "name": "论文精读", "description": "从研究问题到方法、证据和个人研究启发。", "body": "## 研究问题与动机\n\n\n## 核心方法：用自己的话讲清楚\n\n\n## 关键公式与符号\n\n原文位置：\n\n\n## 实验结果与证据\n\n原文位置：\n\n\n## 局限与适用条件\n\n\n## 与我的研究有什么关系\n\n\n## 待核实与下一步\n\n- [ ] \n"},
    {"id": "figure", "name": "图表研读", "description": "逐项记录坐标、曲线、机制和证据边界。", "body": "## 图表位置\n\nPDF 页码：\n图号 / 表号：\n\n## 先看什么：坐标、单位与图例\n\n\n## 每条曲线 / 每个子图在表达什么\n\n\n## 作者结论与图中证据\n\n\n## 我的解释与疑问\n\n请区分观察事实、背景知识与推断。\n\n## 需要回原文核实的细节\n\n- [ ] \n"},
    {"id": "blank", "name": "空白笔记", "description": "自由写想法，也可用于跨文献比较。", "body": ""},
]


class Conflict(ValueError):
    pass


def path_for(directory: Path, note_id: str) -> Path:
    if not isinstance(note_id, str) or not re.fullmatch(r"[a-f0-9]{32}", note_id):
        raise ValueError("笔记编号无效")
    return directory / (note_id + ".json")


def load(directory: Path, note_id: str) -> dict:
    with LOCK:
        path = path_for(directory, note_id)
        if not path.is_file():
            raise FileNotFoundError("笔记不存在")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise ValueError("笔记文件无法读取；请保留原文件并从备份恢复") from None
        if (not isinstance(value, dict) or value.get("id") != note_id
                or any(not isinstance(value.get(key), str) for key in ("title", "body", "template", "createdAt", "updatedAt"))
                or type(value.get("revision")) is not int or value["revision"] < 1
                or (value.get("paper") is not None and not isinstance(value["paper"], dict))):
            raise ValueError("笔记文件格式异常；请保留原文件")
        return value


def listing(directory: Path, query: str = "", item_key: str = "") -> dict:
    with LOCK:
        entries, unreadable = [], 0
        for path in directory.glob("*.json"):
            try:
                value = load(directory, path.stem)
                search = "\n".join((value["title"], value["body"], (value.get("paper") or {}).get("title", "")))
                if query.casefold() not in search.casefold():
                    continue
                if item_key and (value.get("paper") or {}).get("key") != item_key:
                    continue
                entries.append({k: value[k] for k in ("id", "title", "template", "paper", "createdAt", "updatedAt", "revision")})
                entries[-1]["excerpt"] = re.sub(r"[#>*`\[\]\n]+", " ", value["body"])[:120].strip()
            except (ValueError, KeyError, TypeError, OSError):
                unreadable += 1
        entries.sort(key=lambda n: (n["updatedAt"], n["id"]), reverse=True)
        return {"notes": entries, "total": len(entries), "unreadable": unreadable}


def _write(directory: Path, value: dict) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    path = path_for(directory, value["id"])
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return value


def create(directory: Path, payload: dict, paper: dict | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("请提供笔记内容")
    template = next((t for t in TEMPLATES if t["id"] == payload.get("template", "quick")), None)
    if not template:
        raise ValueError("模板不存在")
    now = datetime.now(timezone.utc).isoformat()
    metadata = {key: paper.get(key, "") for key in ("key", "title", "creators", "date", "publicationTitle", "doi")} if paper else None
    requested_title = payload.get("title")
    requested_body = payload.get("body")
    if requested_title is not None and (not isinstance(requested_title, str) or not requested_title.strip() or len(requested_title) > 200):
        raise ValueError("笔记标题需为 1–200 个字符")
    if requested_body is not None and (not isinstance(requested_body, str) or len(requested_body) > MAX_BODY):
        raise ValueError("笔记正文不能超过 200000 个字符")
    title = (requested_title.strip() if isinstance(requested_title, str) else (f"{template['name']} · {paper['title']}" if paper else f"我的{template['name']}"))[:200]
    body = requested_body if isinstance(requested_body, str) else template["body"]
    value = {"id": uuid.uuid4().hex, "title": title, "body": body, "template": template["id"],
             "paper": metadata, "createdAt": now, "updatedAt": now, "revision": 1}
    with LOCK:
        return _write(directory, value)


def update(directory: Path, note_id: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("请提供笔记内容")
    title, body, revision = payload.get("title"), payload.get("body"), payload.get("revision")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError("笔记标题需为 1–200 个字符")
    if not isinstance(body, str) or len(body) > MAX_BODY:
        raise ValueError("笔记正文不能超过 200000 个字符")
    if type(revision) is not int:
        raise ValueError("缺少笔记版本，请重新载入")
    with LOCK:
        value = load(directory, note_id)
        if revision != value["revision"]:
            raise Conflict("其他窗口已更新这篇笔记，本次未覆盖已存内容；请先导出草稿，再载入已存版本。")
        if title.strip() == value["title"] and body == value["body"]:
            return value
        value.update(title=title.strip(), body=body, revision=revision + 1, updatedAt=datetime.now(timezone.utc).isoformat())
        return _write(directory, value)


def delete(directory: Path, note_id: str, payload: dict) -> dict:
    if not isinstance(payload, dict) or type(payload.get("revision")) is not int:
        raise ValueError("缺少笔记版本，请重新载入")
    with LOCK:
        value = load(directory, note_id)
        if payload["revision"] != value["revision"]:
            raise Conflict("其他窗口已更新这篇笔记，本次未删除。请先核对已存版本，再决定是否删除。")
        path_for(directory, note_id).unlink()
        return {"deleted": True, "id": note_id}
