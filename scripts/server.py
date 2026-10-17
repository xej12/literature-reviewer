from __future__ import annotations

import json
import base64
import io
import os
import re
import sqlite3
import sys
import winreg
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from pypdf import PdfReader
from pdf2image import convert_from_path


SKILL_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = SKILL_DIR / "web"
SETTINGS_PATH = SKILL_DIR / "data" / "settings.json"
ANALYSIS_DIR = SKILL_DIR / "data" / "analysis"
DEFAULT_PORT = int(os.environ.get("LITERATURE_REVIEWER_PORT", "8765"))


def discover_zotero_dir() -> Path | None:
    candidates: list[Path] = []
    configured = os.environ.get("ZOTERO_DATA_DIR")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            Path.home() / "Zotero",
            Path(os.environ.get("APPDATA", "")) / "Zotero" / "Zotero" / "Profiles",
        ]
    )
    for candidate in candidates:
        db = candidate / "zotero.sqlite"
        if db.exists():
            return candidate
        if candidate.exists():
            matches = list(candidate.glob("*/zotero.sqlite"))
            if matches:
                return matches[0].parent
    return None


def detect_zotero_version() -> str | None:
    locations = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for root, path in locations:
        try:
            with winreg.OpenKey(root, path) as key:
                for idx in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        name = winreg.EnumKey(key, idx)
                        with winreg.OpenKey(key, name) as item:
                            display = winreg.QueryValueEx(item, "DisplayName")[0]
                            if str(display).lower() == "zotero":
                                return str(winreg.QueryValueEx(item, "DisplayVersion")[0])
                    except (OSError, IndexError):
                        continue
        except OSError:
            continue
    return None


