"""My Bus 设备触发器（0.9.13：按 HA 核心标准样式重做）.

在自动化编辑器中: 添加触发条件 → 设备 → My Bus 设备 → 选择触发器。

0.9.13 实测了 HA 核心与小米集成的标准做法（门窗传感器 / 温湿度计），对齐如下：

- **门窗传感器式**（状态触发器，选中即生效、无下拉框）：
  - ``arrival_arrived``  —— **公交已到站**（到站状态变为「已到站」）
  - ``arrival_arriving`` —— **公交即将到站**（到站状态变为「即将到站」）
- **温湿度计式**（阈值触发器，界面给「高于 / 低于」数字输入框，带单位后缀）：
  - ``remaining_stops`` —— 剩余站数（单位：站）
  - ``remaining_km``    —— 剩余公里数（单位：公里）
  - ``eta``             —— 预计到达（单位：分钟）
  - above/below 都不填 = 任意数值变化时触发；填了就只在满足阈值时触发；
    状态不是数字（如「暂无数据」）时不触发。
- **公交到站**（``bus_arrived``，事件实体）：v0.9.15 起删除，事件实体与
  事件平台一并移除，到站判断全部并入「到站状态」传感器（trigger.py 新体系）。
- 触发器带 ``entity_id``（实体注册表 ID，与小米/核心一致），卡片里能显示所属实体。
- **兼容**：0.9.8~0.9.12 的 4 个旧类型（``remaining_stops_changed`` /
  ``remaining_km_changed`` / ``eta_changed`` / ``arrival_status_changed``）
  仍可校验、仍可挂接（老自动化不报错），但不再出现在界面列表里。
  还在引用 ``bus_arriving`` / ``bus_arrived`` 的老自动化会在重载时报
  「trigger 配置无效」，删掉或改用「公交已到站 / 公交即将到站」即可。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
)
from .arrival_logic import (
    STATUS_ARRIVED,
    STATUS_ARRIVING,
    STATUS_NOT_ARRIVING,
)

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 触发器类型
# ---------------------------------------------------------------------------

# 门窗式：到站状态触发器（0.9.13）
TRIGGER_TYPE_STATUS_ARRIVED = "arrival_arrived"
TRIGGER_TYPE_STATUS_ARRIVING = "arrival_arriving"

# 温湿度式：阈值触发器（0.9.13）
TRIGGER_TYPE_STOPS = "remaining_stops"
TRIGGER_TYPE_KM = "remaining_km"
TRIGGER_TYPE_ETA = "eta"

# 旧类型（兼容 0.9.8~0.9.12 的自动化配置；界面不列）
TRIGGER_TYPE_LEGACY_STOPS = "remaining_stops_changed"
TRIGGER_TYPE_LEGACY_KM = "remaining_km_changed"
TRIGGER_TYPE_LEGACY_ETA = "eta_changed"
TRIGGER_TYPE_LEGACY_STATUS = "arrival_status_changed"

LEGACY_TRIGGER_TYPES = [
    TRIGGER_TYPE_LEGACY_STOPS,
    TRIGGER_TYPE_LEGACY_KM,
    TRIGGER_TYPE_LEGACY_ETA,
    TRIGGER_TYPE_LEGACY_STATUS,
]

# 界面列表（顺序 = 界面顺序；0.9.13 起只列标准样式；0.9.15 起无 bus_arrived）
UI_TRIGGER_TYPES = [
    TRIGGER_TYPE_STATUS_ARRIVED,
    TRIGGER_TYPE_STATUS_ARRIVING,
    TRIGGER_TYPE_STOPS,
    TRIGGER_TYPE_KM,
    TRIGGER_TYPE_ETA,
]

# schema 接受全部（UI + 旧类型，老自动化重载不报错）
TRIGGER_TYPES = [*UI_TRIGGER_TYPES, *LEGACY_TRIGGER_TYPES]

# 旧版「目标状态」下拉的过滤键（arrival_status_changed 专用，保留兼容）
STATUS_OPTIONS = [STATUS_NOT_ARRIVING, STATUS_ARRIVING, STATUS_ARRIVED]
STATUS_FILTER_KEY = "to"

# 阈值触发器 → 协调器里的实体键 + 单位后缀（capabilities 里给界面显示）
THRESHOLD_TRIGGERS: dict[str, tuple[str, str]] = {
    TRIGGER_TYPE_STOPS: ("remaining_stops", "站"),
    TRIGGER_TYPE_KM: ("remaining_km", "公里"),
    TRIGGER_TYPE_ETA: ("eta", "分钟"),
}

# 门窗式状态触发器 → 协调器实体键 + 目标状态
STATUS_TRIGGERS: dict[str, str] = {
    TRIGGER_TYPE_STATUS_ARRIVED: STATUS_ARRIVED,
    TRIGGER_TYPE_STATUS_ARRIVING: STATUS_ARRIVING,
}

# 传感器类触发器（新旧）→ 协调器里记录的实体键（sensor.py 按 translation_key 登记）
SENSOR_TRIGGER_ENTITIES: dict[str, str] = {
    TRIGGER_TYPE_LEGACY_STOPS: "remaining_stops",
    TRIGGER_TYPE_LEGACY_KM: "remaining_km",
    TRIGGER_TYPE_LEGACY_ETA: "eta",
    TRIGGER_TYPE_LEGACY_STATUS: "arrival_status",
    TRIGGER_TYPE_STOPS: "remaining_stops",
    TRIGGER_TYPE_KM: "remaining_km",
    TRIGGER_TYPE_ETA: "eta",
    TRIGGER_TYPE_STATUS_ARRIVED: "arrival_status",
    TRIGGER_TYPE_STATUS_ARRIVING: "arrival_status",
}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
        # 0.9.11 兼容：旧「到站状态变化」的目标状态值（老自动化里已保存的 to）
        vol.Optional(STATUS_FILTER_KEY): str,
        # 0.9.13：温湿度式阈值（界面「高于 / 低于」；description.suffix 给界面显示单位，
        # 与 HA 核心传感器触发器的做法一致）
        vol.Optional("above", description={"suffix": ""}): vol.Coerce(float),
        vol.Optional("below", description={"suffix": ""}): vol.Coerce(float),
        # 0.9.13：前端保存时会带上实体注册表 ID（与小米/核心一致），原样放行
        vol.Optional("entity_id"): str,
    }
)


# ---------------------------------------------------------------------------
# 公共小工具
# ---------------------------------------------------------------------------

def _coordinator_for(hass: HomeAssistant, config: dict[str, Any]):
    """按设备找到对应的协调器."""
    from homeassistant.helpers.device_registry import (
        async_get as async_get_device_registry,
    )

    device_id = config[CONF_DEVICE_ID]
    device: DeviceEntry | None = None
    try:
        device = async_get_device_registry(hass).async_get(device_id)
    except (AttributeError, KeyError):  # 极端情况下设备注册表还没起来
        device = None
    if device is None or not device.config_entries:
        raise HomeAssistantError(f"未找到 My Bus 设备: {device_id}")

    entry_id = next(iter(device.config_entries))
    coordinator = (hass.data.get(DOMAIN) or {}).get(entry_id)
    if coordinator is None:
        raise HomeAssistantError("My Bus 设备尚未就绪，请稍后重试")
    return coordinator


def _entity_registry_ids(hass: HomeAssistant, coordinator) -> dict[str, str]:
    """把协调器登记的实体 entity_id 换成实体注册表 ID（找不到就返回空表）.

    核心与小米的设备触发器都带 entity_id（注册表 ID），前端卡片靠它显示
    「属于哪个实体」。查不到（如极端时序）就不带，不影响功能。
    """
    try:
        from homeassistant.helpers.entity_registry import (
            async_get as async_get_entity_registry,
        )

        registry = async_get_entity_registry(hass)
        out: dict[str, str] = {}
        for key, entity_id in (coordinator.sensor_entity_ids or {}).items():
            entry = registry.async_get(entity_id)
            if entry is not None:
                out[key] = entry.id
        return out
    except (ImportError, AttributeError, Exception):  # 桩环境 / 注册表未就绪
        return {}


def _base_payload(
    config: dict[str, Any],
    trigger_info: dict[str, Any],
    coordinator,
    entity_id: str | None,
) -> dict[str, Any]:
    """触发时传给自动化的公共字段（可在自动化里用 trigger.xxx 取值）."""
    return {
        "platform": "device",
        "domain": DOMAIN,
        "device_id": config[CONF_DEVICE_ID],
        "type": config[CONF_TYPE],
        "entity_id": entity_id,
        "description": trigger_info.get("name", "My Bus"),
        "city": coordinator.city,
        "station": coordinator.station,
        "line": coordinator.line,
        "direction": "上行" if coordinator.direction == "1" else "下行",
    }


def _sensor_payload(
    config: dict[str, Any],
    trigger_info: dict[str, Any],
    coordinator,
    new_state,
    old_state,
) -> dict[str, Any]:
    """传感器状态变化触发器的完整数据."""
    payload = _base_payload(
        config, trigger_info, coordinator, new_state.entity_id
    )
    payload["state"] = new_state.state
    payload["previous_state"] = old_state.state if old_state is not None else None
    attributes = dict(new_state.attributes or {})
    # v0.9.27：传感器属性名改为中文，事件数据字段名保持不变（模板里可能已经在用）。
    payload.update(
        {
            "bus_number": attributes.get("车牌"),
            "remaining_stops": attributes.get("剩余站数"),
            "remaining_km": attributes.get("剩余公里数"),
            "distance_m": attributes.get("剩余距离米"),
            "eta_minutes": attributes.get("预计到达分钟"),
            "status": attributes.get("到站状态"),
        }
    )
    return payload


# ---------------------------------------------------------------------------
# 设备触发器接口
# ---------------------------------------------------------------------------

async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """列出设备可用触发器（界面顺序 = 这里的顺序；0.9.13 起只列标准样式）."""
    coordinator = None
    try:
        config = {CONF_PLATFORM: "device", CONF_DOMAIN: DOMAIN, CONF_DEVICE_ID: device_id}
        coordinator = _coordinator_for(hass, config)
    except Exception:  # noqa: BLE001  设备/协调器未就绪时照常列触发器（不带 entity_id）
        coordinator = None
    er_ids = _entity_registry_ids(hass, coordinator) if coordinator is not None else {}

    def _entity_ref(sensor_key: str) -> dict[str, Any]:
        ref = er_ids.get(sensor_key)
        return {"entity_id": ref} if ref else {}

    return [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: TRIGGER_TYPE_STATUS_ARRIVED,
            "metadata": {},
            **_entity_ref("arrival_status"),
        },
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: TRIGGER_TYPE_STATUS_ARRIVING,
            "metadata": {},
            **_entity_ref("arrival_status"),
        },
        *(
            {
                CONF_PLATFORM: "device",
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: ttype,
                "metadata": {},
                **_entity_ref(THRESHOLD_TRIGGERS[ttype][0]),
            }
            for ttype in (TRIGGER_TYPE_STOPS, TRIGGER_TYPE_KM, TRIGGER_TYPE_ETA)
        ),
    ]


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: dict[str, Any]
) -> dict[str, Any]:
    """触发器的界面附加字段（0.9.13 对齐 HA 核心传感器触发器）.

    - 阈值触发器：「高于 / 低于」两个可选数字输入框，带单位后缀
      （核心做法：``vol.Optional(..., description={"suffix": 单位})``）。
    - 门窗式状态触发器 / 公交到站：无附加字段。
    - 旧「到站状态变化」保留「目标状态」下拉（老自动化兼容，界面已不列）。
    """
    trigger_type = config.get(CONF_TYPE)
    if trigger_type in THRESHOLD_TRIGGERS:
        _, unit = THRESHOLD_TRIGGERS[trigger_type]
        return {
            "extra_fields": vol.Schema(
                {
                    vol.Optional("above", description={"suffix": unit}): vol.Coerce(float),
                    vol.Optional("below", description={"suffix": unit}): vol.Coerce(float),
                }
            )
        }
    if trigger_type == TRIGGER_TYPE_LEGACY_STATUS:
        from homeassistant.helpers.selector import (
            SelectSelector,
            SelectSelectorConfig,
        )

        return {
            "extra_fields": vol.Schema(
                {
                    vol.Optional(STATUS_FILTER_KEY): SelectSelector(
                        SelectSelectorConfig(options=STATUS_OPTIONS)
                    ),
                }
            )
        }
    return {}


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action,
    trigger_info,
) -> CALLBACK_TYPE:
    """把触发器绑定到对应实体的状态变化上."""
    coordinator = _coordinator_for(hass, config)
    trigger_type = config[CONF_TYPE]

    expected: str | None = STATUS_TRIGGERS.get(trigger_type)
    if expected is not None:
        return _attach_state(
            hass, config, action, trigger_info, coordinator,
            "arrival_status", _state_matcher(expected),
        )

    if trigger_type in THRESHOLD_TRIGGERS:
        sensor_key, _ = THRESHOLD_TRIGGERS[trigger_type]
        return _attach_state(
            hass, config, action, trigger_info, coordinator,
            sensor_key, _threshold_matcher(config),
        )

    # ---- 旧类型（0.9.8~0.9.12 的自动化仍能用）----
    sensor_key = SENSOR_TRIGGER_ENTITIES[trigger_type]
    to_filter = config.get(STATUS_FILTER_KEY)
    return _attach_state(
        hass, config, action, trigger_info, coordinator,
        sensor_key,
        (lambda s: str(s) == str(to_filter)) if to_filter else (lambda s: True),
    )


def _state_matcher(expected: str) -> Callable[[str], bool]:
    """门窗式：状态变为目标值时触发."""
    return lambda s: s == expected


def _threshold_matcher(config: dict[str, Any]) -> Callable[[str], bool]:
    """温湿度式：状态可解析为数字且满足 above/below 阈值时触发.

    - above = 高于、below = 低于（与 HA 核心传感器触发器同语义）
    - 两个都不填 = 任意数值变化；状态不是数字（如「暂无数据」）不触发
    """
    above = config.get("above")
    below = config.get("below")
    if above is not None:
        above = float(above)
    if below is not None:
        below = float(below)

    def _match(state: str) -> bool:
        if above is None and below is None:
            return True  # 与核心「数值」触发器一致：不设阈值 = 任意变化
        try:
            value = float(state)
        except (TypeError, ValueError):
            return False
        if above is not None and not value > above:
            return False
        if below is not None and not value < below:
            return False
        return True

    return _match


def _attach_state(
    hass: HomeAssistant,
    config: ConfigType,
    action,
    trigger_info,
    coordinator,
    sensor_key: str,
    matcher: Callable[[str], bool],
) -> CALLBACK_TYPE:
    """传感器状态触发器公共实现（0.9.13 起门窗式 / 温湿度式 / 旧类型共用）.

    只在**状态值**变化时触发（属性变化不算）；实体刚注册（old_state 为 None）
    不触发；再交给 matcher 判断这次新状态是否命中。
    """
    entity_id = (getattr(coordinator, "sensor_entity_ids", None) or {}).get(
        sensor_key
    )
    if not entity_id:
        raise HomeAssistantError(
            f"My Bus 传感器（{sensor_key}）尚未就绪，请稍后重试"
        )

    @callback
    def _async_on_state_change(event):
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None or old_state is None:
            return
        if new_state.state == old_state.state:
            return
        if not matcher(new_state.state):
            return
        hass.async_run_hass_job(
            action,
            _sensor_payload(config, trigger_info, coordinator, new_state, old_state),
        )

    return async_track_state_change_event(
        hass, [entity_id], _async_on_state_change
    )
