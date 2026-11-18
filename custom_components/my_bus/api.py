"""掌上公交（h5.mygolbs.com）异步客户端与中文排序/拼音工具.

接口说明（均为 POST 表单，需 Origin 头，免注册免 Key）:
- CMD=101: 全部服务城市（实测 565 条，字段 cityname）
- CMD=108: **按经纬度反查城市**（返回 status=1 + msg=城市名，如 "厦门市"；与 CITYNAME 无关）
- CMD=110: 站点模糊搜索（支持中文子串与拼音首字母，如 "县口"/"县"/"xklz"/"xk"）
- CMD=114: 线路搜索（部分城市需带"路"字）
- CMD=103: 线路站点拓扑（含站序与坐标，基本静态）
- CMD=104: 某线路实时车辆（index=即将到达站序-1；busToStationNiheDistance=车→该站里程(米)；dislist=全线分段里程）
- CMD=115: 某站台全部线路实时到站预览（neartext 如 "6站"）

所有业务命令都要带 ``CITYNAME``，因此 :class:`XmBusClient` **按城市实例化**。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass

import aiohttp

try:
    from .const import DEFAULT_CITY
except ImportError:  # 允许脱离 HA 直接导入自测
    from const import DEFAULT_CITY  # type: ignore[no-redef]

_LOGGER = logging.getLogger(__name__)

API_URL = "https://h5.mygolbs.com/ApiData.do"
API_ORIGIN = "https://h5.mygolbs.com"


# ---------------------------------------------------------------------------
# 中文/拼音排序与模糊匹配
# ---------------------------------------------------------------------------

def _pypinyin():
    """延迟导入 pypinyin."""
    from pypinyin import lazy_pinyin, Style

    return lazy_pinyin, Style


def cn_sort_key(name: str) -> tuple:
    """按用户要求的排序: 数字 1-9 最前（按数值），其后按拼音 a-z。"""
    name = name.strip()
    m = re.match(r"^(\d+)", name)
    if m:
        return (0, int(m.group(1)), name)
    lazy_pinyin, _ = _pypinyin()
    return (1, "".join(lazy_pinyin(name)).lower(), name)


def cn_sorted(names) -> list[str]:
    return sorted(names, key=cn_sort_key)


def sorted_line_hits(hits: list["LineHit"]) -> list["LineHit"]:
    """线路按 线路名(数字->拼音) 排序，同名再按方向。"""
    return sorted(hits, key=lambda h: (cn_sort_key(h.line_name), h.direction))


def _pinyin_variants(name: str) -> tuple[str, str]:
    """返回 (拼音首字母串, 全拼音串)."""
    lazy_pinyin, Style = _pypinyin()
    initials = "".join(lazy_pinyin(name, style=Style.FIRST_LETTER)).lower()
    full = "".join(lazy_pinyin(name, style=Style.NORMAL)).lower()
    return initials, full


def match_keyword(name: str, keyword: str) -> bool:
    """模糊匹配: 中文子串 / 拼音首字母前缀 / 全拼前缀。"""
    kw = keyword.strip().lower()
    if not kw:
        return True
    if kw in name.lower():
        return True
    initials, full = _pinyin_variants(name)
    return full.startswith(kw) or initials.startswith(kw) or initials.replace(" ", "").startswith(kw)


# ---------------------------------------------------------------------------
# 城市名匹配（定位结果 / 用户输入 → 服务城市列表里的正式名称）
# ---------------------------------------------------------------------------

# 行政区划后缀，用于「南平市」↔「南平县」这类差异的归一化比对
_CITY_SUFFIXES = (
    "特别行政区",
    "自治区",
    "自治州",
    "自治县",
    "自治旗",
    "地区",
    "省",
    "市",
    "县",
    "区",
    "州",
    "盟",
    "旗",
)


def city_base_name(name: str) -> str:
    """去掉行政区划后缀（可叠加，如「XX自治州」→「XX」）."""
    out = (name or "").strip()
    for _ in range(3):
        for suffix in _CITY_SUFFIXES:
            if out.endswith(suffix) and len(out) > len(suffix):
                out = out[: -len(suffix)]
                break
        else:
            return out
    return out


def match_city(cities: list[str], name: str) -> str | None:
    """把定位/输入得到的城市名匹配为服务城市列表中的正式名称.

    依次尝试: 完全相同 → 去后缀相同 → 互相包含（取名称最短者，避免
    「湘西土家族苗族自治州」这类长名压过短名）。匹配不到返回 ``None``。
    """
    raw = (name or "").strip()
    if not raw or not cities:
        return None

    for city in cities:
        if city == raw:
            return city

    base = city_base_name(raw)
    if base:
        for city in cities:
            if city_base_name(city) == base:
                return city
        contained = [
            city
            for city in cities
            if base in city or city_base_name(city) in raw
        ]
        if contained:
            return min(contained, key=len)
    return None


def filter_cities(cities) -> list[str]:
    """清洗城市列表: 去空、去测试条目、去重复、去「同名+编号」的重复数据.

    接口实测会在正式城市之外混入少量脏数据，例如 ``厦门市测试``、
    ``厦门市1``（与 ``厦门市`` 同名的编号副本），这些会干扰用户选择。
    """
    names: list[str] = []
    seen: set[str] = set()
    for item in cities or []:
        name = (item or "").strip()
        if not name or "测试" in name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    reserved = set(names)
    return [
        name
        for name in names
        if not (re.search(r"\d+$", name) and re.sub(r"\d+$", "", name) in reserved)
    ]


def sorted_cities(cities) -> list[str]:
    """城市按拼音排序（复用与站台一致的排序规则）."""
    return sorted(cities, key=cn_sort_key)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class StationHit:
    name: str


@dataclass
class LineHit:
    line_name: str
    direction: str  # "1" 上行 / "2" 下行
    from_stop: str = ""
    to_stop: str = ""
    raw_neartext: str = ""  # CMD115 到站预览，如 "6站"

    @property
    def direction_label(self) -> str:
        if self.from_stop and self.to_stop:
            return f"{self.from_stop}→{self.to_stop}"
        return "上行" if self.direction == "1" else "下行"


@dataclass
class BusPosition:
    """全线某车辆的实时位置.

    position 为车辆即将到达/所在站点的站序（1 起），
    与 CMD104 返回的 index（0 起站序）相差 1。

    ``distance_to_next_stop_m`` 是 CMD104 的 ``busToStationNiheDistance``：
    车辆沿线路到**即将到达站**的里程（米），缺失时为 None。
    """

    plate: str
    current_stop: str
    position: int
    distance_to_next_stop_m: float | None = None
    status_type: str | None = None  # CMD104 原始 statusType（"0"=停站中，"2"=在途）


@dataclass
class RealtimeSnapshot:
    """一轮 CMD104 的完整结果：车辆位置 + 全线分段里程.

    ``segments_m[i]`` = 第 i+1 站 → 第 i+2 站 的线路里程（米），
    末项通常为 0（最后一站没有下一站）。据此可以算出车辆到任意站的里程。
    """

    positions: list[BusPosition]
    segments_m: list[float]


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------

class XmBusClient:
    """掌上公交公开接口客户端（绑定到某一个城市）."""

    def __init__(self, session: aiohttp.ClientSession, city: str = DEFAULT_CITY) -> None:
        self._session = session
        self.city: str = (city or DEFAULT_CITY).strip() or DEFAULT_CITY
        # (线路名, 方向) -> (起点站, 终点站)，来自 CMD114 全量查询，首次使用时拉取并缓存
        self._endpoints: dict[tuple[str, str], tuple[str, str]] | None = None

    async def _post(
        self, params: dict[str, str], _retry: bool = True, check_status: bool = True
    ) -> dict:
        """POST 请求。

        注意: 超时抛出的 asyncio.TimeoutError 并非 aiohttp.ClientError 子类，
        必须单独捕获，否则会冒泡成前端的 "Unknown error occurred"。

        ``check_status=False`` 时不校验 status 字段（CMD108 用 status=2 表示
        「该坐标无服务城市」，属于正常业务分支而非错误）。
        """
        payload = {"CITYNAME": self.city, "CITYKEY": "", **params}
        try:
            async with self._session.post(
                API_URL,
                data=payload,
                headers={"Origin": API_ORIGIN},
                timeout=aiohttp.ClientTimeout(total=25, connect=10),
            ) as resp:
                if resp.status != 200:
                    raise XmBusApiError(f"HTTP {resp.status}")
                raw = await resp.read()
        except XmBusApiError:
            raise
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            if _retry:
                await asyncio.sleep(0.8)
                return await self._post(params, _retry=False, check_status=check_status)
            raise XmBusApiError(
                f"网络请求失败（{type(err).__name__}: {err}）。"
                "请确认 Home Assistant 主机可访问 h5.mygolbs.com"
            ) from err

        # 接口风控会返回非 JSON 内容，需单独识别（重试一次）
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except ValueError as err:
            if _retry:
                await asyncio.sleep(1.2)
                return await self._post(params, _retry=False, check_status=check_status)
            raise XmBusApiError(
                "公交接口返回异常内容（可能触发限流），请稍后重试"
            ) from err

        if not isinstance(data, dict):
            raise XmBusApiError(f"接口返回异常内容: {raw[:120]!r}")
        if check_status and str(data.get("status")) != "1":
            msg = data.get("msg") or data.get("desc")
            raise XmBusApiError(f"接口返回错误: {msg or data}")
        return data

    # -- CMD 101 全部服务城市 ---------------------------------------------
    async def cities(self) -> list[str]:
        """返回掌上公交支持的全部城市（实测 565 条，清洗后 563 条）."""
        data = await self._post({"CMD": "101"})
        return filter_cities(
            item.get("cityname") for item in data.get("data") or []
        )

    # -- CMD 108 按坐标反查城市 -------------------------------------------
    # 实测：同一个请求重发，约有一半会返回 ``{"status":-1}`` —— 纯服务端抖动
    # （换请求头 / 带 Cookie / 把间隔拉长 / 让坐标微抖，命中率都不变，都是 30~50%），
    # 不是「没有服务城市」。因此只能多重试几次；因为与间隔无关，这里用固定短间隔。
    # 只有拿到 ``status=2`` 才认定该坐标确实没有服务城市（实测境外坐标返回 2，
    # 并附带当地地名，如 "Nakano"）。
    LOCATE_ATTEMPTS = 6
    LOCATE_BACKOFF = 0.4

    async def locate_city(self, latitude: float, longitude: float) -> str | None:
        """按经纬度反查城市名（与 CITYNAME 无关）.

        返回：
        - 城市名 —— 命中（``{"status":1,"msg":"厦门市"}``）
        - ``None`` —— 该坐标**确实**不在服务范围内（``{"status":2}``）
        - 抛 :class:`XmBusApiError` —— 重试多次仍只拿到抖动响应（``status:-1``），
          这时不能武断地告诉用户「不在服务范围」，由上层提示稍后重试。

        ``LAT``/``LNG`` 才是被反查的坐标；``MYLAT``/``MYLNG`` 是「我的位置」，
        官方 H5 页面会一起发，实测四者齐全时命中率略高，所以一并带上（值相同）。
        """
        lat = f"{float(latitude):.6f}"
        lng = f"{float(longitude):.6f}"
        for attempt in range(self.LOCATE_ATTEMPTS):
            data = await self._post(
                {"CMD": "108", "LAT": lat, "LNG": lng, "MYLAT": lat, "MYLNG": lng},
                check_status=False,
            )
            status = str(data.get("status"))
            name = (data.get("msg") or "").strip()
            if status == "1" and name:
                return name
            if status == "2":
                return None
            if attempt + 1 < self.LOCATE_ATTEMPTS:
                await asyncio.sleep(self.LOCATE_BACKOFF)
        raise XmBusApiError(
            "定位服务暂时没有响应（接口连续返回 status=-1），请稍后重试"
        )

    # -- CMD 110 站点模糊搜索 --------------------------------------------
    async def search_stations(self, keyword: str) -> list[StationHit]:
        data = await self._post({"CMD": "110", "KEYWORD": keyword.strip()})
        hits = [
            StationHit(name=item.get("stationName", "").strip())
            for item in data.get("busstations") or []
            if item.get("stationName")
        ]
        if not hits and keyword.strip():
            # 接口仅支持首字母/中文子串，全拼用客户端匹配兜底
            hits = await self._fallback_pinyin_station_search(keyword.strip())
        return hits

    async def _fallback_pinyin_station_search(self, keyword: str) -> list[StationHit]:
        try:
            head = await self._post({"CMD": "110", "KEYWORD": keyword[0]})
        except XmBusApiError:
            return []
        return [
            StationHit(name=item["stationName"].strip())
            for item in head.get("busstations") or []
            if item.get("stationName") and match_keyword(item["stationName"], keyword)
        ]

    # -- CMD 114 线路搜索 --------------------------------------------------
    async def search_lines(self, keyword: str) -> list[LineHit]:
        kw = keyword.strip()
        data = await self._post({"CMD": "114", "KEYWORD": kw})
        lines = _parse_line_hits(data)
        if not lines and kw and not kw.endswith("路"):
            data = await self._post({"CMD": "114", "KEYWORD": f"{kw}路"})
            lines = _parse_line_hits(data)
        return lines

    # -- CMD 103 线路站点拓扑 ----------------------------------------------
    async def line_stations(self, line_name: str, direction: str) -> list[dict]:
        data = await self._post(
            {"CMD": "103", "LINENAME": line_name, "DIRECTION": direction}
        )
        stations = data.get("data") or []
        return stations if isinstance(stations, list) else []

    async def station_order(self, line_name: str, direction: str, station_name: str) -> int | None:
        """返回站点在某线路方向上的站序（1 起），不存在返回 None。"""
        for item in await self.line_stations(line_name, direction):
            if item.get("stationName") == station_name:
                try:
                    return int(item.get("stationOrder") or 0) or None
                except (TypeError, ValueError):
                    return None
        return None

    # -- CMD 114 全量线路 (起点/终点映射) ------------------------------------
    async def line_endpoints(
        self, force: bool = False
    ) -> dict[tuple[str, str], tuple[str, str]]:
        """返回 {(线路名, 方向): (起点站, 终点站)} 映射.

        CMD114 空关键词一次返回全部线路（实测 1335 条，from/to 齐全），
        CMD115 的单条线路只带终点 to、起点 from 为空，因此用本映射补齐方向。
        ``force=True`` 时忽略实例缓存重新拉取（数据同步层定期刷新时使用）。
        """
        if self._endpoints is not None and not force:
            return self._endpoints
        data = await self._post({"CMD": "114", "KEYWORD": ""})
        mapping: dict[tuple[str, str], tuple[str, str]] = {}
        for item in data.get("buslines") or []:
            name = (item.get("lineName") or "").strip()
            if not name:
                continue
            direction = str(item.get("upperOrDown") or "1")
            mapping[(name, direction)] = (
                (item.get("from") or "").strip(),
                (item.get("to") or "").strip(),
            )
        self._endpoints = mapping
        return mapping

    # -- CMD 115 站台全部线路（含两个方向） ----------------------------------
    async def station_lines(
        self, station_name: str, direction: str | None = None
    ) -> list[LineHit]:
        """返回该站台停靠的线路，可选按方向过滤.

        实测: ``ALL=0`` 只返回该站名**其中一个物理站台**方向的线路
        （金安大厦站只出 4 条）；``ALL=1`` 一次返回**两个方向**的全部线路
        （金安大厦站上行 10 条 + 下行 10 条）。同一站名在上/下行各有一个
        物理站台，故必须用 ALL=1，否则会漏掉一半线路。
        """
        data = await self._post(
            {"CMD": "115", "STATIONNAME": station_name, "MYLAT": "", "MYLNG": "", "ALL": "1"}
        )
        hits = _parse_line_hits(data)
        if direction:
            hits = [h for h in hits if h.direction == direction]
        if hits and any(not h.from_stop for h in hits):
            # 用 CMD114 全量映射补齐起点（CMD115 的 from 为空）
            try:
                mapping = await self.line_endpoints()
            except XmBusApiError:
                return hits
            for hit in hits:
                pair = mapping.get((hit.line_name, hit.direction))
                if pair:
                    hit.from_stop = hit.from_stop or pair[0]
                    hit.to_stop = hit.to_stop or pair[1]
        return hits

    # -- CMD 104 某线路某站实时车辆位置 --------------------------------------
    async def realtime(self, line_name: str, direction: str) -> RealtimeSnapshot:
        """返回该线路方向上所有实时车辆的位置与全线分段里程.

        实测 CMD104 的 index = 车辆即将到达站的站序 - 1（0 起站序），
        因此 position = index + 1。

        同时返回两样能换算「还剩多少公里」的数据:
        - ``list[].busToStationNiheDistance``: 车辆 → 即将到达站 的里程（米）
        - ``dislist[].d``: 全线分段里程（米），第 i 项 = 第 i+1 站 → 第 i+2 站

        v0.9.2 起同时解析每辆车的官方状态 ``statusType``：
        ``"0"`` = 车正停在即将到达站（已到站），``"2"`` = 在途。
        """
        data = await self._post({"CMD": "104", "LINENAME": line_name, "DIRECTION": direction})
        segments: list[float] = []
        for item in data.get("dislist") or []:
            try:
                segments.append(float((item or {}).get("d") or 0.0))
            except (TypeError, ValueError, AttributeError):
                segments.append(0.0)
        positions: list[BusPosition] = []
        for bus in data.get("list") or []:
            try:
                position = int(bus.get("index") or 0) + 1
            except (TypeError, ValueError):
                continue
            try:
                to_next = float(bus.get("busToStationNiheDistance"))
            except (TypeError, ValueError):
                to_next = None
            status_type = str(bus.get("statusType") or "").strip() or None
            positions.append(
                BusPosition(
                    plate=(bus.get("busNumber") or "").strip(),
                    current_stop=(bus.get("stationName") or "").strip(),
                    position=position,
                    distance_to_next_stop_m=to_next,
                    status_type=status_type,
                )
            )
        return RealtimeSnapshot(positions=positions, segments_m=segments)

    # -- CMD 115 站台到站预览（官方预计到达） ---------------------------------
    async def station_preview(
        self, station_name: str, line_name: str, direction: str
    ) -> dict | None:
        """查 CMD115 上「某站台某线路某方向」的官方到站预览.

        返回 ``{"neartext": "2站"/"已到站"/"即将到站"/"非运营时间",
        "neardis": 官方原文如"2分钟/180米"/"预计发车:11:00",
        "minutes": 2, "meters": 180.0}``；该站台没有这条线路方向时返回 ``None``。
        ``minutes`` / ``meters`` 来自官方 ``neardis``（如「2分钟/180米」），
        是**官方给的时间**，比按均速估算准确得多；缺失时为 ``None``。
        """
        data = await self._post(
            {
                "CMD": "115",
                "STATIONNAME": station_name,
                "MYLAT": "",
                "MYLNG": "",
                "ALL": "1",
            }
        )
        want_line = (line_name or "").strip()
        want_dir = str(direction or "").strip()
        for item in data.get("data") or []:
            if (item.get("lineName") or "").strip() != want_line:
                continue
            if str(item.get("upperOrDown") or "").strip() != want_dir:
                continue
            from .arrival_logic import parse_neardis

            minutes, meters = parse_neardis(item.get("neardis") or "")
            neartext = (item.get("neartext") or "").strip()
            neardis = (item.get("neardis") or "").strip()
            if "已到站" in neartext:
                # 官方明确说「已到站」→ 到达时间就是 0 分钟 / 0 米
                minutes = 0 if minutes is None else minutes
                meters = 0.0 if meters is None else meters
            return {
                "neartext": neartext,
                "neardis": neardis,
                "minutes": minutes,
                "meters": meters,
            }
        return None


def _parse_line_hits(data: dict) -> list[LineHit]:
    hits: list[LineHit] = []
    for item in data.get("buslines") or data.get("data") or []:
        name = (item.get("lineName") or "").strip()
        if not name:
            continue
        hits.append(
            LineHit(
                line_name=name,
                direction=str(item.get("upperOrDown") or "1"),
                from_stop=(item.get("from") or "").strip(),
                to_stop=(item.get("to") or "").strip(),
                raw_neartext=(item.get("neartext") or "").strip(),
            )
        )
    return hits


class XmBusApiError(Exception):
    """接口调用异常."""
