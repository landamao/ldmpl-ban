from __future__ import annotations
import time
import json
import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from astrbot.api.all import logger

永久时间戳: float = 4102416000.0  # 北京时间 2100-01-01
默认清理间隔: float = 60.0       # 后台清理过期条目的默认间隔（秒）
二000年时间 = 946656000          # 北京时间 2000-1-1

# 北京时间 UTC+8
北京时区 = timezone(timedelta(hours=8))


def 格式化北京时间(时间戳: float) -> str:
    """把时间戳按北京时间格式化为：xxxx年xx月xx日xx时xx分"""
    dt = datetime.fromtimestamp(时间戳, tz=北京时区)
    return dt.strftime("%Y年%m月%d日%H时%M分")


def 格式化剩余时长(结束时间: float) -> str:
    """
    传入结束时间戳，自动与当前时间计算剩余时长，
    格式为：x年x月x日x时x分x秒，为0的部分省略。
    """
    当前时间 = time.time()
    秒数 = int(max(0.0, 结束时间 - 当前时间))  # 已经过去则显示0秒

    年, 秒数 = divmod(秒数, 365 * 24 * 3600)
    月, 秒数 = divmod(秒数, 30 * 24 * 3600)
    天, 秒数 = divmod(秒数, 24 * 3600)
    时, 秒数 = divmod(秒数, 3600)
    分, 秒 = divmod(秒数, 60)

    片段 = []
    if 年:
        片段.append(f"{年}年")
    if 月:
        片段.append(f"{月}月")
    if 天:
        片段.append(f"{天}天")
    if 时:
        片段.append(f"{时}时")
    if 分:
        片段.append(f"{分}分")
    if 秒 or not 片段:
        片段.append(f"{秒}秒")

    return "".join(片段)

from enum import Enum

class 操作模式(str, Enum):
    拉黑 = "拉黑"
    屏蔽 = "屏蔽"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_value(cls, v) -> "操作模式":
        """宽容地把 str / 枚举 转成枚举成员，非法值回退到默认"""
        if isinstance(v, cls):
            return v
        try:
            return cls(v.strip())
        except (ValueError, TypeError):
            return cls.屏蔽

默认时间戳 = 永久时间戳
默认用户名 = "未知"
默认理由 = "无理由"
默认操作者 = "WebUI"
默认模式 = 操作模式.屏蔽
# 区分屏蔽和拉黑，避免一些争议

