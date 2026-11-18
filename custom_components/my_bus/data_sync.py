"""My Bus 数据同步层：让城市 / 线路 / 站台等结构数据与掌上公交保持一致.

设计要点
--------
1. **结构数据本地留副本**：城市列表（CMD101）、线路站点拓扑（CMD103）、
   站台停靠线路（CMD115）、线路起终点（CMD114 全量）都会缓存在本地，
   用户在选择时看到的就是掌上公交的数据，且不必每次都打接口。
2. **定期自动同步**：默认每 ``DEFAULT_SYNC_INTERVAL``（12 小时）与掌上公交
   同步一次（可在集成选项里调整间隔或关闭），每次同步会强制刷新城市列表
   以及**所有已配置监控**涉及的线路拓扑与站台线路。
3. **实时数据绝不缓存**：到站预览（CMD104 的 index、CMD115 的 neartext）
   始终实时请求，缓存里只保留静态结构（站名、站序、线路起终点）。
4. **缓存过期即按需拉取**：某项缓存超过 TTL 后，下一次用到它时会立刻从
   服务端拉取并写回，不必等下一个同步周期。
5. **条目自动校对**：每次同步都会用最新拓扑校验已配置监控的站序；掌上公交
   调整站序时自动修正条目（并触发条目重载），线路 / 站台下线时记录问题并
   写日志，避免静默失效。
6. **落盘**：数据保存在 ``<config>/.storage/my_bus.data``，重启 HA 后依旧可用，
   长期未使用的条目会自动清理。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .api import (
    LineHit,
    StationHit,
    XmBusApiError,
    XmBusClient,
    filter_cities,
    sorted_cities,
)
from .const import (
    CITY_CACHE_TTL,
    CONF_CITY,
    CONF_DIRECTION,
    CONF_LINE,
    CONF_STATION,
    CONF_STATION_ORDER,
    DATA_SYNC_KEY,
    DEFAULT_CITY,
    DEFAULT_SYNC_ENABLED,
    DEFAULT_SYNC_INTERVAL,
    DOMAIN,
    LINE_ENDPOINTS_TTL,
    LINE_STATIONS_TTL,
    MAX_SYNC_INTERVAL,
    MIN_SYNC_INTERVAL,
    PRUNE_UNUSED_AFTER,
    SEARCH_CACHE_TTL,
    STATION_LINES_TTL,
    SYNC_SAVE_DELAY,
    SYNC_STORAGE_KEY,
    SYNC_STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

KEY_CITIES = "cities"


# ---------------------------------------------------------------------------
# 缓存键
# ---------------------------------------------------------------------------

def endpoints_key(city: str) -> str:
    return f"{city}|endpoints"


def line_key(city: str, line: str, direction: str) -> str:
    return f"{city}|line|{line}|{direction}"


def station_key(city: str, station: str) -> str:
    return f"{city}|station|{station}"


def dir_text(direction: Any) -> str:
    return "上行" if str(direction) == "1" else "下行"


def station_order_in(stations: list[dict], station: str) -> int | None:
    """在某方向的站点拓扑里取 ``station`` 的站序（1 起），找不到返回 None."""
    for item in stations or []:
        if not isinstance(item, dict):
            continue
        if (item.get("stationName") or "").strip() != station:
            continue
        try:
            order = int(item.get("stationOrder") or 0)
        except (TypeError, ValueError):
            return None
        return order or None
    return None


def _hit_to_dict(hit: LineHit) -> dict[str, Any]:
    """缓存线路静态信息——**不含** neartext（那是实时到站预览）。"""
    return {
        "line_name": hit.line_name,
        "direction": hit.direction,
        "from_stop": hit.from_stop,
        "to_stop": hit.to_stop,
    }


def _hit_from_dict(data: dict[str, Any]) -> LineHit:
    return LineHit(
        line_name=str(data.get("line_name") or ""),
        direction=str(data.get("direction") or "1"),
        from_stop=str(data.get("from_stop") or ""),
        to_stop=str(data.get("to_stop") or ""),
    )


def _iso(ts: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(ts)).astimezone().isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _err_text(err: BaseException) -> str:
    if isinstance(err, XmBusApiError):
        return str(err)
    return f"{type(err).__name__}: {err}"


# ---------------------------------------------------------------------------
# 同步问题（用于诊断与日志）
# ---------------------------------------------------------------------------

@dataclass
class SyncIssue:
    """已配置监控与掌上公交不一致的问题."""

    entry_id: str
    title: str
    city: str
    line: str
    direction: str
    station: str
    reason: str

    @property
    def text(self) -> str:
        return (
            f"{self.city} {self.line}（{dir_text(self.direction)}）"
            f"{self.station}：{self.reason}"
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "entry_id": self.entry_id,
            "title": self.title,
            "city": self.city,
            "line": self.line,
            "direction": self.direction,
            "station": self.station,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# 数据同步对象
# ---------------------------------------------------------------------------

class XmBusDataSync:
    """掌上公交结构数据的本地缓存 + 定期同步."""

    def __init__(
        self,
        hass: HomeAssistant,
        client_factory: Callable[[str], XmBusClient],
    ) -> None:
        self._hass = hass
        self._client_for = client_factory
        self._store: Store = Store(hass, SYNC_STORAGE_VERSION, SYNC_STORAGE_KEY)

        # 持久化缓存: key -> {"ts": float, "data": Any}
        self._items: dict[str, dict[str, Any]] = {}
        # 关键词搜索缓存（仅内存，避免来回翻菜单时反复打接口）
        self._search: dict[str, tuple[float, Any]] = {}

        self._settings: dict[str, Any] = {
            "interval": DEFAULT_SYNC_INTERVAL,
            "enabled": DEFAULT_SYNC_ENABLED,
        }
        self._last_sync: float | None = None
        self._duration: float | None = None
        self._failures = 0
        self._last_error = ""
        self._issues: list[SyncIssue] = []
        # 每次同步成功后 +1：协调器据此判断需要重新读取线路拓扑
        self._generation = 0

        self._loaded = False
        self._fetch_lock = asyncio.Lock()
        self._sync_lock = asyncio.Lock()
        self._unsub: Callable[[], None] | None = None
        self._task: asyncio.Task | None = None

    # ---------------------------------------------------------------- 生命周期
    async def async_load(self) -> None:
        """从磁盘恢复缓存（幂等，只读一次）."""
        if self._loaded:
            return
        self._loaded = True
        try:
            raw = await self._store.async_load()
        except Exception as err:  # noqa: BLE001  缓存坏了不能让集成起不来
            _LOGGER.warning("读取本地公交数据缓存失败，将重新拉取：%s", err)
            return
        if not isinstance(raw, dict):
            return

        items = raw.get("items")
        if isinstance(items, dict):
            self._items = {
                key: value
                for key, value in items.items()
                if isinstance(value, dict) and isinstance(value.get("ts"), (int, float))
            }
        settings = raw.get("settings")
        if isinstance(settings, dict):
            self._settings["interval"] = _clamp_interval(
                settings.get("interval", DEFAULT_SYNC_INTERVAL)
            )
            self._settings["enabled"] = bool(
                settings.get("enabled", DEFAULT_SYNC_ENABLED)
            )
        stats = raw.get("stats")
        if isinstance(stats, dict):
            self._last_sync = stats.get("last_sync") or None
            self._duration = stats.get("duration")
            self._failures = int(stats.get("failures") or 0)
            self._last_error = str(stats.get("last_error") or "")
            self._generation = int(stats.get("generation") or 0)
        _LOGGER.debug(
            "My Bus 数据缓存已载入：%d 项，上次同步 %s",
            len(self._items),
            _iso(self._last_sync) or "从未",
        )

    async def async_start(self) -> None:
        """载入缓存 → 注册定时同步 → 首次启动（数据过期时）补一次同步."""
        await self.async_load()
        self._ensure_timer()
        if self._needs_sync():
            _LOGGER.info("My Bus：本地公交数据已过期，立即与掌上公交同步一次")
            self.schedule_sync()

    async def async_stop(self) -> None:
        """取消定时同步并把缓存落盘（最后一个监控被删除时调用）."""
        self._cancel_timer()
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        try:
            await self._store.async_save(self._as_dict())
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("My Bus 数据缓存落盘失败：%s", err)

    # ------------------------------------------------------------------ 定时器
    def _ensure_timer(self) -> None:
        self._cancel_timer()
        if not self._settings.get("enabled", DEFAULT_SYNC_ENABLED):
            return
        try:
            self._unsub = async_track_time_interval(
                self._hass,
                self._async_tick,
                timedelta(seconds=int(self._settings["interval"])),
            )
        except Exception as err:  # noqa: BLE001  桩环境没有事件循环
            _LOGGER.debug("注册定时同步失败：%s", err)
            self._unsub = None

    def _cancel_timer(self) -> None:
        if self._unsub is not None:
            try:
                self._unsub()
            except Exception:  # noqa: BLE001
                pass
            self._unsub = None

    async def _async_tick(self, _now=None) -> None:
        """定时器回调：交给后台任务，避免长时间占用事件循环."""
        self.schedule_sync()

    def schedule_sync(self) -> None:
        """在后台启动一次同步（已有同步在跑时忽略）."""
        if self._task is not None and not self._task.done():
            return
        try:
            self._task = self._hass.async_create_task(self._async_background_sync())
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("无法启动后台同步任务：%s", err)
            self._task = None

    async def _async_background_sync(self) -> None:
        try:
            await self.async_sync()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("My Bus 数据同步失败")
        finally:
            self._task = None

    # ---------------------------------------------------------------- 读写缓存
    def _fresh(self, key: str, ttl: float) -> Any:
        item = self._items.get(key)
        if not isinstance(item, dict):
            return None
        ts = item.get("ts")
        if not isinstance(ts, (int, float)):
            return None
        if ttl and time.time() - float(ts) > ttl:
            return None
        return item.get("data")

    def _put(self, key: str, data: Any) -> None:
        self._items[key] = {"ts": time.time(), "data": data}

    async def _get_or_fetch(
        self,
        key: str,
        ttl: float,
        fetch: Callable[[], Any],
        *,
        force: bool = False,
    ) -> Any:
        """取缓存；未命中（或已过期 / force）则拉取最新并写回."""
        await self.async_load()
        if not force:
            cached = self._fresh(key, ttl)
            if cached is not None:
                return cached
        async with self._fetch_lock:
            if not force:
                cached = self._fresh(key, ttl)
                if cached is not None:
                    return cached
            data = await fetch()
            self._put(key, data)
            self._store.async_delay_save(self._as_dict, SYNC_SAVE_DELAY)
            return data

    def _as_dict(self) -> dict[str, Any]:
        return {
            "items": self._items,
            "settings": self._settings,
            "stats": {
                "last_sync": self._last_sync,
                "duration": self._duration,
                "failures": self._failures,
                "last_error": self._last_error,
                "generation": self._generation,
            },
        }

    async def _async_save(self, *, immediate: bool = False) -> None:
        if immediate:
            try:
                await self._store.async_save(self._as_dict())
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("My Bus 数据缓存写入失败：%s", err)
            return
        self._store.async_delay_save(self._as_dict, SYNC_SAVE_DELAY)

    # ------------------------------------------------------------ 结构数据读取
    async def async_cities(self, *, force: bool = False) -> list[str]:
        """掌上公交全部服务城市（已清洗，按拼音排序）."""
        data = await self._get_or_fetch(
            KEY_CITIES, CITY_CACHE_TTL, self._fetch_cities, force=force
        )
        return list(data or [])

    async def _fetch_cities(self) -> list[str]:
        cities = await self._client_for(DEFAULT_CITY).cities()
        return sorted_cities(filter_cities(cities))

    async def async_line_stations(
        self, city: str, line: str, direction: str, *, force: bool = False
    ) -> list[dict]:
        """某线路某方向的站点拓扑（含站序，按途经顺序）."""
        key = line_key(city, line, direction)
        data = await self._get_or_fetch(
            key,
            LINE_STATIONS_TTL,
            lambda: self._client_for(city).line_stations(line, direction),
            force=force,
        )
        return [dict(x) for x in (data or []) if isinstance(x, dict)]

    async def async_station_lines(
        self,
        city: str,
        station: str,
        direction: str | None = None,
        *,
        force: bool = False,
    ) -> list[LineHit]:
        """某站台停靠的线路（静态结构，不含实时到站信息）."""
        key = station_key(city, station)
        data = await self._get_or_fetch(
            key,
            STATION_LINES_TTL,
            lambda: self._fetch_station_lines(city, station),
            force=force,
        )
        hits = [
            _hit_from_dict(item)
            for item in (data or [])
            if isinstance(item, dict)
        ]
        hits = [hit for hit in hits if hit.line_name]
        if direction:
            hits = [hit for hit in hits if hit.direction == str(direction)]
        return hits

    async def _fetch_station_lines(self, city: str, station: str) -> list[dict]:
        hits = await self._client_for(city).station_lines(station)
        return [_hit_to_dict(hit) for hit in hits]

    async def async_line_endpoints(
        self, city: str, *, force: bool = False
    ) -> dict[tuple[str, str], tuple[str, str]]:
        """``{(线路名, 方向): (起点站, 终点站)}`` 映射."""
        data = await self._get_or_fetch(
            endpoints_key(city),
            LINE_ENDPOINTS_TTL,
            lambda: self._fetch_endpoints(city),
            force=force,
        )
        mapping: dict[tuple[str, str], tuple[str, str]] = {}
        for key, value in (data or {}).items():
            if not isinstance(value, (list, tuple)) or len(value) < 2:
                continue
            line, _, direction = str(key).rpartition("|")
            if not line:
                continue
            mapping[(line, direction)] = (str(value[0]), str(value[1]))
        return mapping

    async def _fetch_endpoints(self, city: str) -> dict[str, list[str]]:
        client = self._client_for(city)
        mapping = await client.line_endpoints(force=True)
        return {
            f"{line}|{direction}": [from_stop, to_stop]
            for (line, direction), (from_stop, to_stop) in mapping.items()
        }

    # ------------------------------------------------------------ 关键词检索
    async def async_search_stations(
        self, city: str, keyword: str, *, force: bool = False
    ) -> list[StationHit]:
        """站台关键词检索（结果仅做短时内存缓存，避免翻菜单时反复请求）."""
        return await self._search_cached(
            f"station|{city}|{keyword.strip().lower()}",
            lambda: self._client_for(city).search_stations(keyword),
            force=force,
        )

    async def async_search_lines(
        self, city: str, keyword: str, *, force: bool = False
    ) -> list[LineHit]:
        """线路关键词检索（同上）."""
        return await self._search_cached(
            f"line|{city}|{keyword.strip().lower()}",
            lambda: self._client_for(city).search_lines(keyword),
            force=force,
        )

    async def _search_cached(self, key: str, fetch, *, force: bool = False) -> list:
        if not force:
            hit = self._search.get(key)
            if hit is not None and time.time() - hit[0] < SEARCH_CACHE_TTL:
                return list(hit[1])
        data = list(await fetch())
        self._search[key] = (time.time(), data)
        return list(data)

    # -------------------------------------------------------------------- 同步
    def _entries(self) -> list:
        try:
            return list(self._hass.config_entries.async_entries(DOMAIN))
        except Exception:  # noqa: BLE001  桩环境
            return []

    def _targets(self, entries=None) -> set[tuple[str, str, str, str]]:
        targets: set[tuple[str, str, str, str]] = set()
        for entry in entries if entries is not None else self._entries():
            data = getattr(entry, "data", None) or {}
            city = str(data.get(CONF_CITY) or DEFAULT_CITY).strip() or DEFAULT_CITY
            line = str(data.get(CONF_LINE) or "").strip()
            station = str(data.get(CONF_STATION) or "").strip()
            direction = str(data.get(CONF_DIRECTION) or "1")
            if line and station:
                targets.add((city, line, direction, station))
        return targets

    async def async_sync(self, entries=None) -> dict[str, Any]:
        """与掌上公交完整同步一次.

        步骤：刷新城市列表 → 刷新所有已配置监控涉及的线路起终点 / 线路拓扑 /
        站台线路 → 校对已配置条目的站序 → 清理长期未使用的缓存。
        """
        if self._sync_lock.locked():
            _LOGGER.debug("已有同步任务在运行，跳过本次触发")
            return self.status()

        async with self._sync_lock:
            started = time.time()
            await self.async_load()
            errors: list[str] = []
            counts = {
                "cities": 0,
                "lines": 0,
                "stations": 0,
                "endpoints": 0,
                "repaired": 0,
                "pruned": 0,
            }
            entry_list = self._entries() if entries is None else list(entries)
            targets = self._targets(entry_list)

            # 1) 城市列表
            try:
                counts["cities"] = len(await self.async_cities(force=True))
            except Exception as err:  # noqa: BLE001
                errors.append(f"城市列表：{_err_text(err)}")

            # 2) 先刷新线路起终点（CMD114 全量）：站台线路的「起点→终点」标签
            #    依赖它，先拉一次可让后面补齐标签时直接命中客户端缓存，省一次请求
            for city in sorted({target[0] for target in targets}):
                try:
                    await self.async_line_endpoints(city, force=True)
                    counts["endpoints"] += 1
                except Exception as err:  # noqa: BLE001
                    errors.append(f"{city} 线路起终点：{_err_text(err)}")

            # 3) 已配置监控涉及的线路与站台
            for city, line, direction, station in sorted(targets):
                try:
                    if await self.async_line_stations(city, line, direction, force=True):
                        counts["lines"] += 1
                except Exception as err:  # noqa: BLE001
                    errors.append(f"{city} {line}（{dir_text(direction)}）站点：{_err_text(err)}")
                try:
                    if await self.async_station_lines(city, station, force=True):
                        counts["stations"] += 1
                except Exception as err:  # noqa: BLE001
                    errors.append(f"{city} {station} 站台线路：{_err_text(err)}")

            # 4) 校对条目：掌上公交改线 / 站序变化时自动跟随
            try:
                repaired, issues = await self.async_validate_entries(entry_list)
                counts["repaired"] = repaired
                self._issues = issues
            except Exception as err:  # noqa: BLE001
                errors.append(f"校对已配置监控：{_err_text(err)}")

            # 5) 清理长期未使用的缓存
            protected = {KEY_CITIES} | {
                line_key(c, ln, d) for c, ln, d, _ in targets
            } | {
                station_key(c, st) for c, _, _, st in targets
            } | {endpoints_key(c) for c, _, _, _ in targets}
            try:
                counts["pruned"] = self._prune(protected)
            except Exception as err:  # noqa: BLE001
                errors.append(f"清理缓存：{_err_text(err)}")
            self._search.clear()

            # 6) 统计
            self._last_sync = time.time()
            self._duration = round(self._last_sync - started, 2)
            self._generation += 1
            if errors:
                self._failures += 1
                self._last_error = errors[0]
                _LOGGER.warning(
                    "My Bus 数据同步完成（%d 项失败）：%s",
                    len(errors),
                    "；".join(errors),
                )
            else:
                self._last_error = ""
            await self._async_save(immediate=True)

            _LOGGER.info(
                "My Bus 数据同步完成：城市 %d，线路 %d，站台 %d，修正条目 %d，"
                "清理 %d，不一致 %d，用时 %.1fs",
                counts["cities"],
                counts["lines"],
                counts["stations"],
                counts["repaired"],
                counts["pruned"],
                len(self._issues),
                self._duration,
            )
            return {
                "ok": not errors,
                "last_sync": _iso(self._last_sync),
                "duration": self._duration,
                **counts,
                "issues": [issue.as_dict() for issue in self._issues],
                "errors": errors,
            }

    async def async_validate_entries(self, entries=None) -> tuple[int, list[SyncIssue]]:
        """用最新拓扑校对已配置监控，返回 (修正条数, 不一致问题列表).

        - 站序与线上不一致 → 直接修正 ``entry.data[station_order]``
          （HA 的更新监听器会顺带重载该条目，实时判定立刻生效）；
        - 站台被挪到另一个方向 / 已不在线路上 → 记录问题，不擅自改动配置。
        """
        repaired = 0
        issues: list[SyncIssue] = []
        entry_list = self._entries() if entries is None else list(entries)

        for entry in entry_list:
            data = getattr(entry, "data", None) or {}
            city = str(data.get(CONF_CITY) or DEFAULT_CITY).strip() or DEFAULT_CITY
            line = str(data.get(CONF_LINE) or "").strip()
            station = str(data.get(CONF_STATION) or "").strip()
            direction = str(data.get(CONF_DIRECTION) or "1")
            if not (line and station):
                continue
            title = str(getattr(entry, "title", "") or f"{city} {line} {station}")
            entry_id = str(getattr(entry, "entry_id", "") or "")

            def _issue(reason: str) -> SyncIssue:
                return SyncIssue(
                    entry_id=entry_id,
                    title=title,
                    city=city,
                    line=line,
                    direction=direction,
                    station=station,
                    reason=reason,
                )

            try:
                stations = await self.async_line_stations(city, line, direction)
            except Exception as err:  # noqa: BLE001
                issues.append(_issue(f"无法获取线路站点：{_err_text(err)}"))
                continue

            order = station_order_in(stations, station)
            if order is None:
                other = "2" if direction == "1" else "1"
                try:
                    other_stations = await self.async_line_stations(city, line, other)
                except Exception:  # noqa: BLE001
                    other_stations = []
                if station_order_in(other_stations, station) is not None:
                    issues.append(
                        _issue(
                            f"掌上公交已把该站调整到{dir_text(other)}，"
                            "请到集成选项里重新选择线路 / 站台"
                        )
                    )
                else:
                    issues.append(
                        _issue("该站已不在线路上（线路可能改线或站台更名），请重新选择")
                    )
                continue

            try:
                old = int(data.get(CONF_STATION_ORDER))
            except (TypeError, ValueError):
                old = None
            if old != order:
                _LOGGER.info(
                    "My Bus：%s 的站序与掌上公交不一致（%s → %s），已自动修正",
                    title,
                    old if old is not None else "未知",
                    order,
                )
                if self._update_entry(entry, {**data, CONF_STATION_ORDER: order}):
                    repaired += 1

        return repaired, issues

    def _update_entry(self, entry, new_data: dict) -> bool:
        try:
            self._hass.config_entries.async_update_entry(entry, data=new_data)
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("更新 My Bus 条目失败：%s", err)
            return False

    def _prune(self, protected: set[str]) -> int:
        """清理长期未使用、且不属于已配置监控的缓存条目."""
        now = time.time()
        removed = 0
        for key in list(self._items):
            if key in protected:
                continue
            item = self._items.get(key)
            ts = item.get("ts") if isinstance(item, dict) else None
            if not isinstance(ts, (int, float)) or now - float(ts) > PRUNE_UNUSED_AFTER:
                del self._items[key]
                removed += 1
        if removed:
            _LOGGER.debug("My Bus 清理了 %d 条长期未使用的数据缓存", removed)
        return removed

    # ---------------------------------------------------------------- 设置/状态
    async def async_set_interval(self, seconds: Any) -> int:
        """设置定期同步间隔（秒），并立即按新间隔重排定时任务."""
        await self.async_load()
        value = _clamp_interval(seconds)
        self._settings["interval"] = value
        self._ensure_timer()
        await self._async_save(immediate=True)
        return value

    async def async_set_enabled(self, enabled: bool) -> bool:
        """开关定期自动同步（关闭后仍会在缓存过期时按需拉取）."""
        await self.async_load()
        self._settings["enabled"] = bool(enabled)
        self._ensure_timer()
        await self._async_save(immediate=True)
        return self._settings["enabled"]

    def _needs_sync(self) -> bool:
        if not self._settings.get("enabled", DEFAULT_SYNC_ENABLED):
            return False
        if not self._items:
            return True
        last = float(self._last_sync or 0)
        return time.time() - last > int(self._settings["interval"])

    @property
    def generation(self) -> int:
        """每次同步完成后自增：协调器据此决定是否重新读取线路拓扑."""
        return self._generation

    @property
    def interval(self) -> int:
        return int(self._settings.get("interval", DEFAULT_SYNC_INTERVAL))

    @property
    def enabled(self) -> bool:
        return bool(self._settings.get("enabled", DEFAULT_SYNC_ENABLED))

    @property
    def interval_hours(self) -> float:
        return round(self.interval / 3600, 2)

    def cache_keys(self) -> list[str]:
        return sorted(self._items)

    def last_sync_text(self) -> str:
        return _iso(self._last_sync) or "尚未同步"

    def status(self) -> dict[str, Any]:
        """同步状态（选项菜单 / 传感器 / 诊断共用）."""
        cities = self._fresh(KEY_CITIES, 0) or []
        return {
            "enabled": self.enabled,
            "interval": self.interval,
            "interval_hours": self.interval_hours,
            "last_sync": _iso(self._last_sync),
            "last_sync_ts": self._last_sync,
            "duration": self._duration,
            "generation": self._generation,
            "cities": len(cities),
            "lines": sum(1 for key in self._items if "|line|" in key),
            "stations": sum(1 for key in self._items if "|station|" in key),
            "items": len(self._items),
            "failures": self._failures,
            "last_error": self._last_error,
            "issues": [issue.as_dict() for issue in self._issues],
            "issue_texts": [issue.text for issue in self._issues],
        }


def _clamp_interval(value: Any) -> int:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_SYNC_INTERVAL
    return min(max(seconds, MIN_SYNC_INTERVAL), MAX_SYNC_INTERVAL)


# ---------------------------------------------------------------------------
# 域级单例
# ---------------------------------------------------------------------------

def client_for_city(hass: HomeAssistant, city: str) -> XmBusClient:
    """按城市取（并缓存）接口客户端：``hass.data`` 里每个城市一个实例."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    store = hass.data.setdefault(DOMAIN, {})
    name = (city or "").strip() or DEFAULT_CITY
    key = f"client::{name}"
    client = store.get(key)
    if client is None:
        client = store[key] = XmBusClient(async_get_clientsession(hass), name)
    return client


def get_sync(hass: HomeAssistant) -> XmBusDataSync:
    """取（必要时创建）域级同步对象——不触发磁盘读取."""
    store = hass.data.setdefault(DOMAIN, {})
    sync = store.get(DATA_SYNC_KEY)
    if not isinstance(sync, XmBusDataSync):
        sync = store[DATA_SYNC_KEY] = XmBusDataSync(
            hass, lambda city: client_for_city(hass, city)
        )
    return sync


async def async_get_sync(hass: HomeAssistant) -> XmBusDataSync:
    """取域级同步对象，并确保本地缓存已载入."""
    sync = get_sync(hass)
    await sync.async_load()
    return sync
