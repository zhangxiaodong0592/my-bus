"""My Bus 设备条件（0.9.20）。

在自动化编辑器中：添加条件 → 设备 → My Bus 设备 → 选择条件。

**为什么需要这个文件**：HA 核心的「条件」不像触发器那样能由集成任意扩展 ——
条件由**实体域**提供（``binary_sensor/device_condition.py``、
``sensor/device_condition.py``），集成要在「设备」页签里出现自己的条件，
只能自带 ``device_condition.py``（与自带 ``device_trigger.py`` 是同一套机制）。

**为什么我们的「到站状态」此前没有条件**：``sensor`` 域的条件有两个前提
（核心 ``sensor/device_condition.py``）::

    if not unit_of_measurement and not state_class:
        continue          # 无单位、无 state_class 直接跳过

「到站状态」是 ``enum`` 且无单位、无 ``state_class``，于是被核心跳过 ——
条件页签里一条都没有。本文件补上这一块。

仿小米门窗传感器（``binary_sensor`` 域）的「是打开 / 不是打开」样式，
这里给「到站状态」提供 **4 条精确状态条件**（不是取反，是精确等于）::

    is_arrived      —— 是「已到站」
    is_not_arriving —— 是「未到站」
    is_arriving     —— 是「即将到站」
    is_no_bus       —— 是「暂无车辆」

注意：这些是**条件**（此刻状态是什么），与触发器（状态**变成**什么）不同；
触发器由 ``trigger.py`` / ``triggers.yaml`` 提供，二者互不影响。
数值传感器（剩余站数 / 剩余公里数 / 预计到达）不在这里重复提供条件 ——
核心 ``sensor`` 域已按单位自动给出「高于 / 低于」条件（带单位后缀）。

0.9.19 的严格官方口径原样沿用：官方解析不出时状态就是「暂无车辆」，
所以「是『已到站』」这条条件不会误判通过。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_CONDITION_BASE_SCHEMA
from homeassistant.const import (
    CONF_CONDITION,
    CONF_ENTITY_ID,
    CONF_FOR,
    CONF_TYPE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.condition import ConditionCheckerType
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .arrival_logic import (
    STATUS_ARRIVED,
    STATUS_ARRIVING,
    STATUS_NOT_ARRIVING,
    STATUS_NO_BUS,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 条件类型（界面顺序 = CONDITION_TYPES 的顺序）
# ---------------------------------------------------------------------------

CONF_IS_ARRIVED = "is_arrived"
CONF_IS_NOT_ARRIVING = "is_not_arriving"
CONF_IS_ARRIVING = "is_arriving"
CONF_IS_NO_BUS = "is_no_bus"

# 条件类型 → 目标状态（精确匹配，不做取反）
CONDITION_STATES: dict[str, str] = {
    CONF_IS_ARRIVED: STATUS_ARRIVED,
    CONF_IS_NOT_ARRIVING: STATUS_NOT_ARRIVING,
    CONF_IS_ARRIVING: STATUS_ARRIVING,
    CONF_IS_NO_BUS: STATUS_NO_BUS,
}

CONDITION_TYPES = list(CONDITION_STATES)

# 只有「到站状态」实体提供条件（其余传感器由核心 sensor 域负责）
STATUS_TRANSLATION_KEY = "arrival_status"

CONDITION_SCHEMA = DEVICE_CONDITION_BASE_SCHEMA.extend(
    {
        # 前端保存的是实体注册表 ID，手写 YAML 时是 entity_id —— 两者都收
        vol.Required(CONF_ENTITY_ID): cv.string,
        vol.Required(CONF_TYPE): vol.In(CONDITION_TYPES),
        vol.Optional(CONF_FOR): cv.positive_time_period_dict,
    }
)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _as_seconds(value: Any) -> float | None:
    """把 ``for`` 的取值（timedelta / dict / 数字秒）换算成秒."""
    if value is None:
        return None
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        table = {"days": 86400, "hours": 3600, "minutes": 60, "seconds": 1, "milliseconds": 0.001}
        total = 0.0
        for key, factor in table.items():
            if key in value and value[key] is not None:
                total += float(value[key]) * factor
        return total
    return None


def _resolve_entity_id(hass: HomeAssistant, value: str) -> str:
    """把「实体注册表 ID」或「entity_id」统一解析成 entity_id.

    前端保存条件时 ``entity_id`` 字段里存的是**注册表 ID**（与核心、小米一致），
    手写 YAML 时才是 ``sensor.xxx``；两种都要支持，否则从界面保存的条件永远不成立。
    """
    if not isinstance(value, str):
        return str(value)
    if "." in value:  # 已经是 entity_id
        return value
    try:
        registry = er.async_get(hass)
        entry = None
        getter = getattr(registry, "async_get_entry", None)
        if getter is not None:
            entry = getter(value)
        if entry is None:  # 兜底：按 entity_id 再试一次
            entry = registry.async_get(value)
        entity_id = getattr(entry, "entity_id", None)
        if entity_id:
            return entity_id
    except Exception:  # noqa: BLE001  注册表未就绪 / 桩环境
        pass
    return value


def _is_status_entry(entry: Any) -> bool:
    """注册表条目是否是我们这的「到站状态」传感器."""
    translation_key = getattr(entry, "translation_key", None)
    if translation_key == STATUS_TRANSLATION_KEY:
        return True
    unique_id = getattr(entry, "unique_id", "") or ""
    return unique_id.endswith(STATUS_TRANSLATION_KEY)


# ---------------------------------------------------------------------------
# 设备条件接口
# ---------------------------------------------------------------------------

async def async_get_conditions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """列出设备可用条件（顺序 = CONDITION_TYPES 的顺序）.

    与核心一致：每条条件带 ``condition: device``、``domain``、``device_id``、
    ``entity_id``（**注册表 ID**）与 ``type``。
    """
    conditions: list[dict[str, str]] = []
    try:
        registry = er.async_get(hass)
        entries = er.async_entries_for_device(registry, device_id)
    except Exception:  # noqa: BLE001  桩环境 / 注册表未就绪
        return conditions

    for entry in entries:
        if getattr(entry, "platform", None) != DOMAIN:
            continue
        if not _is_status_entry(entry):
            continue
        conditions.extend(
            {
                CONF_CONDITION: "device",
                "device_id": device_id,
                CONF_ENTITY_ID: entry.id,
                CONF_TYPE: ctype,
                # 域标识：本条件由 my_bus 集成提供（前端/后端据此定位实现）
                "domain": DOMAIN,
            }
            for ctype in CONDITION_TYPES
        )
    return conditions


async def async_get_condition_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, Any]:
    """条件在界面上额外的字段：只给「持续」时长（与核心门窗传感器一致）."""
    return {
        "extra_fields": vol.Schema(
            {vol.Optional(CONF_FOR): cv.positive_time_period_dict}
        )
    }


@callback
def async_condition_from_config(
    hass: HomeAssistant, config: ConfigType
) -> ConditionCheckerType:
    """把条件配置编译成判定函数（与核心一样直接按状态比较）.

    - ``type`` 决定期望状态（精确匹配）；
    - ``for`` 有值时还要求「该状态已持续至少这么久」（用状态对象的 last_changed）；
    - 实体不存在 / 状态为 unknown 时一律判 False。
    """
    entity_id = _resolve_entity_id(hass, config[CONF_ENTITY_ID])
    expected = CONDITION_STATES[config[CONF_TYPE]]
    hold_seconds = _as_seconds(config.get(CONF_FOR))

    if hold_seconds is None:

        def _check(
            hass: HomeAssistant, variables: dict | None = None
        ) -> bool:  # noqa: ARG001
            state = hass.states.get(entity_id)
            return state is not None and state.state == expected

        return _check

    def _check_for(
        hass: HomeAssistant, variables: dict | None = None
    ) -> bool:  # noqa: ARG001
        state = hass.states.get(entity_id)
        if state is None or state.state != expected:
            return False
        try:
            elapsed = (dt_util.utcnow() - state.last_changed).total_seconds()
        except (AttributeError, TypeError):
            return True  # 拿不到时间就只比较状态
        return elapsed >= hold_seconds

    return _check_for