@dataclass
class 单个黑名单信息:
    用户ID: str
    群ID: str
    结束时间戳: int | float = 永久时间戳
    用户名: str = 默认用户名
    理由: str = 默认理由
    操作者: str = 默认操作者
    模式: 操作模式 = 默认模式

    def __post_init__(self):
        self.用户ID = str(self.用户ID)
        self.群ID = str(self.群ID)
        self.用户名 = str(self.用户名 or "").strip() or 默认用户名
        self.理由 = str(self.理由 or "").strip() or 默认理由
        self.操作者 = str(self.操作者 or "").strip() or 默认操作者
        self.模式 = 操作模式.from_value(self.模式)
        try:
            self.结束时间戳 = float(self.结束时间戳 or 永久时间戳)
        except (ValueError, TypeError):
            self.结束时间戳 = 永久时间戳

    @property
    def 已屏蔽(self) -> bool:
        return self.模式 == 操作模式.屏蔽 and self.未结束

    @property
    def 已拉黑(self) -> bool:
        return self.模式 == 操作模式.拉黑 and self.未结束

    @property
    def 未结束(self) -> bool:
        return time.time() < self.结束时间戳

    @property
    def 已结束(self) -> bool:
        return not self.未结束

    @property
    def 剩余时间(self):
        if self.结束时间戳 >= 永久时间戳:
            return "∞"
        return 格式化剩余时长(self.结束时间戳)

    @property
    def 结束时间(self):
        if self.结束时间戳 >= 永久时间戳:
            return "无结束时间"
        return 格式化北京时间(self.结束时间戳)

    def 更新信息(
        self,
        用户ID: str,
        群ID: str,
        结束时间戳: int | float | None = None,
        用户名: str | None = None,
        理由: str | None = None,
        操作者: str | None = None,
        模式: 操作模式 | str | None = None,
    ) -> None:
        self.用户ID = str(用户ID or "").strip()
        self.群ID = str(群ID or "").strip()
        if 结束时间戳:
            self.结束时间戳 = 结束时间戳
        a = str(用户名 or "").strip()
        if a:
            self.用户名 = a
        if 理由 is not None:
            self.理由 = str(理由 or "").strip() or 默认理由
        if 操作者 is not None:
            self.操作者 = str(操作者 or "").strip() or 默认操作者
        if 模式 is not None:
            self.模式 = 操作模式.from_value(模式)

    def to_dict(self) -> dict:
        return {
            "用户ID": self.用户ID,
            "群ID": self.群ID,
            "结束时间戳": self.结束时间戳,
            "用户名": self.用户名,
            "理由": self.理由,
            "操作者": self.操作者,
            "模式": self.模式.value,
        }

    def copy(self) -> 单个黑名单信息:
        return self.__class__(
            用户ID=self.用户ID,
            群ID=self.群ID,
            结束时间戳=self.结束时间戳,
            用户名=self.用户名,
            理由=self.理由,
            操作者=self.操作者,
            模式=self.模式,
        )

    @classmethod
    def from_dict(
        cls,
        d: dict,
        群ID: str | None = None,
        用户ID: str | None = None,
    ) -> 单个黑名单信息 | None:
        用户ID = (str(用户ID or "") or str(d.get("用户ID") or "")).strip()
        群ID = (str(群ID or "") or str(d.get("群ID") or "")).strip()
        if not (用户ID and 群ID):
            return None
        return cls(
            用户ID=用户ID, 群ID=群ID,
            结束时间戳=d.get("结束时间戳", 永久时间戳),
            用户名=d.get("用户名", 默认用户名),
            理由=d.get("理由", 默认理由),
            操作者=d.get("操作者", 默认操作者),
            模式=操作模式.from_value(d.get("模式", 默认模式))
        )

