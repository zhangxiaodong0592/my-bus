"""My Bus 触发器（HA 新版触发器体系，2026.10+）.

让「新建自动化 → 添加触发条件 → 按目标」里的 My Bus 实体，
像门窗传感器、温湿度传感器一样列出触发器：

- ``arrival_arrived``      已到站     —— 到站状态变为「已到站」时触发
- ``arrival_arriving``     即将到站   —— 到站状态变为「即将到站」时触发
- ``arrival_not_arriving`` 未到站     —— 到站状态变为「未到站」时触发（v0.9.23）
- ``arrival_no_bus``       暂无车辆   —— 到站状态变为「暂无车辆」时触发（v0.9.23）
- ``remaining_stops``  剩余站数变化   —— 数值变化，可设阈值（单位：站）
- ``remaining_km``     剩余公里数变化 —— 同上（单位：公里）
- ``eta``              预计到达变化   —— 同上（单位：分钟）
- ``data_sync``        数据同步完成   —— 数据同步传感器时间更新（同步完成一次）时触发
- ``plate_becomes``    车牌变为       —— 车牌变成**用户手填的号码**时触发（v0.9.29）；
                                        支持 ``*`` / ``?`` 通配符（v0.9.30）

说明：
- 四条到站状态触发器的名称与「条件」完全同文案（已到站 / 即将到站 /
  未到站 / 暂无车辆，v0.9.23 统一），触发器与条件两侧措辞一致；
- 触发器的 target / 字段（threshold 选择器）描述在 ``triggers.yaml``；
  全部触发器按 device_class 一对一挂载（v0.9.16）：enum → 到站状态、
  timestamp → 数据同步、stop_count / remaining_distance / eta →
  三个数值传感器（sensor.py 声明同名自定义 device_class），
  每个实体页只显示自己的触发器，不再重复；
- 名称与描述翻译在 ``strings.json`` 与 ``translations/*.json`` 的
  ``triggers`` 段（前端按 ``component.my_bus.triggers.<key>.name`` 读取）；
- 非数值状态（如「暂无数据」）不会触发数值类触发器，由基类保证；
- v0.9.15 起「公交到站」事件实体与 ``bus_arrived`` 触发器删除，
  到站判断全部并入「到站状态」传感器；
- v0.9.31 起 ``plate_changed``（车牌变化）/ ``plate_replaced``（换车）
  两条删除（用户要求）：「车牌变为」配通配符已覆盖主流玩法 ——
  ``*`` = 有车出现（unknown → 任意车牌），``闽D06*`` = 换成 06 开头的车；
  但「任意换车」「开走」这两个语义不再单独提供（需要时可用通用
  「状态已变化」触发器绕路）；
- 旧版 ``device_trigger.py`` 保留（老自动化继续可用）。
"""

from __future__ import annotations

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.automation import DomainSpec
from homeassistant.helpers.trigger import (
    EntityTriggerBase,
    StatelessEntityTriggerBase,
    Trigger,
    make_entity_numerical_state_changed_trigger,
    make_entity_target_state_trigger,
)

try:  # v0.9.29「车牌变为」：目标状态触发器基类 + 实体触发器 schema（与核心同名）
    from homeassistant.helpers.trigger import (
        ENTITY_STATE_TRIGGER_SCHEMA_WITH_BEHAVIOR,
        EntityTargetStateTriggerBase,
    )
except ImportError:  # 更早的核心没有这套导出：该触发器不注册，其余照旧可用
    ENTITY_STATE_TRIGGER_SCHEMA_WITH_BEHAVIOR = None  # type: ignore[assignment]
    EntityTargetStateTriggerBase = None  # type: ignore[assignment]

from .arrival_logic import (
    STATUS_ARRIVED,
    STATUS_ARRIVING,
    STATUS_NO_BUS,
    STATUS_NOT_ARRIVING,
    plate_match,
)

_SENSOR_SPECS: dict[str, DomainSpec] = {SENSOR_DOMAIN: DomainSpec()}


class DataSyncTrigger(StatelessEntityTriggerBase):
    """数据同步完成：数据同步传感器的时间戳更新（同步完成一次）时触发."""

    _domain_specs = _SENSOR_SPECS


# 车牌实体（sensor.py 的 XmBusPlateSensor，自定义 device_class: license_plate）
_PLATE_SPECS: dict[str, DomainSpec] = {
    SENSOR_DOMAIN: DomainSpec(device_class="license_plate"),
}


TRIGGERS: dict[str, type[Trigger]] = {
    "arrival_arrived": make_entity_target_state_trigger(
        _SENSOR_SPECS, STATUS_ARRIVED
    ),
    "arrival_arriving": make_entity_target_state_trigger(
        _SENSOR_SPECS, STATUS_ARRIVING
    ),
    "arrival_not_arriving": make_entity_target_state_trigger(
        _SENSOR_SPECS, STATUS_NOT_ARRIVING
    ),
    "arrival_no_bus": make_entity_target_state_trigger(
        _SENSOR_SPECS, STATUS_NO_BUS
    ),
    "remaining_stops": make_entity_numerical_state_changed_trigger(_SENSOR_SPECS),
    "remaining_km": make_entity_numerical_state_changed_trigger(_SENSOR_SPECS),
    "eta": make_entity_numerical_state_changed_trigger(_SENSOR_SPECS),
    "data_sync": DataSyncTrigger,
    # plate_becomes 在下方守卫块里注册（依赖核心导出，且类定义在字典之后）
}


