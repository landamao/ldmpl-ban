import sys
from astrbot.api.all import Star, Context, AstrBotConfig, StarTools, AstrMessageEvent
from astrbot.api.event import filter
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.core.utils.wake_prefix import 获取第一个唤醒词 as zl1

from .ban import 黑名单管理器, 操作模式, 默认理由, 默认模式, 永久时间戳
from .command import 智能参数, 分析指令, 获取模型ID, 是帮助参数, 默认智能时长
from .utils import (
    从艾特或回复查找用户, 格式化拉黑显示, 解析文本参数, 获取用户名,
    格式化解除拉黑显示, 发送回复文本, 获取群名, 解析时长, 查找群成员
)

屏蔽群指令名 = ("屏蔽该群", "屏蔽此群", "屏蔽本群", "屏蔽群", "拉黑该群", "拉黑此群", "拉黑本群", "拉黑群")
解除屏蔽群指令名 = tuple(f"解除{i}" for i in 屏蔽群指令名)
查看黑名单指令名 = ("查看黑名单", "查询黑名单", "查看拉黑名单", "查看屏蔽名单", "查询屏蔽名单")
查看群黑名单指令名 = ("查看群黑名单", "查询群黑名单", "查询群拉黑名单", "查看群屏蔽名单", "查询群屏蔽名单")
智能指令名 = ("智能拉黑", "智能屏蔽", "智能解除拉黑", "智能解除屏蔽")
本插件指令名集合 = set(
    屏蔽群指令名 + 解除屏蔽群指令名 + 查看黑名单指令名 + 查看群黑名单指令名 +
    智能指令名 +
    (
        "拉黑", "屏蔽", "解除拉黑", "解除屏蔽", "清空黑名单",
        "搜索黑名单", "搜索用户"
    )
)

私聊 = "私聊"
"""特殊群，私聊"""
全局 = "全局"
"""特殊群，全局"""
特殊群 = (全局, 私聊)

实例 = None  # type: 黑名单系统 | None

class M:
    def __init__(self, event: AstrMessageEvent):
        self.event = event
        self.str = (event.get_message_str() or "").strip()
        """message_str文本"""
        self.p = self.str.split()
        """split后的列表"""
        self.arg = self.p[1:]
        """split后的[1:]"""
        self.lp = len(self.p)
        """split后的列表长度"""
        self.larg = len(self.arg)
        """split后的[1:]的列表长度"""
        self.gid = event.get_group_id() or ""
        """群号"""
        self.uid = event.get_sender_id()
        """发送者ID"""
        self._gna = None

    async def get_group_name(
            self,
            gid: str | int | None=None,
            event: AiocqhttpMessageEvent | None = None,
            bq:bool=True
    ):
        """获取群名，默认使用当前事件的群号和当前事件，注意await
        bq: 如果是本群，是否立刻返回空，减少API调用"""
        if gid is None:
            gid = self.gid
        gid = str(gid).strip()
        if not gid:
            return ""
        if gid in 特殊群:
            return gid
        _bq = gid == self.gid
        if _bq and bq:
            return ""
        if _bq and self._gna is not None:
            return self._gna
        if event is None:
            event = self.event
        if not isinstance(event, AiocqhttpMessageEvent):
            return ""
        gna = await 获取群名(event, gid)
        if _bq:
            self._gna = gna
        return gna

    async def get_user_name(
            self,
            gid: str | int | None=None,
            uid: str | int | None=None,
            event: AiocqhttpMessageEvent | None = None,
    ):
        """获取群名，默认使用当前事件的群号和发送者和当前事件，注意await"""
        if gid is None:
            gid  = self.gid
        if uid is None:
            uid = self.uid
        gid = str(gid or "").strip()
        uid = str(uid or "").strip()
        if not uid:
            return ""
        if gid in 特殊群:
            gid = ""
        if event is None:
            event = self.event
        if not isinstance(event, AiocqhttpMessageEvent):
            return ""
        return await 获取用户名(event, 用户ID=uid, 群ID=gid)

    async def send(self, text:str, event: AstrMessageEvent | None = None):
        """发送回复文本，注意await"""
        if event is None:
            event = self.event
        return await 发送回复文本(event, text)

    def __getitem__(self, n: int) -> str:
        """快速索引，越界返回空字符串"""
        return self.p[n] if 0 <= n < self.lp else ""

    def __str__(self):
        return self.str

