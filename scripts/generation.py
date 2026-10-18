"""Provider-aware chapter output settings, with no fixed application cap.

DeepSeek contract checked 2026-10-18:
https://api-docs.deepseek.com/api/create-chat-completion
https://api-docs.deepseek.com/guides/thinking_mode
"""
from urllib.parse import urlparse

DEEPSEEK_MODELS = {"deepseek-flash", "deepseek-v4-pro"}
THINKING_MODES = {"auto", "low", "high", "max", "off"}


def settings(value):
    raw_limit = value.get("maxOutputTokens")
    if raw_limit in (None, "", "auto"):
        limit = None
    elif type(raw_limit) is int or (isinstance(raw_limit, str) and raw_limit.isascii() and raw_limit.isdecimal()):
        limit = int(raw_limit)
        if not 1024 <= limit <= 393216:
            raise ValueError("输出预算请填写 1024–393216 之间的整数，或留空使用模型服务默认值。")
    else:
        raise ValueError("输出预算请填写整数，或留空使用模型服务默认值。")
    mode = value.get("thinkingMode", "auto")
    if not isinstance(mode, str) or mode not in THINKING_MODES:
        raise ValueError("未知的思考模式选项")
    return {"maxOutputTokens": limit, "thinkingMode": mode}


def is_deepseek(config):
    return (urlparse(config.get("baseUrl", "")).hostname == "api.deepseek.com"
            and config.get("model") in DEEPSEEK_MODELS)


def profile(config):
    result = settings(config)
    supported = is_deepseek(config)
    result["thinkingSupported"] = supported
    if result["maxOutputTokens"] is not None:
        result["budgetLabel"] = f"本次输出预算上限 {result['maxOutputTokens']:,} Token"
    elif supported:
        expected = {"off": 8192, "max": 131072}.get(result["thinkingMode"], 65536)
        result["budgetLabel"] = f"使用 DeepSeek 服务默认预算（当前文档约 {expected // 1024}K Token）"
    else:
        result["budgetLabel"] = "使用模型服务默认输出预算"
    result["thinkingLabel"] = ({"auto": "跟随服务默认", "off": "关闭思考", "low": "较轻思考", "high": "深入思考", "max": "最大思考"}[result["thinkingMode"]]
                               if supported else "跟随模型服务")
    return result


def request_options(config):
    options = settings(config)
    body = {}
    # Omission is intentional: DeepSeek thinking defaults to 64K/128K, while
    # the former hard-coded 8000 could exhaust thinking before any answer.
    if options["maxOutputTokens"] is not None:
        body["max_tokens"] = options["maxOutputTokens"]
    if is_deepseek(config):
        body["response_format"] = {"type": "json_object"}
        mode = options["thinkingMode"]
        if mode == "off":
            body["thinking"] = {"type": "disabled"}
            body["temperature"] = 0.2
        elif mode != "auto":
            body["thinking"] = {"type": "enabled"}
            body["reasoning_effort"] = mode
    else:
        body["temperature"] = 0.2
    return body


def response_stats(payload, message):
    usage = payload.get("usage") if isinstance(payload, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("completion_tokens_details")
    details = details if isinstance(details, dict) else {}
    fields = {"promptTokens": usage.get("prompt_tokens"), "completionTokens": usage.get("completion_tokens"),
              "reasoningTokens": details.get("reasoning_tokens")}
    result = {key: number for key, number in fields.items() if type(number) is int and number >= 0}
    # Record a boolean for diagnosis, never expose the model's private chain
    # of thought as if it were the requested teaching answer.
    result["hadReasoning"] = bool(message.get("reasoning_content")) if isinstance(message, dict) else False
    return result
