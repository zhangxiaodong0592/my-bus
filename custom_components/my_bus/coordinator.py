"""My Bus 数据协调器：每 N 秒（默认 10 秒）轮询实时车辆位置并判定到站事件.

线路拓扑（总站数、环线判定、目标站序）来自数据同步层的本地缓存，
该缓存会定期与掌上公交同步；每次同步完成后本协调器会自动重新读取拓扑，
以保证站序始终与服务端一致。
"""

from __future__ import annotations

from datetime import timedelta
import inspect
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BusPosition, XmBusApiError, XmBusClient
from .arrival_logic import (
    compute_distances,
    normalize_poll_interval,
)
from .const import (
    CONF_CITY,
    CONF_DIRECTION,
    CONF_LINE,
    CONF_POLL_INTERVAL,
    CONF_STATION,
    CONF_STATION_ORDER,
    DEFAULT_CITY,
    DEFAULT_POLL_INTERVAL,
)
from .data_sync import XmBusDataSync, station_order_in

_LOGGER = logging.getLogger(__name__)


class XmBusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """轮询某线路实时车辆位置并判定到站."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry,
        client: XmBusClient,
        sync: XmBusDataSync | None = None,
    ) -> None:
        # 轮询间隔也过一遍归一化：0 会让协调器变成忙轮询，越界值只会白白加重
        # 对掌上公交接口的压力。
        interval = normalize_poll_interval(
            entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        )
        kwargs: dict[str, Any] = {
            "name": f"my_bus_{entry.entry_id}",
            "update_interval": timedelta(seconds=interval),
        }
        # config_entry 参数在较早的 HA 版本中不存在，按版本兼容处理
        if "config_entry" in inspect.signature(DataUpdateCoordinator.__init__).parameters:
            kwargs["config_entry"] = entry
        super().__init__(hass, _LOGGER, **kwargs)
        self.entry = entry
        self.client = client
        self.sync = sync
        self.city: str = str(entry.data.get(CONF_CITY) or DEFAULT_CITY)
        self.station: str = entry.data[CONF_STATION]
        self.line: str = entry.data[CONF_LINE]
        self.direction: str = str(entry.data[CONF_DIRECTION])
        self.station_order: int = int(entry.data[CONF_STATION_ORDER])

        self.arrivals: list[dict[str, Any]] = []
        # 4 个实时传感器的 entity_id（sensor.py 按 translation_key 登记，
        # 供 device_trigger 的「状态变化」触发器监听）
        self.sensor_entity_ids: dict[str, str] = {}
        # CMD115 官方到站预览（neartext / minutes / meters），缺失时为空 dict
        self.preview: dict[str, Any] = {}

        self._topology_loaded = False
        self._topology_generation: int | None = None
        self._total_stops = 0
        self._is_loop = False

    def nearest_bus(self) -> dict[str, Any] | None:
        """当前离监控站台最近的一辆车（供设备条件使用），没有车时返回 None."""
        best: dict[str, Any] | None = None
        for bus in self.arrivals:
            remaining = bus.get("remaining")
            if remaining is None or remaining < 0:
                continue
            if best is None or remaining < best.get("remaining", 1 << 30):
                best = bus
        return best

    @property
    def device_name(self) -> str:
        return f"My Bus（{self.city} {self.line} {self.station}）"

    @property
    def sync_status(self) -> dict[str, Any] | None:
        """数据同步状态（供诊断传感器使用）."""
        return self.sync.status() if self.sync is not None else None

    async def _async_update_data(self) -> dict[str, Any]:
        if not self._topology_loaded or self._topology_stale():
            await self._async_load_topology()
        try:
            snapshot = await self.client.realtime(self.line, self.direction)
        except XmBusApiError as err:
            raise UpdateFailed(str(err)) from err

        # 兼容「直接返回车辆列表」的客户端（老版本 / 测试桩）：此时没有分段里程，
        # 只有「车正驶向目标站」那一刻还能给出确切里程。
        positions: list[BusPosition] = getattr(snapshot, "positions", snapshot)
        segments: list[float] = list(getattr(snapshot, "segments_m", []) or [])

        self.arrivals = compute_distances(
            positions,
            self.station_order,
            self._total_stops,
            self._is_loop,
            segments_m=segments,
        )

        # v0.9.2：顺带拉一次 CMD115 官方到站预览（预计到达分钟数 / 官方状态文案）。
        # 只作展示增强，失败不影响本轮实时数据（老客户端没有此方法时直接跳过）。
        self.preview = {}
        fetch_preview = getattr(self.client, "station_preview", None)
        if fetch_preview is not None:
            try:
                preview = await fetch_preview(self.station, self.line, self.direction)
            except XmBusApiError as err:
                _LOGGER.debug("My Bus：CMD115 到站预览拉取失败（不影响实时数据）: %s", err)
            else:
                if preview:
                    self.preview = dict(preview)

        return {
            "arrivals": self.arrivals,
            "preview": self.preview,
            "station": self.station,
            "line": self.line,
        }

    def _topology_stale(self) -> bool:
        """数据同步层刚完成一次同步 → 拓扑需要重新读取."""
        return (
            self.sync is not None
            and self._topology_generation != self.sync.generation
        )

    async def _fetch_stations(self) -> list[dict]:
        """线路站点拓扑：优先走数据同步层（本地缓存 + 定期与掌上公交同步）."""
        if self.sync is not None:
            return await self.sync.async_line_stations(
                self.city, self.line, self.direction
            )
        return await self.client.line_stations(self.line, self.direction)

    async def _async_load_topology(self) -> None:
        """加载线路站点表: 总站数、环线判定（首末站同名）与目标站序."""
        try:
            stations = await self._fetch_stations()
        except XmBusApiError as err:
            raise UpdateFailed(f"加载线路站点失败: {err}") from err
        if not stations:
            raise UpdateFailed("线路站点为空，请检查线路与方向配置")
        self._total_stops = len(stations)
        first = (stations[0].get("stationName") or "").strip()
        last = (stations[-1].get("stationName") or "").strip()
        self._is_loop = bool(first and first == last)

        # 站序以掌上公交的最新拓扑为准：改线后不必等用户重新配置
        order = station_order_in(stations, self.station)
        if order is not None and order != self.station_order:
            _LOGGER.info(
                "My Bus：%s %s 在 %s（%s）上的站序已更新 %s → %s，"
                "到站判定已按最新线路数据调整",
                self.city, self.station, self.line,
                "上行" if self.direction == "1" else "下行",
                self.station_order, order,
            )
            self.station_order = order

        self._topology_loaded = True
        self._topology_generation = self.sync.generation if self.sync is not None else None
        _LOGGER.debug(
            "线路 %s 方向 %s: 共 %d 站, 环线=%s, 目标站序=%s",
            self.line, self.direction, self._total_stops, self._is_loop,
            self.station_order,
        )