class 黑名单系统(Star):
    """黑名单系统，区分屏蔽/拉黑，拉黑则拒绝所有消息，屏蔽则仅拒绝llm唤醒，一定程度上还可以避免想屏蔽只能用拉黑表示的争议"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.data_dir = StarTools.get_data_dir()
        self.黑名单管理器 = 黑名单管理器(self.data_dir)
        self.黑名单群聊:list[str] = [ str(i).strip() for i in self.config['黑名单群聊'] if str(i).strip() ]
        self.config['黑名单群聊'] = self.黑名单群聊
        self.不包括管理员 = not self.config['包括管理员']
        self.用户可查 = self.config['用户可查']
        self.用户可查群 = self.config['用户可查群']
        self.管理器已拉黑 = self.黑名单管理器.已拉黑
        self.管理器已屏蔽 = self.黑名单管理器.已屏蔽
        self.llm模式:list[str] = self.config['llm工具模式']
        self.智能模型 = str(self.config.get('模型') or "").strip()
        global 实例
        实例 = self

    # ==========生命周期==========
    async def initialize(self):
        """可选异步初始化，当插件被激活时会调用这个方法"""
        await self.黑名单管理器.启动清理()

    async def terminate(self):
        """当插件被卸载/停用时会调用这个方法"""
        await self.黑名单管理器.关闭清理()


    # ==========处理拉黑==========
    @filter.event_message_type(filter.EventMessageType.ALL, priority=sys.maxsize-1) # 数字越大越先执行
    async def 接收消息(self, event: AstrMessageEvent):
        """接收消息"""
        if event.get_group_id() in self.黑名单群聊:  # 私聊时 event.get_group_id() 为空字符串
            event.stop_event()
            return
        if event.is_admin():
            if self.不包括管理员:
                return
            if (
                    event.is_at_or_wake_command
                    and (p := event.get_message_str().strip().split())
                    and p[0] in 本插件指令名集合
            ):  # 跳过自带指令
                return
        if self.已拉黑(event):
            event.stop_event()

    @filter.on_waiting_llm_request(priority=sys.maxsize-1)
    async def llm队列时(self, event: AstrMessageEvent):
        """llm队列时/请求前"""
        if event.is_admin() and self.不包括管理员:
            return
        if self.已屏蔽(event):
            event.stop_event()
        # llm请求前，指令处理器已跑完无需再判断

    def 已拉黑(self, event: AstrMessageEvent):
        """判断事件发送者是否已被拉黑"""
        群ID = event.get_group_id() or 私聊
        发送者ID = event.get_sender_id()
        return self.管理器已拉黑(全局, 发送者ID) or self.管理器已拉黑(群ID, 发送者ID)

    def 已屏蔽(self, event: AstrMessageEvent):
        """判断事件发送者是否已被屏蔽"""
        群ID = event.get_group_id() or 私聊
        发送者ID = event.get_sender_id()
        return self.管理器已屏蔽(全局, 发送者ID) or self.管理器已屏蔽(群ID, 发送者ID)

    # ==========指令相关==========
    @filter.command("拉黑")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def 拉黑指令(self, event: AstrMessageEvent):
        """拉黑指令：拒绝目标用户的所有消息"""
        event.stop_event()
        await self.执行拉黑或屏蔽(event, 操作模式.拉黑)

    @filter.command("屏蔽")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def 屏蔽指令(self, event: AstrMessageEvent):
        """屏蔽指令：仅拒绝目标用户的llm唤醒"""
        event.stop_event()
        await self.执行拉黑或屏蔽(event, 操作模式.屏蔽)

    @filter.command("智能拉黑", alias={"智能屏蔽"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def 智能拉黑指令(self, event: AstrMessageEvent):
        """智能拉黑/屏蔽，使用llm分析"""
        event.stop_event()
        m = M(event)
        模式 = 操作模式.拉黑 if "拉黑" in m[0] else 操作模式.屏蔽
        await self.执行智能拉黑或屏蔽(event, m, 模式)

    @filter.command("智能解除拉黑", alias={"智能解除屏蔽"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def 智能解除拉黑指令(self, event: AstrMessageEvent):
        """智能解除拉黑/屏蔽，使用llm分析"""
        event.stop_event()
        m = M(event)
        await self.执行智能解除(event, m)

    @staticmethod
    def _智能帮助(指令: str) -> str:
        if "解除" in 指令:
            return (
                f"智能解除：艾特/引用要解除的人，或直接写QQ号，例如：\n"
                f"{zl1()}{指令} @某人\n"
                f"{zl1()}{指令} -u 123456\n"
                f"{zl1()}{指令} -q 全局 -u 123456"
            )
        return (
            f"智能指令：用自然语言描述要{指令[2:]}的对象、原因和时长，例如：\n"
            f"{zl1()}{指令} @某人 刷屏，关10分钟\n"
            f"{zl1()}{指令} -u 123456 在群里发广告 1d\n"
            f"支持艾特/引用、QQ号、本群昵称；时长支持 5min/1h/2d，写“永久”则不过期"
        )

    @staticmethod
    def _规范群ID(gid: str, 当前群: str) -> str:
        g = str(gid or "").strip()
        if g in 特殊群:
            return g
        if g.isdigit():
            return g
        return 当前群 or 私聊

    @staticmethod
    def _提取QQ号(arg: list[str]) -> str:
        """从自然语言参数里找第一个纯数字 QQ 号，跳过 -q/-u/-t 等关键字的值"""
        跳过 = set()
        for i, tok in enumerate(arg):
            if tok.lower() in {"-q", "q", "-g", "g", "-u", "u", "-t", "t", "-time", "time"}:
                if i + 1 < len(arg):
                    跳过.add(i + 1)
        for i, tok in enumerate(arg):
            if i in 跳过 or tok.startswith("-"):
                continue
            if tok.isdigit():
                return tok
        return ""

    async def 智能确定用户(
            self,
            event: AstrMessageEvent,
            m: M,
            解析: 智能参数 | None,
            huid: str,
            hgid: str,
    ) -> tuple[str, str] | None:
        """确定智能指令的目标用户，返回 (用户ID, 用户名)，失败时已提示并返回 None"""
        if 目标 := 从艾特或回复查找用户(event):
            return 目标.id, 目标.name
        if huid.isdigit():
            return huid, (解析.用户名 if 解析 else "")
        搜索群 = hgid if hgid.isdigit() else (m.gid or "")
        关键词 = huid or (解析.用户名 if 解析 else "")
        候选 = await 查找群成员(event, 搜索群, 关键词) if 关键词 and 搜索群 else []
        if len(候选) > 1:
            列表 = "\n".join(f"[{i}] {u.name or '未知'}（{u.id}）" for i, u in enumerate(候选, 1))
            await m.send(f"⚠️ 找到多个匹配「{关键词}」的成员，请改用QQ号或艾特/引用：\n{列表}")
            return None
        if len(候选) == 1:
            return 候选[0].id, 候选[0].name
        if 解析 and 解析.用户ID.isdigit():
            return 解析.用户ID, 解析.用户名
        await m.send("⚠️ 未找到要操作的用户，请艾特/引用，或使用 -u <QQ号>")
        return None

    async def 执行智能拉黑或屏蔽(self, event: AstrMessageEvent, m: M, 模式: 操作模式):
        """智能拉黑/屏蔽：LLM 解析自然语言，失败时回退到普通参数"""
        if not m.larg or 是帮助参数(m[1]):
            await m.send(self._智能帮助(m[0]))
            return
        tail = m.str.split(maxsplit=1)[1].strip() if m.larg else ""
        hgid, huid, ht = 解析文本参数(m.str, 严格=False)
        if not huid:
            huid = self._提取QQ号(m.arg)
        模型ID = 获取模型ID(self.context, self.智能模型, event)
        解析 = await 分析指令(self.context, 模型ID, event, m[0], tail)
        用户 = await self.智能确定用户(event, m, 解析, huid, hgid)
        if 用户 is None:
            return
        uid, una = 用户
        if uid in {event.get_self_id(), event.get_sender_id()}:
            await m.send(f"⚠️ 不能{模式.value}机器人自己或指令发送者")
            return

        if hgid:
            ygid = self._规范群ID(hgid, m.gid)
        elif 解析 and 解析.群ID:
            ygid = self._规范群ID(解析.群ID, m.gid)
        else:
            ygid = m.gid or 私聊
        if not una:
            una = await m.get_user_name(gid=ygid, uid=uid)

        if ht > 0:
            t = ht
        elif 解析 and 解析.永久:
            t = 永久时间戳
        elif 解析 and 解析.时长秒:
            t = 解析.时长秒
        else:
            t = 默认智能时长
        理由 = (解析.理由 if 解析 else "") or 默认理由

        r = self.黑名单管理器.加入黑名单(
            用户ID=uid,
            群ID=ygid,
            用户名=una,
            时间=t,
            理由=理由,
            操作者="智能指令",
            模式=模式
        )
        await m.send(格式化拉黑显示(r))

    async def 执行智能解除(self, event: AstrMessageEvent, m: M):
        """智能解除拉黑/屏蔽：LLM 解析目标，失败时回退到普通参数"""
        if not m.larg or 是帮助参数(m[1]):
            await m.send(self._智能帮助(m[0]))
            return
        tail = m.str.split(maxsplit=1)[1].strip() if m.larg else ""
        hgid, huid, _ = 解析文本参数(m.str, 严格=False)
        if not huid:
            huid = self._提取QQ号(m.arg)
        模型ID = 获取模型ID(self.context, self.智能模型, event)
        解析 = await 分析指令(self.context, 模型ID, event, m[0], tail)
        用户 = await self.智能确定用户(event, m, 解析, huid, hgid)
        if 用户 is None:
            return
        uid, una = 用户

        if hgid:
            ygid = self._规范群ID(hgid, m.gid)
        elif 解析 and 解析.群ID:
            ygid = self._规范群ID(解析.群ID, m.gid)
        else:
            ygid = m.gid or 私聊

        r = self.黑名单管理器.解除拉黑(用户ID=uid, 群ID=ygid)
        if r is None and ygid not in 特殊群:
            r = self.黑名单管理器.解除拉黑(用户ID=uid, 群ID=全局)
            if r is not None:
                ygid = 全局
        if r is None:
            if not una:
                una = await m.get_user_name(gid=ygid, uid=uid)
            if una:
                await m.send(f"⚠️ 未找到用户「{una}（{uid}）」的黑名单记录")
            else:
                await m.send(f"⚠️ 未找到用户「{uid}」的黑名单记录")
        else:
            await m.send(格式化解除拉黑显示(r))

    async def 执行拉黑或屏蔽(self, event: AstrMessageEvent, 模式: 操作模式):
        """拉黑/屏蔽共用逻辑，按指令模式写入黑名单"""
        xs = 模式.value
        m = M(event)
        if m[1].lower() in {"-h","--h","-help","--help","help","帮助","-帮助","--帮助"}:
            await m.send(
                f"引用消息或艾特某人，或使用参数化格式：{zl1()}{xs} -q 群号（all代表全局，不填代表私聊） -u 用户ID"
                "优先解析引用消息或艾特某人"
            )
            return
        # 原始文本，如：拉黑 -q 111。-u 222，“拉黑”之后必有一个空格
        hgid, uid, t = 解析文本参数(m.str)
        if us:=从艾特或回复查找用户(event):
            ygid = hgid or event.get_group_id()
            if not ygid:
                await m.send(
                    f"❌️ 私聊请使用参数化：{zl1()}{xs} -q <群号（all代表全局，不填代表私聊）>"
                    f" -u <用户ID> -t <时长，如1d2h3min4s>"
                )
                return
            yuid = us.id
            yna = us.name
        elif hgid and not uid:
            await m.send(f"❌️ 仅解析到群ID为{hgid}，请传入用户ID")
            return
        elif uid:
            ygid = hgid or m.gid or 私聊
            yuid = uid
            yna = await m.get_user_name(gid=ygid, uid=uid)
        else:
            await m.send(
                f"⚠️ 未找到/解析到需要{xs}的用户，\n"
                f"你可以引用消息或艾特某人，或使用参数\n"
                f"参数化格式：{zl1()}{xs} -q <群号（all代表全局，不填代表私聊）>"
                f" -u 用户ID -t <时长，如1d2h3min4s>")
            return

        if yuid in {event.get_self_id(), event.get_sender_id()}:
            await m.send(f"⚠️ 不能{xs}机器人自己或指令发送者")
            return

        r = self.黑名单管理器.加入黑名单(
            用户ID=yuid,
            群ID=ygid,
            用户名=yna,
            时间=t or 永久时间戳,
            操作者="管理员指令",
            模式=模式
        )

        await m.send( 格式化拉黑显示(r))

    @filter.command("解除拉黑", alias={"解除屏蔽"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def 解除拉黑指令(self, event: AstrMessageEvent):
        """普通解除拉黑/解除屏蔽指令，共用一条，按条目保存的模式显示"""
        event.stop_event()
        m = M(event)
        xs = "解除屏蔽" if "解除屏蔽" in m[0] else "解除拉黑"
        if m[1].lower() in {"-h", "--h", "-help", "--help", "help", "帮助", "-帮助", "--帮助"}:
            await m.send(
                f"引用消息或艾特某人，或使用参数化格式：{zl1()}{xs} -q <群号>（all代表全局，不填代表私聊） -u <用户ID>"
                "优先解析引用消息或艾特某人"
            )
            return
        hgid, uid, _ = 解析文本参数(m.str)
        if us := 从艾特或回复查找用户(event):
            ygid = hgid or event.get_group_id() or 私聊
            yuid = us.id
        elif hgid and not uid:
            await m.send(f"❌️ 仅解析到群ID为{hgid}，请传入用户ID")
            return
        elif uid:
            ygid = hgid or event.get_group_id() or 私聊
            yuid = uid
        else:
            await m.send(
                f"⚠️ 未找到/解析到需要{xs}的用户，\n"
                f"你可以引用消息或艾特某人，或使用参数\n"
                f"参数化格式：{zl1()}{xs} -q <群号（all代表全局，不填代表私聊）> -u <用户ID>")
            return

        r = self.黑名单管理器.解除拉黑(
            用户ID=yuid,
            群ID=ygid
        )
        if r is None and ygid not in 特殊群:
            # 群里没找到，再尝试全局记录
            r = self.黑名单管理器.解除拉黑(用户ID=yuid, 群ID=全局)
            if r is not None:
                ygid = 全局

        if r is None:
            una = await m.get_user_name(gid=ygid, uid=yuid)
            if una:
                await m.send( f"⚠️ 未找到用户「{una}（{yuid}）」的黑名单记录")
            else:
                await m.send( f"⚠️ 未找到用户「{yuid}」的黑名单记录")
        else:
            await m.send( 格式化解除拉黑显示(r))

    @filter.command(查看黑名单指令名[0], alias={*查看黑名单指令名[1:]})
    async def 查看黑名单指令(self, event: AstrMessageEvent):
        """查看黑名单/屏蔽名单指令，支持传入用户ID参数"""
        event.stop_event()
        m = M(event)
        una = ""
        hgid, huid, _ = 解析文本参数(m.str)
        gid = ""

        if us:=从艾特或回复查找用户(event):
            uid = us.id
            una = us.name
            gid = hgid
        elif hgid and not huid:
            await m.send(f"❌️ 仅解析到群ID为{hgid}，请传入用户ID")
            return
        elif huid:
            uid = huid
            gid = hgid
        else:
            uid = event.get_sender_id()
            una = event.get_sender_name()
        if not gid:
            gid = event.get_group_id() or 私聊
        zj = uid == event.get_sender_id() and gid == (event.get_group_id() or 私聊)
        if not event.is_admin():
            if not self.用户可查:
                return
            if not zj:
                await m.send( "❌️ 你只能查询自己的")
                return
        r = self.黑名单管理器.获取用户信息(用户ID=uid, 群ID=gid)
        if (r is None or r.已结束) and gid not in 特殊群:
            全局r = self.黑名单管理器.获取用户信息(用户ID=uid, 群ID=全局)
            if 全局r is not None and not 全局r.已结束:
                gid, r = 全局, 全局r
        end = True if r is None else r.已结束
        if end:
            if zj:
                await m.send( f"你（{uid}）未被屏蔽/拉黑")
            else:
                if una:
                    await m.send( f"用户「{una}（{uid}）」未被拉黑/屏蔽")
                else:
                    await m.send( f"用户「{uid}」未被拉黑/屏蔽")
        else:
            if una:
                self.黑名单管理器.更新用户(
                    用户ID=uid,
                    群ID=r.群ID,
                    用户名=una
                )
            if zj:
                await m.send(
                    f"你（{uid}）已被{r.模式}（{r.群ID}）\n"
                    f"剩余时间：{r.剩余时间}\n理由：{r.理由}"
                )
            else:
                await m.send(
                    f"用户「{r.用户名}（{r.用户ID}）」已被{r.模式}（{r.群ID}）\n"
                    f"剩余时间：{r.剩余时间}\n理由：{r.理由}"
                )

    @filter.command(查看群黑名单指令名[0], alias={*查看群黑名单指令名[1:]})
    async def 查看群黑名单指令(self, event: AstrMessageEvent):
        """查看群黑名单/屏蔽名单"""
        event.stop_event()
        m = M(event)
        gid  = m[1] or m.gid or 私聊
        if gid.lower() in {"全局", "全部", "all", "*"}:
            gid = 全局
        elif gid.lower() in {"私聊", "私信", "private", "dm"}:
            gid = 私聊
        bq = gid == m.gid
        if not event.is_admin():
            if not self.用户可查群:
                return
            if not bq:
                await m.send( "❌️ 你只能查看本群的")
                return
        qr = self.黑名单管理器.获取群信息(gid)
        rs = []
        c = 0
        for uid, r in qr.items():
            if r.已结束:
                continue
            c += 1
            rs.append(
                f"[{c}] 用户：{r.用户名}（{r.用户ID}）"
                f"\n    - 被{r.模式}"
                f"\n    - 剩余时间：{r.剩余时间}"
                f"\n    - 结束时间: {r.结束时间}"
                f"\n    - 理由：{r.理由}\n"
            )
        gna = await m.get_group_name(gid=gid)
        if not rs:
            if bq:
                await m.send(
                    f"⚠️ 本群（{gid}）暂无黑名单/屏蔽用户")
                return
            if gna:
                await m.send(
                    f"⚠️ 群「{gna}（{gid}）」暂无黑名单/屏蔽用户")
            else:
                await m.send(
                    f"⚠️ 群「{gid}」暂无黑名单/屏蔽用户")
        else:
            if bq:
                rs.insert(0, f"本群（{gid}）的黑名单记录，共{c}条：\n")
            elif gna:
                rs.insert(0, f"群「{gna}（{gid}）」的黑名单记录，共{c}条：\n")
            else:
                rs.insert(0, f"群「{gid}」的黑名单记录，共{c}条：\n")
            yield event.plain_result('\n'.join(rs).strip())
            # append的长消息用yield走框架的合并转发

    @filter.command("搜索黑名单", alias={"搜索用户"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def 搜索黑名单指令(self, event: AstrMessageEvent):
        """在全局搜索被拉黑/被屏蔽的用户"""
        event.stop_event()
        m = M(event)
        p1 = m[1]
        p2 = m[2]
        if p1.lower() in ("-h", "--h", "-help", "--help", "help", "帮助", "-帮助", "--帮助"):
            await m.send(
                f"搜索黑名单格式：\n{zl1()}{m[0]} <搜索值>"
                f" [i|m|a]，默认i模式\n"
                f"默认i模式，使用用户ID搜索，m模式使用用户名搜索，a模式使用用户名及用户ID搜索")
            return
        if us:= 从艾特或回复查找用户(event):
            uid = us.id
        elif p1:
            uid = p1
        else:
            await m.send( "请输入需要搜索的用户ID或艾特/引用")
            return
        if p2 in ("m", "-m"):
            用户列表 = []
            全部信息 = self.黑名单管理器.获取所有信息()
            a = uid
            for g, gv in 全部信息.items():
                for u, ur in gv.items():
                    b = ur.用户名
                    if a and b and (a in b or b in a):
                        用户列表.append(ur)
        elif p2 in ("a", "-a"):
            用户列表 = []
            全部信息 = self.黑名单管理器.获取所有信息()
            a = uid
            for g, gv in 全部信息.items():
                for u, ur in gv.items():
                    b = ur.用户名
                    c = ur.用户ID
                    if (
                            a and b and c
                            and (
                            (a in b or b in a)
                            or (a in c or c in a)
                            )
                    ):
                        用户列表.append(ur)
        elif p2 in ("i", "-i", ""):
            用户列表 = self.黑名单管理器.获取用户信息(用户ID=uid) or []
        else:
            await m.send(
                f"❌️ 不支持的模式「{p2}」\n支持的有：i、m、a，默认i模式\n"
                f"i模式使用用户ID搜索，m模式使用用户名搜索（模糊匹配），a模式使用输入搜索用户名及用户ID"
            )
            return

        rs = []
        c = 0
        gdc = {}
        for r in 用户列表:
            gid = r.群ID
            if r.已结束:
                continue
            if gid not in gdc:
                gdc[gid] = await m.get_group_name(gid, bq=False)
            gna = gdc[gid]
            c += 1
            if gna:
                rs.append(
                    f"[{c}] 用户：{r.用户名}（{r.用户ID}）"
                    f"\n    - 被{r.模式}"
                    f"\n    - 剩余时间：{r.剩余时间}"
                    f"\n    - 结束时间: {r.结束时间}"
                    f"\n    - 理由：{r.理由}"
                    f"\n    - 群：{r.群ID}"
                    f"\n    - 群名：{gna}\n")
            else:
                rs.append(
                    f"[{c}] 用户：{r.用户名}（{r.用户ID}）"
                    f"\n    - 被{r.模式}"
                    f"\n    - 剩余时间：{r.剩余时间}"
                    f"\n    - 结束时间: {r.结束时间}"
                    f"\n    - 理由：{r.理由}"
                    f"\n    - 群：{r.群ID}\n"
                )
        if not rs:
            await m.send( f"⚠️ 未搜索到目标{uid}的黑名单记录，搜索模式：{p2}")
            return
        else:
            rs.insert(0, f"搜索到{c}条记录：")
            yield event.plain_result('\n'.join(rs).strip())

    @filter.command("清空黑名单")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def 清空黑名单指令(self, event: AstrMessageEvent):
        """清空黑名单指令"""
        event.stop_event()
        m = M(event)
        位置参数 = [i for i in m.arg if i not in ("y", "-y")]
        gid = 位置参数[0] if 位置参数 else m.gid
        if gid.lower() in {"全局", "全部", "all", "*"}:
            gid = 全局
        if not gid:
            await m.send("私聊请输入要清空的群号，私聊群号：私聊，全局群号：全局")
            return
        bq = gid == m.gid
        gna = await m.get_group_name(gid)
        if self.黑名单管理器.获取群信息(gid):
            if not any(i in m.p for i in ("y", "-y")):
                if bq:
                    t1 = f"确认清空本群（{gid}）的拉黑/屏蔽信息吗？发送带y或-y确认"
                elif gna:
                    t1 = f"确认清空群「{gna}（{gid}）」的拉黑/屏蔽信息吗？发送带y或-y确认"
                else:
                    t1 = f"确认清空群「{gid}」的拉黑/屏蔽信息吗？发送带y或-y确认"
                await m.send(t1 + f"\n{zl1()}{m[0]} {gid} -y")
                return
            gdc = self.黑名单管理器.清空群(gid)
            if bq:
                await m.send(
                    f"✅️ 已清空本群（{gid}）的黑名单/屏蔽列表\n"
                    f"共{len(gdc)}条记录")
            elif gna:
                await m.send(
                    f"✅️ 已清空群「{gna}（{gid}）」的黑名单/屏蔽列表\n"
                    f"共{len(gdc)}条记录")
            else:
                await m.send(
                    f"✅️ 已清空群「{gid}」的黑名单/屏蔽列表\n"
                    f"共{len(gdc)}条记录")
        else:
            if bq:
                await m.send(f"⚠️ 本群（{gid}）暂无黑名单/屏蔽用户")
            elif gna:
                await m.send(f"⚠️ 群「{gna}（{gid}）」暂无黑名单/屏蔽用户")
            else:
                await m.send(f"⚠️ 群「{gid}」暂无黑名单/屏蔽用户")

    @filter.command(屏蔽群指令名[0], alias={*屏蔽群指令名[1:]})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def 屏蔽群指令(self, event: AstrMessageEvent):
        """屏蔽群指令"""
        event.stop_event()
        m = M(event)
        gid = m[1] or m.gid
        if not gid:
            await m.send("私聊请输入需要屏蔽的群")
            return
        bq = gid == m.gid
        w = "屏蔽" if "屏蔽" in m[0] else "拉黑"
        gna = await m.get_group_name(gid)
        if gid in self.黑名单群聊:
            if bq:
                await m.send(f"⚠️ 本群（{gid}）已被{w}")
            elif gna:
                await m.send(f"⚠️ 群「{gna}（{gid}）」已被{w}")
            else:
                await m.send(f"⚠️ 群「{gid}」已被{w}")
        else:
            self.黑名单群聊.append(gid)
            self.config.save_config(indent=4)
            if bq:
                await m.send(f"✅️ 本群（{gid}）已{w}")
            elif gna:
                await m.send(f"✅️ 群「{gna}（{gid}）」已{w}")
            else:
                await m.send(f"✅️️️ 群「{gid}」已{w}")

    @filter.command(解除屏蔽群指令名[0], alias={*解除屏蔽群指令名[1:]})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def 解除屏蔽群指令(self, event: AstrMessageEvent):
        """解除屏蔽群指令"""
        event.stop_event()
        m = M(event)
        gid = m[1] or m.gid
        if not gid:
            await m.send( "私聊请输入需要解除屏蔽的群")
            return
        bq = gid == m.gid
        w = "屏蔽" if "屏蔽" in m[0] else "拉黑"
        gna = await m.get_group_name(gid)
        if gid not in self.黑名单群聊:
            if bq:
                await m.send(f"⚠️ 本群（{gid}）未被{w}")
            elif gna:
                await m.send(f"⚠️ 群「{gna}（{gid}）」未被{w}")
            else:
                await m.send(f"⚠️ 群「{gid}」未被{w}")
        else:
            self.黑名单群聊[:] = [ g for g in self.黑名单群聊 if g!= gid]
            self.config.save_config(indent=4)
            if bq:
                await m.send(f"✅️ 本群（{gid}）已解除{w}")
            elif gna:
                await m.send(f"✅️ 群「{gna}（{gid}）」已解除{w}")
            else:
                await m.send(f"✅️ 群（{gid}）已解除{w}")

    @filter.llm_tool("add_to_blacklist")
    async def 加入黑名单指令(
            self,
            event: AstrMessageEvent,
            user_id: str,
            time: str = "20min",
            reason: str = 默认理由,
            mode: str = 默认模式.value,
    ):
        """添加用户到黑名单/屏蔽列表
        Args:
            user_id(string): 用户ID（QQ号）
            time(string): 时长，格式例如：20day12h20min50s，支持：day/d →天，h →小时，min/m →分钟，s →秒，无单位则视为分钟，不支持小数形式，酌情填写，勿填太大，参考值：轻微5分钟，中等20分钟，严重40分钟，……，不支持永久
            reason(string): 拉黑/屏蔽理由
            mode(string): 必选，可选值："屏蔽", "拉黑"。屏蔽则让用户无法唤醒你聊天，在其他人唤醒你时，你仍可能可以看到该用户消息，如用户道歉消息，具体取决于用户配置，拉黑则拒绝用户所有消息，包括让用户无法使用任何指令，你将无法看到用户的任何消息
        """
        if not self.llm模式:
            return "管理员禁用了此功能"
        模式 = str(mode or "").strip()
        可用模式 = ', '.join(f'"{i}"' for i in self.llm模式)
        if not 模式:
            return f"mode，请填写模式，可选值：{可用模式}"
        if 模式 not in self.llm模式:
            return f"mode，管理员禁用了此模式，可选值：{可用模式}"
        uid = str(user_id or "").strip()
        if not uid:
            return "user_id，请填写有效的用户ID"
        if uid in {event.get_self_id(), event.get_sender_id()}:
            return "不能拉黑/屏蔽机器人自己或指令发送者"
        时长 = 解析时长(str(time or "").strip())
        if not 时长:
            return "time，时长解析失败"
        理由 = str(reason or "").strip() or 默认理由
        模式s = 操作模式.拉黑 if 模式 == 操作模式.拉黑 else 操作模式.屏蔽
        gid = event.get_group_id() or 私聊
        m = M(event)
        用户名 = await m.get_user_name(gid=gid, uid=uid)
        r = self.黑名单管理器.获取用户信息(用户ID=uid, 群ID=gid)
        if r and not r.已结束 and r.操作者 != "llm":
            return (
                f"用户 {uid} 已被管理员{r.模式}（剩余时间：{r.剩余时间}，"
                f"理由：{r.理由}），不能覆盖管理员设置"
            )
        if gid not in 特殊群:
            全局r = self.黑名单管理器.获取用户信息(用户ID=uid, 群ID=全局)
            if 全局r and not 全局r.已结束 and 全局r.操作者 != "llm":
                return (
                    f"用户 {uid} 已被管理员全局{全局r.模式}（剩余时间：{全局r.剩余时间}，"
                    f"理由：{全局r.理由}），无需重复处理"
                )

        rs = self.黑名单管理器.加入黑名单(
            用户ID=uid, 群ID=gid, 时间=时长, 理由=理由, 操作者="llm", 模式=模式s,
            用户名=用户名
        )
        return 格式化拉黑显示(rs)
