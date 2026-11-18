"""My Bus 传感器实体：数据同步状态 + 设备页实时到站信息.

- :class:`XmBusDataSyncSensor`：上次与掌上公交完成同步的时间。
- :class:`XmBusRemainingStopsSensor` / :class:`XmBusRemainingKmSensor` /
  :class:`XmBusEtaSensor` / :class:`XmBusPlateSensor` /
  :class:`XmBusArrivalStatusSensor`：最近一辆车到监控站台
  **还剩几站**、**还剩几公里**、**约几分钟**、**是哪辆车（车牌）**、
  当前处于「未到站 / 已到站」哪个状态 —— 这几个会直接显示在设备页上。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .arrival_logic import (
    STATUS_ARRIVED,
    STATUS_ARRIVING,
    STATUS_NOT_ARRIVING,
    STATUS_NO_BUS,
    distance_km,
    official_arrival_status,
    official_stops,
)
from .const import DOMAIN
from .coordinator import XmBusCoordinator


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator: XmBusCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        return
    async_add_entities([
        XmBusDataSyncSensor(coordinator, entry),
        XmBusRemainingStopsSensor(coordinator, entry),
        XmBusRemainingKmSensor(coordinator, entry),
        XmBusEtaSensor(coordinator, entry),
        # v0.9.28：车牌单独成实体（原本只是「到站状态」的一个属性）
        XmBusPlateSensor(coordinator, entry),
        XmBusArrivalStatusSensor(coordinator, entry),
    ])


class XmBusDataSyncSensor(CoordinatorEntity[XmBusCoordinator], SensorEntity):
    """数据同步传感器.

    v0.9.15 起不再标记为诊断类：新触发器体系下诊断实体会被
    「添加触发条件 → 按目标」的实体树隐藏，「数据同步完成」触发器
    挂在本实体上（device_class: timestamp），必须可见才能选。
    """

    _attr_has_entity_name = True
    _attr_translation_key = "data_sync"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:cloud-sync-outline"

    def __init__(self, coordinator: XmBusCoordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_data_sync"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.device_name,
            manufacturer="My Bus",
            model="公交到站监控",
        )

    @property
    def _status(self) -> dict:
        return self.coordinator.sync_status or {}

    @property
    def native_value(self) -> datetime | None:
        """上次同步完成时间（UTC，HA 会按本地时区显示）."""
        ts = self._status.get("last_sync_ts")
        if not ts:
            return None
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            return None

    @property
    def extra_state_attributes(self) -> dict:
        status = self._status
        # v0.9.27：属性名直接用中文。HA 前端「状态已变化」触发器的「属性（可选）」
        # 下拉框显示的就是属性键本身（把下划线换成空格、首字母大写），没有任何
        # 翻译层，所以想让用户看到中文，只能把键名改成中文。
        return {
            "是否启用": status.get("enabled"),
            "刷新间隔小时": status.get("interval_hours"),
            "上次同步": status.get("last_sync"),
            "耗时秒": status.get("duration"),
            "城市数": status.get("cities"),
            "线路数": status.get("lines"),
            "站台数": status.get("stations"),
            "失败次数": status.get("failures"),
            "最后错误": status.get("last_error"),
            "问题": status.get("issue_texts"),
            # v0.9.24：距上次同步的小时数。状态本身是时间戳（float 转不了数字），
            # 「数据同步」条件靠这个数字属性做高于/低于/区间比较；每轮刷新重算。
            "距上次同步小时数": self._sync_age_hours(),
        }

    def _sync_age_hours(self) -> float | None:
        """距上次同步完成的小时数（未同步过则为 None，条件自动不成立）."""
        ts = self._status.get("last_sync_ts")
        if not ts:
            return None
        try:
            return round(max(0.0, time.time() - float(ts)) / 3600, 2)
        except (TypeError, ValueError, OSError, OverflowError):
            return None


class _XmBusLiveSensor(CoordinatorEntity[XmBusCoordinator], SensorEntity):
    """实时到站传感器公共部分：都只看离监控站台最近的一辆车."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: XmBusCoordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.device_name,
            manufacturer="My Bus",
            model="公交到站监控",
        )

    @property
    def _bus(self) -> dict | None:
        """离监控站台最近的一辆车（当前没有在途车辆时为 None）."""
        return self.coordinator.nearest_bus()

    def _internal_remaining(self, bus: dict | None) -> int | None:
        """最近一辆车的内部几何差（没有车时为 None）.

        仅用于终点站「已到站 / 即将到站」误显防护与排查属性，不再参与展示。
        """
        if bus is None or bus.get("remaining") is None:
            return None
        remaining = int(bus["remaining"])
        return remaining if remaining >= 0 else None

    def _official_text(self) -> str:
        """CMD115 官方到站预览文案（本轮没拉到时为空串）."""
        preview = getattr(self.coordinator, "preview", None) or {}
        return (preview.get("neartext") or "").strip()

    def _stops_display(self, bus: dict | None) -> int | None:
        """剩余站数的**展示值**（v0.9.19 起严格官方，推算口径已删）.

        v0.9.18 是「官方优先、推算兜底」，用户要求**严格与官方一致**，
        v0.9.19 起直接解析 CMD115 官方文案（与 App 完全同源，
        :func:`arrival_logic.official_stops`），解析不出（非运营时间 /
        官方缺失 / 未知文案）就显示「未知」——宁缺勿错，不再用本地推算顶上。
        内部几何差仅用于终点站「已到站」误显防护与排查属性
        ``internal_remaining``。CMD104 一辆车都没给但官方是「N站」时照常显示。
        """
        internal = self._internal_remaining(bus)
        return official_stops(self._official_text(), internal)

    def _status_display(self, bus: dict | None) -> str:
        """到站状态的**展示值**（v0.9.19 起严格官方，推算口径已删）.

        官方「已到站 / 即将到站」原文采信（带终点站误显防护）、
        「N站」→ 未到站；官方解析不出（缺失 / 非运营时间 / 未知文案）→
        「暂无车辆」。与「剩余站数」同一套数据源，两个实体永远自洽。
        """
        internal = self._internal_remaining(bus)
        official = official_arrival_status(self._official_text(), internal)
        return official if official is not None else STATUS_NO_BUS

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # 把自己的 entity_id 登记到协调器，供 device_trigger 的
        # 「状态变化」触发器监听（v0.9.8）
        if self._attr_translation_key:
            self.coordinator.sensor_entity_ids[self._attr_translation_key] = (
                self.entity_id
            )

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {
            "城市": self.coordinator.city,
            "线路": self.coordinator.line,
            "站台": self.coordinator.station,
            "方向": "上行" if self.coordinator.direction == "1" else "下行",
        }
        bus = self._bus
        if bus is None:
            return attrs
        minutes = self._official_minutes()
        attrs.update(
            {
                "车牌": bus.get("plate"),
                "当前站": bus.get("current_stop"),
                # 与「剩余站数」实体同口径（严格官方，v0.9.19）；内部几何差单列，便于排查
                "剩余站数": self._stops_display(bus),
                "内部剩余站数": bus.get("remaining"),
                "剩余距离米": bus.get("distance_m"),
                "剩余公里数": distance_km(bus.get("distance_m")),
                "预计到达分钟": minutes,
                "预计到达来源": "官方" if minutes is not None else None,
                "官方原文": (getattr(self.coordinator, "preview", None) or {}).get("neartext") or None,
                "官方剩余距离": (getattr(self.coordinator, "preview", None) or {}).get("neardis") or None,
                "到站状态": self._status_display(bus),
            }
        )
        return attrs

    def _official_minutes(self) -> int | None:
        """官方预计到达分钟数（CMD115「N分钟」或「已到站」→ 0）；没有官方数据时为 None."""
        preview = getattr(self.coordinator, "preview", None) or {}
        minutes = preview.get("minutes")
        return int(minutes) if minutes is not None else None


