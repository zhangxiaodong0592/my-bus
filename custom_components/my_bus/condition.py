"""My Bus 条件（HA 新版条件体系，2026.10+）.

让「新建自动化 → 添加条件 → 按目标」里的 My Bus 实体，像门窗传感器
（是打开 / 不是打开）、温湿度传感器（高于 / 低于）一样列出条件。
v0.9.24 起条件与触发器对称，共八条：

状态类（target = 到站状态，device_class: enum）
- ``is_arrived``      是「已到站」     —— 此刻车辆正停在监控站台上
- ``is_not_arriving`` 是「未到站」     —— 此刻车辆还没到（官方文案「N站」）
- ``is_arriving``     是「即将到站」   —— 已驶向站台但还没停稳
- ``is_no_bus``       是「暂无车辆」   —— 该方向没车，或官方数据解析不出

数值类（v0.9.24 新增，与同名触发器成对）
- ``remaining_stops`` 剩余站数   —— 几个站（单位：站，高于/低于/区间/等于）
- ``remaining_km``    剩余公里数 —— 几公里（单位：公里）
- ``eta``             预计到达   —— 几分钟（单位：分钟）
- ``data_sync``       数据同步   —— 距上次同步几小时（单位：小时）

车牌类（target = 车牌实体，自定义 device_class: license_plate）
- ``plate_becomes`` 车牌变为 —— 此刻最近一辆车的车牌等于（或通配符匹配）
  用户手填的车牌号。v0.9.28 首版叫「车牌是」（``plate_is``）并配了一条
  反义的「车牌不是」（``plate_is_not``）；v0.9.32 按用户要求删除
  「车牌不是」并把「车牌是」改名「车牌变为」，与触发器同名（键也一致，
  触发器 / 条件是两个独立注册表，不冲突）。v0.9.30 起支持通配符：
  ``*`` 任意多个字、``?`` 一个字，不写通配符就是精确匹配；
  与触发器「车牌变为」共用 ``plate_match``。

车牌条件为什么得自己写类：核心的 ``make_entity_state_condition`` 要求
**在造类时**就把要比对的状态写死，而车牌是用户每次配置时手填的，
所以只能继承 ``EntityConditionBase``，从 ``options.plate`` 读值、
在 ``is_valid_state`` 里比对。schema 在核心那份
``ENTITY_STATE_CONDITION_SCHEMA_ANY_ALL`` 上 extend 一个必填的 ``plate``。
没车时车牌状态是 unknown，核心的 ``_excluded_states`` 会把它排除，
车牌条件判为**不成立**（不能因为没车就断言「是某辆」）。

数值类为什么走「属性」：数据同步传感器的状态是**时间戳**（ISO 时间），
``float(state)`` 必然失败，所以它在 ``sensor.py`` 里额外暴露一个
「距上次同步小时数」数字属性（随每轮刷新重算；v0.9.27 起属性名用中文，
因为「状态已变化」触发器的属性下拉框直接显示属性键），
条件的 ``DomainSpec.value_source`` 指向该属性即可用核心数值比较器
（``make_entity_numerical_condition``）判定，无需自写 Condition 子类。

为什么要文件（0.9.20 → 0.9.21 的教训）：
- 「添加条件 → 按目标」的数据源是核心的**新条件注册表**（WS 命令
  ``get_conditions_for_target``），只认三样东西：本文件（``condition.py``
  的 ``CONDITIONS``）、``conditions.yaml`` 的 target/字段描述、以及
  ``strings.json`` / ``translations/*.json`` 的 ``conditions`` 段。
- 0.9.20 只写了旧版 ``device_condition.py``（服务旧的「按设备」页签），
  新界面完全不读它 —— 所以条件列表空着，和 0.9.13 触发器那次是同一个坑。
- 旧 ``device_condition.py`` 仍然保留，老自动化继续可用（只有 4 条状态条件，
  数值条件那边核心 ``sensor`` 域本来就有「高于/低于」）。

设计要点：
- 四条状态条件都是**精确状态**匹配（不是取反）：「是『未到站』」只匹配
  「未到站」，不会把「即将到站」「暂无车辆」也算进来。
- 每个条件按 ``device_class`` 精确挂载 —— 只有对应实体匹配，不会串到别的
  传感器上（与 0.9.16 触发器一对一挂载同一套判别符）。
- 0.9.19 的严格官方口径原样沿用：官方解析不出时状态就是「暂无车辆」，
  因此「是『已到站』」不会误判通过。
- 条件与触发器（``trigger.py`` / ``triggers.yaml``）互不影响：
  触发器 = 状态**变成**什么；条件 = 此刻**是不是**什么。
"""

