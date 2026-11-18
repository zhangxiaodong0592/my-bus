"""最小 Home Assistant 桩环境，用于脱离 HA 运行 config_flow / data_sync 排查异常.

仅供本地调试，不会被打包进集成。
"""

from __future__ import annotations

import asyncio
import sys
import types


class _SelectorStub:
    def __init__(self, config=None, **kwargs):
        self.config = config

    def __call__(self, value):
        return value


def _mod(name: str) -> types.ModuleType:
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


def _class(name: str, **attrs):
    return type(name, (), attrs)


def _bump_timers(hass, action, interval):
    """记录定时器，便于测试手动触发."""
    timers = getattr(hass, "_timers", None)
    if timers is None:
        timers = hass._timers = []
    entry = {"action": action, "interval": interval, "active": True}
    timers.append(entry)

    def _unsub():
        entry["active"] = False
        if entry in timers:
            timers.remove(entry)

    return _unsub


class _StoreStub:
    """内存版 Store（同一 hass 上模拟「重启后仍能读到」）."""

    def __init__(self, hass, version, key, **kwargs):
        self.hass = hass
        self.version = version
        self.key = key
        self.saves = 0
        self.delayed = 0
        if not hasattr(hass, "_store_data"):
            hass._store_data = {}

    async def async_load(self):
        return self.hass._store_data.get(self.key)

    async def async_save(self, data):
        self.hass._store_data[self.key] = data
        self.saves += 1

    def async_delay_save(self, data_func, delay=0):
        # 桩环境立即落盘，方便断言
        self.hass._store_data[self.key] = data_func()
        self.delayed += 1

    async def async_remove(self):
        self.hass._store_data.pop(self.key, None)


class _DataUpdateCoordinator:
    def __init__(self, hass, logger, *, name=None, update_interval=None, **kwargs):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.config_entry = kwargs.get("config_entry")
        self.data = None
        self.last_update_success = True

    @classmethod
    def __class_getitem__(cls, item):
        return cls

    async def async_config_entry_first_refresh(self):
        self.data = await self._async_update_data()

    async def async_request_refresh(self):
        """真实 HA 里带 10 秒去抖；桩里直接刷新一次（按钮 / 条件用）."""
        self.data = await self._async_update_data()
        return None

    async def _async_update_data(self):  # pragma: no cover - 子类覆写
        return {}


class _CoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    @classmethod
    def __class_getitem__(cls, item):
        return cls

    async def async_added_to_hass(self):
        return None

    def async_write_ha_state(self):
        return None