class XmBusRemainingStopsSensor(_XmBusLiveSensor):
    """最近一辆车到监控站台还剩几站（**严格官方口径**，v0.9.19）.

    v0.9.17 用推算把内部几何差换算成 App 口径，v0.9.18 改「官方优先、推算
    兜底」，用户要求**严格与官方一致**——v0.9.19 起推算口径删除：直接解析
    CMD115 官方 neartext（「N站 / 即将到站 / 已到站」，与 App 完全同源），
    解析不出就显示「未知」，宁缺勿错。到站状态传感器同口径。
    「预计到达」传感器不受影响（一直是官方数据）。

    v0.9.16 起声明自定义 device_class（``stop_count``）：新触发器体系
    「添加触发条件 → 按目标」按 device_class 精确挂载触发器，让
    「剩余站数变化」只出现在本实体下。HA 对未知 device_class 按普通
    数值传感器处理（校验时视为 None），单位与显示不受影响。
    """

    _attr_translation_key = "remaining_stops"
    _attr_icon = "mdi:map-marker-distance"
    _attr_native_unit_of_measurement = "站"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = "stop_count"

    def __init__(self, coordinator: XmBusCoordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_remaining_stops"

    @property
    def native_value(self) -> int | None:
        return self._stops_display(self._bus)


class XmBusRemainingKmSensor(_XmBusLiveSensor):
    """最近一辆车到监控站台还剩几公里（保留 1 位小数）.

    v0.9.16 起声明自定义 device_class（``remaining_distance``），
    让「剩余公里数变化」触发器只挂在本实体上（原理同上）。
    """

    _attr_translation_key = "remaining_km"
    _attr_icon = "mdi:map-marker-path"
    _attr_native_unit_of_measurement = "公里"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_device_class = "remaining_distance"

    def __init__(self, coordinator: XmBusCoordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_remaining_km"

    @property
    def native_value(self) -> float | None:
        bus = self._bus
        return None if bus is None else distance_km(bus.get("distance_m"))


class XmBusEtaSensor(_XmBusLiveSensor):
    """最近一辆车的预计到达时间（分钟）.

    v0.9.3 起只显示**官方数据**，不再本地推算 —— 尽量与掌上公交一致。
    v0.9.7 起官方没给分钟数时直接显示官方原文，让传感器永远有状态：
    「预计发车:11:00」（车还没发出）→「N站」→「等待发车」/「非运营时间」，
    只有官方什么都没给才显示「暂无数据」。
    v0.9.16 起声明自定义 device_class（``eta``），让「预计到达变化」
    触发器只挂在本实体上（原理同上）。HA 把未知 device_class 按普通
    传感器处理，字符串状态（如「暂无数据」）不会触发数值校验。
    """

    _attr_translation_key = "eta"
    _attr_icon = "mdi:timer-outline"
    _attr_device_class = "eta"
    # 不设 state_class：状态可能是数字（分钟）也可能是官方文案字符串
    # 单位只在状态是数字时挂「分钟」（字符串状态挂单位没有意义，读屏也乱）

    @property
    def native_unit_of_measurement(self) -> str | None:
        return "分钟" if isinstance(self.native_value, int) else None

    def __init__(self, coordinator: XmBusCoordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_eta"

    @property
    def native_value(self) -> int | str:
        preview = getattr(self.coordinator, "preview", None) or {}
        minutes = self._official_minutes()
        if minutes is not None:
            return minutes
        # 官方没给分钟数 → 依次退回官方原文（全是掌上公交自己给的字段）
        neardis = (preview.get("neardis") or "").strip()
        if neardis:
            return neardis
        neartext = (preview.get("neartext") or "").strip()
        if neartext:
            return neartext
        return "暂无数据"


class XmBusPlateSensor(_XmBusLiveSensor):
    """最近一辆车的车牌（文本实体，没车时显示「未知」）.

    v0.9.28 起单独成实体。此前车牌只是「到站状态」的一个属性，自动化里
    要用 ``state_attr(实体, '车牌')`` 才取得到，触发器也只能靠「状态已变化
    + 属性」这种绕路的方式盯。单独成实体后：

    - 触发器、条件可以直接选这个实体（配合集成自带的「车牌变化 / 换车」）；
    - 车牌值进入历史记录，能翻「今天来过哪几辆车」；
    - 播报模板里直接写车牌名，不用再套 ``state_attr``。

    没有对应的标准 device_class，故声明自定义 ``license_plate``，
    让触发器/条件按 device_class 一对一挂载（与三个数值传感器同一套做法）。
    """

    _attr_translation_key = "plate"
    _attr_icon = "mdi:license"
    _attr_device_class = "license_plate"

    def __init__(self, coordinator: XmBusCoordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_plate"

    @property
    def native_value(self) -> str | None:
        """车牌号；没有在途车辆时为 None（界面显示「未知」）."""
        bus = self._bus
        if bus is None:
            return None
        plate = bus.get("plate")
        return str(plate) if plate else None


class XmBusArrivalStatusSensor(_XmBusLiveSensor):
    """最近一辆车相对监控站台的状态（未到站 / 即将到站 / 已到站 / 暂无车辆）.

    v0.9.18 起采信 CMD115 官方文案，v0.9.19 起**严格官方**：内部
    statusType 推算删除——「已到站 / 即将到站」原文照搬、「N站」→ 未到站
    （带终点站误显防护），官方缺失或解析不出 → 「暂无车辆」。
    与「剩余站数」传感器同一套数据源，两个实体永远自洽。
    v0.9.15 起声明 ``device_class: enum`` + ``options``：一是 HA 对
    枚举传感器的规范用法，二是新触发器体系里「公交已到站 / 公交即将到站」
    触发器按 device_class: enum 精确挂到本实体上。
    """

    _attr_translation_key = "arrival_status"
    _attr_icon = "mdi:bus-clock"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = (
        STATUS_NOT_ARRIVING,
        STATUS_ARRIVING,
        STATUS_ARRIVED,
        STATUS_NO_BUS,
    )

    def __init__(self, coordinator: XmBusCoordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_arrival_status"

    @property
    def native_value(self) -> str:
        return self._status_display(self._bus)