class 黑名单管理器:

    def __init__(self, data_dir: Path | str, 清理间隔: float = 默认清理间隔):
        self.data_dir = Path(data_dir)
        self.data_path = self.data_dir / "data.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, dict[str, 单个黑名单信息]] = {}
        self.清理间隔 = float(清理间隔)
        self._操作锁 = threading.RLock()
        self._清理任务: asyncio.Task | None = None
        self.加载数据()
        self.拉黑 = self.加入黑名单
        self.屏蔽 = self.加入黑名单
        self.更新用户 = self.加入黑名单
        self.解除拉黑 = self.删除用户
        self.解除屏蔽 = self.删除用户
        self.清理黑名单 = self.清理过期

    def 加载数据(self):
        try:
            if self.data_path.exists():
                try:
                    with open(self.data_path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                        if not isinstance(raw, dict):
                            raise TypeError(f"数据文件顶层对象应为dict，实际：{type(raw).__name__}")
                except (json.decoder.JSONDecodeError, TypeError) as e:
                    # 数据文件无法解析：备份后用空数据启动
                    i = 0
                    name = f"{i}_bak_data.json"
                    while name in {p.name for p in self.data_dir.iterdir()}:
                        i += 1
                        name = f"{i}_bak_data.json"  # 数字在前方便查看和排序
                    self.data_path.rename(self.data_dir / name)
                    raw = {}
                    logger.exception(
                        f"无法解析数据文件{self.data_path}，使用新数据继续，原文件在{self.data_dir / name}\n{e}"
                    )

                self.data = {}
                for gid, users in (raw or {}).items():
                    gid = str(gid or "").strip()
                    if not gid or not isinstance(users, dict):
                        continue
                    g = {}
                    for uid, v in users.items():
                        uid = str(uid or "").strip()
                        if not uid or not isinstance(v, dict):
                            continue
                        info = 单个黑名单信息.from_dict(v, 群ID=gid, 用户ID=uid)
                        if info is not None:
                            g[uid] = info
                    if g: self.data[gid] = g
            else: self.data = {}

            # 尝试写入一次，验证目录/文件可写；失败时抛异常让上层处理
            self.保存()
        except Exception:
            logger.critical(f"处理数据文件失败，插件无法运行")
            raise

    def 保存(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self._操作锁:
            data = {
                gid: {uid: info.to_dict() for uid, info in users.items()}
                for gid, users in self.data.items()
            }
            tmp = self.data_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            tmp.replace(self.data_path)

    def 加入黑名单(
            self, 用户ID: str, 群ID: str, 时间: int | float | None = None, 用户名: str | None = None,
            理由: str | None = None, 操作者: str | None = None, 模式: 操作模式 | None = None
    ) -> 单个黑名单信息:
        """添加 or 更新黑名单
        Args:
            用户ID: 用户ID
            群ID: 群ID
            时间: 小于946656000（北京时间 2000-1-1）（约29年）代表时长秒，大于代表结束时间，默认永久或不更改
            用户名: 用户名
            理由: 理由
            操作者: 操作者"""

        用户ID = str(用户ID).strip()
        群ID = str(群ID).strip()
        if 时间 is None: 结束时间戳 = None
        else:
            if 时间 >= 二000年时间: 结束时间戳 = 时间
            else: 结束时间戳 = time.time() + 时间

        with self._操作锁:
            if 群ID not in self.data: self.data[群ID] = {}
            g = self.data[群ID]
            if r := g.get(用户ID):
                r.更新信息(
                    群ID=群ID, 用户ID=用户ID, 结束时间戳=结束时间戳,
                    用户名=用户名, 理由=理由, 操作者=操作者, 模式=模式
                )
            else:
                g[用户ID] = 单个黑名单信息(
                    群ID=群ID, 用户ID=用户ID, 结束时间戳=结束时间戳,
                    用户名=用户名, 理由=理由, 操作者=操作者, 模式=模式
                )

            r = g[用户ID].copy()
            self.保存()

        return r

    def 已拉黑(self, 群ID, 用户ID) -> bool:
        # 单次读取，频繁调用，无对象返回，不必加锁
        if g := self.data.get(str(群ID).strip()):
            if info := g.get(str(用户ID).strip()):
                return info.已拉黑
        return False

    def 已屏蔽(self, 群ID, 用户ID) -> bool:
        if g := self.data.get(str(群ID).strip()):
            if info := g.get(str(用户ID).strip()):
                return info.已屏蔽
        return False

    def 未结束(self, 群ID, 用户ID) -> bool:
        if g := self.data.get(str(群ID).strip()):
            if info := g.get(str(用户ID).strip()):
                return info.未结束
        return False

    def 已结束(self, 群ID, 用户ID) -> bool:
        if g := self.data.get(str(群ID).strip()):
            if info := g.get(str(用户ID).strip()):
                return info.已结束
        return False

    def 删除用户(self, 群ID, 用户ID) -> 单个黑名单信息 | None:
        with self._操作锁:
            if g := self.data.get(str(群ID or "").strip()):
                if r := g.pop(str(用户ID or "").strip(), None):
                    self.保存()
                return r
            return None

    def 清空群(self, 群ID:str) -> dict[str, 单个黑名单信息] | None:
        with self._操作锁:
            if r := self.data.pop(str(群ID or "").strip(), None):
                self.保存()
            return r

    def 获取群信息(self, 群ID:str | None = None) -> dict[str, 单个黑名单信息]:
        with self._操作锁:
            if gv := self.data.get(str(群ID or "").strip()):
                return {i: j.copy() for i, j in gv.items()}
            return {}

    def 获取用户信息(self, 用户ID, 群ID:str|None=None) -> 单个黑名单信息 | None | list[单个黑名单信息]:
        """获取指定群的用户信息，未传群号则获取所有群的
        Returns:
            传了群号：单个黑名单信息 or None
            未传群号： list[单个黑名单信息]"""
        uid = str(用户ID or "").strip()
        gid = str(群ID or "").strip()
        with self._操作锁:
            if gid:
                if gv := self.data.get(gid):
                    if r := gv.get(uid):
                        return r.copy()
            else:
                l = []
                for i in self.data.values():
                    if uid in i:
                        l.append(i[uid].copy())
                return l
        return None

    def 获取所有信息(self) -> dict[str, dict[str, 单个黑名单信息]]:
        """获取所有信息快照"""
        with self._操作锁:
            return {
                gid: {uid: info.copy() for uid, info in gv.items()}
                for gid, gv in self.data.items()
            }

    def copy(self, 群ID:str | None = None, 用户ID:str | None = None) \
            -> 单个黑名单信息 | None | list[单个黑名单信息] | dict[str, 单个黑名单信息] | dict[str, dict[str, 单个黑名单信息]]:
        """copy数据，若不传群ID也不传用户ID，则copy所有数据
        Args:
            群ID: 需要copy的群ID
            用户ID: 需要copy的用户ID，若未传群号，则返回列表 or None，若传了，则返回单个 or None
        """
        uid = str(用户ID or "").strip()
        gid = str(群ID or "").strip()
        if uid:
            return self.获取用户信息(群ID=gid, 用户ID=uid)
        if gid:
            return self.获取群信息(群ID=gid)
        return self.获取所有信息()

    def clear(self, 群ID:str | None = None, 用户ID:str | None = None)\
            -> 单个黑名单信息 | None | list[单个黑名单信息] | dict[str, 单个黑名单信息] | dict[str, dict[str, 单个黑名单信息]]:
        """清理数据，若不传群ID也不传用户ID，则清理所有数据
        Args:
            群ID: 需要清理的群ID
            用户ID: 需要删除的用户ID，若未传群号，则清空所有包含该用户的数据，若传了，则只删除目标群的
        """
        uid = str(用户ID or "").strip()
        gid = str(群ID or "").strip()
        with self._操作锁:
            if uid:
                if gid:
                    return self.删除用户(gid, uid)
                else:
                    l = []
                    for gv in self.data.values():
                        if r := gv.pop(uid, None):
                            l.append(r)
                    if l:
                        self.保存()
                    return l
            elif gid:
                return self.清空群(gid)
            else:
                data = self.data.copy()
                self.data.clear()
                self.保存()
                return data

    def 清理过期(self):
        with self._操作锁:
            now = time.time()
            g_del = []
            u_del = []


            for gid, gv in self.data.items():
                if not gv:
                    g_del.append(gid)
                for uid, info in gv.items():
                    if now >= info.结束时间戳:
                        u_del.append((gid, uid))

            if not (g_del or u_del):
                return

            for gid in g_del:
                del self.data[gid]
            for gid, uid in u_del:
                del self.data[gid][uid]
                if not self.data[gid]:
                    del self.data[gid]

            self.保存()

    # ---------- 清理调度：启动清理 / 运行中清理 / 关闭清理 ----------

    async def 启动清理(self, 清理间隔: float | None = None):
        """启动清理：先立即清理一次过期条目，再启动后台周期清理任务。
        Args:
            清理间隔: 后台周期清理的间隔（秒），不传则用初始化时的值"""

        async def 后台清理循环():
            try:
                while True:
                    await asyncio.sleep(self.清理间隔)
                    try:
                        self.清理过期()
                    except Exception:
                        logger.exception("黑名单运行中清理出错")
            except asyncio.CancelledError:
                logger.info("黑名单后台清理任务已停止")
        with self._操作锁:
            if 清理间隔 is not None:
                self.清理间隔 = float(清理间隔)
            if self.清理运行中:
                logger.info("黑名单后台清理任务已在运行，跳过重复启动")
                return self._清理任务
            self.清理过期()
            self._清理任务 = asyncio.create_task(后台清理循环(), name="黑名单后台清理")
            return self._清理任务

    @property
    def 清理运行中(self) -> bool:
        """判断后台清理任务是否正在运行"""
        task = self._清理任务
        return task is not None and not task.done()

    async def 关闭清理(self):
        """关闭清理：停止运行中的后台清理任务，再最后清理一次并保存。"""
        with self._操作锁:
            task, self._清理任务 = self._清理任务, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("停止黑名单后台清理任务出错")
        self.清理过期()