from __future__ import annotations

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN, SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.automation import DomainSpec
from homeassistant.helpers.condition import Condition

try:  # 新版核心（与 battery 等核心组件同名）
    from homeassistant.helpers.condition import make_entity_state_condition
except ImportError:  # 兼容更早的核心：触发器工厂的命名对称版本
    from homeassistant.helpers.condition import (  # type: ignore[assignment]
        make_entity_target_state_condition as make_entity_state_condition,
    )

try:  # v0.9.24 数值条件工厂（核心 battery 的 is_level 用的就是它）
    from homeassistant.helpers.condition import make_entity_numerical_condition
except ImportError:  # 极旧核心没有这个工厂：下面自动只注册四条状态条件
    make_entity_numerical_condition = None  # type: ignore[assignment]

try:  # v0.9.28 车牌条件：需要实体条件基类与它的 schema
    from homeassistant.helpers.condition import (
        ENTITY_STATE_CONDITION_SCHEMA_ANY_ALL,
        EntityConditionBase,
    )
except ImportError:  # 更早的核心：车牌条件不注册（触发器照旧可用）
    ENTITY_STATE_CONDITION_SCHEMA_ANY_ALL = None  # type: ignore[assignment]
    EntityConditionBase = None  # type: ignore[assignment]

from .arrival_logic import (
    STATUS_ARRIVED,
    STATUS_ARRIVING,
    STATUS_NO_BUS,
    STATUS_NOT_ARRIVING,
    plate_match,
)

# 只匹配「到站状态」实体（sensor 域 + device_class: enum）。
# 与 triggers.yaml 里 arrival_arrived / arrival_arriving 用的是同一判别符。
_STATE_SPECS: dict[str, DomainSpec] = {
    SENSOR_DOMAIN: DomainSpec(device_class=SensorDeviceClass.ENUM),
}

# 三个数值传感器同样按 device_class 精确挂载（sensor.py 里的自定义 device_class）。
_STOPS_SPECS: dict[str, DomainSpec] = {
    SENSOR_DOMAIN: DomainSpec(device_class="stop_count"),
}
_KM_SPECS: dict[str, DomainSpec] = {
    SENSOR_DOMAIN: DomainSpec(device_class="remaining_distance"),
}
_ETA_SPECS: dict[str, DomainSpec] = {
    SENSOR_DOMAIN: DomainSpec(device_class="eta"),
}
# 数据同步：状态是时间戳（不是数字），改用实体属性「距上次同步小时数」参与数值比较。
# v0.9.27 起属性名统一为中文（属性键就是「状态已变化」触发器里属性下拉框的显示名）。
_SYNC_SPECS: dict[str, DomainSpec] = {
    SENSOR_DOMAIN: DomainSpec(
        device_class=SensorDeviceClass.TIMESTAMP,
        value_source="距上次同步小时数",
    ),
}

# 车牌实体（v0.9.28）：自定义 device_class，与 trigger.py 的 _PLATE_SPECS 一致。
_PLATE_SPECS: dict[str, DomainSpec] = {
    SENSOR_DOMAIN: DomainSpec(device_class="license_plate"),
}