def install() -> None:
    # homeassistant
    ha = _mod("homeassistant")

    core = _mod("homeassistant.core")

    def callback(func):
        return func

    core.callback = callback
    core.CALLBACK_TYPE = object

    class HomeAssistant:  # noqa: D401
        def __init__(self):
            self.data = {}

    core.HomeAssistant = HomeAssistant

    class ServiceCall:
        def __init__(self, data=None):
            self.data = dict(data or {})

    class SupportsResponse:
        ONLY = "only"
        OPTIONAL = "optional"

    core.ServiceCall = ServiceCall
    core.ServiceResponse = dict
    core.SupportsResponse = SupportsResponse

    # homeassistant.const
    const = _mod("homeassistant.const")

    class Platform:
        EVENT = "event"
        SENSOR = "sensor"
        BUTTON = "button"

    class EntityCategory:
        DIAGNOSTIC = "diagnostic"

    const.Platform = Platform
    const.EntityCategory = EntityCategory
    # v0.9.28：车牌触发器要用的两个状态常量（真实 HA 里就是这两个字符串）
    const.STATE_UNAVAILABLE = "unavailable"
    const.STATE_UNKNOWN = "unknown"

    # CONF_xxx / ATTR_xxx 这类常量按需生成，省得逐条列举。
    # 真实 HA 里 CONF_TYPE = "type"、CONF_DEVICE_ID = "device_id"、ATTR_ENTITY_ID = "entity_id"，
    # 也就是「去掉前缀再小写」，所以这里照此还原，别写成 conf_type（会认不出配置里的键）。
    def _const_getattr(name: str):
        for prefix in ("CONF_", "ATTR_"):
            if name.startswith(prefix):
                return name[len(prefix):].lower()
        raise AttributeError(name)

    const.__getattr__ = _const_getattr

    # homeassistant.helpers.typing
    ha_typing = _mod("homeassistant.helpers.typing")
    ha_typing.ConfigType = dict
    ha_typing.TriggerActionType = object
    ha_typing.TriggerInfo = dict

    # homeassistant.helpers.condition（v0.9.21 新版条件注册表）
    ha_cond = _mod("homeassistant.helpers.condition")
    ha_cond.ConditionCheckerType = object
    ha_cond.ConditionCheckParams = dict

    class Condition:
        """新版条件基类（简化桩）：核心要求子类实现 _async_check."""

        def __init__(self, hass=None, config=None, **kwargs):
            self._hass = hass
            self._config = config or {}

        def _async_check(self, **kwargs):
            return False

    def make_entity_state_condition(
        domain_specs, state, primary_entities_only=True, **kwargs
    ):
        """实体状态条件工厂（简化桩）：所有目标实体状态都等于 state 才通过."""

        class CustomCondition(Condition):
            _domain_specs = dict(domain_specs)
            _state = state
            _primary_entities_only = primary_entities_only

            def _async_check(self, **kwargs):
                entity_ids = self._config.get("entity_id") or []
                if isinstance(entity_ids, str):
                    entity_ids = [entity_ids]
                observed = [
                    st
                    for st in (
                        self._hass.states.get(entity_id) for entity_id in entity_ids
                    )
                    if st is not None
                ]
                if not observed:
                    return False
                return all(getattr(st, "state", None) == state for st in observed)

        return CustomCondition

    ha_cond.Condition = Condition
    ha_cond.make_entity_state_condition = make_entity_state_condition

    # v0.9.24：数值条件工厂（真实签名 make_entity_numerical_condition(
    #   domain_specs, valid_unit=UNDEFINED, *, primary_entities_only=True)）
    class _UndefUnit:
        def __repr__(self):
            return "UNDEFINED"

    UNDEFINED_UNIT = _UndefUnit()

    def make_entity_numerical_condition(
        domain_specs, valid_unit=UNDEFINED_UNIT, *, primary_entities_only=True
    ):
        """实体数值条件工厂（简化桩）：只记录规格，判定由回归自行断言."""

        class CustomCondition(Condition):
            _domain_specs = dict(domain_specs)
            _valid_unit = valid_unit
            _primary_entities_only = primary_entities_only

            def _async_check(self, **kwargs):
                return False

        return CustomCondition

    ha_cond.UNDEFINED_UNIT = UNDEFINED_UNIT
    ha_cond.make_entity_numerical_condition = make_entity_numerical_condition

    # v0.9.28：车牌条件要用的实体条件基类 + 状态条件 schema
    class _SchemaStub:
        """probatio.Schema 的桩：只保存结构，不真的校验（.extend 返回新对象）."""

        def __init__(self, schema=None):
            self.schema = dict(schema or {})

        def __call__(self, value):
            return value

        def extend(self, extra):
            merged = dict(self.schema)
            merged.update(dict(extra))
            return _SchemaStub(merged)

    class EntityConditionBase(Condition):
        """实体条件基类（桩）：区分「已排除状态」与「命中状态」."""

        _domain_specs = {}
        _schema = None
        _excluded_states = frozenset({"unavailable", "unknown"})
        _primary_entities_only = True

        def is_valid_state(self, entity_state):
            return False

        def check_state(self, entity_state):
            """桩内的「_async_check 单实体版」：排除状态一律不成立."""
            if getattr(entity_state, "state", None) in self._excluded_states:
                return False
            return self.is_valid_state(entity_state)

    ha_cond.EntityConditionBase = EntityConditionBase
    ha_cond.ENTITY_STATE_CONDITION_SCHEMA_ANY_ALL = _SchemaStub(
        {"target": "required", "options": "required"}
    )

    # homeassistant.util / homeassistant.util.dt（v0.9.20 设备条件「持续」判定用）
    _mod("homeassistant.util")
    util_dt = _mod("homeassistant.util.dt")
    import datetime as _datetime

    util_dt.utcnow = lambda: _datetime.datetime.now(_datetime.timezone.utc)

    # homeassistant.components.device_automation（设备触发器 / 条件的基 schema）
    import voluptuous as _vol

    da = _mod("homeassistant.components.device_automation")
    _device_base = _vol.Schema(
        {
            _vol.Required("platform"): "device",
            _vol.Required("domain"): str,
            _vol.Required("device_id"): str,
        },
        extra=_vol.ALLOW_EXTRA,
    )
    da.DEVICE_TRIGGER_BASE_SCHEMA = _device_base
    da.DEVICE_CONDITION_BASE_SCHEMA = _device_base

    # homeassistant.data_entry_flow
    def_flow = _mod("homeassistant.data_entry_flow")
    def_flow.FlowResult = dict

    # homeassistant.helpers
    _mod("homeassistant.helpers")

    # homeassistant.helpers.storage
    storage = _mod("homeassistant.helpers.storage")
    storage.Store = _StoreStub

    # homeassistant.helpers.event
    event = _mod("homeassistant.helpers.event")
    event.async_track_time_interval = _bump_timers

    def _track_state_change_event(hass, entity_ids, action):
        """桩：只返回一个注销函数，不做真的状态订阅。"""
        return lambda: None

    event.async_track_state_change_event = _track_state_change_event

    # homeassistant.helpers.device_registry
    dev_reg = _mod("homeassistant.helpers.device_registry")
    dev_reg.DeviceInfo = dict

    class DeviceEntry:
        def __init__(self, config_entries=()):
            self.config_entries = set(config_entries)

    dev_reg.DeviceEntry = DeviceEntry
    dev_reg.async_get = lambda hass: getattr(hass, "_device_registry", None)

    # homeassistant.helpers.entity_platform
    ent_plat = _mod("homeassistant.helpers.entity_platform")
    ent_plat.AddEntitiesCallback = object

    # homeassistant.helpers.entity_registry（v0.9.16：清理残留事件实体用）
    er_reg = _mod("homeassistant.helpers.entity_registry")

    class EntityRegistry:
        """内存版实体注册表：entries 为注册条目列表，removed 记录删除."""

        def __init__(self):
            self.entries = []
            self.removed = []

        def async_remove(self, entity_id):
            self.removed.append(entity_id)
            self.entries = [
                e for e in self.entries if getattr(e, "entity_id", None) != entity_id
            ]

        def async_get(self, entity_id):
            for e in self.entries:
                if getattr(e, "entity_id", None) == entity_id:
                    return e
            return None

        def async_get_entry(self, entry_id):
            """按注册表 ID 查条目（v0.9.20：设备条件里的 entity_id 是注册表 ID）."""
            for e in self.entries:
                if getattr(e, "id", None) == entry_id:
                    return e
            return None

    def async_entries_for_config_entry(registry, entry_id):
        return [
            e
            for e in registry.entries
            if getattr(e, "config_entry_id", None) == entry_id
        ]

    def async_entries_for_device(registry, device_id, *args, **kwargs):
        return [
            e
            for e in registry.entries
            if getattr(e, "device_id", None) == device_id
        ]

    er_reg.EntityRegistry = EntityRegistry
    er_reg.async_entries_for_config_entry = async_entries_for_config_entry
    er_reg.async_entries_for_device = async_entries_for_device
    er_reg.async_get = lambda hass: getattr(hass, "_entity_registry", None)

    # homeassistant.helpers.update_coordinator
    uc = _mod("homeassistant.helpers.update_coordinator")
    uc.DataUpdateCoordinator = _DataUpdateCoordinator
    uc.CoordinatorEntity = _CoordinatorEntity

    class UpdateFailed(Exception):
        pass

    uc.UpdateFailed = UpdateFailed

    # homeassistant.components.sensor
    _mod("homeassistant.components")
    sensor = _mod("homeassistant.components.sensor")
    sensor.DOMAIN = "sensor"

    class SensorEntity:
        def async_write_ha_state(self):
            return None

    class SensorDeviceClass:
        TIMESTAMP = "timestamp"
        ENUM = "enum"

    class SensorStateClass:
        MEASUREMENT = "measurement"
        TOTAL = "total"

    sensor.SensorEntity = SensorEntity
    sensor.SensorDeviceClass = SensorDeviceClass
    sensor.SensorStateClass = SensorStateClass

    # homeassistant.components.event（事件实体：测试里要能导入 event.py）
    event_comp = _mod("homeassistant.components.event")
    event_comp.DOMAIN = "event"

    class EventEntity:
        _attr_event_types = None

        async def _trigger_event(self, event_type, data=None):
            return None

        def async_write_ha_state(self):
            return None

    event_comp.EventEntity = EventEntity

    # homeassistant.components.button（按钮实体：设备页「控制」区的同步按钮）
    button_comp = _mod("homeassistant.components.button")

    class ButtonEntity:
        async def async_press(self):
            return None

        def async_write_ha_state(self):
            return None

    button_comp.ButtonEntity = ButtonEntity

    # homeassistant.helpers.config_validation
    cv = _mod("homeassistant.helpers.config_validation")
    cv.string = str
    # v0.9.20：设备条件的「持续」字段（真实实现把 dict 转 timedelta，桩里原样放行）
    cv.positive_time_period_dict = dict
    cv.time_period = lambda value: value
    # v0.9.28：车牌条件 schema 用到的时长校验
    cv.positive_time_period = lambda value: value

    # probatio（v0.9.28 车牌条件的 schema 构造用；桩只做结构标记）
    probatio_mod = _mod("probatio")

    class _FieldMark:
        def __init__(self, key=None, default=None, **kwargs):
            self.key = key
            self.default = default

    probatio_mod.Schema = _SchemaStub
    probatio_mod.Required = lambda key, **kwargs: _FieldMark(key, **kwargs)
    probatio_mod.Optional = lambda key, **kwargs: _FieldMark(key, **kwargs)
    probatio_mod.In = lambda options: options

    # homeassistant.helpers.automation（新版触发器体系的 DomainSpec）
    automation = _mod("homeassistant.helpers.automation")

    class DomainSpec:
        """实体域过滤规格（device_class / value_source 供数值触发器用）."""

        def __init__(self, device_class=None, value_source=None):
            self.device_class = device_class
            self.value_source = value_source

    automation.DomainSpec = DomainSpec

    # homeassistant.helpers.trigger（新版触发器体系，2026.10+）
    trig = _mod("homeassistant.helpers.trigger")

    class _Undefined:
        def __repr__(self):
            return "UNDEFINED"

    UNDEFINED = _Undefined()

    class TriggerConfig:
        """新版触发器配置（key + target + options）."""

        def __init__(self, key, target=None, options=None):
            self.key = key
            self.target = target
            self.options = options

    class Trigger:
        """触发器基类（对应 helpers.trigger.models.Trigger）."""

        def __init__(self, hass, config):
            self._hass = hass
            self._config = config

        @classmethod
        def async_validate_complete_config(cls, hass, complete_config):
            """桩：原样返回（真实实现拆 options/target 后交给子类校验）."""
            return complete_config

        async def async_attach_action(self, action, payload_builder, **kw):
            """桩：不做真实订阅."""
            return lambda: None

    class EntityTriggerBase(Trigger):
        """实体状态触发器基类（语义与真实实现一致，供行为测试用）."""

        _domain_specs = {}
        _excluded_states = frozenset({"unavailable", "unknown"})
        _excluded_from_states = None
        _schema = None

        @classmethod
        def async_validate_config(cls, hass, config):
            if cls._schema is not None:
                return cls._schema(config)
            return config

        def __init__(self, hass, config):
            super().__init__(hass, config)
            self._options = dict(config.options or {})
            self._target = config.target
            if self._excluded_from_states is None:
                self._excluded_from_states = self._excluded_states

        def _get_tracked_value(self, state):
            return state.state

        def is_valid_transition(self, from_state, to_state):
            return from_state.state != to_state.state

        def is_valid_state(self, state, report_not_triggered=None):
            return True

        def is_valid_change(self, from_state, to_state):
            """完整判定：等价真实基类 state_change_listener 的过滤顺序."""
            if from_state is None or to_state is None:
                return False
            if to_state.state in self._excluded_states:
                return False
            if not self.is_valid_state(to_state):
                return False
            if from_state.state in self._excluded_from_states:
                return False
            return self.is_valid_transition(from_state, to_state)

        async def async_attach_runner(self, run_action, did_not_trigger=None):
            return lambda: None

    class StatelessEntityTriggerBase(EntityTriggerBase):
        """无状态实体（事件/按钮）触发器基类."""

    class EntityTargetStateTriggerBase(EntityTriggerBase):
        """目标状态触发器基类."""

        _to_states = set()

        def is_valid_transition(self, from_state, to_state):
            from_value = self._get_tracked_value(from_state)
            return (
                from_value != self._get_tracked_value(to_state)
                and from_value not in self._to_states
            )

        def is_valid_state(self, state, report_not_triggered=None):
            return self._get_tracked_value(state) in self._to_states

    def _threshold_number(entry):
        """阈值条目取数（真实 HA：{"number": float}）。"""
        if entry is None:
            return None
        try:
            return float(entry["number"])
        except (TypeError, ValueError, KeyError):
            return None

    class EntityNumericalStateTriggerBase(EntityTriggerBase):
        """数值状态触发器基类（threshold: {type, value/value_min/value_max}）."""

        def __init__(self, hass, config):
            super().__init__(hass, config)
            threshold = dict(self._options.get("threshold") or {})
            self._threshold_type = threshold.get("type", "any")
            self.threshold = _threshold_number(threshold.get("value"))
            self.lower_threshold = _threshold_number(threshold.get("value_min"))
            self.upper_threshold = _threshold_number(threshold.get("value_max"))

        def _get_tracked_value(self, state):
            try:
                return float(state.state)
            except (TypeError, ValueError):
                return None

        def is_valid_state(self, state, report_not_triggered=None):
            current = self._get_tracked_value(state)
            if current is None:
                return False
            t = self._threshold_type
            if t == "any":
                return True
            if t == "above":
                return self.threshold is not None and current > self.threshold
            if t == "below":
                return self.threshold is not None and current < self.threshold
            if t == "between":
                return (
                    self.lower_threshold is not None
                    and self.upper_threshold is not None
                    and self.lower_threshold <= current <= self.upper_threshold
                )
            if t == "outside":
                return (
                    self.lower_threshold is not None
                    and self.upper_threshold is not None
                    and not (self.lower_threshold <= current <= self.upper_threshold)
                )
            return False

    class EntityNumericalStateChangedTriggerBase(EntityNumericalStateTriggerBase):
        """数值变化触发器基类."""

        def is_valid_transition(self, from_state, to_state):
            return self._get_tracked_value(from_state) != self._get_tracked_value(
                to_state
            )

    def make_entity_target_state_trigger(domain_specs, to_states, **kw):
        to_states_set = {to_states} if isinstance(to_states, str) else set(to_states)

        class CustomTrigger(EntityTargetStateTriggerBase):
            _domain_specs = dict(domain_specs)
            _to_states = to_states_set

        return CustomTrigger

    def make_entity_numerical_state_changed_trigger(
        domain_specs, valid_unit=UNDEFINED, **kw
    ):
        class CustomTrigger(EntityNumericalStateChangedTriggerBase):
            _domain_specs = dict(domain_specs)
            _valid_unit = valid_unit

        return CustomTrigger

    trig.Trigger = Trigger
    trig.TriggerConfig = TriggerConfig
    trig.TriggerProtocol = object
    trig.UNDEFINED = UNDEFINED
    # v0.9.29：车牌变为触发器要在它上面 extend 一个必填 plate
    trig.ENTITY_STATE_TRIGGER_SCHEMA_WITH_BEHAVIOR = _SchemaStub(
        {"target": "required", "options": "required"}
    )
    trig.EntityTriggerBase = EntityTriggerBase
    trig.StatelessEntityTriggerBase = StatelessEntityTriggerBase
    trig.EntityTargetStateTriggerBase = EntityTargetStateTriggerBase
    trig.EntityNumericalStateTriggerBase = EntityNumericalStateTriggerBase
    trig.EntityNumericalStateChangedTriggerBase = (
        EntityNumericalStateChangedTriggerBase
    )
    trig.make_entity_target_state_trigger = make_entity_target_state_trigger
    trig.make_entity_numerical_state_changed_trigger = (
        make_entity_numerical_state_changed_trigger
    )

    # homeassistant.exceptions
    exc = _mod("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    exc.HomeAssistantError = HomeAssistantError

    # selector
    sel = _mod("homeassistant.helpers.selector")

    class SelectSelectorMode:
        DROPDOWN = "dropdown"
        LIST = "list"

    class TextSelectorType:
        TEXT = "text"

    class NumberSelectorMode:
        BOX = "box"

    class SelectOptionDict(dict):
        def __init__(self, value, label):
            super().__init__(value=value, label=label)
            self.value = value
            self.label = label

    # 每种 selector 用独立的桩类：测试里可以断言「页面中没有某个类型的控件」
    # （例如 v0.5.0 起不再使用开关 BooleanSelector）。
    def _sel_class(name: str, kind: str):
        return type(name, (_SelectorStub,), {"kind": kind})

    SelectSelectorStub = _sel_class("SelectSelector", "select")
    TextSelectorStub = _sel_class("TextSelector", "text")
    NumberSelectorStub = _sel_class("NumberSelector", "number")
    BooleanSelectorStub = _sel_class("BooleanSelector", "boolean")

    sel.SelectSelector = SelectSelectorStub
    sel.SelectSelectorConfig = lambda **kw: kw
    sel.SelectSelectorMode = SelectSelectorMode
    sel.TextSelector = TextSelectorStub
    sel.TextSelectorConfig = lambda **kw: kw
    sel.TextSelectorType = TextSelectorType
    sel.NumberSelector = NumberSelectorStub
    sel.NumberSelectorConfig = lambda **kw: kw
    sel.NumberSelectorMode = NumberSelectorMode
    sel.BooleanSelector = BooleanSelectorStub
    sel.BooleanSelectorConfig = lambda **kw: kw
    sel.SelectOptionDict = SelectOptionDict

    # aiohttp_client
    aio = _mod("homeassistant.helpers.aiohttp_client")
    aio.async_get_clientsession = lambda hass: getattr(hass, "_session", None)

    # config_entries
    ce = _mod("homeassistant.config_entries")

    class _FlowBase:
        def __init_subclass__(cls, domain=None, **kwargs):
            super().__init_subclass__(**kwargs)
            if domain:
                cls.domain = domain

        def __init__(self):
            self.hass = None

        def async_show_form(
            self,
            step_id,
            data_schema=None,
            errors=None,
            description_placeholders=None,
            **kw,
        ):
            return {
                "type": "form",
                "step_id": step_id,
                "errors": errors or {},
                "schema": data_schema,
                "placeholders": description_placeholders or {},
                "last_step": kw.get("last_step"),
            }

        def async_show_menu(
            self,
            *,
            step_id=None,
            menu_options=None,
            description_placeholders=None,
            sort=False,
            **kw,
        ):
            return {
                "type": "menu",
                "step_id": step_id,
                "menu_options": menu_options or {},
                "placeholders": description_placeholders or {},
            }

        def async_create_entry(self, title="", data=None, options=None, **kw):
            return {"type": "create_entry", "title": title, "data": data, "options": options}

        def async_abort(self, reason=""):
            return {"type": "abort", "reason": reason}

        async def async_set_unique_id(self, unique_id):
            self._unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            return None

    class ConfigFlow(_FlowBase):
        domain = ""

    class OptionsFlow(_FlowBase):
        pass

    ce.ConfigFlow = ConfigFlow
    ce.OptionsFlow = OptionsFlow
    ce.ConfigEntry = _class("ConfigEntry")

    import voluptuous  # noqa: F401  确保依赖存在


def service_call(data=None):
    """构造一个 ServiceCall（供服务处理函数测试）."""
    return sys.modules["homeassistant.core"].ServiceCall(data)


def _load_package():
    """把 custom_components 加入 sys.path，真正导入 my_bus 包（含 __init__.py）."""
    import importlib
    import os

    root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "custom_components")
    )
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module("my_bus")


