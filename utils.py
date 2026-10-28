from astrbot.api.all import At, Reply, AstrMessageEvent, Plain, logger
from .ban import 单个黑名单信息
from dataclasses import dataclass
import re
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent

@dataclass
class User:
    id:str
    name:str = ""

async def 发送回复文本(event: AstrMessageEvent, 文本: str):
    return await event.send(event.chain_result([Reply(id=event.message_obj.message_id), Plain(文本)]))

def 格式化拉黑显示(r: 单个黑名单信息, 解除拉黑:bool=False):
    if 解除拉黑:
        s = f"✅️ 已解除{r.模式}，原信息："
    else:
        s = f"✅️ 已{r.模式}："
    return (
        f"{s}\n用户：{r.用户名}（{r.用户ID}）"
        f"\n群：{r.群ID}"
        f"\n结束时间：{r.结束时间}"
        f"\n剩余时长：{r.剩余时间}"
        f"\n理由：{r.理由}"
    )

def 格式化解除拉黑显示(r: 单个黑名单信息):
    return 格式化拉黑显示(r, 解除拉黑=True)

def 从艾特或回复查找用户(event: AstrMessageEvent) -> User|None:
    消息列表 = event.get_messages()
    m = event.get_self_id()
    ctn = (m, "all", event.get_sender_id())
    for i in 消息列表:
        if isinstance(i, At):
            q = str(i.qq or "").strip()
            if not q or q in ctn:
                continue
            return User(id=q, name=i.name or "")
        if isinstance(i, Reply):
            q = str(i.sender_id or "").strip()
            if not q or q in ctn:
                continue
            return User(id=q, name=i.sender_nickname or "")

    return None

async def 获取用户名(event: AiocqhttpMessageEvent, 用户ID:str, 群ID:str="") -> str:
    """获取用户名"""
    if not isinstance(event, AiocqhttpMessageEvent):
        return "未知"
    uid = str(用户ID or "").strip()
    gid = str(群ID or "").strip()
    try:
        if gid:
            ifo = await event.bot.call_action(
                action="get_group_member_info",
                group_id=gid,
                user_id=uid
            )
            return ifo.get("card") or ifo.get("nickname", "未知")
        else:
            ifo = await event.bot.call_action(
                action="get_stranger_info",
                user_id=uid
            )
            return ifo.get("nickname", "")
    except Exception as e:
        logger.warning(f"获取用户信息失败：{e}", exc_info=True)
        return ""

async def 获取群名(event: AiocqhttpMessageEvent, 群ID:str="") -> str:
    if not isinstance(event, AiocqhttpMessageEvent):
        return ""
    gid = str(群ID or "").strip() or event.get_group_id()
    if not gid:
        return ""
    try:
        info = await event.bot.call_action(
            action="get_group_info",
            group_id=gid
        )
        return info.get("group_name", "")
    except Exception as e:
        logger.warning(f"获取群信息失败：{e}", exc_info=True)
        return ""

async def 查找群成员(
        event: AiocqhttpMessageEvent,
        群ID: str,
        关键词: str,
        上限: int = 10,
) -> list[User]:
    """按昵称/群名片在当前群查找成员，先精确匹配，再模糊匹配。"""
    if not isinstance(event, AiocqhttpMessageEvent):
        return []
    gid = str(群ID or "").strip()
    kw = str(关键词 or "").strip()
    if not gid or not kw:
        return []
    try:
        members = await event.bot.call_action(
            action="get_group_member_list",
            group_id=int(gid) if gid.isdigit() else gid
        )
    except Exception as e:
        logger.warning(f"获取群成员列表失败：{e}", exc_info=True)
        return []
    if not isinstance(members, list):
        return []

    def 名字(m: dict) -> tuple[str, str]:
        return str(m.get("card") or "").strip(), str(m.get("nickname") or "").strip()

    def 转换(m: dict) -> User:
        card, nickname = 名字(m)
        return User(id=str(m.get("user_id") or ""), name=card or nickname)

    精确 = [m for m in members if kw in 名字(m)]
    if 精确:
        return [转换(m) for m in 精确[:上限] if str(m.get("user_id") or "")]
    模糊 = [
        m for m in members
        if any(kw in n for n in 名字(m) if n)
    ]
    return [转换(m) for m in 模糊[:上限] if str(m.get("user_id") or "")]


