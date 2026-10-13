from astrbot.api.all import At, Reply, AstrMessageEvent, Plain, logger
from .rds import 单个黑名单信息
from dataclasses import dataclass
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent

@dataclass
class User:
    id:str
    name:str = ""

async def 发送回复文本(event: AstrMessageEvent, 文本: str):
    return await event.send(event.chain_result([Reply(id=event.message_obj.message_id), Plain(文本)]))

def 格式化拉黑显示(r: 单个黑名单信息, 显示:str="屏蔽", 解除拉黑:bool=False):
    if 解除拉黑:
        s = f"✅️ 已解除{显示}，原信息："
    else:
        s = f"✅️ 已{显示}："
    return (
        f"{s}\n用户：{r.用户名}（{r.用户ID}）"
        f"\n群：{r.群ID}"
        f"\n结束时间：{r.结束时间}"
        f"\n剩余时长：{r.剩余时间}"
        f"\n理由：{r.理由}"
    )

def 格式化解除拉黑显示(r: 单个黑名单信息, 显示:str="拉黑"):
    return 格式化拉黑显示(r, 显示=显示, 解除拉黑=True)

def 从艾特或回复查找用户(event: AstrMessageEvent) -> User|None:
    l = event.get_messages()
    m = event.get_self_id()
    ctn = (m, "all", event.get_sender_id())
    for i in l:
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

def 解析文本参数(text: str) -> tuple[str, str]:
    """
    解析拉黑指令中的群号和用户ID，返回 (群号, 用户ID)。
    不存在的参数用空字符串表示。

    支持以下形式（群聊：-q/q/-g/g，用户：-u/u）：
        拉黑 234 123  没有关键词则视为 用户ID 群ID
        拉黑 -q ddd -u 234
        屏蔽 g 123 u 234
        拉黑 -g 123 -u ssss
        拉黑 q 123 -u 234
    """
    parts = text.strip().split()
    if len(parts) <= 1:
        return "", ""

    arg = parts[1:]  # 去掉指令头

    group_keys = {"q", "-q", "g", "-g"}
    user_keys = {"u", "-u"}
    all_keys = group_keys | user_keys

    def is_key(tok: str) -> bool:
        return tok.lower() in all_keys

    # 是否存在显式关键词
    has_key = any(is_key(tok) for tok in arg)

    def find_value(keys: set[str]) -> str:
        """查找某个关键词后面第一个非关键词参数"""
        for idx, tok in enumerate(arg):
            if tok.lower() in keys:
                if idx + 1 >= len(arg):
                    return ""
                nxt = arg[idx + 1]
                if is_key(nxt):
                    continue
                return nxt
        return ""

    if has_key:
        gid = find_value(group_keys)
        uid = find_value(user_keys)
    else:
        # 无关键词：按“用户ID 群号”顺序
        if len(arg) >= 2:
            uid, gid = arg[0], arg[1]
        else:
            uid, gid = arg[0], ""

    if gid.lower() in {"全局", "全部", "all", "*"}:
        gid = "全局"

    return gid, uid