"""My Bus 服务：供 AI 助手 / 语音 / 自动化调用.

服务:
- ``my_bus.get_arrivals``：查询某站台各线路的实时到站信息（**实时请求**，不走缓存）。
- ``my_bus.sync_data``：立即与掌上公交同步一次城市 / 线路 / 站台等结构数据。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .api import XmBusApiError
from .const import CONF_CITY, DEFAULT_CITY, DOMAIN
from .data_sync import async_get_sync, client_for_city

_LOGGER = logging.getLogger(__name__)

GET_ARRIVALS_SCHEMA = vol.Schema(
    {
        vol.Required("station"): cv.string,
        vol.Optional("line"): cv.string,
        vol.Optional("direction"): vol.All(vol.Coerce(int), vol.In([1, 2])),
        vol.Optional("city"): cv.string,
    }
)

SYNC_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("city"): cv.string,
    }
)

_STATION_NUM_RE = re.compile(r"(\d+)")


def _default_city(hass: HomeAssistant) -> str:
    """取已配置条目的城市；没有条目时回退到默认城市."""
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
    except Exception:  # noqa: BLE001
        entries = []
    for entry in entries:
        city = str((entry.data or {}).get(CONF_CITY) or "").strip()
        if city:
            return city
    return DEFAULT_CITY


def async_setup_services(hass: HomeAssistant) -> None:
    """注册 my_bus.get_arrivals 与 my_bus.sync_data."""

    async def handle_get_arrivals(call: ServiceCall) -> ServiceResponse:
        station: str = call.data["station"].strip()
        line: str | None = call.data.get("line")
        line = line.strip() if line else None
        direction: int | None = call.data.get("direction")
        city: str = (call.data.get("city") or "").strip() or _default_city(hass)

        client = client_for_city(hass, city)

        # 站名归一化: 允许用户输入不带"站"/"路"字的简称
        candidates = _station_candidates(station)
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                # 实时数据不缓存：每次都直接问掌上公交
                hits = await client.station_lines(candidate)
            except XmBusApiError as err:
                last_error = err
                continue
            if not hits:
                continue
            arrivals = _format_line_hits(hits, line, direction)
            if arrivals:
                return {
                    "city": city,
                    "station": candidate,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "arrivals": arrivals,
                    "summary": _summarize(candidate, arrivals),
                }
        if last_error is not None:
            raise HomeAssistantError(f"查询公交数据失败: {last_error}")
        return {
            "city": city,
            "station": station,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "arrivals": [],
            "summary": f"未查询到 {city} {station} 的公交到站信息",
        }

    hass.services.async_register(
        DOMAIN,
        "get_arrivals",
        handle_get_arrivals,
        schema=GET_ARRIVALS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    async def handle_sync_data(call: ServiceCall) -> ServiceResponse:
        """立即与掌上公交同步一次（城市 + 已配置监控涉及的线路 / 站台）."""
        sync = await async_get_sync(hass)
        city = (call.data.get("city") or "").strip()
        entries = None
        if city:
            # 只同步该城市的监控（城市列表仍会整体刷新 —— CMD101 与城市参数无关）
            try:
                entries = [
                    entry
                    for entry in hass.config_entries.async_entries(DOMAIN)
                    if str((entry.data or {}).get(CONF_CITY) or DEFAULT_CITY).strip() == city
                ]
            except Exception:  # noqa: BLE001
                _LOGGER.debug("读取配置条目失败，改为同步全部城市", exc_info=True)
                entries = None
        summary = await sync.async_sync(entries)
        summary["city"] = city or None
        return summary

    hass.services.async_register(
        DOMAIN,
        "sync_data",
        handle_sync_data,
        schema=SYNC_DATA_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _station_candidates(station: str) -> list[str]:
    """生成站名候选: 原样 → 补"路" → 补"路站"。"""
    base = station
    candidates = [base]
    if not base.endswith("路"):
        candidates.append(f"{base}路")
    if not base.endswith("站"):
        candidates.append(f"{base}路站")
    return candidates


def _format_line_hits(
    hits, line: str | None, direction: int | None
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in hits:
        line_name = item.line_name
        if line and line not in line_name:
            continue
        if direction is not None and str(direction) != item.direction:
            continue
        remaining = None
        match = _STATION_NUM_RE.search(item.raw_neartext or "")
        if match:
            remaining = int(match.group(1))
        result.append(
            {
                "line": line_name,
                "direction": "上行" if item.direction == "1" else "下行",
                "direction_code": item.direction,
                "towards": item.to_stop or item.direction_label,
                "nearest_bus_remaining_stops": remaining,
                "nearest_bus_text": item.raw_neartext or "",
            }
        )
    return result


def _summarize(station: str, arrivals: list[dict[str, Any]]) -> str:
    """生成一句中文摘要，方便 AI 直接播报."""
    if not arrivals:
        return f"当前没有查询到经过 {station} 的线路"
    parts = []
    for a in arrivals:
        text = a["nearest_bus_text"] or "暂无车辆"
        parts.append(f"{a['line']}（{a['direction']}，开往{a['towards']}）最近车辆{text}")
    return f"{station}：" + "；".join(parts) + "。"