def _plate_becomes_schema():
    """「车牌变为」的 schema：核心实体触发器 schema 上加一个必填 plate.

    与 condition.py 的车牌条件同一套路 —— 基类 schema 的 options 是
    PREVENT_EXTRA（0.9.11 的坑），前端保存时额外带上的 ``plate`` 键
    不声明就会被 400 拒收，所以必须在 options 里补齐 behavior / for / plate。
    """
    if ENTITY_STATE_TRIGGER_SCHEMA_WITH_BEHAVIOR is None:
        return None
    import probatio
    from homeassistant.const import CONF_FOR, CONF_OPTIONS
    from homeassistant.helpers import config_validation as cv

    try:  # 与核心完全一致：behavior 兼容旧式写法（列表等）
        from homeassistant.helpers.trigger.entity_trigger import (
            _backwards_compatible_behavior as _compat,
        )
    except ImportError:  # 拿不到私有校验器就退化为普通 In 校验（新配置都是字符串）
        _compat = None

    behavior = (
        probatio.All(_compat, probatio.In(["first", "all", "each"]))
        if _compat is not None
        else probatio.In(["first", "all", "each"])
    )
    return ENTITY_STATE_TRIGGER_SCHEMA_WITH_BEHAVIOR.extend({
        probatio.Required(CONF_OPTIONS, default={}): {
            probatio.Required("behavior", default="each"): behavior,
            probatio.Optional(CONF_FOR): cv.positive_time_period,
            probatio.Required("plate"): str,
        },
    })


_PLATE_BECOMES_SCHEMA = _plate_becomes_schema()

if EntityTargetStateTriggerBase is not None and _PLATE_BECOMES_SCHEMA is not None:

    class PlateBecomesTrigger(EntityTargetStateTriggerBase):
        """车牌变为：车牌变成用户手填的号码时触发（首班车恰好是它也算）.

        继承核心 ``EntityTargetStateTriggerBase``（目标状态触发器），但目标
        状态不在造类时写死（那是 ``make_entity_target_state_trigger`` 的做法，
        车牌没法预知），而是实例化时从 ``options.plate`` 读。

        v0.9.30 起支持**通配符**（与条件「车牌是/不是」同一套
        :func:`arrival_logic.plate_match`）：``*`` 任意多个字、``?`` 一个字，
        不写通配符就是精确匹配。通配符没法装进 ``_to_states`` 集合
        （基类用 ``in`` 做集合成员判断），所以覆写两个判定方法：

        - ``is_valid_state``：新状态匹配 pattern（含 unknown / unavailable 防护）；
        - ``is_valid_transition``：镜像基类语义 —— 值变了、且**起点本来就不匹配**
          pattern（起点已在目标集内就不再触发，如 闽D0611D → 闽D0616D 同属 闽D06*）。

        排除规则与「车牌变化」一致 —— 只排除 unavailable（设备掉线），
        unknown（没车）是合法起点，所以首班车就是目标车也能触发：

        - 首班车就是目标车：unknown → 闽D12345D ✅ 触发
        - 别的车换过来：     闽D67890D → 闽D12345D ✅ 触发
        - 开走 / 换成别车：  闽D12345D → unknown / 闽D67890D ❌ 不触发
        """

        _domain_specs = _PLATE_SPECS
        _schema = _PLATE_BECOMES_SCHEMA
        _excluded_states = frozenset({STATE_UNAVAILABLE})
        _excluded_from_states = frozenset({STATE_UNAVAILABLE})

        def __init__(self, hass, config) -> None:
            super().__init__(hass, config)
            options = config.options or {}
            self._plate = str(options.get("plate") or "").strip()
            # 基类注解要求有 _to_states；通配符下走覆写的判定方法，集合置空
            # （空串 plate 时也永不触发；schema 层面 plate 必填，正常配置到不了）
            self._to_states = set()

        def is_valid_state(self, state, report_not_triggered=None) -> bool:
            """新状态是否匹配手填的车牌（支持通配符）."""
            return plate_match(self._plate, state.state)

        def is_valid_transition(self, from_state, to_state) -> bool:
            """值变了、且起点本来就不匹配 pattern（镜像基类语义）."""
            from_value = self._get_tracked_value(from_state)
            return (
                from_value != self._get_tracked_value(to_state)
                and not plate_match(self._plate, from_value)
            )

    TRIGGERS["plate_becomes"] = PlateBecomesTrigger


async def async_get_triggers(hass: HomeAssistant) -> dict[str, type[Trigger]]:
    """Return the triggers for My Bus."""
    return TRIGGERS
