"""Conservative local JSON formatting repair; never complete missing content."""
import json
import re


def visible_text(content):
    """Use answer text, not a provider's separate reasoning field."""
    if isinstance(content, list):
        content = "\n".join(c["text"] for c in content if isinstance(c, dict) and isinstance(c.get("text"), str))
    if not isinstance(content, str):
        return ""
    text = content.lstrip("\ufeff \t\r\n")
    while text.startswith("<think>"):
        end = text.find("</think>")
        if end < 0:
            return ""
        text = text[end + len("</think>"):].lstrip()
    return text


def repair_format(text):
    """Fix escaping/commas only, without inventing values, quotes or braces."""
    out, notes = [], set()
    quoted, math, i = False, None, 0
    while i < len(text):
        c = text[i]
        if c == '"':
            quoted = not quoted
            math = None
            out.append(c)
            i += 1
            continue
        if not quoted:
            if c == ',' and re.match(r"\s*[}\]]", text[i + 1:]):
                notes.add("已在本电脑移除 JSON 末尾多余逗号。")
                i += 1
                continue
            out.append(c)
            i += 1
            continue
        if c == '$':
            delimiter = '$$' if text[i:i + 2] == '$$' else '$'
            math = None if math == delimiter else delimiter if math is None else math
            out.append(delimiter)
            i += len(delimiter)
            continue
        if c == '\\' and i + 1 < len(text):
            following = text[i + 1]
            if following == '\\':
                # Correctly JSON-escaped LaTeX must remain byte-for-byte intact.
                if text[i + 2:i + 3] in ('(', '['):
                    math = ')' if text[i + 2] == '(' else ']'
                elif text[i + 2:i + 3] in (')', ']'):
                    math = None
                out.append(text[i:i + 2])
                i += 2
                continue
            if following in ('(', '['):
                math = ')' if following == '(' else ']'
            elif following in (')', ']'):
                math = None
            command = re.match(r"[A-Za-z]+", text[i + 1:])
            valid_unicode = following == 'u' and bool(re.match(r"[0-9a-fA-F]{4}", text[i + 2:i + 6]))
            # \beta / \frac / \theta otherwise parse as backspace, formfeed,
            # or tab with silently corrupted mathematics, even in valid JSON.
            tex_command = command and not valid_unicode and ((math is not None and len(command[0]) > 1) or command[0] in {
                'frac', 'beta', 'bar', 'begin', 'boldsymbol', 'theta', 'tau', 'times',
                'text', 'tilde', 'tan', 'tanh', 'nabla', 'nu', 'neq', 'notin', 'rho',
                'right', 'rightarrow', 'rangle', 'rm', 'bf',
            })
            invalid_escape = following not in '"\\/bfnrtu' or (following == 'u' and not valid_unicode)
            if invalid_escape or (tex_command and following not in '"/'):
                out.append('\\\\')
                notes.add("已在本电脑修复公式反斜杠的 JSON 转义。")
                i += 1
                continue
            out.append(text[i:i + 2])
            i += 2
            continue
        if ord(c) < 32:
            out.append(json.dumps(c)[1:-1])
            notes.add("已在本电脑修复 JSON 字符串中的换行或控制字符。")
        else:
            out.append(c)
        i += 1
    return ''.join(out), sorted(notes)


def parse_chapter(content, finish_reason=None):
    text = visible_text(content)
    if finish_reason == 'length':
        if not text:
            raise ValueError("模型在生成正文前耗尽了本次预算，没有返回讲解内容。思考模式也会占用输出预算；请使用自动预算或提高预算后重新生成。")
        raise ValueError("模型输出达到长度限制，答复可能未写完；原始答复已保存，未作为完整章节采用。")
    if not text:
        raise ValueError("模型没有返回可整理的正文答复，已保存本次返回状态。")
    # Ignore prose/fences outside the answer object. raw_decode also ignores
    # closing fences and suffix explanations without guessing missing brackets.
    start = text.find('{')
    if start < 0:
        raise ValueError("模型返回了普通文本，暂不能整理为章节；原始答复已保存，可以直接查看。")
    candidate = text[start:]
    repaired, notes = repair_format(candidate)
    try:
        value, _ = json.JSONDecoder().raw_decode(repaired)
    except ValueError as exc:
        raise ValueError("模型答复仍有无法安全修复的格式问题；原始答复已保存，已有章节保留。") from exc
    if not isinstance(value, dict):
        raise ValueError("模型没有返回章节对象，原始答复已保存。")
    return value, notes