class ZoteroStore:
    def __init__(self) -> None:
        self.data_dir = discover_zotero_dir()
        if not self.data_dir:
            raise RuntimeError("未找到 Zotero 数据目录。可设置环境变量 ZOTERO_DATA_DIR。")
        self.db_path = self.data_dir / "zotero.sqlite"
        self.version = detect_zotero_version()
        self._pdf_cache: dict[str, dict[str, Any]] = {}
        self._image_cache: dict[str, bytes] = {}

    def connect(self) -> sqlite3.Connection:
        # Prefer the normal read-only view so SQLite can include Zotero's live
        # WAL. Fall back to immutable mode if a transient lock prevents it.
        for suffix in ("?mode=ro", "?mode=ro&immutable=1"):
            try:
                uri = f"file:{self.db_path.as_posix()}{suffix}"
                conn = sqlite3.connect(uri, uri=True, timeout=0.5)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA query_only=ON")
                conn.execute("SELECT 1")
                return conn
            except sqlite3.Error:
                try:
                    conn.close()
                except UnboundLocalError:
                    pass
        raise RuntimeError("无法以只读方式打开 Zotero 数据库")

    def _field_map(self, conn: sqlite3.Connection, item_id: int) -> dict[str, str]:
        rows = conn.execute(
            """
            SELECT f.fieldName, v.value
            FROM itemData d
            JOIN fields f ON f.fieldID = d.fieldID
            JOIN itemDataValues v ON v.valueID = d.valueID
            WHERE d.itemID = ?
            """,
            (item_id,),
        ).fetchall()
        return {str(row[0]): str(row[1]) for row in rows if row[1] is not None}

    def _creators(self, conn: sqlite3.Connection, item_id: int) -> list[str]:
        rows = conn.execute(
            """
            SELECT c.firstName, c.lastName
            FROM itemCreators ic JOIN creators c ON c.creatorID = ic.creatorID
            WHERE ic.itemID = ? ORDER BY ic.orderIndex
            """,
            (item_id,),
        ).fetchall()
        return [" ".join(part for part in (row[0], row[1]) if part).strip() for row in rows]

    def _collections(self, conn: sqlite3.Connection, item_id: int) -> list[dict[str, str]]:
        rows = conn.execute(
            """
            SELECT c.key, c.collectionName
            FROM collectionItems ci JOIN collections c ON c.collectionID = ci.collectionID
            WHERE ci.itemID = ? ORDER BY c.collectionName
            """,
            (item_id,),
        ).fetchall()
        return [{"key": str(row[0]), "name": str(row[1])} for row in rows]

    def _attachments(self, conn: sqlite3.Connection, item_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT i.key, a.contentType, a.path, a.storageHash
            FROM itemAttachments a JOIN items i ON i.itemID = a.itemID
            WHERE a.parentItemID = ? OR (a.parentItemID IS NULL AND a.itemID = ?)
            ORDER BY i.dateAdded
            """,
            (item_id, item_id),
        ).fetchall()
        result = []
        for row in rows:
            raw_path = str(row[2] or "")
            filename = raw_path.split(":", 1)[1] if raw_path.startswith("storage:") else raw_path
            # Zotero stores each attachment under the attachment item's key,
            # even when it has a parent bibliographic item.
            path = self.data_dir / "storage" / str(row[0]) / filename if filename else None
            result.append(
                {
                    "key": str(row[0]),
                    "contentType": row[1],
                    "filename": filename,
                    "exists": bool(path and path.exists()),
                    "size": path.stat().st_size if path and path.exists() else None,
                }
            )
        return result

    def _item(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        fields = self._field_map(conn, int(row["itemID"]))
        item = {
            "key": str(row["key"]),
            "itemType": str(row["typeName"]),
            "title": fields.get("title", "未命名条目"),
            "abstract": fields.get("abstractNote", ""),
            "date": fields.get("date", ""),
            "doi": fields.get("DOI", ""),
            "publicationTitle": fields.get("publicationTitle", ""),
            "url": fields.get("url", ""),
            "language": fields.get("language", ""),
            "pages": fields.get("pages", ""),
            "creators": self._creators(conn, int(row["itemID"])),
            "collections": self._collections(conn, int(row["itemID"])),
        }
        item["attachments"] = self._attachments(conn, int(row["itemID"]))
        return item

    def health(self) -> dict[str, Any]:
        with self.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM items WHERE itemTypeID NOT IN (1, 3, 14, 15, 28)"
            ).fetchone()[0]
        return {
            "ok": True,
            "zoteroVersion": self.version,
            "dataDir": str(self.data_dir),
            "itemCount": int(count),
            "readOnly": True,
        }

    def collections(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.key, c.collectionName, COUNT(i.itemID) AS itemCount
                FROM collections c
                LEFT JOIN collectionItems ci ON ci.collectionID = c.collectionID
                LEFT JOIN items i ON i.itemID = ci.itemID AND i.itemTypeID NOT IN (1, 3, 14, 15, 28)
                GROUP BY c.collectionID ORDER BY c.collectionName COLLATE NOCASE
                """
            ).fetchall()
        return [{"key": str(r[0]), "name": str(r[1]), "itemCount": int(r[2])} for r in rows]

    def items(self, query: str = "", collection: str = "", limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 200))
        where = ["i.itemTypeID NOT IN (1, 3, 14, 15, 28)"]
        params: list[Any] = []
        if query:
            where.append(
                "EXISTS (SELECT 1 FROM itemData d JOIN fields f ON f.fieldID=d.fieldID JOIN itemDataValues v ON v.valueID=d.valueID WHERE d.itemID=i.itemID AND f.fieldName IN ('title','abstractNote') AND v.value LIKE ? COLLATE NOCASE)"
            )
            params.append(f"%{query}%")
        if collection:
            where.append(
                "EXISTS (SELECT 1 FROM collectionItems ci JOIN collections c ON c.collectionID=ci.collectionID WHERE ci.itemID=i.itemID AND c.key=?)"
            )
            params.append(collection)
        sql = f"""
            SELECT i.itemID, i.key, it.typeName
            FROM items i JOIN itemTypes it ON it.itemTypeID=i.itemTypeID
            WHERE {' AND '.join(where)}
            ORDER BY i.dateModified DESC LIMIT ?
        """
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._item(conn, row) for row in rows]

    def item(self, key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT i.itemID, i.key, it.typeName FROM items i JOIN itemTypes it ON it.itemTypeID=i.itemTypeID WHERE i.key=?",
                (key,),
            ).fetchone()
            return self._item(conn, row) if row else None

    def attachment_path(self, attachment_key: str) -> Path | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT path FROM itemAttachments a JOIN items i ON i.itemID=a.itemID WHERE i.key=?",
                (attachment_key,),
            ).fetchone()
        if not row or not row[0]:
            return None
        raw_path = str(row[0])
        filename = raw_path.split(":", 1)[1] if raw_path.startswith("storage:") else raw_path
        if not filename:
            return None
        path = (self.data_dir / "storage" / attachment_key / filename).resolve()
        storage_root = (self.data_dir / "storage").resolve()
        return path if storage_root in path.parents and path.exists() else None

    def pdf_page(self, attachment_key: str, page: int) -> dict[str, Any]:
        path = self.attachment_path(attachment_key)
        if not path:
            raise FileNotFoundError("找不到 PDF 附件")
        if path.suffix.lower() != ".pdf":
            raise ValueError("该附件不是 PDF")
        mtime = path.stat().st_mtime_ns
        cached = self._pdf_cache.get(attachment_key)
        if not cached or cached["path"] != str(path) or cached["mtime"] != mtime:
            reader = PdfReader(str(path))
            pages = [pdf_page.extract_text() or "" for pdf_page in reader.pages]
            cached = {"path": str(path), "mtime": mtime, "pages": pages}
            self._pdf_cache[attachment_key] = cached
        pages = cached["pages"]
        if not pages:
            raise ValueError("PDF 没有可提取的页面")
        page = max(1, min(int(page), len(pages)))
        return {
            "attachmentKey": attachment_key,
            "page": page,
            "pageCount": len(pages),
            "text": pages[page - 1],
            "hasText": bool(pages[page - 1].strip()),
        }

    def pdf_page_image(self, attachment_key: str, page: int) -> bytes:
        path = self.attachment_path(attachment_key)
        if not path:
            raise FileNotFoundError("找不到 PDF 附件")
        cache_key = f"{attachment_key}:{page}:{path.stat().st_mtime_ns}"
        if cache_key not in self._image_cache:
            # A slightly higher raster resolution keeps axis labels and small
            # table text usable both in the preview and for vision models.
            rendered = convert_from_path(str(path), first_page=page, last_page=page, dpi=150, fmt="png")
            if not rendered:
                raise ValueError("无法渲染 PDF 页面")
            stream = io.BytesIO()
            rendered[0].save(stream, format="PNG")
            self._image_cache[cache_key] = stream.getvalue()
        return self._image_cache[cache_key]

    def analysis_context(self, key: str, max_chars: int = 30000) -> tuple[dict[str, Any], str]:
        item = self.item(key)
        if not item:
            raise FileNotFoundError("条目不存在")
        chunks = [
            f"标题：{item['title']}",
            f"作者：{'、'.join(item['creators'])}",
            f"来源：{item['publicationTitle']} {item['date']}",
        ]
        if item["abstract"]:
            chunks.append(f"摘要：{item['abstract']}")
        pdf = next((a for a in item["attachments"] if a["contentType"] == "application/pdf" and a["exists"]), None)
        if pdf:
            self.pdf_page(pdf["key"], 1)
            pages = self._pdf_cache[pdf["key"]]["pages"]
            remaining = max_chars - sum(len(chunk) for chunk in chunks)
            for index, text in enumerate(pages[:12], start=1):
                if remaining <= 0:
                    break
                excerpt = text[:remaining]
                chunks.append(f"[第 {index} 页]\n{excerpt}")
                remaining -= len(excerpt)
        return item, "\n\n".join(chunks)[:max_chars]


