"""智能指令解析：用 LLM 从自然语言里提取拉黑/屏蔽所需的参数。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from astrbot.api.all import AstrMessageEvent, Context, Plain, logger

from .ban import 北京时区
from .utils import User, 解析时长

默认智能时长 = 20 * 60
"""智能解析未给出时长时的默认值（秒）"""

帮助词 = {"-h", "--h", "-help", "--help", "help", "帮助", "-帮助", "--帮助"}

系统提示 = (
    "你是一个黑名单指令解析器，只负责把管理员的一句话解析成结构化参数。"
    "你只输出一个 JSON 对象，不输出解释、Markdown 或代码块。"
)

输出格式 = '{"用户ID": "", "用户名": "", "群号": "", "理由": "", "时长": ""}'


@dataclass
class 智能参数:
    用户ID: str = ""
    用户名: str = ""
    群ID: str = ""
    理由: str = ""
    时长秒: int | None = None
    """解析出的时长秒数，None 表示没有给出有效时长"""
    永久: bool = False
    """是否明确要求永久"""


def 提取JSON(text: str) -> dict | None:
    """从模型回复里提取第一个 JSON 对象，兼容 Markdown 代码块和前后废话。"""
    if not text:
        return None
    s = text.strip()
    block = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL | re.IGNORECASE)
    if block:
        s = block.group(1).strip()
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(s[start : i + 1])
                except json.JSONDecodeError:
                    return None
                return data if isinstance(data, dict) else None
    return None


def 获取模型ID(context: Context, 配置值: str, event: AstrMessageEvent) -> str:
    """取插件配置的模型 ID，留空则使用当前会话的默认对话模型。"""
    pid = str(配置值 or "").strip()
    if pid:
        return pid
    try:
        prov = context.get_using_provider(umo=event.unified_msg_origin)
    except Exception:
        logger.warning("智能指令：获取当前会话模型失败", exc_info=True)
        return ""
    if prov is None:
        return ""
    return str(prov.provider_config.get("id") or "")


def 构建提示(
    event: AstrMessageEvent,
    指令: str,
    原始文本: str,
    目标: User | None = None,
) -> str:
    """把当前聊天上下文和原始指令拼成给模型的提示词。"""
    gid = event.get_group_id() or "私聊"
    sender = event.get_sender_name() or "未知"
    lines = [
        "请从下面这句管理员指令中提取参数。",
        "",
        "【当前上下文】",
        f"- 当前时间：{datetime.now(北京时区).strftime('%Y-%m-%d %H:%M')}（北京时间）",
        f"- 当前群号：{gid}",
        f"- 指令发送者：{sender}（{event.get_sender_id()}）",
    ]
    if 目标 is not None:
        lines.append(f"- 被艾特/引用的用户：{目标.name or '未知'}（{目标.id}）")
    text = 原始文本.strip()
    lines += [
        f"- 管理员指令：{指令}" + (f" {text}" if text else ""),
        "",
        "【输出 JSON 格式】",
        输出格式,
        "",
        "【规则】",
        "1. 用户ID：只能填管理员明确给出的 QQ 号；没有给出就留空，绝对不能编造。",
        "2. 用户名：管理员指认对象的昵称；没有给出就留空。",
        '3. 群号：填纯数字群号、"全局"或"私聊"；没指定就留空（表示当前群）。',
        '4. 理由：用简短中文概括违规原因，不超过 30 字；没有说明就填"无理由"。',
        '5. 时长：使用 5min、1h、2d 这类格式；没有说明就填"20min"；'
        '管理员明确要求永久时填"永久"。',
        "6. 只输出 JSON，不要输出任何其他内容。",
    ]
    return "\n".join(lines)


def _取字段(data: dict, *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is None or isinstance(value, (dict, list)):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def 规整解析(data: dict) -> 智能参数:
    """把模型返回的 JSON 统一成 智能参数。"""
    uid = _取字段(data, "用户ID", "用户id", "user_id", "uid", "QQ", "qq", "QQ号")
    name = _取字段(data, "用户名", "用户昵称", "user_name", "nickname", "name")
    gid = _取字段(data, "群号", "群ID", "群id", "group_id", "gid", "group")
    reason = _取字段(data, "理由", "原因", "reason")
    duration = _取字段(data, "时长", "时间", "duration", "time")

    gid_key = re.sub(r"\s+", "", gid).lower()
    if gid_key in {"全局", "全部", "all", "所有", "*"}:
        gid = "全局"
    elif gid_key in {"私聊", "私信", "private", "dm"}:
        gid = "私聊"
    elif gid_key in {"当前群", "本群", "当前", "this", "current", "当前聊天"}:
        gid = ""

    permanent = duration.lower().replace(" ", "") in {
        "永久",
        "永远",
        "无期",
        "无限",
        "forever",
        "permanent",
        "∞",
    }
    seconds = None
    if duration and not permanent:
        seconds = 解析时长(duration) or None

    return 智能参数(
        用户ID=uid,
        用户名=name,
        群ID=gid,
        理由=reason,
        时长秒=seconds,
        永久=permanent,
    )


def _回复文本(resp) -> str:
    text = str(getattr(resp, "completion_text", "") or "").strip()
    if text:
        return text
    chain = getattr(resp, "result_chain", None)
    if chain:
        return "".join(
            str(part.text) for part in chain.chain if isinstance(part, Plain)
        ).strip()
    return ""


async def 分析指令(
    context: Context,
    模型ID: str,
    event: AstrMessageEvent,
    指令: str,
    原始文本: str,
    目标: User | None = None,
) -> 智能参数 | None:
    """调用模型解析一条智能指令，失败时返回 None。"""
    if not 模型ID:
        return None
    prompt = 构建提示(event, 指令, 原始文本, 目标)
    try:
        resp = await context.llm_generate(
            chat_provider_id=模型ID,
            prompt=prompt,
            system_prompt=系统提示,
        )
    except Exception as e:
        logger.warning(f"智能指令：调用模型失败，回退到普通参数解析：{e}")
        return None

    data = 提取JSON(_回复文本(resp))
    if data is None:
        logger.warning(f"智能指令：模型未返回可解析的 JSON：{_回复文本(resp)[:200]}")
        return None
    return 规整解析(data)


def 是帮助参数(text: str) -> bool:
    return text.strip().lower() in 帮助词