def _state_condition(
    domain_specs: dict[str, DomainSpec], state: str
) -> type[Condition]:
    """造一条「实体状态等于 state」的条件（不同核心版本签名略有差异）."""
    try:
        return make_entity_state_condition(
            domain_specs, state, primary_entities_only=False
        )
    except TypeError:  # 早期版本没有 primary_entities_only 关键字
        return make_entity_state_condition(domain_specs, state)


def _numerical_condition(domain_specs: dict[str, DomainSpec]) -> type[Condition]:
    """造一条「实体数值高于/低于/区间」的条件（阈值由 conditions.yaml 描述）.

    不传 ``valid_unit``：保持核心默认（不过滤单位）。若传 ``None``，
    核心会要求实体**没有**单位，我们三个传感器都有单位（站/公里/分钟），
    条件将永不成立 —— 这是最容易踩的坑。
    """
    try:
        return make_entity_numerical_condition(  # type: ignore[misc]
            domain_specs, primary_entities_only=False
        )
    except TypeError:  # 早期版本没有 primary_entities_only 关键字
        return make_entity_numerical_condition(domain_specs)  # type: ignore[misc]


CONDITIONS: dict[str, type[Condition]] = {
    "is_arrived": _state_condition(_STATE_SPECS, STATUS_ARRIVED),
    "is_not_arriving": _state_condition(_STATE_SPECS, STATUS_NOT_ARRIVING),
    "is_arriving": _state_condition(_STATE_SPECS, STATUS_ARRIVING),
    "is_no_bus": _state_condition(_STATE_SPECS, STATUS_NO_BUS),
}

if make_entity_numerical_condition is not None:
    CONDITIONS.update({
        "remaining_stops": _numerical_condition(_STOPS_SPECS),
        "remaining_km": _numerical_condition(_KM_SPECS),
        "eta": _numerical_condition(_ETA_SPECS),
        "data_sync": _numerical_condition(_SYNC_SPECS),
    })


def _plate_schema():
    """车牌条件的 schema：核心「实体状态条件」的 schema 上加一个必填 plate."""
    if ENTITY_STATE_CONDITION_SCHEMA_ANY_ALL is None:
        return None
    import probatio
    from homeassistant.const import CONF_FOR, CONF_OPTIONS
    from homeassistant.helpers import config_validation as cv

    return ENTITY_STATE_CONDITION_SCHEMA_ANY_ALL.extend({
        probatio.Required(CONF_OPTIONS): {
            probatio.Required("behavior", default="any"): probatio.In(
                ["any", "all"]
            ),
            probatio.Optional(CONF_FOR): cv.positive_time_period,
            probatio.Required("plate"): str,
        },
    })


_PLATE_SCHEMA = _plate_schema() if EntityConditionBase is not None else None

if EntityConditionBase is not None and _PLATE_SCHEMA is not None:

    class PlateBecomesCondition(EntityConditionBase):
        """车牌变为：此刻最近一辆车的车牌等于（或通配符匹配）填写的号码.

        没车时车牌状态是 unknown，会被核心的 ``_excluded_states`` 排除，
        因此没车时本条件**不成立**（不能因为没车就断言「是某辆」）。
        """

        _domain_specs = _PLATE_SPECS
        _schema = _PLATE_SCHEMA
        _primary_entities_only = False

        def __init__(self, hass, config) -> None:
            super().__init__(hass, config)
            options = config.options or {}
            self._plate = str(options.get("plate") or "").strip()

        def is_valid_state(self, entity_state) -> bool:
            # v0.9.30 起支持通配符（* 任意多个字 / ? 一个字），
            # 不写通配符就是精确匹配 —— 与 0.9.28 行为完全一致。
            return plate_match(self._plate, entity_state.state)

    CONDITIONS.update({
        "plate_becomes": PlateBecomesCondition,
    })


async def async_get_conditions(hass: HomeAssistant) -> dict[str, type[Condition]]:
    """Return the conditions for My Bus."""
    return CONDITIONS