def saved_model_config() -> dict[str, str]:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return {"baseUrl": str(data.get("baseUrl", "")), "model": str(data.get("model", "")), "apiKey": str(data.get("apiKey", ""))}
    except (OSError, json.JSONDecodeError):
        return {"baseUrl": "", "model": "", "apiKey": ""}


def model_config() -> dict[str, str | bool]:
    saved = saved_model_config()
    key = os.environ.get("LITERATURE_REVIEWER_API_KEY") or os.environ.get("OPENAI_API_KEY") or saved["apiKey"]
    base_url = (os.environ.get("LITERATURE_REVIEWER_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or saved["baseUrl"] or "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("LITERATURE_REVIEWER_MODEL") or os.environ.get("OPENAI_MODEL") or saved["model"] or "gpt-4o-mini"
    is_local = "localhost" in base_url or "127.0.0.1" in base_url
    return {"configured": bool(key) or is_local, "baseUrl": base_url, "model": model, "apiKey": key or ""}


def save_model_config(payload: dict[str, Any]) -> dict[str, str | bool]:
    base_url = str(payload.get("baseUrl", "")).strip().rstrip("/")
    model = str(payload.get("model", "")).strip()
    api_key = str(payload.get("apiKey", "")).strip()
    if not base_url or not model:
        raise ValueError("请填写 API 地址和模型名称")
    if not api_key:
        api_key = saved_model_config()["apiKey"]
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps({"baseUrl": base_url, "model": model, "apiKey": api_key}, ensure_ascii=False, indent=2), encoding="utf-8")
    config = model_config()
    return {"configured": config["configured"], "baseUrl": config["baseUrl"], "model": config["model"]}


def analysis_path(item_key: str) -> Path:
    if not re.fullmatch(r"[A-Z0-9]+", item_key):
        raise ValueError("无效的文献键")
    return ANALYSIS_DIR / f"{item_key}.json"


def load_analysis(item_key: str) -> dict[str, Any]:
    try:
        result = json.loads(analysis_path(item_key).read_text(encoding="utf-8"))
        # Older cache files predate figure analysis. Keep them readable while
        # giving the client a stable shape for the new feature.
        result.setdefault("figures", {})
        return result
    except (OSError, json.JSONDecodeError):
        return {"itemKey": item_key, "summary": None, "terms": None, "figures": {}, "updatedAt": None, "model": None}


def save_analysis(item_key: str, kind: str, result: dict[str, Any]) -> dict[str, Any]:
    existing = load_analysis(item_key)
    existing[kind] = result.get(kind)
    existing["itemKey"] = item_key
    existing["title"] = result.get("title", existing.get("title", ""))
    existing["model"] = result.get("model", existing.get("model"))
    existing["updatedAt"] = __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    analysis_path(item_key).write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return existing


def save_figure(item_key: str, figure_key: str, result: dict[str, Any]) -> dict[str, Any]:
    """Save one page's figure result without replacing other cached pages."""
    existing = load_analysis(item_key)
    figures = existing.setdefault("figures", {})
    figures[figure_key] = result.get("figure")
    existing["itemKey"] = item_key
    existing["title"] = result.get("title", existing.get("title", ""))
    existing["model"] = result.get("model", existing.get("model"))
    existing["updatedAt"] = __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    analysis_path(item_key).write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return existing


def generate_summary(key: str) -> dict[str, Any]:
    config = model_config()
    if not config["configured"]:
        raise RuntimeError("尚未配置模型。请设置 LITERATURE_REVIEWER_API_KEY，或使用兼容 OpenAI API 的本地模型。")
    item, context = STORE.analysis_context(key)  # type: ignore[union-attr]
    prompt = (
        "你是科研文献助理。请只根据提供的论文信息，输出严格 JSON，不要 Markdown，不要额外解释。\n"
        "JSON 必须包含四个字符串字段：research_question（研究问题）、methods（方法与数据）、"
        "findings（主要发现）、limitations（局限性与需要核对之处）。\n"
        "每个字段用简洁的中文段落回答；如果原文没有足够证据，明确写‘原文未说明’，不要猜测。\n"
        "回答中涉及的关键判断尽量保留页码标记，例如‘（第 2 页）’。\n\n论文信息：\n" + context
    )
    body = json.dumps(
        {
            "model": config["model"],
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "你输出的是供科研人员核对的结构化文献摘要。"},
                {"role": "user", "content": prompt},
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{config['baseUrl']}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config['apiKey']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"模型请求失败（HTTP {exc.code}）：{detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接模型服务：{exc.reason}") from exc
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("模型返回的内容不是有效 JSON，请更换模型或重试。") from exc
    for field in ("research_question", "methods", "findings", "limitations"):
        result.setdefault(field, "原文未说明")
    return {"itemKey": item["key"], "title": item["title"], "summary": result, "model": config["model"]}


def generate_terms(key: str) -> dict[str, Any]:
    config = model_config()
    if not config["configured"]:
        raise RuntimeError("尚未配置模型。请先打开右上角的模型设置。")
    item, context = STORE.analysis_context(key)  # type: ignore[union-attr]
    prompt = (
        "你是科研文献助理。请只根据提供的论文信息，输出严格 JSON，不要 Markdown，不要额外解释。\n"
        "JSON 必须是对象，包含 terms 数组。数组最多 8 项，每项包含 term、explanation、context、page 四个字段。\n"
        "term 是论文中的专业名词或关键方法；explanation 用面向初学者的中文解释；context 说明它在本文中的具体含义；"
        "page 填页码数字，没有页码就填 null。不要把普通词汇列为术语，不要凭空补充论文没有支持的定义。\n\n论文信息：\n" + context
    )
    body = json.dumps(
        {
            "model": config["model"],
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "你输出的是供科研人员核对的术语卡片。"},
                {"role": "user", "content": prompt},
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{config['baseUrl']}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config['apiKey']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"模型请求失败（HTTP {exc.code}）：{detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接模型服务：{exc.reason}") from exc
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("模型返回的内容不是有效 JSON，请更换模型或重试。") from exc
    terms = result.get("terms", []) if isinstance(result, dict) else []
    normalized = []
    for term in terms[:8]:
        if isinstance(term, dict) and term.get("term"):
            normalized.append({
                "term": str(term.get("term")),
                "explanation": str(term.get("explanation", "原文未说明")),
                "context": str(term.get("context", "原文未说明")),
                "page": term.get("page"),
            })
    return {"itemKey": item["key"], "title": item["title"], "terms": normalized, "model": config["model"]}


def generate_figure(key: str, attachment_key: str, page: int) -> dict[str, Any]:
    """Ask a vision-capable OpenAI-compatible model to interpret one PDF page."""
    config = model_config()
    if not config["configured"]:
        raise RuntimeError("尚未配置模型。请先打开右上角的模型设置。")
    item = STORE.item(key)  # type: ignore[union-attr]
    if not item:
        raise FileNotFoundError("条目不存在")
    page_info = STORE.pdf_page(attachment_key, page)  # type: ignore[union-attr]
    image = STORE.pdf_page_image(attachment_key, page_info["page"])  # type: ignore[union-attr]
    image_data = base64.b64encode(image).decode("ascii")
    prompt = (
        "你是科研文献助理。请查看这张论文 PDF 页面截图，重点识别其中的图、表、坐标轴、图例和注释。"
        "如果页面没有清晰的图表，请明确说明。只根据图片中可见内容，输出严格 JSON，不要 Markdown。\n"
        "JSON 必须包含四个字符串字段：description（图表展示了什么）、trends（主要趋势或组间差异）、"
        "takeaway（对读者最重要的结论）、caveats（图表解读的限制或需要核对之处）。"
        "不要臆测看不清的数值；无法判断时写‘图中无法确认’。用简洁中文回答。\n\n"
        f"论文标题：{item['title']}\nPDF 页码：第 {page_info['page']} 页（共 {page_info['pageCount']} 页）"
    )
    body = json.dumps(
        {
            "model": config["model"],
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "你输出的是供科研人员核对的结构化图表解读。"},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}", "detail": "high"}},
                ]},
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{config['baseUrl']}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config['apiKey']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"模型请求失败（HTTP {exc.code}）：{detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接模型服务：{exc.reason}") from exc
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(content).strip(), flags=re.IGNORECASE)
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("模型返回的内容不是有效 JSON，请更换支持视觉输入的模型或重试。") from exc
    figure = {
        "description": str(result.get("description", "图中无法确认")),
        "trends": str(result.get("trends", "图中无法确认")),
        "takeaway": str(result.get("takeaway", "图中无法确认")),
        "caveats": str(result.get("caveats", "图中无法确认")),
        "attachmentKey": attachment_key,
        "page": page_info["page"],
        "pageCount": page_info["pageCount"],
    }
    return {"itemKey": item["key"], "title": item["title"], "figure": figure, "model": config["model"]}


