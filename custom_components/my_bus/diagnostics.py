"""My Bus 诊断信息（设置 → 设备与服务 → My Bus → 下载诊断）.

包含条目配置、协调器的实时判定状态，以及数据同步层的缓存概况 ——
用来确认本地数据与掌上公交是否一致、上次同步是否成功。
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .data_sync import async_get_sync


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry
) -> dict[str, Any]:
    """返回该条目的诊断数据."""
    coordinator = (hass.data.get(DOMAIN) or {}).get(entry.entry_id)

    try:
        sync = await async_get_sync(hass)
        sync_info: dict[str, Any] = sync.status()
        sync_info["cache_keys"] = sync.cache_keys()
    except Exception as err:  # noqa: BLE001
        sync_info = {"error": f"{type(err).__name__}: {err}"}

    runtime: dict[str, Any] = {}
    if coordinator is not None:
        runtime = {
            "city": coordinator.city,
            "line": coordinator.line,
            "station": coordinator.station,
            "direction": coordinator.direction,
            "station_order": coordinator.station_order,
            "total_stops": coordinator._total_stops,  # noqa: SLF001 诊断用
            "is_loop": coordinator._is_loop,  # noqa: SLF001 诊断用
            "arrivals": coordinator.arrivals,
        }

    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "runtime": runtime,
        "data_sync": sync_info,
    }
