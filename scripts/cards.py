"""Small independent cards captured while reading; never calls a model."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading
import uuid

LOCK = threading.RLock()
MAX_CONTENT = 20_000
MAX_SUMMARY = 20_000
MAX_QUESTION = 4_000
MAX_MESSAGES = 40


def path_for(directory: Path, card_id: str) -> Path:
    if not isinstance(card_id, str) or not re.fullmatch(r"[a-f0-9]{32}", card_id):
        raise ValueError("卡片编号无效")
    return directory / f"{card_id}.json"


def load(directory: Path, card_id: str) -> dict:
    with LOCK:
        path = path_for(directory, card_id)
        if not path.is_file():
            raise FileNotFoundError("卡片不存在")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise ValueError("卡片文件无法读取；请保留原文件") from None
        required = ("id", "title", "content", "createdAt", "updatedAt")
        if (not isinstance(value, dict) or value.get("id") != card_id
                or any(not isinstance(value.get(key), str) for key in required)
                or len(value["content"]) > MAX_CONTENT
                or (value.get("summary", "") is not None and not isinstance(value.get("summary", ""), str))
                or len(str(value.get("summary", "") or "")) > MAX_SUMMARY
                or (value.get("conversation", []) is not None and not isinstance(value.get("conversation", []), list))
                or (value.get("paper") is not None and not isinstance(value["paper"], dict))):
            raise ValueError("卡片文件格式异常；请保留原文件")
        return value


def _write(directory: Path, value: dict) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    path = path_for(directory, value["id"])
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return value


def listing(directory: Path) -> dict:
    with LOCK:
        cards, unreadable = [], 0
        for path in directory.glob("*.json"):
            try:
                value = load(directory, path.stem)
                cards.append({"id": value["id"], "title": value["title"], "excerpt": value["content"][:180],
                              "summary": str(value.get("summary", ""))[:240],
                              "paper": value.get("paper"), "source": value.get("source", ""),
                              "createdAt": value["createdAt"], "updatedAt": value["updatedAt"]})
            except (ValueError, KeyError, TypeError, OSError):
                unreadable += 1
        cards.sort(key=lambda card: (card["updatedAt"], card["id"]), reverse=True)
        return {"cards": cards, "total": len(cards), "unreadable": unreadable}


def create(directory: Path, payload: dict, paper: dict | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("请提供卡片内容")
    content = payload.get("content", "")
    if not isinstance(content, str) or not content.strip() or len(content) > MAX_CONTENT:
        raise ValueError("卡片内容不能为空且不能超过 20000 个字符")
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        title = content.strip().splitlines()[0][:80] or "阅读卡片"
    if len(title) > 200:
        raise ValueError("卡片标题不能超过 200 个字符")
    now = datetime.now(timezone.utc).isoformat()
    metadata = {key: paper.get(key, "") for key in ("key", "title", "creators", "date", "publicationTitle", "doi")} if paper else None
    value = {"id": uuid.uuid4().hex, "title": title.strip(), "content": content.strip(), "summary": "", "conversation": [],
             "paper": metadata, "source": str(payload.get("source", "")).strip()[:500],
             "createdAt": now, "updatedAt": now}
    with LOCK:
        return _write(directory, value)


def update(directory: Path, card_id: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("请提供卡片更新内容")
    with LOCK:
        value = load(directory, card_id)
        if "title" in payload:
            title = payload["title"]
            if not isinstance(title, str) or not title.strip() or len(title) > 200:
                raise ValueError("卡片标题不能为空且不能超过 200 个字符")
            value["title"] = title.strip()
        if "summary" in payload:
            summary = payload["summary"]
            if not isinstance(summary, str) or len(summary) > MAX_SUMMARY:
                raise ValueError("卡片总结不能超过 20000 个字符")
            value["summary"] = summary.strip()
        if "conversation" in payload:
            conversation = payload["conversation"]
            if not isinstance(conversation, list) or len(conversation) > MAX_MESSAGES:
                raise ValueError("卡片对话记录过长")
            cleaned = []
            for message in conversation:
                if not isinstance(message, dict) or message.get("role") not in ("user", "assistant") or not isinstance(message.get("content"), str):
                    raise ValueError("卡片对话记录格式异常")
                if len(message["content"]) > MAX_QUESTION:
                    raise ValueError("卡片对话内容过长")
                cleaned.append({"role": message["role"], "content": message["content"], "createdAt": str(message.get("createdAt", ""))})
            value["conversation"] = cleaned
        value["updatedAt"] = datetime.now(timezone.utc).isoformat()
        return _write(directory, value)


def delete(directory: Path, card_id: str) -> dict:
    with LOCK:
        path_for(directory, card_id).unlink()
        return {"deleted": True, "id": card_id}