try:
    STORE = ZoteroStore()
except Exception as exc:  # report a useful JSON error in the browser
    STORE = None
    STARTUP_ERROR = str(exc)


class Handler(BaseHTTPRequestHandler):
    server_version = "LiteratureReviewer/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stdout.write("[web] " + (format % args) + "\n")

    def send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        params = parse_qs(parsed.query)
        try:
            if path == "/api/health":
                if STORE is None:
                    self.send_json({"ok": False, "error": STARTUP_ERROR}, HTTPStatus.INTERNAL_SERVER_ERROR)
                else:
                    self.send_json(STORE.health())
                return
            if path == "/api/model":
                config = model_config()
                self.send_json({"configured": config["configured"], "baseUrl": config["baseUrl"], "model": config["model"]})
                return
            if path == "/api/collections":
                if STORE is None:
                    raise RuntimeError(STARTUP_ERROR)
                self.send_json(STORE.collections())
                return
            if path == "/api/items":
                if STORE is None:
                    raise RuntimeError(STARTUP_ERROR)
                q = params.get("q", [""])[0].strip()
                collection = params.get("collection", [""])[0].strip()
                limit = int(params.get("limit", ["50"])[0])
                self.send_json(STORE.items(q, collection, limit))
                return
            match = re.fullmatch(r"/api/items/([A-Z0-9]+)/analysis", path)
            if match:
                self.send_json(load_analysis(match.group(1)))
                return
            match = re.fullmatch(r"/api/items/([A-Z0-9]+)", path)
            if match:
                if STORE is None:
                    raise RuntimeError(STARTUP_ERROR)
                item = STORE.item(match.group(1))
                if item is None:
                    self.send_json({"error": "条目不存在"}, HTTPStatus.NOT_FOUND)
                else:
                    self.send_json(item)
                return
            match = re.fullmatch(r"/api/attachments/([A-Z0-9]+)/text", path)
            if match:
                if STORE is None:
                    raise RuntimeError(STARTUP_ERROR)
                page = int(params.get("page", ["1"])[0])
                self.send_json(STORE.pdf_page(match.group(1), page))
                return
            match = re.fullmatch(r"/api/attachments/([A-Z0-9]+)/page-image", path)
            if match:
                if STORE is None:
                    raise RuntimeError(STARTUP_ERROR)
                page = int(params.get("page", ["1"])[0])
                page_info = STORE.pdf_page(match.group(1), page)
                body = STORE.pdf_page_image(match.group(1), page_info["page"])
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "private, max-age=3600")
                self.end_headers()
                self.wfile.write(body)
                return
            match = re.fullmatch(r"/api/attachments/([A-Z0-9]+)/file", path)
            if match:
                if STORE is None:
                    raise RuntimeError(STARTUP_ERROR)
                attachment = STORE.attachment_path(match.group(1))
                if not attachment:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                body = attachment.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Disposition", "inline")
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/" or path == "/index.html":
                self.serve_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
                return
            if path.startswith("/static/"):
                file_path = (WEB_DIR / path.removeprefix("/static/")).resolve()
                if WEB_DIR.resolve() not in file_path.parents:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                content_types = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
                self.serve_file(file_path, content_types.get(file_path.suffix, "application/octet-stream"))
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, sqlite3.Error, RuntimeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/model":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                self.send_json(save_model_config(payload))
            except (ValueError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        match = re.fullmatch(r"/api/items/([A-Z0-9]+)/(summary|terms|figure)", path)
        if not match:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            if STORE is None:
                raise RuntimeError(STARTUP_ERROR)
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            kind = match.group(2)
            cached = load_analysis(match.group(1))
            if kind == "figure":
                attachment_key = str(payload.get("attachmentKey", "")).strip()
                page = int(payload.get("page", 1))
                if not re.fullmatch(r"[A-Z0-9]+", attachment_key):
                    raise ValueError("请先选择一个 PDF 附件")
                if page < 1:
                    raise ValueError("页码必须是正整数")
                # Clamp once before constructing the cache key so an out of
                # range request cannot create a duplicate entry for the same
                # physical PDF page.
                page = STORE.pdf_page(attachment_key, page)["page"]  # type: ignore[union-attr]
                figure_key = f"{attachment_key}:{page}"
                cached_figure = cached.get("figures", {}).get(figure_key)
                if cached_figure and not payload.get("force"):
                    self.send_json({**cached, "figure": cached_figure, "figureKey": figure_key, "cached": True})
                    return
                result = generate_figure(match.group(1), attachment_key, page)
                saved = save_figure(match.group(1), figure_key, result)
                self.send_json({**saved, "figure": saved["figures"][figure_key], "figureKey": figure_key, "cached": False})
                return
            if not payload.get("force") and cached.get(kind):
                self.send_json({**cached, "cached": True})
                return
            result = generate_summary(match.group(1)) if kind == "summary" else generate_terms(match.group(1))
            saved = save_analysis(match.group(1), kind, result)
            self.send_json({**saved, "cached": False})
        except FileNotFoundError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.FAILED_DEPENDENCY)

    def serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Literature Reviewer running at http://127.0.0.1:{port}")
    if STORE:
        print(f"Zotero: {STORE.data_dir} (version {STORE.version or 'unknown'})")
    else:
        print(f"Zotero error: {STARTUP_ERROR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
