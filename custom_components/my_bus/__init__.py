"""My Bus：以公交线路到站作为 Home Assistant 自动化触发条件."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_CITY, DATA_SYNC_KEY, DEFAULT_CITY, DOMAIN
from .coordinator import XmBusCoordinator
from .data_sync import async_get_sync, client_for_city
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


def _async_remove_orphan_event_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """清理 v0.9.15 之前注册的事件实体（如「公交到站」）.

    v0.9.15 删除了 event 平台，但 HA 实体注册表不会自动删除旧记录，
    设备页会一直显示「集成 my_bus 不再提供此实体」。这里在启动时把
    本条目名下的事件实体从注册表移除，让设备页只显示 5 个传感器。
    """
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.domain == "event":
            _LOGGER.info(
                "清理不再提供的事件实体 %s（v0.9.15 起到站判断并入「到站状态」传感器）",
                reg_entry.entity_id,
            )
            registry.async_remove(reg_entry.entity_id)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """注册域级服务（AI/语音可调用）."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    # 清理旧版本残留的事件实体（公交到站），详见 _async_remove_orphan_event_entities
    _async_remove_orphan_event_entities(hass, entry)
    city = str(entry.data.get(CONF_CITY) or DEFAULT_CITY).strip() or DEFAULT_CITY
    # 复用配置流里已建立的同城市客户端，避免重复创建
    client = client_for_city(hass, city)

    # 数据同步层：把城市 / 线路 / 站台等结构数据与掌上公交保持一致的本地缓存
    sync = await async_get_sync(hass)
    await sync.async_start()

    coordinator = XmBusCoordinator(hass, entry, client, sync)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """把旧条目（v1，仅厦门）升级到 v2（带城市字段）."""
    if entry.version > 2:
        # 条目来自更新的版本，当前代码无法安全降级
        return False
    if entry.version < 2:
        city = str(entry.data.get(CONF_CITY) or DEFAULT_CITY).strip() or DEFAULT_CITY
        _LOGGER.info("升级 My Bus 条目 %s 到 v2（城市=%s）", entry.entry_id, city)
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_CITY: city}, version=2
        )
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        # 最后一个监控被删除后，停掉定时同步并把缓存落盘
        if not _has_loaded_entries(hass):
            sync = hass.data[DOMAIN].get(DATA_SYNC_KEY)
            if sync is not None:
                await sync.async_stop()
    return unload_ok


def _has_loaded_entries(hass: HomeAssistant) -> bool:
    """是否还有已加载的监控（决定要不要保留定时同步任务）."""
    data = hass.data.get(DOMAIN) or {}
    return any(isinstance(value, XmBusCoordinator) for value in data.values())
