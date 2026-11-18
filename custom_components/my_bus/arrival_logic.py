"""到站判定纯逻辑（不依赖 Home Assistant，便于离线测试）.

判定模型（经厦门掌上公交实测数据校准）:
- CMD104 返回的 index = 车辆即将到达站序 - 1（0 起），车辆位置 p = index + 1
- 普通线路: 距目标站 d = target_order - p（负数 = 已过站）
- 环线（首末站同名）: d = (target_order - p) % 总站数，过站后自动绕回
- d == 0 → 「已到站」

里程（公里）模型（v0.6.0，数据源与掌上公交 H5 一致）:
- CMD104 的 list[].busToStationNiheDistance = 车辆 → 即将到达站 的线路里程（米）
- CMD104 的 dislist[].d[i] = 第 i+1 站 → 第 i+2 站 的分段里程（米）
- 车辆到目标站的里程 = 到即将到达站的里程 + 从该站到目标站的分段里程之和
  即剩余 d 个站时累加 d 段的里程（d == 0 时只剩「车→目标站」那一段）
- 车辆已过目标站（非环线）时里程无意义，置 None

v0.9.1 起移除「提前多少站 / 提前多少公里」阈值（用户：「我只要一个到站传感器」）。
v0.9.15 起事件体系（ArrivalTracker / ArrivalEventData / bus_arrived 事件）整体移除，
到站判断只保留「到站状态」传感器的三个状态值（未到站 / 即将到站 / 已到站）。

v0.9.2 起到站判定改用**官方口径**（CMD104 每辆车的 ``statusType``）：
- ``statusType == "0"`` → 车辆**正停在**即将到达站（距离恒为 0 米）→「已到站」
- ``statusType == "2"`` → 车辆在途（哪怕 ``remaining == 0``，也只是驶向该站）
- 接口没给 ``statusType``（老客户端 / 测试桩）→ 退回「剩余站数 == 0」判定
预计到达（分钟）v0.9.2 起改用 CMD115 的官方 ``neardis``（「N分钟/M米」）；
v0.9.3 起**只认官方数据**，缺失时设备页显示「暂无数据」，不再本地推测。
剩余站数与到站状态展示 v0.9.18 起采信 CMD115 官方文案
（:func:`official_stops` / :func:`official_arrival_status`）：
官方在车进站停稳时就减 1，而 CMD104 的 index 发车才跳，推算总慢「一个停站时间」。
v0.9.19 起按用户要求**严格官方**：内部推算展示口径（app_style_stops /
arrival_status 的 statusType 判定）删除，官方解析不出就显示「未知 / 暂无车辆」；
内部几何差只留作最近车辆选取、里程计算与误显防护。
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from typing import Any

from .const import (
    DEFAULT_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)

# 设备页上「到站状态」传感器用的文案
STATUS_NO_BUS = "暂无车辆"              # 该方向当前没有在途车辆
STATUS_NOT_ARRIVING = "未到站"
STATUS_ARRIVING = "即将到站"            # v0.9.2：剩余 0 站但车还在途（官方 statusType=2）
STATUS_ARRIVED = "已到站"

# CMD115 neardis 官方预计到达文案，如「2分钟/180米」「小于1分钟/390米」「3分钟/1公里」
_NEARDIS_RE = re.compile(r"(小于)?(\d+(?:\.\d+)?)\s*分钟\s*/\s*(\d+(?:\.\d+)?)\s*(米|公里)")

# HA 侧「没有一辆车」的占位状态：任何车牌（含通配符）都不该匹配上它们
_PLATE_NON_STATES = frozenset({"", "UNKNOWN", "UNAVAILABLE", "NONE"})


def plate_match(pattern: str, state: str) -> bool:
    """车牌通配符匹配（v0.9.30，触发器「车牌变为」与条件「车牌是/不是」共用）.

    - ``pattern`` 含 ``*``（任意多个字）或 ``?``（恰好一个字）→ 通配符匹配；
    - 不含通配符 → 精确匹配（与 0.9.28/0.9.29 行为完全一致，老配置零影响）；
    - 两端去空白、忽略大小写（闽d06* 与 闽D06* 等价）；
    - ``pattern`` 为空一律不成立；``state`` 是 unknown / unavailable（没车）
      也一律不成立 —— 否则「车牌变为 *」会在没车时误触发。
    """
    p = (pattern or "").strip().upper()
    s = (state or "").strip().upper()
    if not p or s in _PLATE_NON_STATES:
        return False
    if "*" not in p and "?" not in p:
        return p == s
    return re.fullmatch(
        "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in p),
        s,
    ) is not None


def parse_neardis(text: str | None) -> tuple[int | None, float | None]:
    """解析 CMD115 的官方预计到达文案，返回（分钟, 米）.

    - ``"2分钟/180米"`` → ``(2, 180.0)``
    - ``"小于1分钟/390米"`` → ``(0, 390.0)``（不足 1 分钟记 0）
    - ``"3分钟/1公里"`` → ``(3, 1000.0)``
    - 其它（空 / 「非运营时间」等）→ ``(None, None)``
    """
    if not text:
        return (None, None)
    m = _NEARDIS_RE.search(str(text))
    if not m:
        return (None, None)
    minutes = 0 if m.group(1) else int(float(m.group(2)))
    meters = float(m.group(3)) * (1000.0 if m.group(4) == "公里" else 1.0)
    return (minutes, meters)

# v0.9.3 起「预计到达」只认官方数据（CMD115），本地按均速 / 站数推测的
# estimate_eta_minutes 已删除 —— 用户要求「尽量和官方数据一致」。


def normalize_poll_interval(value: Any) -> int:
    """把「数据刷新间隔」归一到合法范围（秒，5 ~ 120）.

    前端 NumberSelector 会拦越界值，但表单之外（旧条目、手工改 .storage、
    直接调 service）仍可能塞进 0 或 9999。0 会让协调器变成忙轮询，所以
    这里统一夹取，非法值退回默认值。
    """
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_POLL_INTERVAL
    return max(MIN_POLL_INTERVAL, min(seconds, MAX_POLL_INTERVAL))


@dataclass
class BusPosition:
    """全线某车辆的实时位置（站序，1 起）."""

    plate: str
    current_stop: str
    position: int
    distance_to_next_stop_m: float | None = None
    status_type: str | None = None  # CMD104 原始 statusType（"0"=停站中，"2"=在途）


def distance_km(distance_m: float | None) -> float | None:
    """把剩余里程（米）换算成公里（保留 1 位小数）；数据缺失时为 None.

    掌上公交的 :data:`distance_m` 是线路里程（米），设备页按「公里」展示更直观。
    数值只在**有分段里程**时才有值。
    """
    if distance_m is None:
        return None
    try:
        meters = float(distance_m)
    except (TypeError, ValueError):
        return None
    if meters < 0:
        return None
    return round(meters / 1000.0, 1)


def remaining_stops(position: int, target_order: int, total_stops: int, is_loop: bool) -> int | None:
    """车辆到目标站的剩余站数（已过站且非环线时为 None）.

    ⚠️ 内部几何差，v0.9.19 起**只用于**：最近车辆选取、剩余公里数计算、
    终点站「已到站」误显防护与排查属性 ``internal_remaining``，
    不再作为「剩余站数 / 到站状态」传感器的展示口径（严格官方）。
    """
    raw = target_order - position
    if raw < 0:
        if not is_loop:
            return None
        raw = raw % total_stops if total_stops else 0
    return raw


def official_stops(neartext: str | None, internal_remaining: int | None) -> int | None:
    """CMD115 官方到站预览文案 → 剩余站数（v0.9.18，v0.9.19 起严格官方）.

    官方文案直接就是 App 上显示的内容：``"N站"`` → N、``"即将到站"`` → 1、
    ``"已到站"`` → 0。实测（2026-10-28 快1路探针）官方口径在车**进站停稳**
    （statusType 翻 0）那一刻就减 1，而 CMD104 的 index 要**发车**才跳下一站，
    用 index 推算总比官方慢「一个停站时间」——v0.9.19 起推算口径
    （app_style_stops / statusType 判定）已按用户要求删除，展示值只认官方。

    防终点站误显（v0.9.2 教训：终点站大量误显「已到站」）：``已到站`` /
    ``即将到站`` 只在内部几何差 ≤ 1 时才采信（车确实到了/快到了），否则视为
    误显返回 None。其余文案（非运营时间 / 空串 / 未知格式）返回 None。
    展示层对 None 显示「未知 / 暂无车辆」，宁缺勿错。
    """
    text = (neartext or "").strip()
    if not text:
        return None
    if text in (STATUS_ARRIVED, STATUS_ARRIVING):
        if internal_remaining is None or internal_remaining > 1:
            return None
        return 0 if text == STATUS_ARRIVED else 1
    match = re.fullmatch(r"(\d+)\s*站", text)
    if match:
        return int(match.group(1))
    return None


def official_arrival_status(
    neartext: str | None, internal_remaining: int | None
) -> str | None:
    """CMD115 官方文案 → 「到站状态」三态（v0.9.18，v0.9.19 起严格官方）.

    ``"已到站"`` → 已到站、``"即将到站"`` → 即将到站、``"N站"`` → 未到站；
    ``已到站`` / ``即将到站`` 同样受终点站误显防护（内部几何差 ≤ 1 才采信）。
    其余文案返回 None，展示层显示「暂无车辆」。
    """
    text = (neartext or "").strip()
    if not text:
        return None
    if text in (STATUS_ARRIVED, STATUS_ARRIVING):
        if internal_remaining is None or internal_remaining > 1:
            return None
        return text
    if re.fullmatch(r"\d+\s*站", text):
        return STATUS_NOT_ARRIVING
    return None


def route_distance_m(
    position: int,
    to_next_stop_m: float | None,
    segments_m: list[float] | None,
    target_order: int,
    total_stops: int,
    is_loop: bool,
) -> float | None:
    """车辆到目标站的线路里程（米）；数据不足或已过站时返回 None."""
    if to_next_stop_m is None:
        return None
    remaining = remaining_stops(position, target_order, total_stops, is_loop)
    if remaining is None:
        return None
    if not segments_m:
        # 没有分段里程时，只有「车正驶向目标站」这一刻能给出确切里程
        return float(to_next_stop_m) if remaining == 0 else None

    total = float(to_next_stop_m)
    count = len(segments_m)
    for k in range(remaining):
        index = position - 1 + k
        if index >= count:
            if not is_loop:
                return None
            index %= count
        try:
            total += float(segments_m[index] or 0.0)
        except (TypeError, ValueError):
            return None
    return total


def compute_distances(
    positions: list[BusPosition],
    target_order: int,
    total_stops: int,
    is_loop: bool,
    segments_m: list[float] | None = None,
) -> list[dict]:
    """把车辆绝对位置换算为相对目标站的剩余站数与剩余里程."""
    result: list[dict] = []
    for bus in positions:
        if bus.position <= 0:
            continue
        remaining = remaining_stops(bus.position, target_order, total_stops, is_loop)
        if remaining is None:
            continue
        distance_m = route_distance_m(
            bus.position,
            bus.distance_to_next_stop_m,
            segments_m,
            target_order,
            total_stops,
            is_loop,
        )
        # 官方停站标志：statusType == "0" 表示车正停在即将到达站。
        # 接口没给 statusType（老客户端 / 测试桩）时视为「已停」，保持老判定口径。
        stopped = bus.status_type is None or str(bus.status_type) == "0"
        result.append(
            {
                "plate": bus.plate,
                "current_stop": bus.current_stop,
                "remaining": remaining,
                "distance_m": distance_m,
                "stopped": stopped,
            }
        )
    return result