def _load_config_flow():
    import importlib

    _load_package()
    return importlib.import_module("my_bus.config_flow")


def _fake_hass(
    session=None,
    latitude=24.4798,
    longitude=118.0894,
    entries=None,
    store_data=None,
):
    """构造 fake hass：支持 config_entries、后台任务与「已落盘的缓存」."""

    class _States:
        def __init__(self, states=None):
            self._states = states or {}

        def get(self, entity_id):
            return self._states.get(entity_id)

    class _ConfigEntries:
        def __init__(self, items):
            self._entries = list(items or [])
            self.updated = []
            self.reloaded = []

        def async_entries(self, domain=None, *args, **kwargs):
            if domain is None:
                return list(self._entries)
            return [e for e in self._entries if getattr(e, "domain", "my_bus") == domain]

        def async_update_entry(self, entry, **kwargs):
            self.updated.append((entry, kwargs))
            if "data" in kwargs:
                try:
                    entry.data = kwargs["data"]
                except Exception:  # noqa: BLE001
                    pass
            return True

        def async_reload(self, entry_id):
            self.reloaded.append(entry_id)

            async def _noop():
                return None

            return _noop()

    class _Services:
        def __init__(self):
            self.registered = {}

        def async_register(self, domain, name, func, schema=None, supports_response=None):
            self.registered[f"{domain}.{name}"] = {
                "handler": func,
                "schema": schema,
                "supports_response": supports_response,
            }

    class FakeHass:
        def __init__(self):
            self.data = {}
            self.config = types.SimpleNamespace(
                language="zh-Hans", latitude=latitude, longitude=longitude
            )
            self.states = _States()
            self.config_entries = _ConfigEntries(entries)
            self.services = _Services()
            self._tasks = []
            if store_data:
                self._store_data = dict(store_data)

        def async_create_task(self, coro, name=None):
            if not asyncio.iscoroutine(coro):
                return None
            task = asyncio.ensure_future(coro)
            self._tasks.append(task)
            return task

        async def async_block_till_done(self):
            """等待所有后台任务结束（含其链式创建的任务）."""
            while self._tasks:
                pending = list(self._tasks)
                self._tasks.clear()
                await asyncio.gather(*pending, return_exceptions=True)

    hass = FakeHass()
    hass._session = session
    # 内存版实体注册表（v0.9.16：残留事件实体清理测试用）
    hass._entity_registry = sys.modules[
        "homeassistant.helpers.entity_registry"
    ].EntityRegistry()
    return hass