def 解析文本参数(text: str, 严格: bool = True) -> tuple[str, str, int]:
    """
    解析拉黑指令中的群号、用户ID、时长，返回 (群号, 用户ID, 时长秒)。
    不存在的参数用空字符串表示，时长不存在/非法用 0 表示。

    支持：
        拉黑 -q 123 -u 234 -t 1
        拉黑 -u 234 -t 2s
        拉黑 -q 234 -t 4
        拉黑 123 234 -t 3
        拉黑 123 -t 3

    不支持：
        拉黑 -q 123 345
        拉黑 -u 234 345

    严格模式下多余的裸参数视为格式错误；非严格模式（智能指令）会忽略
    这些自然语言描述，只取能识别的参数。
    """
    if not isinstance(text, str):
        return "", "", 0

    # 可选：兼容中文逗号、英文逗号分隔
    text = text.replace("，", " ").replace(",", " ")

    parts = text.strip().split()
    if len(parts) <= 1:
        return "", "", 0

    arg = parts[1:]  # 去掉指令头

    group_keys = {"q", "-q", "g", "-g"}
    user_keys = {"u", "-u"}
    time_keys = {"t", "-t", "time", "-time"}  # 如果只允许 -t/-time，改成 {"-t", "-time"}
    all_keys = group_keys | user_keys | time_keys
    特殊群别名 = {"全局", "全部", "all", "*", "私聊", "私信", "private", "dm"}

    def lower(tok: str) -> str:
        return tok.lower()

    def is_group_key(tok: str) -> bool:
        return lower(tok) in group_keys

    def is_user_key(tok: str) -> bool:
        return lower(tok) in user_keys

    def is_time_key(tok: str) -> bool:
        return lower(tok) in time_keys

    def is_any_key(tok: str) -> bool:
        return lower(tok) in all_keys

    consumed = [False] * len(arg)
    t = 0

    # 1. 先解析 -t / -time，并标记已消费
    time_found = False
    for i, tok in enumerate(arg):
        if is_time_key(tok):
            if time_found:
                # 多个时间关键词，视为非法
                if 严格:
                    return "", "", 0
                continue

            time_found = True
            consumed[i] = True

            if i + 1 < len(arg) and not is_any_key(arg[i + 1]):
                consumed[i + 1] = True
                t = 解析时长(arg[i + 1])
            else:
                t = 0

    has_group_or_user_key = any(
        is_group_key(tok) or is_user_key(tok) for tok in arg
    )

    gid = ""
    uid = ""

    if has_group_or_user_key:
        # 2. 有群/用户关键词：只允许关键词后跟一个值，不能有多余裸参数
        i = 0
        while i < len(arg):
            if consumed[i]:
                i += 1
                continue

            tok = arg[i]

            if is_group_key(tok):
                consumed[i] = True
                if i + 1 < len(arg) and not is_any_key(arg[i + 1]):
                    gid = arg[i + 1]
                    consumed[i + 1] = True
                i += 1

            elif is_user_key(tok):
                consumed[i] = True
                if i + 1 < len(arg) and not is_any_key(arg[i + 1]):
                    uid = arg[i + 1]
                    consumed[i + 1] = True
                i += 1

            else:
                i += 1

        # 还有没被消费的参数，说明有多余裸数字，例如 -q 123 345
        if 严格 and any(not used for used in consumed):
            return "", "", 0

    else:
        # 3. 没有群/用户关键词：剩余非时间参数按位置解析
        # 无关键词时规则：用户ID 群号
        positional = [tok for i, tok in enumerate(arg) if not consumed[i]]

        if len(positional) == 0:
            gid, uid = "", ""
        elif len(positional) == 1:
            if not 严格 and positional[0].lower() in 特殊群别名:
                gid, uid = positional[0], ""
            else:
                uid, gid = positional[0], ""
        elif len(positional) == 2:
            if not 严格 and positional[0].lower() in 特殊群别名:
                gid, uid = positional[0], positional[1]
            elif not 严格 and not positional[0].isdigit() and positional[1].isdigit():
                # 自然语言顺序可能是“昵称 QQ号”，把数字当用户ID
                uid, gid = positional[1], ""
            else:
                uid, gid = positional[0], positional[1]
        else:
            # 无关键词时也最多只接受两个位置参数
            if 严格:
                return "", "", 0
            # 非严格模式：自然语言里可能有多个词，只识别其中的全局/私聊标记
            gid, uid = "", ""
            for tok in positional:
                if tok.lower() in 特殊群别名:
                    gid = tok
                    break

    # 4. 群号全局处理
    if gid.lower() in {"全局", "全部", "all", "*"}:
        gid = "全局"
    elif gid.lower() in {"私聊", "私信", "private", "dm"}:
        gid = "私聊"

    return gid, uid, t

def 解析时长(text: str) -> int:
    """
    解析时长字符串，返回秒数；格式错误返回 0。

    支持：
      day / d   -> 天
      h         -> 小时
      min / m   -> 分钟
      s         -> 秒

    规则：
      - 纯数字无单位时，视为分钟，例如 "20" -> 20分钟
      - 不区分大小写
      - 不支持小数
      - 每个字段最多出现一次
      - 字段需按 天 -> 小时 -> 分钟 -> 秒 的顺序，可省略
      - 一旦出现单位，则每个数字都必须带单位
      - 必须是连续字符串，不能有空格等分隔符
    """
    if not isinstance(text, str) or text == "":
        return 0

    # 纯数字：无单位，视为分钟
    if re.fullmatch(r"[0-9]+", text):
        return int(text) * 60

    pattern = re.compile(
        r"(?:([0-9]+)(day|d))?"
        r"(?:([0-9]+)(h))?"
        r"(?:([0-9]+)(min|m))?"
        r"(?:([0-9]+)(s))?",
        re.IGNORECASE
    )

    m = pattern.fullmatch(text)
    if not m:
        return 0

    # 至少有一个字段
    if not any(m.group(i) is not None for i in (1, 3, 5, 7)):
        return 0

    total = 0

    if m.group(1) is not None:      # 天
        total += int(m.group(1)) * 86400

    if m.group(3) is not None:      # 小时
        total += int(m.group(3)) * 3600

    if m.group(5) is not None:      # 分钟
        total += int(m.group(5)) * 60

    if m.group(7) is not None:      # 秒
        total += int(m.group(7))

    return total