async def main() -> None:
    """真实网络冒烟：菜单按钮式向导（城市 → 检索方式 → 站台/线路 → 参数 → 确认创建）.

    v0.5.0 起每一步都是**菜单**（选项渲染成真实按钮），只有需要键盘输入的
    两处用表单：检索关键词、到站参数。
    """
    install()
    cf = _load_config_flow()

    import aiohttp

    def hint_of(res) -> str:
        return (res.get("placeholders") or {}).get("hint") or ""

    def dump(res, label):
        print(f"[{label}] {res.get('type')} {res.get('step_id')}")
        if res.get("type") == "menu":
            for key, text in (res.get("menu_options") or {}).items():
                print(f"       按钮 {key}: {text}")
        else:
            fields = [getattr(k, "schema", None) for k in (res.get("schema").schema if res.get("schema") else {})]
            print(f"       输入框: {fields}")
        for line in hint_of(res).splitlines()[:4]:
            print("     文案:", line[:110])

    def click(flow, key):
        """点菜单按钮：HA 走 async_step_<key>."""
        handler = getattr(flow, f"async_step_{key}", None)
        assert handler is not None, f"菜单按钮 {key} 没有 async_step_{key}"
        return handler(None)

    def pick(flow, index):
        """点第 index 个候选按钮（__getattr__ 动态生成的 async_step_pick_<N>）."""
        handler = getattr(flow, f"async_step_{cf.KEY_PICK}{index}", None)
        assert handler is not None, f"候选按钮 {cf.KEY_PICK}{index} 没有对应方法"
        return handler(None)

    async def choose_station(flow, keyword="县口路"):
        """检索并选中一个站台；唯一结果会被自动采用，这时直接就是线路页."""
        res = await flow.async_step_station_keyword({cf.STATION_KW_FIELD: keyword})
        if res["step_id"] == "line":
            print(f"     （「{keyword}」唯一结果已自动采用 → 直接进线路页）")
            return res
        assert res["step_id"] == "station" and flow._station_options, "没检索到站台"
        target = "县口路站" if "县口路站" in flow._station_options else flow._station_options[0]
        return await pick(flow, flow._station_options.index(target))

    class _Entry:
        """一条已创建的监控（用于冒烟选项流）."""

        def __init__(self):
            self.data = {
                "city": "厦门市", "station": "县口路站", "line": "615路",
                "direction": "1", "station_order": 1,
            }
            self.options = {"poll_interval": 10}
            self.entry_id = "smoke"
            self.title = "厦门市 615路 县口路站"
            self.domain = "my_bus"
            self.version = 2

    async with aiohttp.ClientSession() as session:
        # --- 场景 A: 定位城市 → 先选站台（县口路）→ 线路 → 参数 → 确认 ---
        flow = cf.XmBusConfigFlow()
        flow.hass = _fake_hass(session)

        res = await flow.async_step_user(None)
        dump(res, "A0 第1步 选择城市")
        assert res["type"] == "menu" and res["step_id"] == "city"
        assert cf.KEY_BACK not in res["menu_options"], "第 1 步不该有「上一步」"
        # 0.8.4：第 1 步说明区第一行是欢迎语（没有「上一步」时用一行文字占住第一位），
        # 让「🔍 检索城市名」落到第二行，与第 3 步「⬅ 返回上一步 → 🔍 检索站台」对齐。
        lines0 = [ln for ln in res["placeholders"]["hint"].splitlines() if ln.strip()]
        assert lines0[0] == cf._T["welcome"] and lines0[1] == "第 1 步 / 共 7 步", lines0[:2]
        # v0.8.9：「同步最新数据」按钮已从第 1 步移除（同步挪到向导第 6 步）
        assert "city_sync" not in res["menu_options"], res["menu_options"]
        # v0.9.0：第 1 步没有「上一步」，由欢迎语占位 ⇒「🔍 检索城市名」在整页里的
        # 次序（说明区之后的下一个元素）与第 3 步的「🔍 检索站台」完全一致
        assert list(res["menu_options"])[0] == "city_keyword", res["menu_options"]
        print("     第 1 步按钮:", list(res["menu_options"].values()))

        res = await click(flow, "city_locate")
        dump(res, "A1 用家庭位置识别城市 → 第2步")
        if res["step_id"] == "mode":
            print("     识别到的城市:", flow._city)
        else:
            # CMD108 抖动会重试，仍失败时如实提示「稍后重试」；这里回退到关键词检索继续跑
            print("     （这次定位没成功，回退到关键词检索继续冒烟）")
            res = await flow.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
            dump(res, "A1' 输入「厦门市」→ 第2步")
        assert res["step_id"] == "mode", res["step_id"]

        # 第 2 步是独立的「选择检索方式」：「返回」排在整页第一个
        dump(res, "A2 第2步 选择检索方式（返回 / 先选站台 / 先选线路）")
        assert list(res["menu_options"]) == [cf.KEY_BACK, "mode_station", "mode_line"], \
            res["menu_options"]

        res = await click(flow, "mode_station")
        dump(res, "A3 点「先选站台」→ 第3步 选择站台（返回 / 检索站台）")
        assert res["step_id"] == "station", res["step_id"]
        assert list(res["menu_options"]) == [cf.KEY_BACK, "station_keyword"], \
            res["menu_options"]
        assert res["menu_options"].get(cf.KEY_BACK) == cf._T["back_to"]

        # v0.8.3：宽泛关键词会命中一大批站台，而掌上公交的单次检索上限约 30 条 ——
        # 界面必须如实说明「被截断」，否则用户以为「就这么几条」。
        res = await flow.async_step_station_keyword({cf.STATION_KW_FIELD: "站"})
        wide = len(flow._station_options)
        print(f"     宽泛关键词「站」命中 {wide} 条（接口单次上限按 {cf.SEARCH_LIMIT} 条判定）")
        if wide >= cf.SEARCH_LIMIT:
            assert "最多返回" in hint_of(res), hint_of(res)
            print("     ✔ 提示里已说明被截断，可多加一个字收窄")
        else:
            print("     （这一次没有触顶，跳过截断提示断言）")

        res = await choose_station(flow)
        dump(res, "A4 检索并选中「县口路」→ 第4步 选择线路")
        assert res["step_id"] == "line", res["step_id"]
        assert flow._line_options, "该站台没有线路"
        assert res["menu_options"].get(cf.KEY_BACK) == cf._T["back_to"]

        res = await pick(flow, 0)
        dump(res, "A5 选中线路 → 第5步 选择到站参数")
        assert res["step_id"] == "settings", res["step_id"]

        res = await click(flow, "settings_params")
        assert res["type"] == "form" and res["step_id"] == "settings_params"
        # 故意塞越界值：后端必须夹到合法范围（9999 秒 → 120 秒）
        res = await flow.async_step_settings_params({
            cf.POLL_INTERVAL_FIELD: 9999,
        })
        dump(res, "A6 保存越界参数（应被夹取）")
        assert res["step_id"] == "settings" and "已保存" in hint_of(res)
        assert flow._poll_interval == 120, flow._poll_interval

        res = await click(flow, "to_sync")
        dump(res, "A7 第6步 数据同步")
        assert res["step_id"] == "sync"
        assert list(res["menu_options"]) == [
            cf.KEY_BACK, "sync_now", "sync_interval", "sync_toggle", "to_confirm",
        ], res["menu_options"]

        res = await click(flow, "to_confirm")
        dump(res, "A8 第7步 确认创建")
        assert res["step_id"] == "confirm"
        assert list(res["menu_options"]) == [cf.KEY_BACK, "finish"], res["menu_options"]

        res = await click(flow, "finish")
        print("[A9 创建]", res["type"], res.get("title"), res.get("data"), res.get("options"))
        assert res["type"] == "create_entry" and res["data"]["city"] == "厦门市"

        # --- 场景 B: 输入城市名 → 先选线路（615）→ 途经顺序选站台 → 参数 → 确认 ---
        flow2 = cf.XmBusConfigFlow()
        flow2.hass = _fake_hass(session)
        await flow2.async_step_user(None)

        res = await flow2.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
        dump(res, "B0 输入「厦门市」→ 第2步 选择检索方式")
        assert res["step_id"] == "mode" and flow2._city == "厦门市", flow2._city

        res = await click(flow2, "mode_line")
        dump(res, "B1 点「先选线路」→ 第3步 选择线路（线路优先）")
        assert res["step_id"] == "line" and flow2._search_mode == cf.MODE_LINE_FIRST, \
            res["step_id"]
        assert list(res["menu_options"]) == [cf.KEY_BACK, "line_keyword"], res["menu_options"]

        res = await click(flow2, "line_keyword")
        assert res["type"] == "form" and res["step_id"] == "line_keyword", res["step_id"]

        res = await flow2.async_step_line_keyword({cf.LINE_KW_FIELD: "615"})
        dump(res, "B2 检索线路 615 → 第3步 选择线路")
        assert res["step_id"] == "line" and flow2._line_options, "没检索到线路"
        assert res["menu_options"].get(cf.KEY_BACK) == cf._T["back_to"]

        res = await pick(flow2, 0)
        dump(res, "B3 选线路 → 第4步 选择站台")
        assert res["step_id"] == "line_station", res["step_id"]
        print("     前 5 站:", flow2._station_options[:5])
        assert res["menu_options"].get(cf.KEY_BACK) == cf._T["back_to"]

        res = await pick(flow2, 0)
        dump(res, "B4 选站台 → 第5步 选择到站参数")
        assert res["step_id"] == "settings", res["step_id"]

        res = await click(flow2, "to_sync")
        dump(res, "B5 第6步 数据同步（真实网络：看本地缓存规模）")
        assert res["step_id"] == "sync", res["step_id"]

        res = await click(flow2, "to_confirm")
        assert res["step_id"] == "confirm"
        res = await click(flow2, "finish")
        print("[B6 创建]", res["type"], res.get("title"), res.get("data"), res.get("options"))
        assert res["type"] == "create_entry"

        # --- 场景 C: 「上一步」是真实按钮，逐级可退 ---
        flow3 = cf.XmBusConfigFlow()
        flow3.hass = _fake_hass(session)
        await flow3.async_step_user(None)
        await flow3.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
        res = await click(flow3, cf.KEY_BACK)
        dump(res, "C0 第2步「选择检索方式」点「上一步」按钮")
        assert res["step_id"] == "city", res["step_id"]
        assert cf.KEY_BACK not in res["menu_options"], "回到第 1 步后不该还有「上一步」"
        print("     按钮文字:", list(res["menu_options"].values()))

        # --- 场景 D: 选项流（按钮式入口菜单 + 跳过参数页时「上一步」仍指回来路）---
        entry = _Entry()
        opt = cf.XmBusOptionsFlow(entry)
        opt.hass = _fake_hass(session, entries=[entry])

        res = await opt.async_step_init(None)
        dump(res, "D0 选项菜单")
        assert res["type"] == "menu" and res["step_id"] == "init"
        assert set(res["menu_options"]) == {
            "edit_city", "edit_line", "edit_settings", "sync", "done",
        }, res["menu_options"]

        res = await click(opt, "edit_line")
        dump(res, "D1 修改线路/站台 → 第2步 选择检索方式")
        assert res["step_id"] == "mode"
        assert res["menu_options"].get(cf.KEY_BACK) == cf._T["back_to_menu"]

        res = await click(opt, "mode_station")
        assert res["step_id"] == "station", res["step_id"]

        res = await choose_station(opt)
        dump(res, "D2 选中站台 → 线路页")
        assert res["step_id"] == "line", res["step_id"]
        res = await pick(opt, 0)
        dump(res, "D3 选完线路直接进确认页（跳过参数页）")
        assert res["step_id"] == "confirm"
        assert any("保存修改" in v for v in res["menu_options"].values()), res["menu_options"]
        assert res["menu_options"].get(cf.KEY_BACK) == cf._T["back_to"], res["menu_options"]

        res = await click(opt, "finish")
        dump(res, "D4 点「保存修改」→ 回到选项菜单")
        assert res["step_id"] == "init" and "已更新为" in hint_of(res)

        # --- 场景 E: 设备页实体（v0.9.4 起 5 个传感器，无按钮）---
        # 平台文件导入失败时 HA 只会记日志、界面静默少项（见 device_trigger 的历史
        # bug），所以这里至少要确认新平台能导入、实体类存在、换算函数正确。
        import importlib

        sensor_plat = importlib.import_module("my_bus.sensor")
        logic_mod = importlib.import_module("my_bus.arrival_logic")
        assert sensor_plat.XmBusRemainingKmSensor is not None
        assert sensor_plat.XmBusRemainingStopsSensor is not None
        assert logic_mod.distance_km(1332.0) == 1.3
        assert logic_mod.distance_km(None) is None
        print("E0 设备页实体：剩余公里数（1332m → 1.3 公里）可导入（v0.9.4 起无同步按钮）")

        print("\n真实网络冒烟：全部通过 ✔")


if __name__ == "__main__":
    asyncio.run(main())
