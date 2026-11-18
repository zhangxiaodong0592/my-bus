"""
My Bus 回归验证（覆盖至 v0.9.32）.

v0.9.32 需求（用户：「删除“车牌不是”条件，把“车牌是”条件改名为“车牌变为”，
和触发器保持一致」）：

★ **删除 ``plate_is_not``（车牌不是）** —— 注册表 / conditions.yaml /
  translations / strings.json / icons.json 全链路移除。
★ **``plate_is``（车牌是）→ ``plate_becomes``（车牌变为）** —— 键与名称
  都与触发器同名（触发器 / 条件是两个独立注册表，键相同不冲突）；
  类改名 ``PlateIsCondition`` → ``PlateBecomesCondition``，语义不变：
  此刻最近一辆车的车牌等于（或通配符匹配）手填号码，没车（unknown）
  仍不成立。通配符照常可用（0.9.30 的 plate_match）。
  条件 10→9 条，与触发器 9 条重新对称。
  （`AG7`~`AG9` 改写守新键名；反向断言守 plate_is / plate_is_not 消失）

v0.9.31 需求（用户：「请删除“车牌变化”和“换车”两个触发器」）：

★ **删除 ``plate_changed`` / ``plate_replaced`` 两条触发器** ——
  「车牌变为」配通配符已覆盖主流玩法：``*`` = 有车出现（unknown → 任意
  车牌）、``闽D06*`` = 换成 06 开头的车；但「任意换车」「开走」两个语义
  不再单独提供（需要时可用通用「状态已变化」触发器绕路）。
  车牌**条件**：v0.9.32 改为仅剩「车牌变为」（原「车牌是」改名）。
  触发器 11→9 条。老自动化里若引用过这两个 key 会在重载时报错，
  需改用「车牌变为」重建（现存自动化均未引用，无实际影响）。
  （`AG3`/`AG4` 反向断言守；AG5/AG6 随被删触发器一并移除）

v0.9.30 需求（用户：「这个车牌号能支持模糊输入，或者模糊搜索吗」→ 选通配符方案）：

★ **车牌通配符匹配** —— 「车牌变为」触发器与「车牌是 / 车牌不是」条件
  共用新增的 :func:`arrival_logic.plate_match`：
  - 填 ``*``（任意多个字）/ ``?``（恰好一个字）→ 通配符匹配，
    如 ``闽D06*`` = 以闽D06开头、``闽D?616D`` = ?抵一个任意字符；
  - 不写通配符 → 精确匹配，与 0.9.28/0.9.29 行为完全一致（老配置零影响）；
  - 两端去空白、忽略大小写；pattern 为空不成立；
    state 是 unknown / unavailable（没车）也不成立
    （否则「车牌变为 *」会在没车时误触发）。
  触发器侧通配符装不进 ``_to_states`` 集合（基类用 ``in`` 判断），
  ``PlateBecomesTrigger`` 覆写 ``is_valid_state`` / ``is_valid_transition``
  （后者镜像基类语义：起点已在目标集内不重复触发，如 闽D0611D→闽D0616D
  同属 ``闽D06*``）。
  （`AI1`~`AI4` 守）

v0.9.29 需求（用户：「如果我想把车牌号作为触发器可不可以，比如点那个触发器，
然后输入车牌号，操作就像条件那样」）：

★ **「车牌变为」触发器**（``plate_becomes``）—— 触发器侧也能像条件那样
  手填车牌号：点触发器 → 文本框填车牌 → 车牌变成这个号码就触发。
  继承核心 ``EntityTargetStateTriggerBase``（目标状态触发器），但目标状态
  不在造类时写死，而是实例化时从 ``options.plate`` 读；schema 在核心
  ``ENTITY_STATE_TRIGGER_SCHEMA_WITH_BEHAVIOR`` 上 extend 一个必填 plate
  （options 是 PREVENT_EXTRA，不声明就 400，与 0.9.11 / 0.9.21 同一个坑）。
  排除规则与「车牌变化」一致（只排除 unavailable）：unknown（没车）是
  合法起点，所以**首班车恰好是目标车**也能触发。
★ 触发器 10→11 条，仍按 device_class 一对一挂载到「车牌」实体。
  （`AH1`~`AH5` 守）

v0.9.28 需求（用户：「那就新增车牌传感器和 2 个触发器和 2 个条件」）：

★ **车牌单独成实体** —— 原来车牌只是「到站状态」的一个属性，自动化里必须
  用 ``state_attr(实体, '车牌')`` 才取得，触发器只能靠「状态已变化 + 属性」绕路。
  新增 ``XmBusPlateSensor``（``translation_key="plate"``、
  自定义 ``device_class="license_plate"``、没有车时为 None → 界面「未知」）。
★ **2 条新触发器**：``plate_changed``（车牌任何变化，含「有车 ↔ 没车」）、
  ``plate_replaced``（换车：只认一辆换另一辆，忽略有车 ↔ 没车）。
  二者的差别只在「车牌从空变有 / 从有变空」这四个节点：前者把 unknown 当正常
  状态，后者沿用基类默认（unknown 两端都排除）。
★ **2 条新条件**：``plate_is``（车牌是）、``plate_is_not``（车牌不是），
  继承核心 ``EntityConditionBase``，从 ``options.plate`` 读用户手填的车牌，
  schema 在 ``ENTITY_STATE_CONDITION_SCHEMA_ANY_ALL`` 上 extend 一个必填 plate。
  （0.9.32 起只保留一条并改名 ``plate_becomes``「车牌变为」）
★ 触发器 8→10 条、条件 8→10 条，仍按 device_class 一对一挂载。
  （`AG1`~`AG9` 守）

v0.9.27 需求（用户：「选择了『到站状态』的『状态已变化』通用触发器有『属性（可选）』，
点进去的 City、Current stop、Direction、Distance km 等都是英文，能否改成中文」）：

★ **传感器属性名改为中文** —— HA 前端「状态已变化」触发器的属性下拉框显示的就是
  属性键本身（下划线→空格、首字母大写），没有任何翻译层，所以要中文只能改键名。
  四个实时传感器（剩余站数 / 预计到达 / 剩余公里数 / 到站状态）共用基类属性：
  城市、线路、站台、方向、车牌、当前站、剩余站数、内部剩余站数、剩余距离米、
  剩余公里数、预计到达分钟、预计到达来源（值为「官方」）、官方原文、官方剩余距离、
  到站状态；数据同步传感器：是否启用、刷新间隔小时、上次同步、耗时秒、城市数、
  线路数、站台数、失败次数、最后错误、问题、距上次同步小时数。
  连带改动：``condition.py`` 的 value_source 改为「距上次同步小时数」；
  ``device_trigger.py``（旧按设备路径）按新键名读属性，但**事件数据字段名不变**。
  （`AF1`~`AF8` 守；旧英文键必须全部消失）

v0.9.26 需求（用户：「把可精确到 0.1 公里、可填到 0.1 公里这样的文案去掉，
你不用过度考虑读屏用户的习惯」）：

★ **撤掉界面里的「0.1 公里」说明文案，`step: 0.1` 保留** —— 决策不变（阈值能填
  1.3），只是三份语言文件里 remaining_km 的触发/条件描述与 threshold 字段说明
  恢复成 0.9.24 的措辞，不再额外解释精度。
  （`AE5` 改为反向断言：文案里不得出现「0.1」）

v0.9.25 需求（用户：「剩余公里数在触发器和条件选择数值时是整数，但是传感器中
可以精确到小数点后 1 位数，所以这个数值能否也精确到小数点后 1 位数呢」）：

★ **剩余公里数阈值支持 1 位小数** —— ``triggers.yaml`` / ``conditions.yaml``
  里 remaining_km 的 threshold 数字选择器补 ``step: 0.1``（核心 number 选择器
  step 默认 1，box 模式下前端 step 不匹配就会把 1.3 判为非法值，用户只能填整数）。
  与传感器口径对齐：``arrival_logic.distance_km`` 本来就 ``round(..., 1)``。
  剩余站数 / 预计到达仍是整数（官方 API 口径），data_sync 保持 ``step: any``。
  （`AE1`~`AE4`、`AE6` 守）

v0.9.24 需求（用户：「如果要再增加剩余公里数、剩余站数、数据同步、预计到达
4 个条件，使触发器和条件都是 8 个可以吗」）：

★ **条件补齐到八条，与触发器一一对称** —— 4 条状态条件之外新增 4 条数值条件
  （remaining_stops / remaining_km / eta / data_sync），全部走核心
  ``make_entity_numerical_condition`` 工厂 + ``conditions.yaml`` 的 threshold
  选择器（mode: is），不手写 Condition 子类：
  - 三个数值传感器直接比对状态值（站 / 公里 / 分钟）；
  - 数据同步实体状态是**时间戳**，``float(state)`` 必然失败，因此在 sensor.py
    里暴露「距上次同步小时数」属性（距上次同步的小时数，每轮刷新重算），
    条件用 ``DomainSpec(value_source="距上次同步小时数")`` 比对（单位：小时）；
  - 数值条件**不传 valid_unit**：传 ``None`` 会要求实体无单位 ⇒ 条件永不成立。
  （`AD1`~`AD10` 守）

v0.9.21 需求（用户部署 0.9.20 后：「现在看不到你添加的条件，你可能犯了和添加
触发器一样的错误」——完全说对了）：

★ **条件改走 HA 新版条件注册表** —— 0.9.20 只写了旧版 ``device_condition.py``，
  它只服务老的「按设备」页签；「添加条件 → 按目标」对话框读的是核心**新条件
  注册表**（WS 命令 ``get_conditions_for_target``，实测返回 ``[]``），数据源是
  集成三件套：``condition.py``（``CONDITIONS`` 注册表）+ ``conditions.yaml``
  （target / 字段描述）+ ``translations`` 的 ``conditions`` 段。与 0.9.14
  触发器那次是同一个坑。修复：
  - 新增 ``condition.py``：4 条精确状态条件（is_arrived / is_not_arriving /
    is_arriving / is_no_bus），用核心 ``make_entity_state_condition`` 工厂；
  - 新增 ``conditions.yaml``：target 限定 ``integration: my_bus`` +
    ``domain: sensor`` + ``device_class: enum``（只挂「到站状态」），
    并声明 ``behavior`` / ``for`` 字段（否则前端保存被 PREVENT_EXTRA 拒绝）；
  - 三份语言文件补 ``conditions`` 段（对象形式，与 ``triggers`` 同规则）；
  - ``icons.json`` 补 ``conditions`` 图标；
  - 旧 ``device_condition.py`` 保留（老自动化 / 旧页签继续可用）。
  （`AC1`~`AC9` 守）

v0.9.20 需求（用户：「能不能做已到站和未到站的条件，就像已到站和未到站的触发器
那样呢」——希望条件页签里也能直接选到站状态，而不是手写实体状态条件）：

★ **新增设备条件 `device_condition.py`** —— 实测（2026-10-30，用户 HA + 核心源码）
  HA 的「条件」由**实体域**提供（`binary_sensor` / `sensor` 各有
  `device_condition.py`），集成自带 `device_condition.py` 才能在「设备」页签
  出现自己的条件（与自带 `device_trigger.py` 同一机制；核心没有 conditions.yaml）。
  小米官方集成 `xiaomi_home` 零条件文件，门窗传感器的「是打开 / 不是打开」
  全部由 `binary_sensor` 域按 device_class 生成 —— 我们照同一形态补：
  - 给「到站状态」提供 4 条**精确状态**条件（不是取反）：
    `is_arrived`（是「已到站」）/ `is_not_arriving`（是「未到站」）/
    `is_arriving`（是「即将到站」）/ `is_no_bus`（是「暂无车辆」）；
  - 支持「持续」时长（`for`），语义同核心门窗传感器；
  - 保存的 `entity_id` 可能是**实体注册表 ID**（前端行为），文件内自动解析回
    `entity_id`，否则界面保存的条件永远不成立；
  - 数值传感器不重复提供条件（核心 `sensor` 域已按单位给「高于 / 低于」）；
  - 三份语言文件补 `device_automation.condition_type`（两份 translations 仍逐字节一致）。
  （`AB1`~`AB10` 守）

v0.9.19 需求（用户部署 0.9.18 后反馈「现在已经很好了」，但要求**严格与官方
保持一致**，删掉原来的推算兜底口径）：

★ **推算口径整体删除** —— 「剩余站数」与「到站状态」传感器只认 CMD115
  官方文案：官方解析不出（缺失 / 非运营时间 / 未知文案）→ 剩余站数显示
  「未知」、到站状态显示「暂无车辆」，宁缺勿错，不再用本地推算顶上。
  ``arrival_logic.app_style_stops``（0.9.17 App 口径换算）与
  ``arrival_logic.arrival_status``（statusType 内部判定）两个推算函数删除；
  内部几何差 ``remaining`` 只留作最近车辆选取、剩余公里数计算、终点站
  「已到站」误显防护与排查属性「内部剩余站数」。
  （`AA11b` / `AA14` / `U1`~`U3c` 更新守）

v0.9.18 需求（用户继续观察快1路：集成显示 3 站时 App 已显示 2 站，且集成**总是**
慢半站、不是时间窗那种时快时慢；用户怀疑「接口本身提供了已到站/即将到站，我们
把即将到站当成了到达上一站」）：

★ **剩余站数 / 到站状态改为官方文案优先（与掌上公交 App 同源）** ——
  2026-10-28 快1路探针实测（CMD104 + CMD115 每 10 秒对照 4 分钟）确认：
  官方（CMD115 neartext，就是 App 显示的来源）在车**进站停稳**
  （statusType 翻 0）那一刻就减 1，而 CMD104 的 index 要**发车**才跳
  下一站 —— 用 index 推算总比官方慢「一个停站时间」。修复：
  - 新增纯函数 ``official_stops()``（「N站」→ N、「即将到站」→ 1、
    「已到站」→ 0，带终点站「已到站」误显防护）与
    ``official_arrival_status()``（「已到站/即将到站」原文采信、「N站」→ 未到站）；
  - 「剩余站数」与「到站状态」传感器展示值优先解析官方文案（v0.9.19 起只认官方）；
  - CMD104 一辆车都没给但官方是「N站」时照常显示（内部差 None 仍可采信）
  （`AA1`~`AA14` 守）。

v0.9.17 需求（用户拿集成与掌上公交 App 实时数据逐站对比，发现「集成总比 App 小 1」，
如 App 显示 9 站、集成显示 8 站）：

★ **剩余站数改为掌上公交 App 口径** —— App 的「还有 N 站」把车辆**正在驶向 /
  停靠**的那一站也算作还没进的一站（车还要进 N 次站），而内部几何差
  ``remaining = 监控站序 - 即将到达站序`` 已把那一站减掉 → 在途时 App = 内部 + 1。
  修复：新增纯函数 ``app_style_stops()``，「剩余站数」传感器展示值与属性
  ``remaining_stops`` 改用 App 口径（正停在监控站台 = 0 不变），内部原值放新属性
  「内部剩余站数」。到站状态传感器、内部到站判定、剩余公里数、触发器
  挂载均不变。影响：自动化阈值语义随 App（「剩 8 站」= App 显示 8）。
  （`U1` / `U4` / `U3c` 守回归）

v0.9.16 需求（用户部署 0.9.15 后反馈：「实体里的触发器还是有重复的」「到站状态和
公交到站没有合并」）：

★ **五条触发器全部按 device_class 一对一精确挂载** —— 重核 2026.10.2
  `websocket_api/automation.py`：实体过滤器只支持 integration / domain /
  device_class / supported_features（没有 unique_id / entity_id / 排除语法），
  0.9.15 的数值三条（不限 device_class）因此挂到了全部 5 个实体上 —— 这就是
  「每个实体点进去的触发器还是有重复」的根因。修复：给三个数值传感器声明
  **自定义 device_class**（HA 明确支持：`_numeric_state_expected` 把未知
  device_class 按 None 处理，校验不报错；注册表保留原值供触发器匹配）：
  - 「剩余站数」→ ``stop_count``；「剩余公里数」→ ``remaining_distance``；
    「预计到达」→ ``eta``；
  - triggers.yaml 数值三条 target 加上同名 device_class；
  ⇒ 每个实体页只显示自己的触发器：到站状态 2 条、数据同步 1 条、
  剩余站数 / 剩余公里数 / 预计到达各 1 条（`T16` / `T22` / `O8` 守）。
★ **启动时自动清理残留事件实体** —— 0.9.15 删除 event 平台后，HA 实体
  注册表仍保留「公交到站」旧记录（设备页显示「集成 my_bus 不再提供此实体」，
  用户看到的就是「没有合并」）。``__init__.py`` 在 ``async_setup_entry``
  里把本条目名下的 ``event.*`` 注册条目移除，无需用户手动删
  （`T23` / `O9` 守）。

v0.9.15 需求（用户部署 0.9.14 后反馈：「每个实体点进去的触发器是重复的」「那个同步的
触发器不见了」「到站状态和公交到站这两者可以合并」，并要求触发器描述去掉括号说明）：

★ **触发器按实体功能精确挂载** —— 实测 2026.10.2 的实体过滤器只支持
  integration / domain / device_class / supported_features 四个字段（匹配代码
  根本不读 unit_of_measurement，也没有 unique_id / entity_id / 排除语法），
  因此给实体声明 device_class 作为挂载判别符：
  - 「到站状态」传感器：``device_class: enum`` + ``options``（四个状态）；
  - 「数据同步」传感器：保持 ``timestamp``；
  - ``arrival_arrived`` / ``arrival_arriving`` → target device_class: enum；
    新增 ``data_sync``（数据同步完成）→ target device_class: timestamp；
    数值三条保持 integration + domain sensor（v0.9.16 起改为按自定义
    device_class 一对一挂载，见文首）。
★ **「公交到站」事件实体与 ``bus_arrived`` 触发器删除**（用户：「到站状态和
  公交到站可以合并」）—— ``event.py`` / ``Platform.EVENT`` / ArrivalTracker /
  ArrivalEventData / EVENT_BUS_ARRIVED / pending_events 全部移除，
  到站判断全部并入「到站状态」传感器（`Q7` / `T19` 守）。
★ **「数据同步」实体不再是诊断类** —— 新触发器体系的实体树会隐藏诊断实体，
  不取消就选不到「数据同步完成」触发器（`O3` / `T20` 守）。
★ **触发器描述去掉括号说明**（用户要求），三份语言文件同步（`T21` 守）；
  旧版 ``device_trigger.py`` 同步删除 bus_arrived（`R1`~`R4` 守）。

v0.9.14 需求（部署 0.9.13 后用户反馈「新建自动化还是和原来的一样」；
浏览器实测 + 直连 HA 2026.10.2 + 对照 HA 核心与前端源码定位根因后重做）：

★ **接入 HA 新版触发器体系（trigger.py + triggers.yaml）** —— 新版
  「添加触发条件 → 按目标」对话框走 `get_triggers_for_target` WebSocket 命令，
  数据源是核心的**新触发器注册表**（集成 `trigger.py` 平台 + `triggers.yaml`
  描述 + translations 的 `triggers` 段翻译），**完全不读旧版
  device_trigger.py** —— 这就是 0.9.13 服务端 `device_automation/trigger/list`
  数据全对、界面却纹丝不动的根因。修复：
  - 新增 ``trigger.py``：六个新式触发器（键 → ``my_bus.<key>``）
    ``bus_arrived``（事件实体，仿核心 event.received）、
    ``arrival_arrived`` / ``arrival_arriving``（目标状态 = 已到站 / 即将到站，
    仿核心 battery 的 became_low，门窗式）、
    ``remaining_stops`` / ``remaining_km`` / ``eta``（数值变化，
    threshold 选择器 numeric_threshold changed 模式：任意变化 / 高于 / 低于 /
    区间，温湿度式）；全部用核心基类 / 工厂实现，非数值状态不触发；
  - 新增 ``triggers.yaml``：target 全部限定 ``integration: my_bus`` +
    ``domain: sensor/event``；数值触发器 threshold 字段带单位（站 / 公里 / 分钟）；
  - 新增 ``icons.json``：六个触发器图标；
  - strings.json 与两份 translations 加 ``triggers`` 段（前端按
    ``component.my_bus.triggers.<key>.name`` 读取；两份 translations
    仍逐字节一致且全中文）；
  - 旧版 ``device_trigger.py`` 保留不动，老自动化继续可用。
  - 核心版本对照：HA 2026.10.2 的 event / battery 组件（trigger.py +
    triggers.yaml + strings.json triggers 段）与 helpers/trigger 基类。
  （`T1`~`T18` 守）

v0.9.13 需求（用户：「到站状态参考门窗传感器或开关，剩下 3 个参考温湿度传感器，
看一下小米的集成是怎么做的」；直连用户 HA 实测小米触发器结构后重做）：

★ **设备触发器全面对齐 HA 核心标准样式**（小米集成自己零自定义触发器，
  靠 device_class 让核心生成；我们是自定义集成，按同样形态手写）：
  - 门窗式：``arrival_arrived``（公交已到站）/ ``arrival_arriving``（公交即将到站），
    独立触发器、选中即生效，不再用「目标状态」下拉框；
  - 温湿度式：``remaining_stops`` / ``remaining_km`` / ``eta``，capabilities 给
    「高于 / 低于」两个可选数字框（``vol.Optional(..., description={"suffix": 单位})``，
    与核心传感器触发器同款）；above/below 都不填 = 任意数值变化；非数字状态（如
    「暂无数据」）不触发；
  - 触发器带 ``entity_id``（实体注册表 ID，核心/小米都带），卡片显示所属实体；
  - 界面列表只列 6 个标准触发器；0.9.8~0.9.12 的 4 个旧类型保留校验与挂接
    （老自动化不报错）但不再列出（`R36`~`R46` 守）。
★ 实测用户 HA（WebSocket device_automation/trigger/list + capabilities）：
  门窗传感器 = opened/not_opened；温湿度计 = temperature/humidity/battery_level，
  extra_fields = {"type":"float","name":"above","description":{"suffix":"°F"}} 等。

v0.9.12 需求（translations 的 trigger_type 必须是纯字符串，否则前端显示英文名/「未知」）：

v0.9.12 需求（用户：「0.9.11 不行，只有你自己可以操作，请根据 Home Assistant
的规范重新设计自动化功能」；远程核查确认根因后重做）：

★ **修正 translations 里 trigger_type 的取值形态** —— HA 规范：
  ``strings.json`` 里 ``device_automation.trigger_type`` 用
  ``{"name": ..., "description": ...}`` 对象形式（hassfest / 文档用）；
  但**运行时前端读取的 ``translations/<lang>.json`` 必须是纯字符串**
  （``"bus_arrived": "公交到站"``）。0.9.8 起三份文件全写成对象形式，
  前端取不到中文标签 → 设备触发器列表显示原始英文名（bus_arrived、
  arrival_status_changed…）或「未知」，用户在标准界面流程里根本没法选。
  修复：``translations/zh-Hans.json`` 与 ``translations/en.json`` 里
  trigger_type 全部改为纯字符串（`R33`~`R35` 守）；
  ``strings.json`` 保留对象形式（它的规范用途就是文档）。
  修复后标准流程可用：添加触发条件 → 设备 → My Bus → 列表显示
  公交到站 / 剩余站数变化 / 剩余公里数变化 / 预计到达变化 / 到站状态变化。

v0.9.11 需求（远程核查用户 HA 发现：0.9.10 的下拉框值保存被拒）：

★ **TRIGGER_SCHEMA 声明接受 ``to`` 字段** —— HA 的设备自动化基础 schema 是
  PREVENT_EXTRA（多余键一律拒绝）；0.9.10 的「目标状态」下拉框值 ``to`` 没在
  集成的 TRIGGER_SCHEMA 里声明，真机上界面选完保存报
  「not a valid option at 'to'」（REST POST /api/config/automation/config 实测 400）。
  修复：TRIGGER_SCHEMA 里加 ``vol.Optional("to"): str``（`R30`~`R32` 守）。

v0.9.10 需求（用户：「有没有办法在集成里面做出修改，使得用户可以下拉选择呢」）：

★ **「到站状态变化」触发器带「目标状态」下拉框** —— ``async_get_trigger_capabilities``
  对 ``arrival_status_changed`` 返回 SelectSelector（未到站 / 即将到站 / 已到站），
  选中后只在状态变为该值时触发，界面里选、不用手打中文（`R25`~`R28` 守）。
★ 其余触发器的 capabilities 仍为空（`R3` 继续守）。

（真机 bug 修复：远程核查用户 HA 时发现「公交到站」设备触发器永不触发）：

★ **根因** —— HA 的 EventEntity 规范：实体的 ``state`` 是**时间戳**，事件类型在属性
  ``event_type`` 里；旧代码比较 ``state == "bus_arrived"``，真机上永不成立
  （测试桩里 FakeState 的 state 直接是 "bus_arrived"，掩盖了问题）。
★ **修复** —— ``device_trigger._attach_arrived`` 改为检查属性 ``event_type``；
  同时保留 ``state == "bus_arrived"`` 兼容旧桩（`R22` / `R23` / `R24` 守）。

（用户：「我希望这4个传感器的状态变化可以作为自动化的触发条件，请删除无效和多余的自动化」）：

★ **设备触发器扩展为 5 个** —— 「公交到站」（事件，最可靠）之外，4 个实时传感器各有一个
  「状态变化」触发器（``remaining_stops_changed`` / ``remaining_km_changed`` /
  ``eta_changed`` / ``arrival_status_changed``），只在**状态值**变化时触发
  （属性变化不算、实体刚注册不算）（`R16`~`R21` 守）。
★ **删除无效多余的自动化遗留** —— ``bus_arriving`` 兼容桩整个删除（0.9.1 起它就永不触发）：
  schema 不再接受，语言文件里的「公交即将到站（已停用）」条目删除（`R2` / `R14` 守）。
  传感器 entity_id 由 sensor.py 按 translation_key 登记到 ``coordinator.sensor_entity_ids``。


v0.9.6 需求（用户：「想让配置向导看上去更美观可以吗」，全选三项）：

★ **标题 emoji 体系** —— translations 里 config.step.* / options.step.* 的 title
  全部带上主题 emoji（📍 城市 / 🚏 站台 / 🚌 线路 / ⏱ 参数 / 🔄 同步 / ✅ 确认 /
  🔍 检索子页 / 🧭 检索方式 / 🏙 浏览城市 / 🔁 修改线路）；同类操作永远同一 emoji
  （`Z1` 守）。
★ **确认页分块排版** —— 确认清单分「── 监控内容 ──」与「── 参数 ──」两块，中间空行
  （`Z2` / `Z3` 守）。
★ **候选列表视觉提示** —— 站台候选加「🚏 」、线路候选加「🚌 」前缀；城市候选保持
  裸名称（563 条太长，逐条多念一个 emoji 名反而拖慢读屏）（`Z4` / `Z5` 守）。


v0.9.5 需求（用户：「配置向导的第7步，是不是少了同步的内容呢」）：

v0.9.5 需求（用户：「配置向导的第7步，是不是少了同步的内容呢」）：

★ **第 7 步确认页补上「自动同步：每 N 小时 / 已关闭」一行** —— 0.9.1 删阈值两行后
  确认清单只剩 城市/站台/线路/刷新间隔 四行，同步设置没在里面。自动同步是**全局**
  数据同步层状态（跨条目共享），只作展示；同步层不可用时如实显示「未启用」
  （`C11` / `D7` / `W14` / `W15` 守回归）。


v0.9.4 需求（用户：「我还要去掉控制的那个同步按钮」）：

★ **设备页「控制」区的「立即同步」按钮删除** —— `button.py` 整个文件删除、
  ``PLATFORMS`` 移除 ``Platform.BUTTON``、三份语言文件的 ``entity.button`` 节删除。
  手动同步入口不丢：``my_bus.sync_data`` 服务与选项菜单「🔄 数据同步」仍在
  （`O1` / `V4` 守回归）。


v0.9.3 需求（用户：「如果没有官方数据时显示为暂无数据，不用本地推测的可不可以，这样尽量和官方数据一致」）：

★ **预计到达只认官方数据** —— CMD115「N分钟/M米」或「已到站」（→ 0 分钟）之外的
  一律显示**「暂无数据」**：本地按均速 / 站数推测的 ``estimate_eta_minutes`` 从
  ``arrival_logic`` 删除，ETA 传感器不再设 ``state_class``（状态可能是数字或字符串），
  属性「预计到达来源」只在有官方数据时为「官方」、否则 None（`U2` / `U6` / `U6b` /
  `U7` / `U8` / `U9` / `Y11` 守回归）。对自动化的影响：数字状态触发器遇到
  「暂无数据」自动跳过不误触发；「公交到站」触发器完全不受影响。


v0.9.2 需求（用户看了「掌上公交接口还提供了哪些状态」的分析后拍板：**「好的，按照你的做」**
= 建议清单里的 ①② 两项）：

★ **① 预计到达官方化** —— CMD115 的官方 ``neardis``（如「2分钟/180米」「3分钟/1公里」）
  提供了**官方分钟级预计到达**。协调器每轮顺带拉一次 CMD115（按站台+线路+方向匹配，
  失败不阻塞实时数据），「预计到达」传感器优先显示官方分钟数，官方缺失时才退回
  均速估算；实体属性新增「预计到达来源」（官方 / 估算）与
  「官方原文」；实体名去掉「（实验性）」后缀（`Y1`~`Y9`、`U2c` 守回归）。

★ **② 到站判定官方化** —— CMD104 每辆车的 ``statusType``：``"0"`` = 车正停在
  即将到达站（已到站，距离恒 0 米）、``"2"`` = 在途。``bus_arrived`` 只在
  「剩余站数 == 0 **且** 官方确认停站」时触发（消灭「剩 0 站但车还在途」的误报）；
  接口没给 ``statusType``（老客户端 / 测试桩）时退回老口径。「到站状态」传感器恢复
  三态：``未到站 / 即将到站 / 已到站``——剩 0 站但在途 = 即将到站（`Q7`~`Q13b`、`U3b` 守回归）。

v0.9.1 需求（用户：「现在请移除第5步的提前多少公里提醒和提前多少站提醒，这两项相关的功能也一并移除」；范围确认：**彻底移除** —— 删掉两个参数输入框、站数/公里阈值触发逻辑、设备触发器与条件里的「少于多少站/公里」项；保留「已到站」事件与全部传感器）：

★ **第 5 步表单只剩「数据刷新间隔」一个字段** —— 提前站数 / 提前公里数从向导、选项流、确认页、创建条目的 options 里全部拿掉（`B5`~`B9`、`H1`~`H12`、`J9`~`J11` 守回归）。

★ **ArrivalTracker 只剩「已到站」一种事件** —— 车辆剩余站数变为 0 时触发一次 ``bus_arrived``；「即将到站」事件、``reason`` 字段（stops/distance）、阈值字段全部删除（`Q7`~`Q13` 守回归）。

★ **设备触发器只列「公交到站」** —— ``bus_remaining_below`` / ``bus_distance_below`` 两个触发器删除；``device_condition.py`` 整个文件删除（两个条件全是阈值类）；老的 ``bus_arriving`` 类型保留在 schema 里让旧自动化不报错，但永远不会触发（`R1`~`R10` 守回归）。

★ **到站状态传感器变二元** —— 只剩「未到站 / 已到站（暂无车辆）」，不再有「即将到站」（`U3` / `U5` 守回归）。

v0.9.0 需求（用户：「第一.每一步的『⬅ 返回上一步』请放置于相同的位置，在前几轮对话中，
我们已经把他放在左上角的位置……第二.在第1步的『🔍 检索城市名』和第3步的『🔍 检索站台』
和『🔍 检索线路』的按钮也要放置于相同位置，这样便于用户理解。第三.我们还要修改一些
文案：……」；补充说明：「第一步就不存在上一步，所以『欢迎使用 My Bus，这是一个实时
公交监控集成。』占据了那个位置」）：

★ **① 按钮版式全流程统一（位置层面不改逻辑，只做核查 + 固化）**
  - 「⬅ 返回上一步」在**每一页都排在按钮列表第一位**（左上角），文案也完全一致；
  - 第 1 步是流程起点、**没有**上一步，那一页由说明区第一行的**欢迎语**占位
    —— 于是「🔍 检索…」在整页里的落点是同一个：第 1 步 = 说明区 3 段 + 按钮第 1 个，
    第 3 步 = 说明区 2 段 + 按钮第 2 个 ⇒ 两边都是**整页第 4 个元素**。
  ⇒ `X1`~`X4` 用 `page_index()`（说明区段数 + 按钮下标）把这条量化守住。

★ **② 文案精简**（逐条对应用户给的原句）
  - 第 1 步提示：`不知道城市名，可以点「定位当前城市」。`
    → **`请检索城市名，或通过 Home Assistant 地图定位城市，或显示城市列表。`**
  - 第 2 步提示：`知道站名选「先选站台」，知道线路号选「先选线路」。`
    → **`先选站台然后选择停靠线路，或先选线路然后选择途经站台。`**
  - 第 4 步步骤名：`选择途经站台` → **`选择站台`**（语言文件两个 scope 的 title 同步）；
    提示去掉「点要在哪站提醒」，只留 **`线路「…」（…）途经 N 站。`**
  - 第 5 步步骤名：`到站提醒参数` → **`选择到站参数`**；
    提示 → **`选择刷新频率和预设范围。`**；表单说明 → **`输入数字。`**；
    三个字段名的括号：`（秒，填 5 到 120）` → **`（秒，范围 5 到 120）`**（另两个同理，
    自动同步间隔一并统一成「范围 1 到 168」）。
  - 两个「下一步」按钮：`⏭ 下一步：数据同步` / `⏭ 下一步：确认创建` → **统一 `⏭ 下一步`**；
  - 第 6 步开场白：`创建前可以先把数据同步到最新；不改也能直接下一步。`
    → **`创建前可以先把数据同步到最新。`**
  - 第 7 步提示：`确认无误点「完成」，要改就点「⬅ 返回上一步」。` → **`请确认配置`**
  ⇒ `X5`~`X12` 守回归。累计 **321 项**。

v0.8.9 需求（用户：「需要在向导的第5步和第6步之间再加上一步『数据同步』，与选项的
『数据同步』相应。原来的第6步改为第7步，文案也要做出调整。去掉第1步的同步按钮。」）：

★ **① 向导插入第 6 步「数据同步」** —— 原来第 5 步「到站提醒参数」的下一个按钮
  直接去「确认创建」，现在改成先去**「数据同步」**（`to_sync`），到确认页要先过
  这一步。这一步与**选项菜单里的「🔄 数据同步」共用同一套实现**（同一个
  `step_id` = `sync`、同一批按钮：立即同步 / 修改同步间隔 / 关闭或启用自动同步、
  同一批文案），差别只有两处：说明区开场白（向导讲「创建前可以先同步」，选项讲
  缓存规模）与出口（向导多一个「⏭ 下一步：确认创建」，选项靠「⬅ 返回选项菜单」）。
  ⇒ 向导步数 `WIZARD_TOTAL` 6 → **7**，抬头变成「第 N 步 / 共 7 步」
  （`A10b` / `A16` / `A16a` / `A18` / `H14` 守回归；新增 `[W]` 组 `W1`～`W12`）。

★ **② 「确认创建」从第 6 步变成第 7 步**，连带调整的文案：
  - 第 5 步的下一步按钮：`⏭ 下一步` → **`⏭ 下一步：数据同步`**（`act_next_sync`）；
  - 第 6 步（数据同步）的下一步按钮：**`⏭ 下一步：确认创建`**（`act_next_confirm`）；
  - `config.step` 语言文件里新增 `sync` 一档（标题「数据同步」）；
  - 「上一步」链：确认页 → 数据同步页 → 参数页（`D1` / `D4` 守回归）。

★ **③ 第 1 步去掉「🔄 同步最新数据」按钮** —— 同步挪到第 6 步后，第 1 步只留
  三个按钮：`🔍 检索城市名` / `📍 定位当前城市` / `🏙 全部城市列表（共 N 个）`；
  随之清掉死文案 `act_city_sync` 与 `h_sync_ok`（`E1` / `E1b` / `I17` 守回归）。

v0.8.8 需求（用户：「第一.还要在传感器中添加一个剩余公里数，位置在剩余站数和预计
到达之间。第二.要有一个控制，里面是同步按钮，可以进行手动同步。」）：

★ **① 新增「剩余公里数」传感器** —— 设备页实时信息的顺序变成
  `剩余站数` → **`剩余公里数`** → `预计到达（实验性）` → `到站状态`。值 = 接口给的线路里程
  （`distance_m`）换算成公里、保留 1 位小数；没有分段里程时显示「未知」
  （纯函数 `arrival_logic.distance_km()`，`V1`～`V6` 守回归）。
  ⚠️ 用户还要求把「预计到达」实体名标成**「预计到达（实验性）」** —— 接口不提供时间，
  分钟数只是按均速 / 每站 2 分钟推出来的约数，名字里点明这一点（`U12b` 守回归）。

★ **② 新增「控制」区的「立即同步」按钮** —— HA 的设备页只在「控制」区块渲染
  按键类实体，所以新增 `button` 平台（`button.py`），设备页上出现一个
  `立即同步` 按钮。按下即走数据同步层的 `async_sync()`（与 `my_bus.sync_data`
  服务同一条路径），同步完再请协调器立即刷新一次，不用等下一轮轮询
  （`V7`～`V12` 守回归）。

v0.8.7 需求（用户：「能否实现在设备页中展示公交实时信息呢，如3站 4分钟 未到站」）：

★ **设备页新增 3 个实时到站传感器** —— HA 的设备页只能展示「该设备的实体」，
  所以给监控设备加：`剩余站数`（单位「站」）/ `预计到达`（单位「分钟」）/
  `到站状态`（未到站 / 即将到站 / 已到站）。三者都只看**离监控站台最近的一辆车**，
  车牌 / 当前站 / 剩余里程等放在实体属性里。
  ⚠️ 掌上公交接口**不提供时间**，`预计到达` 是按「里程 ÷ 20km/h 均速」或
  「站数 × 2 分钟」估算的约数（`U1`～`U13` 守回归）。

v0.8.6 需求（用户：「把设备信息中的『厦门市公交到站监控』改成『公交到站监控』」）：

★ **设备信息里的「型号」不再带城市前缀** —— `sensor.py` 与 `event.py` 的
  `DeviceInfo(model=...)` 曾是 `f"{city}公交到站监控"`（如「厦门市公交到站监控」），
  现在改成固定的 **`公交到站监控`**。设备名 `My Bus（厦门市 615路 县口路站）` 里已经写明
  城市与线路，型号再重复一遍城市反而啰嗦（`O2b` / `O2c` 守回归）。

v0.8.5 需求（用户：「我已经把 Home Assistant 的集成删除了。这时候如果你也把域名
改成 My Bus 会影响吗」）：

★ **域名由 `xm_bus` 改为 `my_bus`** —— 0.8.4 只改了显示名（manifest 的 `name`），
  域名字段一直是 `xm_bus`。用户已把集成从 HA 删除 ⇒ 配置条目不存在，正是零成本
  改域名的窗口期，故本版一并改掉。HA 规定 domain 只能用小写字母 + 数字 + 下划线，
  所以是 `my_bus` 而不是带空格的 `My Bus`（`My Bus` 是显示名）。
  安装目录 `custom_components/my_bus/`、服务名 `my_bus.*`、存储文件
  `.storage/my_bus.data`、实体前缀 `my_bus_*` 全部跟随改名（`S7` / `S8` / `S9` 守回归）。

v0.8.4 需求：

① **第 1 步的第一行不再是检索按钮** —— 用户：「第 1 步的『🔍 检索城市名』和第 3 步的
   『🔍 检索站台 / 检索线路』能否放置在相同的位置」。根因是第 1 步是向导起点，没有
   「⬅ 返回上一步」可放，于是整页第一个元素就是检索按钮，和第 3 步「第一行导航、
   第二行检索」的版式对不上。用户给的方案：**第 1 步第 1 位写上欢迎语** ——
   现在说明区第一行是「欢迎使用 My Bus，这是一个实时公交监控集成。」，抬头退到
   第二行（`S1` / `S1b` / `S1c` 守回归）。欢迎语只在**向导**第 1 步的**落地页**
   （`city`）出现：子页（关键词表单 / 全部城市列表）与选项流的「修改城市」都不
   重复（`S2` / `S3` / `S4` 守回归）。
② **集成改名为 My Bus** —— 原「XM Bus」含地名缩写（厦门），而集成早已覆盖掌上
   公交全国 563 个城市。manifest 的 `name`、设备制造商、设备名、选项菜单标题、
   README 全部改为 **My Bus**（`S6` / `S10` 守回归）。当时域名仍是 `xm_bus`，
   到 0.8.5 才一并改掉。

v0.8.3 需求（用户圈定：「2、7」）：

② **抬头不再重复步骤名** —— v0.8.0 只是把「第 N 步 · 」从对话框标题挪到了说明
   区（抬头），步骤名照旧被念两遍：「选择站台 …… 第 3 步 / 共 7 步 · 选择站台」。
   现在抬头只留「第 N 步 / 共 7 步」，步骤名交给对话框标题（`I16c` 守回归）。
⑦ **检索结果被截断时要说出来** —— 掌上公交的关键词检索单次最多约 30 条，命中数
   触顶时用户会以为「就这么几条」。现在提示补一句
   「（关键词检索一次最多返回 30 条，可多加一个字收窄。）」（`F9` / `G8b` 守回归）。

v0.8.2 需求（用户反馈：「第3步的选择站台或选择线路会显示『第 3 / 4 步』」）：
① 真 bug——站台优先时「选择线路」是第 4 步，但它的输入子页 ``line_keyword``
   写死返回第 3 步，用户点「🔍 检索线路」时抬头会从第 4 步掉回第 3 步；
   现在输入子页与父页同号（`H14`/`H14b` 守回归）。
② 用户看到的「第 3 / 4 步」字面串其实来自 **0.7.0 的旧标题**
   （`config.step.line.title` = `第 3 / 4 步 · 选择线路`），0.8.x 的标题里
   已不含步号；`I16b` 禁止标题里再出现任何数字。

v0.8.1 需求（用户原话：「向导要恢复到6步，其他的不改动」）：把 v0.8.0 并掉的
第 2 步「选择检索方式」恢复成独立的一步（`WIZARD_TOTAL` 5 → 6），并去掉 v0.8.0
加在站台页 / 线路页上的互跳按钮；**v0.8.0 的其它 7 项与 emoji 规则全部保留**。
步骤重新变成：城市 → 检索方式 → 站台/线路 → 线路/途经站台 → 参数 → 确认。

v0.8.0 需求（用户原话：「现在这个向导还有什么可以改进的吗。我希望这个向导既符合
普通人的使用，也符合盲人通过读屏软件使用他」，随后圈定 8 项）：

④ **每一页的第一个按钮都是「⬅ 返回上一步」** —— 读屏是按 Tab 顺序逐个听按钮的，
   「全部城市列表」这类页面有几百个候选项，返回排在最后就得听完整个列表才够得到；
⑦ **对话框标题只写步骤名**（去掉「第 N 步 · 」）—— 步号只在说明区出现一次，
   否则读屏会把「第 1 步 · 选择城市」念两遍；
⑧ **说明区不重复按钮上已经写着的当前参数**，表单说明也不再重复字段名里的范围；
⑩ **第 3 步「选择途经站台」用真实起终点标注方向**（四林总站→丙洲东头尾站），
   不再只写「上行 / 下行」；
⑬ 「全部城市列表」按钮带上城市总数（读屏也知道有多少个）；
⑭ 清掉死文案与死参数（`back_none` / `h_mode` / `step_mode` / `menu_back_init` /
   `h_checking` / `opt_unchanged`，以及 `h_city` 的 `when=`、`h_sync_interval` 的
   `max_hours=`）；
⑮ **范围夹取从「只靠前端 NumberSelector」改成后端也兜一层**：新增
   `normalize_poll_interval()` / `normalize_threshold()`（0 秒会让协调器变成忙轮询）；
⑯ **「先选站台 / 先选线路」曾经不单独占一步**（第 2 步同时给出两个检索入口、
   6 步 → 5 步），后来**用户要求恢复成 6 步**——现在它又是独立的第 2 步，
   站台页 / 线路页上的互跳按钮一并去掉，完全回到 0.7.0 的结构。

历史需求（v0.5.0 起的无障碍基线，仍然全部守在这里）：

① **每一步都是按钮，不是开关**：把全部步骤做成 HA 的菜单（menu），
   候选与「上一步」都渲染成真正可点击的按钮；只有需要键盘输入的地方才用表单。
   全程不出现 BooleanSelector；
② **每一步都有真实的「⬅ 返回上一步」按钮**，且指回用户真正的来路
   （`_trail` 足迹记录，选项流里跳过参数页也不会指错）；
③ **不会出现英文**：按钮文字写死在 Python 里、不走翻译层；
   strings.json / zh-Hans.json / en.json 三份内容完全一致且全部中文；
   表单字段名用中文文本做键兜底；
④ 失败不中断流程：创建 / 校验失败留在当前步给中文提示；
⑤ CMD108（坐标反查城市）接口抖动时退避重试，不误报「不在服务范围」；
⑥ 选项流复用同一套向导步骤，「上一步」的终点是选项菜单。

历史回归：v0.7.0 站数去掉 0（1~5）+ 提前里程 0.1~20 + 4 触发器 / 2 条件、
v0.5.1 文案对齐 0.3.0 的简洁风格、v0.4.0 的向导与选项流、
v0.3.0 数据同步层（缓存 / 定期同步 / 站序自动修正）、v0.2.0 全国城市 + 坐标识别、
v0.1.7 参数页两个数字输入框、v0.1.6 站台每站一条 + 反向站台。
"""

from __future__ import annotations

import asyncio
import collections
import importlib
import json
import os
import re
import sys
import time
import types
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stub_ha  # noqa: E402

stub_ha.install()
cf = stub_ha._load_config_flow()
api = importlib.import_module("my_bus.api")
logic = importlib.import_module("my_bus.arrival_logic")
ds = importlib.import_module("my_bus.data_sync")
coord_mod = importlib.import_module("my_bus.coordinator")
svc = importlib.import_module("my_bus.services")
diag = importlib.import_module("my_bus.diagnostics")
entry_init = importlib.import_module("my_bus")
const_mod = importlib.import_module("my_bus.const")

MODE_STATION_FIRST = cf.MODE_STATION_FIRST
MODE_LINE_FIRST = cf.MODE_LINE_FIRST
BACK = cf.KEY_BACK
T = cf._T

# 伪造的掌上公交城市列表（含脏数据，用于验证清洗）
FAKE_CITIES = [
    "厦门市",
    "厦门市测试",
    "厦门市1",
    "北京市",
    "上海市",
    "福州市",
    "广州市",
    "泉州市",
    "漳州市",
    "长沙市",
    "深圳市",
]
FAKE_CITY_COUNT = 9

# 伪造的线路站点拓扑（可被单个用例改写以模拟掌上公交改线）
DEFAULT_TOPOLOGY = {
    ("615路", "1"): [
        {"stationName": "四林总站", "stationOrder": 1},
        {"stationName": "梨子林站", "stationOrder": 2},
        {"stationName": "县口路站", "stationOrder": 12},
        {"stationName": "四林总站", "stationOrder": 99},
    ],
    ("615路", "2"): [
        {"stationName": "丙洲东头尾站", "stationOrder": 1},
        {"stationName": "县口路站", "stationOrder": 5},
        {"stationName": "同安汽车站", "stationOrder": 6},
    ],
    ("618路", "2"): [
        {"stationName": "方特旅游区站", "stationOrder": 1},
        {"stationName": "1号站", "stationOrder": 3},
        {"stationName": "县口路站", "stationOrder": 7},
    ],
}

DEFAULT_ENDPOINTS = {
    ("615路", "1"): ("四林总站", "丙洲东头尾站"),
    ("615路", "2"): ("丙洲东头尾站", "四林总站"),
    ("618路", "2"): ("方特旅游区站", "梧侣公交场站"),
}

_HERE = os.path.dirname(__file__)
_CC = os.path.join(_HERE, "..", "custom_components", "my_bus")
_ROOT = os.path.join(_HERE, "..")
STRINGS = json.load(open(os.path.join(_CC, "strings.json"), encoding="utf-8"))
EN = json.load(open(os.path.join(_CC, "translations", "en.json"), encoding="utf-8"))
ZH = json.load(open(os.path.join(_CC, "translations", "zh-Hans.json"), encoding="utf-8"))

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(("  OK   " if cond else " FAIL  ") + name + ("" if cond or not detail else f"  -> {detail}"))


# ---------------------------------------------------------------------------
class FakeClient:
    """镜像真实客户端（ALL=1 返回两方向线路，direction 参数做过滤）."""

    def __init__(
        self,
        *,
        fail_station=False,
        fail_line=False,
        empty=False,
        fail_cities=False,
        fail_topology=False,
        located="厦门市",
        city="厦门市",
        topology=None,
        endpoints=None,
        preview=None,
    ):
        self.fail_station = fail_station
        self.fail_line = fail_line
        self.empty = empty
        self.fail_cities = fail_cities
        self.fail_topology = fail_topology
        self.located = located
        self.city = city
        self.topology = topology if topology is not None else DEFAULT_TOPOLOGY
        self.endpoints_map = endpoints if endpoints is not None else DEFAULT_ENDPOINTS
        self.preview_data = preview      # CMD115 官方到站预览（None = 没查到）
        self.calls = collections.Counter()
        self.locate_calls: list[tuple[float, float]] = []

    # -- CMD101 / CMD108 --------------------------------------------------
    async def cities(self):
        self.calls["cities"] += 1
        if self.fail_cities:
            raise api.XmBusApiError("boom")
        return list(FAKE_CITIES)

    async def locate_city(self, latitude, longitude):
        self.calls["locate_city"] += 1
        if self.fail_cities:
            raise api.XmBusApiError("boom")
        self.locate_calls.append((latitude, longitude))
        return self.located

    # -- CMD110 / CMD114 --------------------------------------------------
    async def search_stations(self, keyword):
        self.calls["search_stations"] += 1
        if self.fail_station:
            raise api.XmBusApiError("boom")
        if self.empty:
            return []
        return [api.StationHit(name=n) for n in ("同安一中站", "县口路站", "1号站", "同安汽车站")]

    async def search_lines(self, keyword):
        self.calls["search_lines"] += 1
        if self.fail_line:
            raise api.XmBusApiError("boom")
        if self.empty:
            return []
        return [
            api.LineHit(line_name="615路", direction="1", from_stop="四林总站", to_stop="丙洲东头尾站"),
            api.LineHit(line_name="615路", direction="2", from_stop="丙洲东头尾站", to_stop="四林总站"),
            api.LineHit(line_name="615路", direction="1", from_stop="四林总站", to_stop="丙洲东头尾站"),
        ]

    # -- CMD115 -----------------------------------------------------------
    async def station_lines(self, station, direction=None):
        self.calls["station_lines"] += 1
        if self.fail_line:
            raise api.XmBusApiError("boom")
        if self.empty:
            return []
        hits = [
            api.LineHit(line_name="618路", direction="2", from_stop="方特旅游区站", to_stop="梧侣公交场站"),
            api.LineHit(line_name="619路", direction="2", from_stop="三秀山站", to_stop="乐海公交场站"),
            api.LineHit(line_name="615路", direction="1", from_stop="四林总站", to_stop="丙洲东头尾站"),
            api.LineHit(line_name="615路", direction="1", from_stop="四林总站", to_stop="丙洲东头尾站"),
        ]
        if direction:
            hits = [h for h in hits if h.direction == direction]
        return hits

    # -- CMD103 -----------------------------------------------------------
    async def line_stations(self, line, direction):
        self.calls["line_stations"] += 1
        if self.fail_topology:
            raise api.XmBusApiError("拓扑不可用")
        return [dict(item) for item in self.topology.get((line, str(direction)), [])]

    # -- CMD114 全量 -------------------------------------------------------
    async def line_endpoints(self, force=False):
        self.calls["line_endpoints"] += 1
        return dict(self.endpoints_map)

    # -- CMD104 实时车辆位置 ------------------------------------------------
    async def realtime(self, line, direction):
        self.calls["realtime"] += 1
        return [api.BusPosition(plate="闽D-TEST", current_stop="梨子林站", position=2)]

    # -- CMD115 官方到站预览（v0.9.2） --------------------------------------
    async def station_preview(self, station, line, direction):
        self.calls["station_preview"] += 1
        if self.preview_data is None:
            return None
        if isinstance(self.preview_data, Exception):
            raise self.preview_data
        return dict(self.preview_data)


class OneStationClient(FakeClient):
    """站台检索只返回 1 条（用于验证「唯一结果自动采用」）."""

    async def search_stations(self, keyword):
        self.calls["search_stations"] += 1
        return [api.StationHit(name="县口路站")]


class NoLinesClient(FakeClient):
    """站台存在、但该站台上查不到任何线路."""

    async def station_lines(self, station, direction=None):
        self.calls["station_lines"] += 1
        return []


class DownOnlyClient(FakeClient):
    """该站台只有下行侧线路（用于验证自动换向）."""

    async def station_lines(self, station, direction=None):
        self.calls["station_lines"] += 1
        hits = [
            api.LineHit(line_name="618路", direction="2", from_stop="方特旅游区站", to_stop="梧侣公交场站"),
        ]
        if direction:
            hits = [h for h in hits if h.direction == direction]
        return hits


# ---------------------------------------------------------------------------
def make_sync(hass, client, *, cities=None, last_sync=None):
    """在 hass.data 里挂一个「客户端已就绪」的数据同步层（默认城市已缓存）."""
    sync = ds.XmBusDataSync(hass, lambda city: client)
    sync._loaded = True
    if cities is not None:
        sync._put(ds.KEY_CITIES, list(cities))
        sync._last_sync = time.time() if last_sync is None else last_sync
    hass.data.setdefault("my_bus", {})["sync"] = sync
    for name in FAKE_CITIES:
        hass.data["my_bus"].setdefault(f"client::{name}", client)
    return sync


# ---------------------------------------------------------------------------
# v0.5.0 菜单式向导的测试辅助
# ---------------------------------------------------------------------------
PICK = cf.KEY_PICK


class FakeEntry:
    """一条已创建的监控条目."""

    def __init__(self, **overrides):
        self.data = {
            "city": "厦门市",
            "station": "县口路站",
            "line": "615路",
            "direction": "1",
            "station_order": 12,
        }
        self.data.update(overrides)
        self.options = {
            "poll_interval": 10,
        }
        self.entry_id = "e1"
        self.title = f"{self.data['city']} {self.data['line']} {self.data['station']}"
        self.domain = "my_bus"
        self.version = 2


class NoMatchClient(FakeClient):
    """站台检索永远查不到（验证「没有找到」提示）."""

    async def search_stations(self, keyword):
        self.calls["search_stations"] += 1
        return []


class NoLineMatchClient(FakeClient):
    """线路检索永远查不到（验证「没有找到」提示）."""

    async def search_lines(self, keyword):
        self.calls["search_lines"] += 1
        return []


class ManyStationsClient(FakeClient):
    """站台检索刚好命中 30 条 —— 掌上公交关键词检索的单次上限.

    用于验证：命中数触顶时提示会如实说明「被截断」，而不是让用户以为
    「就这么几条」。
    """

    async def search_stations(self, keyword):
        self.calls["search_stations"] += 1
        return [api.StationHit(name=f"{i}号站") for i in range(1, 31)]


class ManyLinesClient(FakeClient):
    """线路检索刚好命中 30 条（同样是单次上限）."""

    async def search_lines(self, keyword):
        self.calls["search_lines"] += 1
        return [
            api.LineHit(
                line_name=f"{i}路", direction="1", from_stop="起点站", to_stop="终点站"
            )
            for i in range(1, 31)
        ]


def new_flow(client, *, cities=None, seed_cities=True, lat=24.4798, lng=118.0894, entries=None):
    """构造配置流：注入 FakeClient 并预置城市缓存（免网络）."""
    flow = cf.XmBusConfigFlow()
    hass = stub_ha._fake_hass(None, latitude=lat, longitude=lng, entries=entries)
    make_sync(
        hass,
        client,
        cities=(list(cities) if cities is not None else api.filter_cities(FAKE_CITIES))
        if seed_cities
        else None,
    )
    flow.hass = hass
    return flow


def new_options(entry, client):
    """构造选项流：复用同一套向导步骤."""
    opt = cf.XmBusOptionsFlow(entry)
    hass = stub_ha._fake_hass(None, entries=[entry])
    make_sync(hass, client, cities=api.filter_cities(FAKE_CITIES))
    opt.hass = hass
    return opt, hass


def is_menu(res) -> bool:
    return res.get("type") == "menu"


def is_form(res) -> bool:
    return res.get("type") == "form"


def menu_of(res) -> dict:
    return dict(res.get("menu_options") or {})


def menu_keys(res) -> list:
    return list(menu_of(res))


def menu_labels(res) -> list:
    return list(menu_of(res).values())


def text_of(res) -> str:
    return (res.get("placeholders") or {}).get("hint") or ""


def header_line(index: int, text: str) -> str:
    """取某一步说明区里的**抬头**行（「第 N 步 / 共 7 步」）.

    说明区是 Markdown，几段之间用空行隔开（``\\n\\n``），所以先滤掉空行。
    v0.8.4 起向导第 1 步的说明区第一行是欢迎语，抬头退到第二行；其余步骤
    抬头仍在第一行。
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if index == 1 and len(lines) > 1:
        return lines[1]
    return lines[0] if lines else ""


def fields_of(res) -> set:
    return {getattr(k, "schema", None) for k in res["schema"].schema}


def field_map(res) -> dict:
    return {getattr(k, "schema", None): v for k, v in res["schema"].schema.items()}


def selector_kinds(res) -> set:
    """表单里出现的控件类型（select / text / number / boolean）."""
    return {getattr(v, "kind", "") for v in field_map(res).values()}


def marker_of(res, key):
    """取表单里某个字段的 vol marker（用来判断 Required / Optional）."""
    for m in res["schema"].schema:
        if getattr(m, "schema", None) == key:
            return m
    return None


def field_is_optional(res, key) -> bool:
    """该字段必须是 vol.Optional（前端才允许留空提交，不会拦「必填」）."""
    m = marker_of(res, key)
    return isinstance(m, cf.vol.Optional)


def has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def has_ascii_word(text: str) -> bool:
    """是否含连续英文字母（用来断言「按钮上不会出现英文」）."""
    return re.search(r"[A-Za-z]{2,}", text or "") is not None


def _iter_strings(node):
    """递归取出 JSON 里所有的字符串值."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("documentation", "issue_tracker", "url", "name_placeholder"):
                continue
            yield from _iter_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_strings(item)
    elif isinstance(node, str):
        yield node


def all_chinese_labels(res) -> bool:
    return bool(menu_labels(res)) and all(has_cjk(x) for x in menu_labels(res))


def click(flow, key):
    """模拟 HA 点击菜单项：调用 async_step_<key>."""
    handler = getattr(flow, f"async_step_{key}", None)
    if handler is None:
        raise AssertionError(f"菜单项 {key} 没有对应的 async_step_{key} 方法")
    return handler(None)


def click_pick(flow, index):
    """模拟点击第 index 个候选按钮（走 __getattr__ 动态生成的步骤）."""
    handler = getattr(flow, f"async_step_{PICK}{index}", None)
    if handler is None:
        raise AssertionError(f"候选按钮 {PICK}{index} 没有对应方法")
    return handler(None)


def menu_step_keys(res) -> list:
    """菜单里所有 key 都要能对应到真实方法（HA 的硬要求）."""
    return menu_keys(res)


async def menu_reachable(flow, res) -> bool:
    """菜单里的每个 key 都必须有 async_step_<key>（否则 HA 会报 not implemented）."""
    for key in menu_step_keys(res):
        if getattr(flow, f"async_step_{key}", None) is None:
            return False
    return True


async def walk_to_mode(client=None, city="厦门市"):
    """城市 → 停在第 2 步「选择检索方式」菜单（先选站台 / 先选线路）."""
    flow = new_flow(client or FakeClient())
    await flow.async_step_user(None)
    return flow, await flow.async_step_city_keyword({cf.CITY_KW_FIELD: city})


async def walk_to_station(client=None, city="厦门市"):
    """城市 → 选「🚏 先选站台」，停在第 3 步「选择站台」菜单."""
    flow, _ = await walk_to_mode(client, city)
    return flow, await click(flow, "mode_station")


async def walk_to_line(client=None, city="厦门市", station="县口路站"):
    """城市 → 站台，停在第 4 步「选择线路」菜单."""
    flow, _ = await walk_to_station(client, city)
    res = await flow.async_step_station_keyword({cf.STATION_KW_FIELD: station})
    if res.get("step_id") == "station":
        return flow, await click_pick(flow, flow._station_options.index(station))
    return flow, res


async def walk_to_settings(client=None, city="厦门市", station="县口路站"):
    """走到第 5 步「到站提醒参数」菜单."""
    flow, res = await walk_to_line(client, city, station)
    return flow, await click_pick(flow, 0)


async def walk_to_sync(client=None, city="厦门市", station="县口路站"):
    """走到第 6 步「数据同步」菜单（v0.8.9 新增的一步）."""
    flow, _ = await walk_to_settings(client, city, station)
    return flow, await click(flow, "to_sync")


async def walk_to_confirm(client=None, city="厦门市", station="县口路站"):
    """走到第 7 步「确认创建」菜单（要先过第 6 步「数据同步」）."""
    flow, _ = await walk_to_sync(client, city, station)
    return flow, await click(flow, "to_confirm")


async def main() -> None:
    # ============ A. 按钮式向导骨架 ============
    print("\n[A] 按钮式向导骨架：每步都是按钮、全中文、没有开关")

    flowA = new_flow(OneStationClient())
    rA = await flowA.async_step_user(None)
    step_headers: list[str] = []
    backs: list[str] = []
    no_switch = True

    check("A1 第一步「选择城市」是菜单（选项渲染成真实按钮）",
          is_menu(rA) and rA["step_id"] == "city", f"{rA.get('type')}/{rA.get('step_id')}")
    step_headers.append(text_of(rA))
    check("A2 第一步没有「上一步」按钮（它就是向导起点）",
          BACK not in menu_keys(rA), str(menu_keys(rA)))
    check("A3 抬头写明「第 1 步 / 共 7 步」，且抬头里不再重复步骤名（步骤名只在对话框标题里）",
          "第 1 步 / 共 7 步" in text_of(rA)
          and "· " not in text_of(rA).splitlines()[0], text_of(rA).splitlines()[0])
    check("A4 城市页按钮全部是中文",
          all_chinese_labels(rA) and any("检索城市名" in x for x in menu_labels(rA)),
          str(menu_labels(rA)))
    check("A5 城市页按钮不含英文单词",
          not any(has_ascii_word(x) for x in menu_labels(rA)), str(menu_labels(rA)))
    check("A6 城市页菜单项 key 都能对应到真实方法", await menu_reachable(flowA, rA))

    rA = await flowA.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
    step_headers.append(text_of(rA))
    backs.append(menu_of(rA).get(BACK, ""))
    check("A7 第 2 步「选择检索方式」抬头正确（它是独立的一步）",
          rA["step_id"] == "mode"
          and "第 2 步 / 共 7 步" in text_of(rA)
          and "· 选择检索方式" not in text_of(rA),
          text_of(rA).splitlines()[0])
    check("A8 第 2 步有真实的「⬅ 返回上一步」按钮",
          menu_of(rA).get(BACK) == "⬅ 返回上一步", str(menu_of(rA).get(BACK)))
    check("A9 第 2 步只有「先选站台 / 先选线路」两个按钮 + 上一步（没有开关）",
          menu_keys(rA) == [BACK, "mode_station", "mode_line"], str(menu_keys(rA)))
    check("A10 两个按钮都是「emoji + 动词」短句（🚏 先选站台 / 🚌 先选线路）",
          any(x == "🚏 先选站台" for x in menu_labels(rA))
          and any(x == "🚌 先选线路" for x in menu_labels(rA)),
          str(menu_labels(rA)))
    check("A10b 向导是 7 步，且「选择检索方式」这一步真的存在",
          hasattr(flowA, "async_step_mode") and cf.WIZARD_TOTAL == 7,
          f"WIZARD_TOTAL={cf.WIZARD_TOTAL}")

    rA = await click(flowA, "mode_station")
    step_headers.append(text_of(rA))
    backs.append(menu_of(rA).get(BACK, ""))
    check("A10c 点「🚏 先选站台」→ 第 3 步「选择站台」，且站台页不再有改走线路的按钮",
          rA["step_id"] == "station"
          and "第 3 步 / 共 7 步" in text_of(rA)
          and "· 选择站台" not in text_of(rA)
          and menu_keys(rA) == [BACK, "station_keyword"], str(menu_keys(rA)))

    rA = await flowA.async_step_station_keyword({cf.STATION_KW_FIELD: "县口路站"})
    step_headers.append(text_of(rA))
    backs.append(menu_of(rA).get(BACK, ""))
    check("A11 第 4 步「选择线路」抬头与上一步按钮正确",
          rA["step_id"] == "line"
          and "第 4 步 / 共 7 步" in text_of(rA)
          and "· 选择线路" not in text_of(rA)
          and menu_of(rA).get(BACK) == "⬅ 返回上一步",
          str(text_of(rA).splitlines()[0]))
    check("A13 线路页有真实的「🔄 反向站台」按钮（不是开关）",
          any("反向站台" in x for x in menu_labels(rA))
          and "line_reverse" in menu_keys(rA), str(menu_labels(rA)))

    rA = await click_pick(flowA, 0)
    step_headers.append(text_of(rA))
    backs.append(menu_of(rA).get(BACK, ""))
    check("A14 第 5 步「到站提醒参数」抬头正确 + 上一步回到线路",
          rA["step_id"] == "settings"
          and "第 5 步 / 共 7 步" in text_of(rA)
          and "· 到站提醒参数" not in text_of(rA)
          and menu_of(rA).get(BACK) == "⬅ 返回上一步",
          str(text_of(rA).splitlines()[0]))
    check("A15 参数页把「当前参数」写进按钮文字里（不用开关）",
          any("修改到站参数" in x and "10 秒" in x for x in menu_labels(rA)),
          str(menu_labels(rA)))
    check("A15b 参数页的下一步按钮是通用的「⏭ 下一步」（v0.9.0：按钮不再复述目的地）",
          menu_of(rA).get("to_sync") == "⏭ 下一步"
          and "to_confirm" not in menu_keys(rA),
          str(menu_of(rA)))

    rA = await click(flowA, "to_sync")
    step_headers.append(text_of(rA))
    backs.append(menu_of(rA).get(BACK, ""))
    check("A16a 第 6 步「数据同步」抬头正确 + 上一步回到参数页 + 多一个「⏭ 下一步」",
          rA["step_id"] == "sync"
          and "第 6 步 / 共 7 步" in text_of(rA)
          and "· 数据同步" not in text_of(rA)
          and menu_of(rA).get(BACK) == "⬅ 返回上一步"
          and menu_of(rA).get("to_confirm") == "⏭ 下一步",
          str(text_of(rA).splitlines()[0]))

    rA = await click(flowA, "to_confirm")
    step_headers.append(text_of(rA))
    backs.append(menu_of(rA).get(BACK, ""))
    check("A16 第 7 步「确认创建」抬头正确 + 上一步回到数据同步页",
          rA["step_id"] == "confirm"
          and "第 7 步 / 共 7 步" in text_of(rA)
          and "· 确认创建" not in text_of(rA)
          and menu_of(rA).get(BACK) == "⬅ 返回上一步",
          str(text_of(rA).splitlines()[0]))
    check("A17 最后一步的按钮是「⬅ 返回上一步」+「✅ 完成」（除它们以外没有别的按钮）",
          menu_keys(rA) == [BACK, "finish"] and "✅ 完成" in menu_labels(rA),
          str(menu_labels(rA)))

    check("A18 七个步骤的抬头依次是第 1～7 步",
          all(f"第 {i} 步 / 共 7 步" in h for i, h in enumerate(step_headers, start=1)),
          str([h.splitlines()[0] for h in step_headers]))
    check("A19 第 2～7 步每一步都有「⬅ 返回上一步」按钮",
          len(backs) == 6 and all(b.startswith("⬅") for b in backs), str(backs))

    # 无障碍：读屏是按 Tab 顺序逐个听按钮的，「返回」必须排在最前面，
    # 否则「全部城市列表」这种几百个按钮的页面要听完整个列表才够得到返回。
    first_keys = [menu_keys(res)[0] for res in (
        (await walk_to_mode())[1],
        (await walk_to_station())[1],
        (await walk_to_line())[1],
        (await walk_to_settings())[1],
        (await walk_to_sync())[1],
        (await walk_to_confirm())[1],
    )]
    check("A19b 每一页的「⬅ 返回上一步」都是**第一个**按钮（读屏不用穿过候选列表）",
          all(k == BACK for k in first_keys), str(first_keys))

    rA = await click(flowA, "finish")
    check("A20 点「✅ 完成」后创建条目，城市/线路/站台/站序齐全",
          rA.get("type") == "create_entry"
          and rA["data"]["city"] == "厦门市"
          and rA["data"]["line"] == "615路"
          and rA["data"]["station"] == "县口路站"
          and rA["data"]["station_order"] == 12,
          str(rA.get("data")))
    check("A21 条目标题形如「厦门市 615路 县口路站」",
          rA.get("title") == "厦门市 615路 县口路站", str(rA.get("title")))

    # 全程不应出现任何开关控件
    for res in (
        await new_flow(FakeClient()).async_step_settings_params(None),
    ):
        if selector_kinds(res) & {"boolean"}:
            no_switch = False
    check("A22 到站参数页只有数字输入框，没有任何开关",
          no_switch and selector_kinds(
              await new_flow(FakeClient()).async_step_settings_params(None)
          ) == {"number"},
          str(selector_kinds(await new_flow(FakeClient()).async_step_settings_params(None))))

    # ============ B. 完整流程（先选站台） ============
    print("\n[B] 完整流程（先选站台）：城市 → 站台 → 线路 → 参数 → 创建")

    flowB = new_flow(FakeClient())
    await flowB.async_step_user(None)
    rB = await click(flowB, "city_locate")
    check("B1 点「用 HA 位置识别城市」→ 进入第 2 步「选择检索方式」",
          rB["step_id"] == "mode" and flowB._city == "厦门市", str(rB.get("step_id")))
    rB = await click(flowB, "mode_station")
    check("B1b 点「🚏 先选站台」→ 进入第 3 步「选择站台」",
          rB["step_id"] == "station", str(rB.get("step_id")))
    rB = await flowB.async_step_station_keyword({cf.STATION_KW_FIELD: "县口路站"})
    check("B2 检索到多个站台 → 列成候选按钮等用户点选",
          rB["step_id"] == "station" and len(flowB._station_options) == 4
          and sum(1 for x in menu_labels(rB) if x.removeprefix("🚏 ") in flowB._station_options) == 4,
          str(flowB._station_options))
    rB = await click_pick(flowB, flowB._station_options.index("县口路站"))
    check("B3 点「县口路站」候选按钮 → 进入第 4 步线路页",
          rB["step_id"] == "line" and flowB._station == "县口路站", str(rB.get("step_id")))

    rB = await click_pick(flowB, 0)
    check("B4 选中线路后进入参数页，方向和线路都记下来了",
          rB["step_id"] == "settings" and flowB._line == "615路" and flowB._direction == "1",
          f"{flowB._line}/{flowB._direction}")
    rB = await click(flowB, "settings_params")
    check("B5 参数页只剩「数据刷新间隔」一个数字输入框（v0.9.1 起没有站数/公里），"
          "字段名直接用中文且自带范围",
          is_form(rB) and rB["step_id"] == "settings_params"
          and fields_of(rB) == {cf.POLL_INTERVAL_FIELD}
          and selector_kinds(rB) == {"number"}
          and all(any("\u4e00" <= ch <= "\u9fff" for ch in k) for k in fields_of(rB))
          and "范围 5 到 120" in cf.POLL_INTERVAL_FIELD,
          str(fields_of(rB)))
    defaultsB = {}
    for key, sel in field_map(rB).items():
        defaultsB[key] = sel.config.get("min"), sel.config.get("max")
    check("B6 刷新间隔数字框带范围与单位（读屏会朗读单位）",
          defaultsB[cf.POLL_INTERVAL_FIELD] == (5, 120)
          and field_map(rB)[cf.POLL_INTERVAL_FIELD].config.get("unit_of_measurement") == "秒",
          str(defaultsB))
    check("B6b 后端兜一层夹取：0 秒（会让协调器忙轮询）夹到最小值 5",
          cf._settings_schema(10)({})[cf.POLL_INTERVAL_FIELD] == 10
          and cf._settings_schema(0)({})[cf.POLL_INTERVAL_FIELD] == 5,
          str(cf._settings_schema(0)({})))

    rB = await flowB.async_step_settings_params(
        {cf.POLL_INTERVAL_FIELD: 8}
    )
    check("B7 保存参数后回到参数页并提示已保存",
          rB["step_id"] == "settings" and "已保存" in text_of(rB), text_of(rB))
    rB = await click(flowB, "to_sync")
    check("B7b 完整流程里第 5 步之后是第 6 步「数据同步」（不再直奔确认页）",
          rB["step_id"] == "sync" and "第 6 步 / 共 7 步" in text_of(rB),
          str(rB.get("step_id")))
    rB = await click(flowB, "to_confirm")
    body = text_of(rB)
    check("B8 确认页（第 7 步）把城市/站台/线路/方向（起终点）/参数都列了出来",
          rB["step_id"] == "confirm"
          and all(x in body for x in
                  ("厦门市", "县口路站", "615路", "四林总站→丙洲东头尾站", "8 秒"))
          and "提前" not in body,
          body.replace("\n", " / "))
    check("C11 v0.9.5 确认页（第 7 步）补上「自动同步：每 12 小时」一行（默认启用 12h）",
          "自动同步：每 12 小时" in body, body.replace("\n", " / "))
    rB = await click(flowB, "finish")
    check("B9 创建成功且参数写进 options（v0.9.1 起只有刷新间隔）",
          rB.get("type") == "create_entry"
          and rB["options"] == {"poll_interval": 8},
          str(rB.get("options")))

    # ============ C. 完整流程（先选线路） ============
    print("\n[C] 完整流程（先选线路）：城市 → 线路 → 途经站台 → 参数 → 数据同步 → 创建")

    flowC = new_flow(FakeClient())
    await flowC.async_step_user(None)
    rC = await flowC.async_step_city_keyword({cf.CITY_KW_FIELD: "北京市"})
    check("C0 第 2 步「选择检索方式」只有两个按钮 + 上一步",
          rC["step_id"] == "mode"
          and menu_keys(rC) == [BACK, "mode_station", "mode_line"]
          and any("先选站台" in x for x in menu_labels(rC))
          and any("先选线路" in x for x in menu_labels(rC)), str(menu_keys(rC)))
    rC = await click(flowC, "mode_line")
    check("C1 点「🚌 先选线路」→ 进入第 3 步线路页，并切到「线路优先」",
          rC["step_id"] == "line"
          and "第 3 步 / 共 7 步" in text_of(rC)
          and flowC._search_mode == cf.MODE_LINE_FIRST
          and menu_of(rC).get(BACK) == "⬅ 返回上一步", text_of(rC).splitlines()[0])
    rC = await click(flowC, "line_keyword")
    check("C2 线路关键词是可选字段（前端允许留空提交，不拦「必填」）",
          is_form(rC) and rC["step_id"] == "line_keyword"
          and fields_of(rC) == {cf.LINE_KW_FIELD}
          and has_cjk(cf.LINE_KW_FIELD)
          and field_is_optional(rC, cf.LINE_KW_FIELD), str(fields_of(rC)))

    rC = await flowC.async_step_line_keyword({cf.LINE_KW_FIELD: "615"})
    check("C2b 线路优先时「选择线路」是第 3 步，且页面上没有改走站台的按钮",
          rC["step_id"] == "line" and "第 3 步 / 共 7 步" in text_of(rC)
          and menu_of(rC).get(BACK) == "⬅ 返回上一步"
          and "mode_station" not in menu_keys(rC), str(menu_keys(rC)))
    check("C3 检索到 2 条线路（同一线路的上下行各一条，去重后列成按钮）",
          len(flowC._line_options) == 2
          and sum(1 for x in menu_labels(rC) if x.removeprefix("🚌 ") in flowC._line_options) == 2,
          str(flowC._line_options))
    rC = await click_pick(flowC, 0)
    check("C4 选线路后第 4 步列出途经站台，按途经顺序编号",
          rC["step_id"] == "line_station"
          and "第 4 步 / 共 7 步" in text_of(rC)
          and "· 选择途经站台" not in text_of(rC)
          and flowC._station_options[0] == "1. 四林总站"
          and flowC._station_options[2] == "3. 县口路站",
          str(flowC._station_options))
    check("C5 站台按钮直接写着「3. 县口路站」（按途经顺序编号）",
          any(x == "🚏 3. 县口路站" for x in menu_labels(rC)), str(menu_labels(rC)))
    rC = await click_pick(flowC, 2)
    rC = await click(flowC, "to_sync")
    rC = await click(flowC, "to_confirm")
    rC = await click(flowC, "finish")
    check("C6 先选线路也能走到创建，站序按线上拓扑取到 12",
          rC.get("type") == "create_entry" and rC["data"]["station_order"] == 12
          and rC["data"]["line"] == "615路" and rC["data"]["city"] == "北京市",
          str(rC.get("data")))

    # ============ D. 「上一步」是真实按钮，逐步可回退 ============
    print("\n[D] 「上一步」按钮：每一步都能真的退回上一步")

    step_names = {
        "city": "city", "mode": "mode", "station": "station",
        "line": "line", "line_station": "line_station",
        "settings": "settings", "sync": "sync", "confirm": "confirm",
    }
    prev_chain = {
        "mode": "city",
        "station": "mode",
        "line": "station",
        "line_station": "line",
        "settings": "line",
        "sync": "settings",
        "confirm": "sync",
    }
    flowD, _ = await walk_to_confirm(FakeClient())
    ok_all = True
    details = []
    for step in ("confirm", "sync", "settings", "line", "station", "mode"):
        res = await click(flowD, BACK)
        want = prev_chain[step]
        details.append(f"{step}->{res.get('step_id')}")
        if res.get("step_id") != step_names[want]:
            ok_all = False
    check("D1 确认页 → 数据同步页 → 参数页 → 线路 → 站台 → 检索方式 → 城市 逐级回退",
          ok_all, str(details))

    flowD2 = new_flow(FakeClient())
    await flowD2.async_step_user(None)
    await flowD2.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
    rD = await click(flowD2, BACK)
    check("D2 第 2 步「选择检索方式」点「上一步」回到第 1 步城市页",
          rD["step_id"] == "city" and BACK not in menu_keys(rD), str(rD.get("step_id")))

    flowD3 = new_flow(FakeClient())
    await flowD3.async_step_user(None)
    await flowD3.async_step_city_keyword({cf.CITY_KW_FIELD: "北京市"})
    await click(flowD3, "mode_line")
    rD3 = await click(flowD3, BACK)
    check("D3 检索方式页 →「🚌 先选线路」→ 线路页，上一步退回用户真正来过的检索方式页（不是从没去过的站台页）",
          rD3["step_id"] == "mode", str(rD3.get("step_id")))

    check("D4 _prev_step 静态链：站台优先与线路优先两条路径都对（确认页的上一步是数据同步页）",
          (lambda f: (
              f._search_mode == cf.MODE_STATION_FIRST
              and f._prev_step("mode") == "city"
              and f._prev_step("station") == "mode"
              and f._prev_step("line") == "station"
              and f._prev_step("settings") == "line"
              and f._prev_step("sync") == "settings"
              and f._prev_step("sync_interval") == "sync"
              and f._prev_step("confirm") == "sync"
          ))(new_flow(FakeClient()))
          and (lambda f: (
              setattr(f, "_search_mode", cf.MODE_LINE_FIRST) or
              f._prev_step("mode") == "city"
              and f._prev_step("line") == "mode"
              and f._prev_step("line_keyword") == "mode"
              and f._prev_step("line_station") == "line"
              and f._prev_step("settings") == "line_station"
              and f._prev_step("sync") == "settings"
              and f._prev_step("confirm") == "sync"
          ))(new_flow(FakeClient())))

    # ============ E. 第 1 步：城市 ============
    print("\n[E] 第 1 步「选择城市」：检索城市名 / 定位当前城市 / 全部城市列表（全部是按钮）")

    flowE = new_flow(FakeClient())
    rE = await flowE.async_step_user(None)
    check("E1 城市页剩下 3 个动作按钮（v0.8.9 起「同步最新数据」已移到第 6 步）",
          {"city_locate", "city_keyword", "city_browse"} <= set(menu_keys(rE)),
          str(menu_keys(rE)))
    check("E1b 「检索城市名」排第一（与第 3 步的检索按钮同位置），且本页已无同步按钮",
          menu_keys(rE) == ["city_keyword", "city_locate", "city_browse"]
          and "city_sync" not in menu_keys(rE),
          str(menu_keys(rE)))
    check("E1c 城市页提示把三种找城市的方式都列出来（v0.9.0 起不再只说「可以定位」）",
          "请检索城市名" in text_of(rE)
          and "Home Assistant" in text_of(rE)
          and "显示城市列表" in text_of(rE)
          and "请选择城市。" not in text_of(rE)
          and "要监控" not in text_of(rE), repr(text_of(rE)))
    check("E1d 城市页提示里不重复「第 N 步」进度（步号只在抬头出现一次）",
          text_of(rE).count("共 7 步") == 1, repr(text_of(rE)))
    check("E2 「全部城市列表」按钮存在，且带上了城市总数（读屏也知道有多少个）",
          any("全部城市列表" in x and f"共 {FAKE_CITY_COUNT} 个" in x
              for x in menu_labels(rE)), str(menu_labels(rE)))
    check("E3 城市页不再出现「同步最新数据」按钮（同步挪到第 6 步「数据同步」）",
          not any("同步" in x for x in menu_labels(rE)), str(menu_labels(rE)))
    rE = await click(flowE, "city_browse")
    check("E4 浏览全部 → 每个城市一个按钮 + 上一步",
          len(menu_of(rE)) == FAKE_CITY_COUNT + 1
          and sum(1 for x in menu_labels(rE) if x in flowE._city_options) == FAKE_CITY_COUNT,
          str(len(menu_of(rE))))
    check("E5 城市按钮不带英文（拼音首字母只在城市名里出现）",
          all(has_cjk(x) for x in menu_labels(rE)), str(menu_labels(rE)[:3]))
    rE = await click(flowE, BACK)
    check("E6 从「浏览全部」可以点上一步回到城市页",
          rE["step_id"] == "city" and "全部城市列表" in str(menu_labels(rE)))

    rE = await click(flowE, "city_keyword")
    check("E7 输入城市名是表单，字段用中文键（翻译失效也不会变英文）",
          is_form(rE) and fields_of(rE) == {cf.CITY_KW_FIELD} and has_cjk(cf.CITY_KW_FIELD),
          str(fields_of(rE)))
    check("E8 表单提示教用户可以用全拼和首字母",
          "全拼" in text_of(rE) and "首字母" in text_of(rE), text_of(rE))
    check("E8b 城市关键词是可选字段（前端允许留空提交，不拦「必填」）",
          field_is_optional(rE, cf.CITY_KW_FIELD), str(marker_of(rE, cf.CITY_KW_FIELD)))
    rE = await flowE.async_step_city_keyword({cf.CITY_KW_FIELD: "xm"})
    check("E9 输入拼音首字母 xm → 唯一命中厦门市 → 直接进入第 2 步「选择检索方式」",
          rE["step_id"] == "mode" and flowE._city == "厦门市", flowE._city)

    flowE2 = new_flow(FakeClient())
    await flowE2.async_step_user(None)
    rE = await flowE2.async_step_city_keyword({cf.CITY_KW_FIELD: "市"})
    check("E10 多个命中 → 回到城市页，把候选列成按钮",
          rE["step_id"] == "city"
          and sum(1 for x in menu_labels(rE) if x in flowE2._city_options) == len(flowE2._city_options),
          str(flowE2._city_options[:4]))
    rE = await click_pick(flowE2, 0)
    check("E11 点候选城市按钮 → 进入第 2 步「选择检索方式」",
          rE["step_id"] == "mode" and flowE2._city in FAKE_CITIES, flowE2._city)

    flowE3 = new_flow(FakeClient())
    await flowE3.async_step_user(None)
    rE = await flowE3.async_step_city_keyword({cf.CITY_KW_FIELD: "火星市"})
    check("E12 找不到 → 回到城市页并给出中文提示",
          rE["step_id"] == "city" and "没有找到" in text_of(rE), text_of(rE))
    flowE4 = new_flow(FakeClient())
    await flowE4.async_step_user(None)
    rE = await flowE4.async_step_city_keyword({cf.CITY_KW_FIELD: ""})
    check("E13 关键词留空 → 回到城市页（等于取消）", rE["step_id"] == "city")

    flowE5 = new_flow(FakeClient())
    await flowE5.async_step_user(None)
    await click(flowE5, "city_browse")
    rE = await click(flowE5, BACK)
    check("E14 从「浏览全部」退回城市页后，本页仍然没有同步按钮",
          rE["step_id"] == "city"
          and menu_of(rE).get("city_sync") is None
          and any("检索城市名" in x for x in menu_labels(rE)),
          str(menu_keys(rE)))

    flowE6 = new_flow(FakeClient(fail_cities=True), seed_cities=False)
    rE = await flowE6.async_step_user(None)
    check("E15 城市列表取不到 → 中文提示；不再显示「浏览全部」按钮",
          "城市列表暂时取不到" in text_of(rE) and "city_browse" not in menu_keys(rE),
          text_of(rE))
    check("E16 取不到城市时仍可点「用 HA 位置识别城市」兜底",
          "city_locate" in menu_keys(rE), str(menu_keys(rE)))

    flowE7 = new_flow(FakeClient(), lat=0.0, lng=0.0)
    await flowE7.async_step_user(None)
    rE = await click(flowE7, "city_locate")
    check("E17 HA 没设位置 → 提示去设置里填位置（不报错）",
          rE["step_id"] == "city" and "位置" in text_of(rE), text_of(rE))
    flowE8 = new_flow(FakeClient(located=""))
    await flowE8.async_step_user(None)
    rE = await click(flowE8, "city_locate")
    check("E18 坐标不在服务范围 → 中文提示",
          rE["step_id"] == "city" and "不在掌上公交的服务范围内" in text_of(rE), text_of(rE))

    flowE9 = new_flow(OneStationClient())
    await flowE9.async_step_user(None)
    await flowE9.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})            # 城市 → 第 2 步站台
    await flowE9.async_step_station_keyword({cf.STATION_KW_FIELD: "县口路站"})   # 唯一 → 线路页
    await click_pick(flowE9, 0)                                                 # 选线路 → 参数页
    await click(flowE9, BACK)   # 参数 → 线路
    await click(flowE9, BACK)   # 线路 → 站台
    await click(flowE9, BACK)   # 站台 → 城市
    await flowE9.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
    check("E19 城市没变 → 后面的站台/线路选择保留（不会被清空）",
          flowE9._station == "县口路站" and flowE9._line == "615路",
          f"{flowE9._station}/{flowE9._line}")
    rE = await flowE9.async_step_city_keyword({cf.CITY_KW_FIELD: "北京市"})
    check("E20 换了城市 → 站台/线路/方向全部作废",
          flowE9._city == "北京市" and not flowE9._station and not flowE9._line
          and flowE9._direction == "1",
          f"{flowE9._city}/{flowE9._station}/{flowE9._line}")

    # ============ F. 第 3 步：站台 ============
    print("\n[F] 第 3 步「选择站台」：先输入关键词，再把结果列成按钮")

    flowF, rF = await walk_to_station(FakeClient())
    check("F1 首次进入只有「返回 / 检索站台」两个按钮（没有候选）",
          menu_keys(rF) == [BACK, "station_keyword"], str(menu_keys(rF)))
    check("F2 提示里写明支持中文 / 拼音 / 首字母并举了例子",
          "拼音" in text_of(rF) and "火车站" in text_of(rF), text_of(rF))
    rF = await flowF.async_step_station_keyword({cf.STATION_KW_FIELD: "同安"})
    check("F3 检索到多个 → 列成候选按钮并把关键词回显",
          rF["step_id"] == "station" and "同安" in text_of(rF)
          and any("同安一中站" in x for x in menu_labels(rF)), str(menu_labels(rF)))
    rF = await click(flowF, "station_keyword")
    check("F4 再次点检索按钮 → 打开输入表单，且按钮已变成「修改关键词」",
          is_form(rF) and fields_of(rF) == {cf.STATION_KW_FIELD}
          and any("修改关键词" in x
                  for x in menu_labels(await flowF.async_step_station(None))),
          str(fields_of(rF)))
    check("F4b 站台关键词是可选字段（前端允许留空提交，不拦「必填」）",
          field_is_optional(rF, cf.STATION_KW_FIELD), str(marker_of(rF, cf.STATION_KW_FIELD)))
    flowF5, _ = await walk_to_station(NoMatchClient())
    rF = await flowF5.async_step_station_keyword({cf.STATION_KW_FIELD: "不存在站"})
    check("F5 无匹配 → 中文提示且候选为空",
          rF["step_id"] == "station" and "没有找到" in text_of(rF)
          and not flowF5._station_options, text_of(rF))
    rF = await flowF5.async_step_station_keyword({cf.STATION_KW_FIELD: ""})
    check("F6 站台关键词留空 → 回站台页", rF["step_id"] == "station")

    flowF2, _ = await walk_to_station(FakeClient(fail_station=True))
    rF = await flowF2.async_step_station_keyword({cf.STATION_KW_FIELD: "同安"})
    check("F7 接口异常 → 中文「查询失败」提示（不冒泡成 Unknown error）",
          rF["step_id"] == "station" and "查询失败" in text_of(rF), text_of(rF))
    flowF3, _ = await walk_to_station(OneStationClient())
    rF = await flowF3.async_step_station_keyword({cf.STATION_KW_FIELD: "县口"})
    check("F8 唯一结果自动采用 → 直接进入第 3 步（少点一次）",
          rF["step_id"] == "line" and flowF3._station == "县口路站", str(rF.get("step_id")))

    # v0.8.3：掌上公交的关键词检索单次最多给约 30 条，命中数触顶时必须说出来 ——
    # 否则用户以为「就这么几条」，不会想到再加一个字收窄关键词。
    flowF4, _ = await walk_to_station(ManyStationsClient())
    rF = await flowF4.async_step_station_keyword({cf.STATION_KW_FIELD: "站"})
    check("F9 站台命中触顶（30 条）→ 提示说明「一次最多返回 30 条，可多加一个字收窄」",
          "最多返回 30 条" in text_of(rF) and len(flowF4._station_options) == 30,
          f"{len(flowF4._station_options)} 条 / {text_of(rF)}")

    # ============ G. 第 2 / 3 步：线路 ============
    print("\n[G] 第 2 / 3 步「选择线路」：站台线路按钮 + 换到马路对面 + 途经站台")

    class BothDirClient(FakeClient):
        """该站台上下行都有车（验证「换到马路对面站台」按钮）."""

        async def station_lines(self, station, direction=None):
            self.calls["station_lines"] += 1
            hits = [
                api.LineHit(line_name="615路", direction="1",
                            from_stop="四林总站", to_stop="丙洲东头尾站"),
                api.LineHit(line_name="618路", direction="2",
                            from_stop="方特旅游区站", to_stop="梧侣公交场站"),
            ]
            if direction:
                hits = [h for h in hits if h.direction == direction]
            return hits

    flowG, rG = await walk_to_line(BothDirClient())
    check("G1 线路按钮直接写成「615路（四林总站→丙洲东头尾站）」（带起终点）",
          any(x == "🚌 615路（四林总站→丙洲东头尾站）" for x in menu_labels(rG)),
          str(menu_labels(rG)))
    check("G2 有「🔄 反向站台」按钮，且是按钮不是开关",
          menu_of(rG).get("line_reverse") == "🔄 反向站台",
          str(menu_of(rG).get("line_reverse")))
    rG = await click(flowG, "line_reverse")
    check("G3 点它就切到下行，按钮文案保持「🔄 反向站台」",
          flowG._direction == "2"
          and menu_of(rG).get("line_reverse") == "🔄 反向站台"
          and any("618路" in x for x in menu_labels(rG)),
          f"{flowG._direction} / {menu_labels(rG)}")

    flowG2, rG = await walk_to_line(DownOnlyClient())
    check("G4 选中的方向没车 → 自动换到有车的一侧并说明原因",
          "已切换到下行侧" in text_of(rG), text_of(rG))
    flowG3, rG = await walk_to_line(NoLinesClient())
    check("G5 该站台查不到任何线路 → 中文提示，仍保留「换到马路对面站台」",
          "没有查到线路" in text_of(rG) and "line_reverse" in menu_keys(rG), text_of(rG))
    flowG4, rG = await walk_to_line(FakeClient(fail_line=True))
    check("G6 站台线路接口异常 → 中文「查询失败」提示",
          "查询失败" in text_of(rG), text_of(rG))

    flowG5 = new_flow(NoLineMatchClient())
    await flowG5.async_step_user(None)
    await flowG5.async_step_city_keyword({cf.CITY_KW_FIELD: "北京市"})
    rG = await click(flowG5, "mode_line")
    check("G7 点「🚌 先选线路」→ 进入线路页（线路优先），只有「返回 / 检索线路」",
          rG["step_id"] == "line" and flowG5._search_mode == cf.MODE_LINE_FIRST
          and menu_keys(rG) == [BACK, "line_keyword"], str(menu_keys(rG)))
    rG = await click(flowG5, "line_keyword")
    check("G7b 线路输入框举例用「1」而不是某条具体线路",
          is_form(rG) and rG["step_id"] == "line_keyword" and "例如 1" in text_of(rG),
          text_of(rG))
    rG = await flowG5.async_step_line_keyword({cf.LINE_KW_FIELD: "888"})
    check("G7c 无结果时回到线路页（返回 + 检索线路 + 上一步）",
          rG["step_id"] == "line" and menu_keys(rG) == [BACK, "line_keyword"],
          str(menu_keys(rG)))
    check("G8 线路检索无结果 → 中文提示",
          rG["step_id"] == "line" and "没有找到" in text_of(rG), text_of(rG))
    flowG8, _ = await walk_to_line(ManyLinesClient())
    rG = await flowG8.async_step_line_keyword({cf.LINE_KW_FIELD: "路"})
    check("G8b 线路命中触顶（30 条）→ 提示同样说明被截断（站台 / 线路共用同一条规则）",
          "最多返回 30 条" in text_of(rG) and len(flowG8._line_options) == 30,
          f"{len(flowG8._line_options)} 条 / {text_of(rG)}")
    flowG6, _ = await walk_to_line(FakeClient(fail_line=True))
    rG = await flowG6.async_step_line_keyword({cf.LINE_KW_FIELD: "615"})
    check("G9 线路检索接口异常 → 中文「查询失败」提示",
          "查询失败" in text_of(rG), text_of(rG))
    flowG7 = new_flow(FakeClient(fail_topology=True))
    await flowG7.async_step_user(None)
    await flowG7.async_step_city_keyword({cf.CITY_KW_FIELD: "北京市"})
    await click(flowG7, "mode_line")
    rG = await flowG7.async_step_line_keyword({cf.LINE_KW_FIELD: "615"})
    rG = await click_pick(flowG7, 0)
    check("G10 线路拓扑取不到 → 途经站台页给出中文提示",
          rG["step_id"] == "line_station" and "查询失败" in text_of(rG), text_of(rG))

    # ============ H. 第 5 / 6 / 7 步：参数与数据同步与确认 ============
    print("\n[H] 第 5～7 步：参数页只用数字框、数据同步页能改同步、确认页是「完成创建」按钮")

    flowH, rH = await walk_to_settings(FakeClient())
    check("H1 参数页把当前值写进按钮文字（不用开关，不用读数；公里默认 1）",
          any(x == "⏱ 修改到站参数（当前：每 10 秒刷新）"
              for x in menu_labels(rH)),
          str(menu_labels(rH)))
    check("H2 参数页有通用的「⏭ 下一步」，且本页没有直达确认页的按钮（v0.8.9 起同步是第 6 步）",
          menu_of(rH).get("to_sync") == "⏭ 下一步"
          and menu_of(rH).get("to_confirm") is None, str(menu_of(rH)))
    rH = await click(flowH, "settings_params")
    check("H3 参数表单取值被限制在 5～120 秒（v0.9.1 起是唯一字段）",
          selector_kinds(rH) == {"number"}
          and field_map(rH)[cf.POLL_INTERVAL_FIELD].config.get("max") == 120
          and field_map(rH)[cf.POLL_INTERVAL_FIELD].config.get("min") == 5,
          str(selector_kinds(rH)))
    check("H4 表单说明只说「输入数字」，不重复字段名里已经写着的取值范围（读屏只听一遍）",
          "输入数字" in text_of(rH)
          and "三个框都要填数字" not in text_of(rH)
          and "提前" not in text_of(rH)
          and "范围 5 到 120" not in text_of(rH),
          text_of(rH))
    rH = await flowH.async_step_settings_params(
        {cf.POLL_INTERVAL_FIELD: 30}
    )
    check("H5 保存后回到参数页，提示已保存且按钮文字跟着更新",
          rH["step_id"] == "settings" and "已保存" in text_of(rH)
          and any("30 秒" in x for x in menu_labels(rH)),
          str(menu_labels(rH)))
    rH = await click(flowH, "to_sync")
    check("H5b 参数页的下一步进第 6 步「数据同步」，确认页还要再点一次下一步",
          rH["step_id"] == "sync" and "第 6 步 / 共 7 步" in text_of(rH)
          and menu_of(rH).get("to_confirm") == "⏭ 下一步",
          str(rH.get("step_id")))
    rH = await click(flowH, "to_confirm")
    check("H6 确认页把内容都列清楚（城市/站台/线路/方向/间隔），不再有提前量",
          rH["step_id"] == "confirm"
          and all(x in text_of(rH) for x in
                  ("厦门市", "县口路站", "615路", "四林总站→丙洲东头尾站", "30 秒"))
          and "提前" not in text_of(rH),
          text_of(rH).replace("\n", " / "))

    flowH2 = new_flow(FakeClient())
    flowH2._city, flowH2._line, flowH2._station = "厦门市", "615路", "不存在站"
    flowH2._direction, flowH2._poll_interval = "1", 10
    rH = await click(flowH2, "finish")
    check("H7 站台不在线路上 → 留在确认页并说明，不中断流程",
          rH["step_id"] == "confirm" and "不在线路" in text_of(rH), text_of(rH))

    flowH3 = new_flow(FakeClient(fail_topology=True))
    flowH3._city, flowH3._line, flowH3._station = "厦门市", "615路", "县口路站"
    rH = await click(flowH3, "finish")
    check("H8 拓扑连不上 → 留在确认页提示稍后重试",
          rH["step_id"] == "confirm" and "连不上公交数据服务" in text_of(rH), text_of(rH))

    flowH4 = new_flow(FakeClient())
    flowH4._city, flowH4._line, flowH4._station = "厦门市", "615路", "同安汽车站"
    flowH4._direction = "1"
    order = await flowH4._resolve_station_order()
    check("H9 站台只在反方向时自动换向并取到站序",
          order == 6 and flowH4._direction == "2", f"order={order}/{flowH4._direction}")

    flowH5 = new_flow(FakeClient())
    flowH5._city, flowH5._line, flowH5._station = "厦门市", "615路", "县口路站"
    flowH5._direction = "1"
    rH = await click(flowH5, "finish")
    check("H10 正常创建：条目里存了站序，options 里存了参数",
          rH.get("type") == "create_entry"
          and rH["data"]["station_order"] == 12
          and set(rH["options"]) == {"poll_interval"},
          str(rH.get("data")))

    # v0.8.0 #15：范围夹取从「只靠前端 NumberSelector」改成后端也兜一层
    check("H11 越界参数在后端也会被夹取（0 秒会导致忙轮询，999 站无意义）",
          logic.normalize_poll_interval(0) == cf.MIN_POLL_INTERVAL
          and logic.normalize_poll_interval(9999) == cf.MAX_POLL_INTERVAL
          and logic.normalize_poll_interval("abc") == cf.DEFAULT_POLL_INTERVAL
          and logic.normalize_poll_interval(None) == cf.DEFAULT_POLL_INTERVAL,
          f"iv0={logic.normalize_poll_interval(0)} iv9999={logic.normalize_poll_interval(9999)}")

    flowH6, _ = await walk_to_settings(FakeClient())
    await flowH6.async_step_settings_params({cf.POLL_INTERVAL_FIELD: 9999})
    rH = await click(flowH6, "finish")
    check("H12 绕过前端塞进来的越界值，创建条目时同样被夹到 120 秒",
          rH.get("type") == "create_entry"
          and rH["options"]["poll_interval"] == 120,
          str(rH.get("options")))

    # 旧条目里的 0 站 / 0 公里在向导里显示成合法值（表单默认值与选项菜单口径一致）
    entryH = FakeEntry()
    entryH.options = {"poll_interval": 0}
    flowH7, _ = new_options(entryH, FakeClient())
    rH = await flowH7.async_step_init(None)
    labelsH = menu_labels(rH)
    check("H13 旧条目里的 0 秒在选项菜单里显示成夹取后的合法值"
          "（0 秒曾被当成「不刷新」，现在夹到最小值 5 秒）",
          any("每 5 秒刷新" in x for x in labelsH),
          str(labelsH))

    # ---- 步号自洽（v0.8.2 修的 bug：站台优先时 line_keyword 曾回落成第 3 步；
    #      v0.8.9 插入第 6 步「数据同步」后，最后一步确认页是第 7 步）
    idx_flow = new_flow(FakeClient())
    path_station_first = ["city", "mode", "station", "station_keyword",
                          "line", "line_keyword", "settings", "settings_params",
                          "sync", "sync_interval", "confirm"]
    path_line_first = ["city", "mode", "line", "line_keyword",
                       "line_station", "settings", "settings_params",
                       "sync", "sync_interval", "confirm"]
    seq = {}
    for mode, path in ((cf.MODE_STATION_FIRST, path_station_first),
                       (cf.MODE_LINE_FIRST, path_line_first)):
        idx_flow._search_mode = mode
        seq[mode] = [idx_flow._step_index(s) for s in path]
    check("H14 同一条路上步骤序号只增不减（不会出现第 4 步之后又跳回第 3 步）",
          all(a <= b for s in seq.values() for a, b in zip(s, s[1:]))
          and seq[cf.MODE_STATION_FIRST][0] == 1 and seq[cf.MODE_LINE_FIRST][0] == 1
          and seq[cf.MODE_STATION_FIRST][-1] == 7 and seq[cf.MODE_LINE_FIRST][-1] == 7,
          str(seq))
    idx_flow._search_mode = cf.MODE_STATION_FIRST
    pair_ok = (
        idx_flow._step_index("city") == idx_flow._step_index("city_keyword") == 1
        and idx_flow._step_index("station") == idx_flow._step_index("station_keyword") == 3
        and idx_flow._step_index("line") == idx_flow._step_index("line_keyword") == 4
        and idx_flow._step_index("settings") == idx_flow._step_index("settings_params") == 5
        and idx_flow._step_index("sync") == idx_flow._step_index("sync_interval") == 6
    )
    idx_flow._search_mode = cf.MODE_LINE_FIRST
    pair_ok = pair_ok and (
        idx_flow._step_index("line") == idx_flow._step_index("line_keyword") == 3
        and idx_flow._step_index("line_station") == 4
        and idx_flow._step_index("settings") == idx_flow._step_index("settings_params") == 5
        and idx_flow._step_index("sync") == idx_flow._step_index("sync_interval") == 6
        and idx_flow._step_index("confirm") == 7
    )
    check("H14b 输入子页与父页同号（站台优先时「输入线路号查找」必须是第 4 步；"
          "「修改同步间隔」必须与「数据同步」同号）",
          pair_ok, f"站台优先={seq[cf.MODE_STATION_FIRST]} 线路优先={seq[cf.MODE_LINE_FIRST]}")

    # ============ I. 文案与无障碍 ============
    print("\n[I] 文案与无障碍：三份语言文件全中文 / 表单标签中文 / 无开关残留")

    # v0.9.12 起：strings.json 的 device_automation.trigger_type 按 hassfest 规范用
    # {"name":..., "description":...} 对象形式（文档用途，运行时不读）；
    # translations/<lang>.json 运行时前端读取，trigger_type 必须是纯字符串。
    # v0.9.20 起 device_automation.condition_type 同理（同一套设备自动化翻译规范）。
    # 除此之外两份文件的内容必须完全一致。
    _strings_norm = json.loads(json.dumps(STRINGS))
    _strings_norm["device_automation"]["trigger_type"] = ZH["device_automation"]["trigger_type"]
    _strings_norm["device_automation"]["condition_type"] = ZH["device_automation"]["condition_type"]
    check("I1 strings.json 与 translations/zh-Hans.json 内容一致"
          "（仅 device_automation.trigger_type / condition_type 按 HA 规范允许形态差异："
          "strings.json 对象形式 / translations 纯字符串）",
          _strings_norm == ZH,
          "差异键: " + str(sorted(set(_strings_norm) ^ set(ZH))) if _strings_norm != ZH else "OK")
    check("I2 translations/en.json 也是中文（HA 回退到 en 时不会出现英文界面）",
          EN == ZH, "en.json 与 zh-Hans.json 不一致")
    non_cjk = [v for v in _iter_strings(EN) if v.strip() and v != "{hint}" and not has_cjk(v)]
    check("I3 en.json 的每一句文案都含中文（没有纯英文句子）", not non_cjk, str(non_cjk[:5]))

    form_steps = {
        "config": ["city_keyword", "station_keyword", "line_keyword", "settings_params"],
        "options": ["city_keyword", "station_keyword", "line_keyword", "settings_params",
                    "sync_interval"],
    }
    menu_steps = {
        "config": ["city", "city_browse", "station", "line", "line_station",
                   "settings", "confirm"],
        "options": ["init", "sync"],
    }
    bad_title = [
        f"{scope}.{sid}"
        for scope, ids in menu_steps.items()
        for sid in ids
        if sid not in STRINGS[scope]["step"]
    ]
    check("I4 所有菜单步骤都在语言文件里有 title / description", not bad_title, str(bad_title))
    bad_ph = [
        f"{scope}.{sid}"
        for scope, ids in {**menu_steps, **form_steps}.items()
        for sid in ids
        if "{hint}" not in (STRINGS[scope]["step"].get(sid, {}).get("description") or "")
    ]
    check("I5 所有步骤的说明都用了 {hint} 占位符（抬头+提示由程序拼）", not bad_ph, str(bad_ph))
    bad_submit = [
        f"{scope}.{sid}"
        for scope, ids in form_steps.items()
        for sid in ids
        if not has_cjk((STRINGS[scope]["step"].get(sid, {}).get("submit") or ""))
    ]
    check("I6 每个表单的提交按钮都是中文", not bad_submit, str(bad_submit))
    bad_field = [
        f"{scope}.{sid}.{key}"
        for scope, ids in form_steps.items()
        for sid in ids
        for key in (STRINGS[scope]["step"].get(sid, {}).get("data") or {})
        if not has_cjk(STRINGS[scope]["step"][sid]["data"][key])
    ]
    check("I7 每个表单字段的标签都是中文", not bad_field, str(bad_field))

    # 表单字段 key 本身必须中文：翻译一旦没刷新，HA 会把 key 原样显示出来
    # （用户实测看到过 `arriving_distance` 这种英文）
    form_field_consts = (
        cf.CITY_KW_FIELD, cf.LINE_KW_FIELD, cf.STATION_KW_FIELD,
        cf.POLL_INTERVAL_FIELD, cf.SYNC_INTERVAL_FIELD,
    )
    check("I12 所有表单字段名都是中文，且不含下划线（不会退化成英文 key）",
          all(has_cjk(x) for x in form_field_consts)
          and not any("_" in x for x in form_field_consts),
          str([x for x in form_field_consts if not has_cjk(x) or "_" in x]))

    en_data_keys = [
        f"{scope}.{sid}.{key}"
        for scope in ("config", "options")
        for sid in STRINGS[scope]["step"]
        for key in (STRINGS[scope]["step"][sid].get("data") or {})
        if not has_cjk(key)
    ]
    check("I13 语言文件 data 段的字段 key 也全是中文（参数字段已改为中文 key）",
          not en_data_keys, str(en_data_keys))

    legacy = {"back", "locate", "sync_now", "reverse", "search_mode"}
    leftovers = [
        f"{scope}.{sid}.{key}"
        for scope in ("config", "options")
        for sid in STRINGS[scope]["step"]
        for key in (STRINGS[scope]["step"][sid].get("data") or {})
        if key in legacy
    ]
    check("I8 旧版的开关字段（back/locate/sync_now/reverse/search_mode）已全部移除",
          not leftovers, str(leftovers))
    check("I9 提交按钮不再使用「提交」这类模糊字样，而是明确动作",
          not any((STRINGS[scope]["step"][sid].get("submit") or "") == "提交"
                  for scope in form_steps for sid in form_steps[scope]),
          str([STRINGS["config"]["step"][s].get("submit") for s in form_steps["config"]]))

    flowI = new_flow(FakeClient())
    rI = await flowI.async_step_user(None)
    check("I10 城市页按钮是 0.3.0 式「emoji + 动词」短句",
          all(x[:1] in "📍🔍🔄🏙" for x in menu_labels(rI)), str(menu_labels(rI)))
    verbs = ("定位", "检索", "同步", "全部")
    check("I11 城市页每个按钮 emoji 后面都是明确的动作词（读屏能听懂要干什么）",
          all(x.split(" ", 1)[-1].startswith(verbs) for x in menu_labels(rI)),
          str(menu_labels(rI)))

    # —— 🔍 检索按钮的「位置一致性」：第 1 步与第 2 步的两个分支都排在动作组第一位
    #    （整页第一个按钮固定是「⬅ 返回上一步」，所以这里看的是它在动作组里的位置）
    def first_action(res) -> list:
        return [k for k in menu_keys(res) if k != BACK][:1]

    aligned = {"第 1 步（城市）": first_action(rI)}
    flowIm = new_flow(FakeClient())
    await flowIm.async_step_user(None)
    rIm = await flowIm.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
    aligned["第 2 步（检索方式）"] = first_action(rIm)
    flowIs = new_flow(FakeClient())
    await flowIs.async_step_user(None)
    await flowIs.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
    rIs = await click(flowIs, "mode_station")
    aligned["第 3 步（站台优先）"] = first_action(rIs)
    flowIl = new_flow(FakeClient())
    await flowIl.async_step_user(None)
    await flowIl.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
    rIl = await click(flowIl, "mode_line")
    aligned["第 3 步（线路优先）"] = first_action(rIl)
    check("I14 🔍 检索按钮在每一步都排在动作组的第一个（读屏换一步不用重新找位置）",
          aligned == {"第 1 步（城市）": ["city_keyword"],
                      "第 2 步（检索方式）": ["mode_station"],
                      "第 3 步（站台优先）": ["station_keyword"],
                      "第 3 步（线路优先）": ["line_keyword"]},
          str(aligned))
    check("I14b 每一页整页第一个按钮都是「⬅ 返回上一步」（不必穿过候选列表才够得到）",
          menu_keys(rIm)[0] == BACK and menu_keys(rIs)[0] == BACK
          and menu_keys(rIl)[0] == BACK and BACK not in menu_keys(rI),
          f"{menu_keys(rIm)} / {menu_keys(rIs)} / {menu_keys(rIl)}")

    # —— 第 1 步检索之后：候选紧跟检索按钮，动作按钮排在候选之后（与第 3 步版式一致）
    flowIk = new_flow(FakeClient())
    await flowIk.async_step_user(None)
    rIk = await flowIk.async_step_city_keyword({cf.CITY_KW_FIELD: "市"})
    keysIk = menu_keys(rIk)
    picksIk = [k for k in keysIk if k.startswith(PICK)]
    check("I15 第 1 步检索后，候选城市紧跟检索按钮、两个动作按钮排在候选之后"
          "（v0.8.9 起「同步最新数据」按钮已从本页移除）",
          keysIk[0] == "city_keyword"
          and len(picksIk) >= 2
          and keysIk[1:1 + len(picksIk)] == picksIk
          and keysIk[1 + len(picksIk):] == ["city_locate", "city_browse"],
          str(keysIk))
    check("I15b 第 1 步是向导起点，所以页面上没有「⬅ 返回上一步」",
          BACK not in keysIk, str(keysIk))

    # v0.8.0 #7：对话框标题只写步骤名，步号只在说明区（抬头）出现一次，
    # 否则读屏会把「第 1 步 · 选择城市」念两遍。
    all_titles = [
        STRINGS[scope]["step"][sid].get("title", "")
        for scope in ("config", "options")
        for sid in STRINGS[scope]["step"]
    ]
    check("I16 所有步骤标题都只有步骤名，不含「第 N 步 ·」前缀（不与抬头重复）",
          all("· " not in t and not re.match(r"^第\s*\d", t) for t in all_titles),
          str(all_titles))
    # v0.8.2：0.7.0 曾把「选择线路」的标题写成「第 3 / 4 步 · 选择线路」（它随模式
    # 在 3 与 4 之间变，作者用斜杠含糊过去）。标题里出现数字一定会和抬头的
    # 「第 N 步 / 共 7 步」打架，读起来像同一步在 3 和 4 之间来回跳。
    numeric_titles = [t for t in all_titles if any(c.isdigit() for c in t)]
    check("I16b 步骤标题里不出现任何数字（0.7.0 的「第 3 / 4 步 · 选择线路」式写法不再复活）",
          not numeric_titles, str(numeric_titles))
    # v0.8.3 #2：反过来，**抬头也不写步骤名** —— 对话框标题已经写着步骤名了
    # （「选择站台」），抬头再写一遍就是「选择站台 …… 第 3 步 / 共 7 步 · 选择站台」，
    # 读屏要把同一个词念两遍。抬头只留「第 N 步 / 共 7 步」。
    check("I16c 抬头只报「第 N 步 / 共 7 步」，不带「· 步骤名」（步骤名只由对话框标题给出）",
          "{name}" not in T["progress"]
          and all(f"第 {i} 步 / 共 7 步" in header_line(i, h)
                  and "· " not in header_line(i, h)
                  for i, h in enumerate(step_headers, start=1)),
          f"{T['progress']} / {[h.splitlines()[:2] for h in step_headers]}")

    # ============ S. 第 1 步的第一行（v0.8.4） ============
    print("\n[S] 第 1 步：说明区第一行是欢迎语（整页第一个元素不再是「🔍 检索城市名」）")

    # v0.8.4 #1：用户要求「第 1 步的第 1 位写上欢迎语」—— 第 1 步是向导起点，
    # 没有「⬅ 返回上一步」可放，所以用一行欢迎语顶上，让「检索」按钮落到第二行，
    # 与第 3 步「⬅ 返回上一步 → 🔍 检索站台」的版式对齐。
    flowK = new_flow(FakeClient())
    rK = await flowK.async_step_user(None)
    linesK = [ln for ln in text_of(rK).splitlines() if ln.strip()]
    check("S1 第 1 步说明区第一行是欢迎语，第二行才是抬头「第 1 步 / 共 7 步」",
          linesK[0] == cf._T["welcome"] and linesK[1] == "第 1 步 / 共 7 步",
          str(linesK[:3]))
    check("S1b 欢迎语一句话说清「这是什么集成」（读屏用户一进来就知道装的是什么）",
          "欢迎使用" in cf._T["welcome"] and "实时公交" in cf._T["welcome"]
          and "集成" in cf._T["welcome"], cf._T["welcome"])
    check("S1c 欢迎语用中文标点、以句号收尾（读屏停顿自然，不会前后粘成一串）",
          cf._T["welcome"].endswith("。")
          and not any(c in cf._T["welcome"] for c in (",", ";", "!", "?")),
          cf._T["welcome"])

    check("S2 欢迎语只在向导第 1 步出现，第 2～6 步的说明区都没有",
          all(cf._T["welcome"] not in h for h in step_headers[1:]),
          str([cf._T["welcome"] in h for h in step_headers]))

    # 落地页才有自我介绍：翻进第 1 步的两个子页（关键词表单 / 全部城市列表）
    # 再念一遍欢迎语，读屏用户会觉得啰嗦。
    flowKb = new_flow(FakeClient())
    await flowKb.async_step_user(None)
    rKb = await flowKb.async_step_city_browse(None)
    rKk = await flowKb.async_step_city_keyword(None)
    check("S3 第 1 步的子页（全部城市列表 / 检索城市名表单）不重复欢迎语",
          cf._T["welcome"] not in text_of(rKb)
          and cf._T["welcome"] not in text_of(rKk),
          f"{text_of(rKb)[:16]!r} / {text_of(rKk)[:16]!r}")

    # 选项流里的「修改城市」是单点修改，不是向导起点，不需要自我介绍。
    entryK = FakeEntry()
    optK, _hassK = new_options(entryK, FakeClient())
    await optK.async_step_init(None)
    rKo = await optK.async_step_edit_city(None)
    check("S4 选项流「修改城市」页没有欢迎语（它不是向导的第 1 步）",
          cf._T["welcome"] not in text_of(rKo) and "第 1 步" not in text_of(rKo),
          repr(text_of(rKo)))

    # 用户要的版式：两页都是「第一行放一个非检索元素，第二行才是检索按钮」——
    # 第 1 步第一行是欢迎语（文字），第 3 步第一行是「⬅ 返回上一步」（按钮）。
    flowKs = new_flow(FakeClient())
    await flowKs.async_step_user(None)
    await flowKs.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
    rKs = await click(flowKs, "mode_station")
    check("S5 第 1 步与第 3 步版式对齐：第一行都不是检索，检索排第二",
          linesK[0] == cf._T["welcome"]
          and menu_keys(rK)[0] == "city_keyword"
          and menu_keys(rKs)[:2] == [BACK, "station_keyword"],
          f"{linesK[0]!r} → {menu_keys(rK)[:1]} | {menu_keys(rKs)[:2]}")

    # v0.8.5：域名由 xm_bus 改为 my_bus。
    # 用户已把集成从 HA 删除 ⇒ 没有配置条目会失效，是零成本改域名的窗口期。
    # HA 规定 domain 只能用小写字母 + 数字 + 下划线，所以是 my_bus 而不是 My Bus。
    manifest = json.load(open(os.path.join(_CC, "manifest.json"), encoding="utf-8"))
    check("S6 集成名是 My Bus（manifest 的 name 与设备制造商都改了）",
          manifest["name"] == "My Bus" and const_mod.MANUFACTURER == "My Bus",
          f"{manifest['name']} / {const_mod.MANUFACTURER}")
    check("S7 域名是 my_bus，存储文件名随之变为 my_bus.data",
          manifest["domain"] == "my_bus"
          and const_mod.DOMAIN == "my_bus"
          and const_mod.SYNC_STORAGE_KEY == "my_bus.data",
          f"{manifest['domain']} / {const_mod.DOMAIN} / {const_mod.SYNC_STORAGE_KEY}")
    # HA 强制要求安装目录名 == domain，否则集成加载失败。
    check("S9 安装目录名是 my_bus（HA 要求目录名与 domain 同名）",
          os.path.basename(os.path.normpath(_CC)) == "my_bus",
          os.path.basename(os.path.normpath(_CC)))

    UI_FILES = ("config_flow.py", "const.py", "coordinator.py", "__init__.py",
                "strings.json", "translations/zh-Hans.json",
                "translations/en.json", "sensor.py", "trigger.py",
                "triggers.yaml", "icons.json", "services.py",
                "device_trigger.py", "data_sync.py",
                "diagnostics.py")
    readme_path = os.path.join(_ROOT, "README.md")
    # README 不在集成包内，包内复跑时跳过；「版本历史」里允许保留当时的域名（史实），
    # 所以只检查它之前的正文。
    readme_body = ""
    if os.path.exists(readme_path):
        readme_body = open(readme_path, encoding="utf-8").read().split("## 版本历史")[0]
    check("S8 界面文件里不再出现旧域名字面量「xm_bus」",
          not any("xm_bus" in open(os.path.join(_CC, f), encoding="utf-8").read()
                  for f in UI_FILES),
          "")
    # README 正文只在「升级说明」里允许提到旧域名（要告诉用户删旧目录、改服务名），
    # 其余正文一律用新域名。
    body_xm = [ln for ln in readme_body.splitlines() if "xm_bus" in ln]
    check("S8b README 正文里旧域名只出现在「升级说明」行（其余正文都用 my_bus）",
          all("升级" in ln for ln in body_xm),
          str(body_xm))
    check("S10 界面文字与 README 标题里不再出现旧名「XM Bus」",
          (not os.path.exists(readme_path)
           or open(readme_path, encoding="utf-8").read().splitlines()[0].startswith("# My Bus"))
          and not any("XM Bus" in open(os.path.join(_CC, f), encoding="utf-8").read()
                      for f in UI_FILES),
          "")

    # v0.8.0 #14：文案表里的死键（定义了却没人取用）与死参数一律清掉
    src = open(os.path.join(_CC, "config_flow.py"), encoding="utf-8").read()
    dead_keys = sorted(
        k for k in cf._T
        if not k.endswith("_opt") and src.count(f'"{k}"') < 2
    )
    check("I17 文案表里没有「定义了却没人取用」的死键",
          not dead_keys, str(dead_keys))
    # h_mode / step_mode 在「恢复 6 步」后重新用上了，不再属于死文案；
    # v0.8.9 又清掉三个：第 1 步的同步按钮及其专用文案，以及被改写的「下一步」变体。
    gone_words = ("back_none", "menu_back_init", "h_checking", "opt_unchanged",
                  "act_city_sync", "h_sync_ok", "act_next_confirm_opt")
    check("I17b 已删除的死文案不再残留",
          all(w not in cf._T for w in gone_words)
          and not any(f'"{w}"' in src for w in gone_words),
          str([w for w in gone_words if f'"{w}"' in src]))
    check("I18 说明文字里不再带着没人消费的占位符参数（when= / max_hours= 已清掉）",
          "max_hours=" not in src
          and re.search(r'_t\("h_city",', src) is None
          and re.search(r'_t\("h_sync_interval",', src) is None, "")

    # v0.8.0 后续拍板：**保留 emoji**（用户：「emoji 对于现在的读屏软件影响不大，
    # 如果保留是不是更利于普通用户呢」）。现代读屏对 emoji 的处理基本是跳过或
    # 只念一次名称，真正会「卡住」用户的是**只有 emoji、没有文字**的按钮。
    # 所以约定收紧为：emoji 只能当**前缀装饰**，文字必须永远完整。
    EMOJI = re.compile(
        "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
        "\U00002300-\U000023FF\U000020E3\U0000FE0F]"
    )
    EMOJI_LEAD = re.compile(
        "^[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
        "\U00002300-\U000023FF\U000020E3\U0000FE0F]+[ \u00a0]*"
    )
    cjk = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF]")

    def _tail_after_icon(text: str) -> str:
        """返回剥掉「开头那串图标 + 一个空格」之后的剩余部分."""
        m = EMOJI_LEAD.match(text)
        return text[m.end():] if m else text

    button_keys = [
        k for k, v in cf._T.items()
        if isinstance(v, str) and k.startswith(("act_", "back_", "menu_", "opt_"))
    ]
    emoji_buttons = [k for k in button_keys if EMOJI.search(cf._T[k])]
    check("I19 按钮保留 emoji，但 emoji 只当前缀装饰：去掉它必须还剩完整中文",
          bool(emoji_buttons)
          and all(cjk.search(EMOJI.sub("", cf._T[k])) for k in button_keys)
          and all(not EMOJI.search(_tail_after_icon(cf._T[k])) for k in emoji_buttons),
          str([k for k in button_keys if not cjk.search(EMOJI.sub("", cf._T[k]))]))

    # 图标本身就是可记忆的定位线索（对读屏用户也一样，前几个字就听出来了）：
    # 同一类动作必须共用同一个前缀图标。
    icon_groups = {
        "🔍": ("act_city_keyword", "act_city_keyword_again", "act_station_keyword",
               "act_station_keyword_again", "act_line_keyword", "act_line_keyword_again"),
        "🚏": ("act_mode_station",),
        "🚌": ("act_mode_line",),
        "⬅": ("back_to", "back_to_menu"),
        "🔄": ("act_sync_now", "act_sync_on", "act_sync_off", "opt_sync"),
        "⏱": ("act_settings_params", "opt_settings", "act_sync_interval"),
        "⏭": ("act_next_sync", "act_next_confirm"),
        "✅": ("act_finish", "act_finish_opt", "menu_finish"),
    }
    bad_icon = {
        icon: [k for k in keys if cf._T[k].split(" ")[0] != icon]
        for icon, keys in icon_groups.items()
    }
    check("I19b 同类动作共用同一个前缀图标（检索🔍 / 选站台🚏 / 选线路🚌 / 返回⬅ / 同步🔄 / 参数⏱ / 下一步⏭ / 完成✅）",
          not any(bad_icon.values()), str({k: v for k, v in bad_icon.items() if v}))

    # 说明文字（h_*）不受前缀限制——它可以引述按钮名，例如
    # 「确认无误点『完成』，要改就点『⬅ 返回上一步』。」
    hint_with_emoji = [
        k for k, v in cf._T.items()
        if isinstance(v, str) and k.startswith("h_") and EMOJI.search(v)
    ]
    check("I19c 说明文字引述按钮名时允许中途带 emoji（只约束按钮，不约束提示；候选模板除外）",
          all("「" in cf._T[k] for k in hint_with_emoji if k not in ("h_pick_station", "h_pick_line")),
          str([k for k in hint_with_emoji if "「" not in cf._T[k]]))

    # ============ J. 选项流 ============
    print("\n[J] 选项流：按钮式入口菜单 + 与配置流相同的向导步骤")

    entryJ = FakeEntry()
    flowJ, hassJ = new_options(entryJ, FakeClient())
    rJ = await flowJ.async_step_init(None)
    check("J1 选项菜单 5 个按钮，文案都带当前值",
          set(menu_keys(rJ)) == {"edit_city", "edit_line", "edit_settings", "sync", "done"}
          and any("修改城市（当前：厦门市）" in x for x in menu_labels(rJ))
          and any(x == "✅ 完成" for x in menu_labels(rJ)),
          str(menu_labels(rJ)))
    check("J2 选项菜单不显示「第 N 步」进度（它不是向导）",
          "步 / 共 7 步" not in text_of(rJ), text_of(rJ).splitlines()[0])
    check("J3 选项菜单没有多余的「上一步」按钮", BACK not in menu_keys(rJ), str(menu_keys(rJ)))

    rJ = await click(flowJ, "edit_line")
    check("J4 修改线路/站台 → 从第 2 步「选择检索方式」开始，且「上一步」是「⬅ 返回选项菜单」",
          rJ["step_id"] == "mode" and menu_of(rJ).get(BACK) == "⬅ 返回选项菜单",
          f"{rJ.get('step_id')} / {menu_of(rJ).get(BACK)}")
    rJ = await click(flowJ, "mode_station")
    check("J4b 选项流里点「🚏 先选站台」→ 进入第 3 步「选择站台」",
          rJ["step_id"] == "station", str(rJ.get("step_id")))
    rJ = await flowJ.async_step_station_keyword({cf.STATION_KW_FIELD: "县口路站"})
    rJ = await click_pick(flowJ, flowJ._station_options.index("县口路站"))   # 选站台
    rJ = await click_pick(flowJ, 0)                                        # 选线路
    check("J5 选完线路直接进确认页，按钮改成「保存修改」，上一步回到刚才选的线路",
          rJ["step_id"] == "confirm" and any("保存修改" in x for x in menu_labels(rJ))
          and menu_of(rJ).get(BACK) == "⬅ 返回上一步"
          and flowJ._prev_step("confirm") == "line",
          f"{menu_labels(rJ)}")
    check("D7 v0.9.5 选项流的确认页同样列出「自动同步：每 12 小时」一行",
          "自动同步：每 12 小时" in text_of(rJ), text_of(rJ).replace("\n", " / "))
    rJ = await click(flowJ, "finish")
    check("J6 点「保存修改」→ 写回条目并回到选项菜单",
          rJ["step_id"] == "init"
          and hassJ.config_entries.updated
          and hassJ.config_entries.updated[-1][1]["data"]["station"] == "县口路站"
          and "已更新为" in text_of(rJ),
          text_of(rJ))

    rJ = await click(flowJ, "edit_city")
    check("J7 修改城市 → 从第 1 步开始（第 1 步也带「⬅ 返回选项菜单」按钮）",
          rJ["step_id"] == "city"
          and menu_of(rJ).get(BACK) == "⬅ 返回选项菜单", str(rJ.get("step_id")))
    rJ = await click(flowJ, BACK)
    check("J8 点「上一步」真的回到选项菜单", rJ["step_id"] == "init", str(rJ.get("step_id")))

    flowJ2, _ = new_options(FakeEntry(), FakeClient())
    await flowJ2.async_step_init(None)
    rJ = await click(flowJ2, "edit_settings")
    check("J9 修改到站参数 → 直接打开数字表单（不用再多点一次）",
          is_form(rJ) and rJ["step_id"] == "settings_params"
          and selector_kinds(rJ) == {"number"}, str(rJ.get("step_id")))
    rJ = await flowJ2.async_step_settings_params(
        {cf.POLL_INTERVAL_FIELD: 45}
    )
    check("J10 保存参数 → 写回 options 并结束选项流（其余选项保留）",
          rJ.get("type") == "create_entry"
          and rJ["data"] == {"poll_interval": 45},
          str(rJ.get("data")))

    flowJ3, _ = new_options(FakeEntry(), FakeClient())
    await flowJ3.async_step_init(None)
    rJ = await click(flowJ3, "done")
    check("J11 点「完成」原样结束，不丢已有选项",
          rJ.get("type") == "create_entry"
          and rJ["data"] == {"poll_interval": 10},
          str(rJ.get("data")))

    # ============ M. 选项流「数据同步」菜单 ============
    print("\n[M] 数据同步菜单：立即同步 / 改间隔 / 开关自动同步（都是按钮）")

    entryM2 = FakeEntry()
    flowM, hassM = new_options(entryM2, FakeClient())
    await flowM.async_step_init(None)
    rM = await click(flowM, "sync")
    check("M1 同步菜单 3 个动作按钮 + 「返回选项菜单」",
          set(menu_keys(rM)) == {"sync_now", "sync_interval", "sync_toggle", BACK},
          str(menu_keys(rM)))
    check("M2 提示里写明上次同步 / 自动同步 / 本地缓存规模",
          all(x in text_of(rM) for x in ("上次同步", "自动同步", "本地缓存")), text_of(rM))
    check("M3 「立即同步」按钮带上次同步时间",
          any(x.startswith("🔄 立即同步（上次：") for x in menu_labels(rM)), str(menu_labels(rM)))
    rM = await click(flowM, "sync_now")
    check("M4 点「立即同步」→ 显示同步结果并留在菜单",
          rM["step_id"] == "sync" and "同步完成" in text_of(rM), text_of(rM))

    flowM3, _hassM3 = new_options(FakeEntry(), FakeClient(fail_cities=True))
    await flowM3.async_step_init(None)
    rM3 = await click(flowM3, "sync_now")
    check("M4b 同步失败时只报失败，不显示「同步完成：城市 0、线路 0、站台 0」",
          "同步失败" in text_of(rM3) and "同步完成" not in text_of(rM3)
          and "城市 0" not in text_of(rM3),
          text_of(rM3))

    rM = await click(flowM, "sync_toggle")
    rM2 = await click(flowM, "sync")
    check("M5 点「关闭自动同步」→ 同一位置变成「启用自动同步」按钮（没有开关控件）",
          "启用自动同步" in menu_of(rM2).get("sync_toggle", "")
          and "关闭自动同步" not in menu_of(rM2).get("sync_toggle", ""),
          str(menu_of(rM2).get("sync_toggle")))
    rM = rM2
    rM = await click(flowM, "sync_interval")
    check("M6 改同步间隔是数字表单（单位：小时），字段名中文且自带范围",
          is_form(rM) and fields_of(rM) == {cf.SYNC_INTERVAL_FIELD}
          and selector_kinds(rM) == {"number"}
          and field_map(rM)[cf.SYNC_INTERVAL_FIELD].config.get("unit_of_measurement") == "小时"
          and "范围 1 到 168" in cf.SYNC_INTERVAL_FIELD,
          str(selector_kinds(rM)))
    rM = await flowM.async_step_sync_interval({cf.SYNC_INTERVAL_FIELD: 24})
    check("M7 提交后间隔变成每 24 小时并回到同步菜单",
          rM["step_id"] == "sync" and "每 24 小时" in text_of(rM), text_of(rM))
    syncM = hassM.data["my_bus"]["sync"]
    check("M8 同步设置写进了数据同步层（重启后仍生效）", syncM.interval == 24 * 3600,
          str(syncM.interval))

    print("\n[K] 数据同步层：缓存 / 过期 / 落盘 / 定时 / 清理")

    clientK = FakeClient()
    hassS = stub_ha._fake_hass(None)
    syncK = ds.XmBusDataSync(hassS, lambda city: clientK)

    live = await syncK.async_cities()
    check("K1 首次读取城市→请求接口并按拼音排序(已清洗)",
          len(live) == FAKE_CITY_COUNT and "厦门市测试" not in live
          and live == api.sorted_cities(api.filter_cities(FAKE_CITIES)), str(live))
    await syncK.async_cities()
    check("K2 第二次读取命中缓存，不再请求接口", clientK.calls["cities"] == 1)

    syncK._items[ds.KEY_CITIES]["ts"] = time.time() - (ds.CITY_CACHE_TTL + 60)
    await syncK.async_cities()
    check("K3 缓存过期后自动重新拉取", clientK.calls["cities"] == 2)

    blob = hassS._store_data.get(ds.SYNC_STORAGE_KEY)
    check("K4 缓存已落盘（items/settings/stats 齐备）",
          isinstance(blob, dict) and {"items", "settings", "stats"} <= set(blob), str(blob)[:60])

    syncK2 = ds.XmBusDataSync(hassS, lambda city: clientK)
    restored = await syncK2.async_cities()
    check("K5 重启后可从磁盘恢复缓存（不再请求接口）",
          restored == live and clientK.calls["cities"] == 2)

    syncK2._last_sync = time.time()
    await syncK2.async_start()
    timers = [t for t in getattr(hassS, "_timers", []) if t["active"]]
    check("K6 async_start 注册定时同步（间隔=配置间隔）",
          len(timers) == 1 and timers[0]["interval"] == timedelta(seconds=syncK2.interval))
    check("K7 默认间隔=12 小时", syncK2.interval == cf.DEFAULT_SYNC_INTERVAL
          and syncK2.interval_hours == 12.0)
    await syncK2.async_set_interval(30 * 3600)
    timers = [t for t in hassS._timers if t["active"]]
    check("K8 修改间隔后定时器按新间隔重建",
          len(timers) == 1 and timers[0]["interval"] == timedelta(hours=30))
    await syncK2.async_set_interval(0)
    check("K9 间隔越界被夹到下限(1 小时)", syncK2.interval == cf.MIN_SYNC_INTERVAL)
    await syncK2.async_set_interval(999 * 24 * 3600)
    check("K10 间隔越界被夹到上限(168 小时)", syncK2.interval == cf.MAX_SYNC_INTERVAL)
    await syncK2.async_set_interval(12 * 3600)
    await syncK2.async_set_enabled(False)
    check("K11 关闭自动同步后没有活动定时器",
          not [t for t in hassS._timers if t["active"]] and not syncK2.enabled)
    await syncK2.async_set_enabled(True)
    check("K12 重新启用后定时器恢复",
          len([t for t in hassS._timers if t["active"]]) == 1 and syncK2.enabled)

    st = syncK2.status()
    check("K13 status() 字段齐备",
          {"enabled", "interval", "interval_hours", "last_sync", "cities", "lines",
           "stations", "failures", "last_error", "issue_texts"} <= set(st), str(sorted(st)))

    topo = await syncK2.async_line_stations("厦门市", "615路", "1")
    check("K14 线路站点拓扑入缓存（含站序）",
          len(topo) == 4 and topo[2]["stationOrder"] == 12)
    await syncK2.async_line_stations("厦门市", "615路", "1")
    check("K15 第二次读拓扑命中缓存", clientK.calls["line_stations"] == 1)

    hits = await syncK2.async_station_lines("厦门市", "县口路站")
    cached_raw = syncK2._fresh(ds.station_key("厦门市", "县口路站"), 0)
    check("K16 站台线路入缓存", len(hits) == 4)
    check("K17 实时到站信息(neartext)不入缓存",
          all("raw_neartext" not in item and "neartext" not in item for item in cached_raw))

    endpoints = await syncK2.async_line_endpoints("厦门市")
    check("K18 线路起终点入缓存",
          endpoints.get(("615路", "1")) == ("四林总站", "丙洲东头尾站"))

    await syncK2.async_search_stations("厦门市", "同安")
    await syncK2.async_search_stations("厦门市", "同安")
    check("K19 关键词搜索走短时内存缓存（第二次不再请求）",
          clientK.calls["search_stations"] == 1)
    await syncK2.async_search_stations("厦门市", "同安", force=True)
    check("K20 force=True 时绕开搜索缓存", clientK.calls["search_stations"] == 2)

    stale_unprotected = ds.station_key("厦门市", "很久以前的站")
    stale_protected = ds.line_key("厦门市", "615路", "1")
    fresh_unprotected = ds.line_key("厦门市", "999路", "1")
    syncK2._items[stale_unprotected] = {"ts": time.time() - (ds.PRUNE_UNUSED_AFTER + 60), "data": []}
    syncK2._items[stale_protected] = {"ts": time.time() - (ds.PRUNE_UNUSED_AFTER + 60), "data": []}
    syncK2._items[fresh_unprotected] = {"ts": time.time(), "data": []}
    pruned = syncK2._prune({ds.KEY_CITIES, stale_protected})
    check("K21 清理长期未使用条目，受保护/仍新鲜的保留",
          pruned == 1 and stale_unprotected not in syncK2._items
          and stale_protected in syncK2._items and fresh_unprotected in syncK2._items,
          f"pruned={pruned}")

    entryK = FakeEntry()
    hassE = stub_ha._fake_hass(None, entries=[entryK])
    clientE = FakeClient()
    syncE = make_sync(hassE, clientE, cities=api.filter_cities(FAKE_CITIES))
    before_gen = syncE.generation
    summary = await syncE.async_sync()
    check("K22 async_sync 返回同步摘要（城市/线路/站台）",
          summary["ok"] and summary["cities"] == FAKE_CITY_COUNT
          and summary["lines"] == 1 and summary["stations"] == 1,
          str({k: summary[k] for k in ("ok", "cities", "lines", "stations")}))
    check("K23 同步后 generation 递增（协调器据此刷新拓扑）",
          syncE.generation == before_gen + 1)
    check("K24 同步后记录 last_sync 并落盘",
          syncE.status()["last_sync"] is not None
          and hassE._store_data[ds.SYNC_STORAGE_KEY]["stats"]["last_sync"] is not None)
    check("K25 同步强制刷新城市（绕过 TTL）", clientE.calls["cities"] == 1)

    syncF = make_sync(stub_ha._fake_hass(None), FakeClient(),
                      cities=api.filter_cities(FAKE_CITIES))
    syncF.schedule_sync()
    first_task = syncF._task
    syncF.schedule_sync()
    check("K26 后台同步任务去重（同时只跑一个）", syncF._task is first_task)
    await syncF._hass.async_block_till_done()

    syncG = make_sync(stub_ha._fake_hass(None), FakeClient(), cities=None, last_sync=0)
    check("K27 空缓存 + 无同步 → _needs_sync() 为真", syncG._needs_sync() is True)
    await syncG.async_start()
    await syncG._hass.async_block_till_done()
    check("K28 启动时发现数据过期→自动补一次同步",
          syncG.status()["last_sync"] is not None and bool(syncG._fresh(ds.KEY_CITIES, 0)))

    # ============ L. 条目校对 ============
    print("\n[L] 条目校对：站序自动修正 / 改线提示")

    entryL = FakeEntry()
    hassL = stub_ha._fake_hass(None, entries=[entryL])
    topologyL = dict(DEFAULT_TOPOLOGY)
    topologyL[("615路", "1")] = [
        {"stationName": "四林总站", "stationOrder": 1},
        {"stationName": "梨子林站", "stationOrder": 2},
        {"stationName": "县口路站", "stationOrder": 15},
    ]
    syncL = make_sync(hassL, FakeClient(topology=topologyL), cities=api.filter_cities(FAKE_CITIES))
    repaired, issues = await syncL.async_validate_entries([entryL])
    check("L1 站序与线上不一致→自动修正条目",
          repaired == 1 and entryL.data["station_order"] == 15 and not issues,
          f"repaired={repaired}, order={entryL.data['station_order']}")
    check("L2 修正通过 config_entries 写回（触发条目重载）",
          hassL.config_entries.updated
          and hassL.config_entries.updated[-1][1]["data"]["station_order"] == 15)

    entryM = FakeEntry(station="同安汽车站", direction="1")
    hassM = stub_ha._fake_hass(None, entries=[entryM])
    syncM = make_sync(hassM, FakeClient(), cities=api.filter_cities(FAKE_CITIES))
    repaired, issues = await syncM.async_validate_entries([entryM])
    check("L3 站台被挪到另一方向→提示重新选择（不改动配置）",
          repaired == 0 and len(issues) == 1 and "下行" in issues[0].reason
          and entryM.data["direction"] == "1", str([i.reason for i in issues]))

    entryN = FakeEntry(station="不存在站")
    hassN = stub_ha._fake_hass(None, entries=[entryN])
    syncN = make_sync(hassN, FakeClient(), cities=api.filter_cities(FAKE_CITIES))
    repaired, issues = await syncN.async_validate_entries([entryN])
    check("L4 站台已不在线路上→记录问题",
          repaired == 0 and len(issues) == 1 and "不在线路上" in issues[0].reason,
          str([i.reason for i in issues]))

    entryO = FakeEntry()
    hassO = stub_ha._fake_hass(None, entries=[entryO])
    syncO = make_sync(hassO, FakeClient(fail_topology=True), cities=api.filter_cities(FAKE_CITIES))
    repaired, issues = await syncO.async_validate_entries([entryO])
    check("L5 拓扑取不到→记录「无法获取线路站点」",
          repaired == 0 and len(issues) == 1 and "无法获取线路站点" in issues[0].reason)

    entryP = FakeEntry()
    hassP = stub_ha._fake_hass(None, entries=[entryP])
    syncP = make_sync(hassP, FakeClient(topology=topologyL), cities=api.filter_cities(FAKE_CITIES))
    summary = await syncP.async_sync([entryP])
    check("L6 async_sync 携带修正条数",
          summary["repaired"] == 1 and entryP.data["station_order"] == 15
          and syncP.status()["issues"] == [])

    issue = ds.SyncIssue(
        entry_id="e9", title="t", city="厦门市", line="615路",
        direction="1", station="县口路站", reason="测试原因",
    )
    check("L7 不一致问题可读文案",
          issue.text == "厦门市 615路（上行）县口路站：测试原因", issue.text)

    print("\n[N] 服务：get_arrivals（实时）/ sync_data（同步）")

    svc_hass = stub_ha._fake_hass(None, entries=[FakeEntry()])
    svc_client = FakeClient()
    make_sync(svc_hass, svc_client, cities=api.filter_cities(FAKE_CITIES))
    svc.async_setup_services(svc_hass)
    reg = svc_hass.services.registered
    check("N1 注册 get_arrivals / sync_data",
          {"my_bus.get_arrivals", "my_bus.sync_data"} <= set(reg), str(sorted(reg)))
    check("N2 get_arrivals 只返回响应(ONLY)，sync_data 可选响应(OPTIONAL)",
          reg["my_bus.get_arrivals"]["supports_response"] == "only"
          and reg["my_bus.sync_data"]["supports_response"] == "optional")

    arrivals = await reg["my_bus.get_arrivals"]["handler"](
        stub_ha.service_call({"station": "县口路", "line": "615"}))
    check("N3 get_arrivals 走的是实时接口（不读缓存）",
          svc_client.calls["station_lines"] >= 1 and arrivals["arrivals"]
          and arrivals["arrivals"][0]["line"] == "615路")
    check("N4 get_arrivals 返回摘要供 AI 播报", "最近车辆" in arrivals["summary"])

    before = svc_client.calls["cities"]
    summary = await reg["my_bus.sync_data"]["handler"](stub_ha.service_call({}))
    check("N5 sync_data 返回同步摘要",
          summary["ok"] and summary["cities"] == FAKE_CITY_COUNT
          and svc_client.calls["cities"] == before + 1)
    summary_bj = await reg["my_bus.sync_data"]["handler"](
        stub_ha.service_call({"city": "北京市"}))
    check("N6 sync_data 支持按城市限定监控", summary_bj["city"] == "北京市")

    print("\n[O] 数据同步传感器 / 诊断 / 平台注册 / 旧条目迁移")

    check("O1 PLATFORMS 只含 sensor（v0.9.15 起事件平台随公交到站一起删除）",
          entry_init.PLATFORMS == ["sensor"]
          or [str(x) for x in entry_init.PLATFORMS] == ["event", "sensor"]
          or ["event", "sensor"] == [getattr(x, "value", x) for x in entry_init.PLATFORMS],
          str(entry_init.PLATFORMS))
    check("O1b button.py 已删除（设备页不再有「控制」区的同步按钮）",
          not os.path.exists(os.path.join(_CC, "button.py")))

    entryT = FakeEntry()
    hassT = stub_ha._fake_hass(None, entries=[entryT])
    syncT = make_sync(hassT, FakeClient(), cities=api.filter_cities(FAKE_CITIES))
    coord = coord_mod.XmBusCoordinator(hassT, entryT, FakeClient(), syncT)
    sensor_mod = importlib.import_module("my_bus.sensor")
    sensor = sensor_mod.XmBusDataSyncSensor(coord, entryT)
    check("O2 传感器唯一 ID 与设备信息",
          sensor._attr_unique_id == "e1_data_sync"
          and sensor._attr_device_info["name"].startswith("My Bus（厦门市"),
          str(sensor._attr_device_info))
    # v0.8.6：设备信息的「型号」不再带城市前缀（设备名里已经有城市与线路了）。
    check("O2b 设备型号是「公交到站监控」，不再带城市前缀",
          sensor._attr_device_info["model"] == "公交到站监控"
          and "厦门" not in str(sensor._attr_device_info["model"]),
          str(sensor._attr_device_info.get("model")))
    check("O3 数据同步 v0.9.15 起不是诊断类（否则实体树里选不到同步触发器）+ 时间戳设备类",
          getattr(sensor, "_attr_entity_category", None) is None
          and sensor._attr_device_class == "timestamp")

    await syncT.async_sync([entryT])
    check("O4 传感器状态=上次同步时间(UTC)",
          sensor.native_value is not None and sensor.native_value.tzinfo is not None)
    attrs = sensor.extra_state_attributes
    check("O5 传感器属性含间隔/缓存规模/问题",
          attrs["刷新间隔小时"] == 12.0 and attrs["城市数"] == FAKE_CITY_COUNT
          and attrs["线路数"] == 1 and attrs["站台数"] == 1 and attrs["问题"] == [],
          str(attrs))

    hassT.data["my_bus"][entryT.entry_id] = coord
    info = await diag.async_get_config_entry_diagnostics(hassT, entryT)
    check("O6 诊断信息含 entry / runtime / data_sync",
          set(info) == {"entry", "runtime", "data_sync"}
          and info["entry"]["data"]["city"] == "厦门市"
          and info["runtime"]["line"] == "615路"
          and info["data_sync"]["cities"] == FAKE_CITY_COUNT, str(sorted(info)))
    check("O7 诊断包含缓存键清单（便于确认一致性）",
          ds.KEY_CITIES in info["data_sync"]["cache_keys"])

    class OldEntry(FakeEntry):
        def __init__(self):
            super().__init__()
            self.data.pop("city", None)
            self.version = 1

    old = OldEntry()
    hassU = stub_ha._fake_hass(None, entries=[old])
    ok = await entry_init.async_migrate_entry(hassU, old)
    check("O8 旧条目(v1)迁移补上城市字段", ok and old.data["city"] == "厦门市"
          and hassU.config_entries.updated[-1][1]["version"] == 2)
    check("O9 最后一个监控卸载后停掉定时同步",
          entry_init._has_loaded_entries(hassU) is False)

    print("\n[P] 协调器：拓扑取自同步层，改线后自动跟随")

    entryV = FakeEntry()
    hassV = stub_ha._fake_hass(None, entries=[entryV])
    clientV = FakeClient()
    syncV = make_sync(hassV, clientV, cities=api.filter_cities(FAKE_CITIES))
    coordV = coord_mod.XmBusCoordinator(hassV, entryV, clientV, syncV)
    await coordV._async_update_data()
    check("P1 拓扑取自数据同步层缓存（走缓存而非每次请求）",
          coordV._total_stops == 4 and clientV.calls["line_stations"] == 1,
          f"stops={coordV._total_stops} calls={clientV.calls['line_stations']}")
    check("P2 目标站序按线上数据校正", coordV.station_order == 12)
    check("P3 协调器向外暴露同步状态",
          coordV.sync_status is not None and coordV.sync_status["cities"] == FAKE_CITY_COUNT)

    new_topology = dict(DEFAULT_TOPOLOGY)
    new_topology[("615路", "1")] = [
        {"stationName": "四林总站", "stationOrder": 1},
        {"stationName": "梨子林站", "stationOrder": 2},
        {"stationName": "新加站", "stationOrder": 3},
        {"stationName": "县口路站", "stationOrder": 15},
    ]
    clientV.topology = new_topology
    await syncV.async_sync([entryV])
    await coordV._async_update_data()
    check("P4 同步完成后协调器自动重读拓扑并跟随站序/站数",
          coordV.station_order == 15 and coordV._total_stops == 4,
          f"order={coordV.station_order} stops={coordV._total_stops}")
    check("P5 已配置条目也被同步流程修正到最新站序",
          entryV.data["station_order"] == 15)
    check("P6 未到同步周期时不重复读拓扑", clientV.calls["line_stations"] == 2)
    await coordV._async_update_data()
    check("P7 generation 未变则不再重读拓扑", clientV.calls["line_stations"] == 2)

    coordW = coord_mod.XmBusCoordinator(hassV, FakeEntry(), clientV)
    await coordW._async_update_data()
    check("P8 无同步层时仍可直接工作（兼容路径）",
          coordW._total_stops == 4 and coordW.sync_status is None)

    # ============ Q. 里程换算与到站判定（v0.9.1 起无阈值） ============
    print("\n[Q] 里程：CMD104 的「车→下一站」+ 分段里程 换算成「到监控站还有多少公里」")
    SEG = [1000.0, 2000.0, 3000.0, 0.0]   # 4 站线路：1→2 / 2→3 / 3→4 / 末站

    out = logic.compute_distances(
        [logic.BusPosition("闽D1", "2号站", 3, 450.0)], 3, 4, False, SEG
    )
    check("Q1 车正驶向目标站（剩余 0 站）→ 里程就是「车→该站」的 450 米",
          out and out[0]["remaining"] == 0 and out[0]["distance_m"] == 450.0, str(out))

    out = logic.compute_distances(
        [logic.BusPosition("闽D1", "1号站", 2, 800.0)], 3, 4, False, SEG
    )
    check("Q2 还差 1 站 → 车→下一站 800 + 一段分段里程 2000 = 2800 米",
          out[0]["remaining"] == 1 and out[0]["distance_m"] == 2800.0, str(out))

    out = logic.compute_distances(
        [logic.BusPosition("闽D1", "1号站", 1, 500.0)], 3, 4, False, SEG
    )
    check("Q3 还差 2 站 → 500 + 1000 + 2000 = 3500 米",
          out[0]["distance_m"] == 3500.0, str(out))

    out = logic.compute_distances(
        [logic.BusPosition("闽D1", "2号站", 3, 450.0)], 3, 4, False, []
    )
    check("Q4 没有分段里程时：只有「车正驶向目标站」能给确切里程，其余为未知",
          out[0]["distance_m"] == 450.0
          and logic.compute_distances(
              [logic.BusPosition("闽D2", "1号站", 2, 800.0)], 3, 4, False, []
          )[0]["distance_m"] is None)

    out = logic.compute_distances(
        [logic.BusPosition("闽D1", "3号站", 4, 300.0)], 2, 4, False, SEG
    )
    check("Q5 非环线已过站 → 该车不再参与判定（不会给出负数里程）", out == [], str(out))

    out = logic.compute_distances(
        [logic.BusPosition("闽D1", "末站", 4, 500.0)], 2, 4, True, SEG
    )
    check("Q6 环线过站后绕回：里程按分段里程累加（500+0+1000=1500 米）",
          out and out[0]["remaining"] == 2 and out[0]["distance_m"] == 1500.0, str(out))

    def km_bus(remaining, distance_m, plate="闽D9", stopped=True):
        return {
            "plate": plate, "current_stop": "某站",
            "remaining": remaining, "distance_m": distance_m,
            "stopped": stopped,
        }

    # v0.9.15：事件体系整体删除
    check("Q7 v0.9.15 ArrivalTracker / ArrivalEventData / EVENT_BUS_ARRIVED 已删除",
          not hasattr(logic, "ArrivalTracker") and not hasattr(logic, "ArrivalEventData")
          and not hasattr(logic, "EVENT_BUS_ARRIVED"))

    out = logic.compute_distances(
        [logic.BusPosition("闽D1", "2号站", 3, 450.0, status_type="2")], 3, 4, False, SEG
    )
    check("Q15 statusType=2（在途）→ arrivals 标记 stopped=False",
          out and out[0]["remaining"] == 0 and out[0]["stopped"] is False, str(out))
    out = logic.compute_distances(
        [logic.BusPosition("闽D1", "2号站", 3, 0.0, status_type="0")], 3, 4, False, SEG
    )
    check("Q16 statusType=0（停站中）→ arrivals 标记 stopped=True",
          out and out[0]["stopped"] is True, str(out))
    out = logic.compute_distances(
        [logic.BusPosition("闽D1", "2号站", 3, 450.0)], 3, 4, False, SEG
    )
    check("Q17 接口没给 statusType（老客户端/测试桩）→ 按老口径视为停站",
          out and out[0]["stopped"] is True, str(out))

    class DistanceClient(FakeClient):
        """CMD104 带分段里程与「车→下一站」距离."""

        async def realtime(self, line, direction):
            self.calls["realtime"] += 1
            return api.RealtimeSnapshot(
                positions=[
                    api.BusPosition(
                        plate="闽D-TEST", current_stop="梨子林站", position=2,
                        distance_to_next_stop_m=800.0,
                    )
                ],
                segments_m=[1000.0] * 12,
            )

    hassQ = stub_ha._fake_hass()
    syncQ = make_sync(hassQ, DistanceClient(), cities=api.filter_cities(FAKE_CITIES))
    entryQ = FakeEntry()
    coordQ = coord_mod.XmBusCoordinator(hassQ, entryQ, DistanceClient(), syncQ)
    await coordQ._async_update_data()
    nearestQ = coordQ.nearest_bus()
    check("Q14 协调器把里程算进 arrivals，并能给出「最近的一辆车」",
          coordQ.arrivals[0]["distance_m"] == 800.0 + 1000.0 * 10
          and nearestQ is not None and nearestQ["remaining"] == 10,
          str(coordQ.arrivals))

    # v0.9.1：阈值与 apply_options 已随「提前站数 / 公里」一起移除；
    # 改刷新间隔走条目更新监听器（重载协调器），不需要单独的即时同步方法。

    # ============ Y. v0.9.2：官方预计到达（CMD115 neardis）+ 官方到站判定 ============
    print("\n[Y] v0.9.2：CMD115 官方「N分钟/M米」→ 预计到达官方化；CMD104 statusType → 到站判定官方化")

    check("Y1 neardis「2分钟/180米」→（2 分钟, 180 米）",
          logic.parse_neardis("2分钟/180米") == (2, 180.0),
          str(logic.parse_neardis("2分钟/180米")))
    check("Y2 neardis「小于1分钟/390米」→（0 分钟, 390 米）",
          logic.parse_neardis("小于1分钟/390米") == (0, 390.0),
          str(logic.parse_neardis("小于1分钟/390米")))
    check("Y3 neardis「3分钟/1公里」→（3 分钟, 1000 米）",
          logic.parse_neardis("3分钟/1公里") == (3, 1000.0),
          str(logic.parse_neardis("3分钟/1公里")))
    check("Y4 neardis 缺失/非预期文案（空、「已到站」、「非运营时间」）→（None, None）",
          logic.parse_neardis("") == (None, None)
          and logic.parse_neardis("已到站") == (None, None)
          and logic.parse_neardis("非运营时间") == (None, None)
          and logic.parse_neardis(None) == (None, None))

    class _PreviewPostClient(api.XmBusClient):
        """覆盖 _post：用假 CMD115 响应测真实 station_preview 的匹配逻辑."""

        def __init__(self, payload):
            super().__init__(session=None)
            self.payload = payload

        async def _post(self, params, _retry=True, check_status=True):
            self.last_params = dict(params)
            return self.payload

    _CMD115 = {
        "status": 1,
        "data": [
            {"lineName": "1路", "upperOrDown": "2", "neartext": "即将到站", "neardis": "小于1分钟/390米"},
            {"lineName": "1路", "upperOrDown": "1", "neartext": "2站", "neardis": "3分钟/1公里"},
            {"lineName": "45路", "upperOrDown": "2", "neartext": "即将到站", "neardis": "2分钟/180米"},
        ],
    }

    pc = _PreviewPostClient(_CMD115)
    got = await pc.station_preview("中华城站", "1路", "1")
    check("Y5 station_preview 按 线路名+方向 精确匹配（1路 上行 → 3分钟/1公里）",
          got == {"neartext": "2站", "neardis": "3分钟/1公里", "minutes": 3, "meters": 1000.0}
          and pc.last_params.get("CMD") == "115"
          and pc.last_params.get("ALL") == "1"
          and pc.last_params.get("STATIONNAME") == "中华城站",
          str(got))
    got = await pc.station_preview("中华城站", "45路", "2")
    check("Y6 换一条线路方向也能匹配（45路 下行 → 2分钟/180米）",
          got == {"neartext": "即将到站", "neardis": "2分钟/180米", "minutes": 2, "meters": 180.0}, str(got))
    got = await pc.station_preview("中华城站", "999路", "1")
    check("Y7 该站台没有这条线路 → None", got is None, str(got))
    pc2 = _PreviewPostClient({
        "status": 1,
        "data": [{"lineName": "954路", "upperOrDown": "2",
                  "neartext": "已到站", "neardis": ""}],
    })
    got = await pc2.station_preview("第一码头站", "954路", "2")
    check("Y11 官方「已到站」（无 neardis）→ 分钟数记 0（官方口径，不显示暂无数据）",
          got == {"neartext": "已到站", "neardis": "", "minutes": 0, "meters": 0.0}, str(got))

    async def _fail_preview(*a, **k):
        raise api.XmBusApiError("CMD115 爆了")

    class PreviewFailClient(FakeClient):
        station_preview = staticmethod(_fail_preview)

    hassY = stub_ha._fake_hass()
    syncY = make_sync(hassY, FakeClient(), cities=api.filter_cities(FAKE_CITIES))
    coordY = coord_mod.XmBusCoordinator(hassY, FakeEntry(), PreviewFailClient(), syncY)
    await coordY._async_update_data()
    check("Y8 CMD115 拉取失败不阻塞实时数据（preview 为空、轮询不报错）",
          coordY.preview == {} and coordY.last_update_success,
          str(coordY.preview))

    entryY = FakeEntry()
    hassY2 = stub_ha._fake_hass(None, entries=[entryY])
    syncY2 = make_sync(hassY2, FakeClient(), cities=api.filter_cities(FAKE_CITIES))
    clientY = FakeClient(preview={"neartext": "2分钟/800米", "minutes": 2, "meters": 800.0})
    coordY2 = coord_mod.XmBusCoordinator(hassY2, entryY, clientY, syncY2)
    dataY2 = await coordY2._async_update_data()
    check("Y9 协调器把官方预览放进 self.preview 并带进 data（供 ETA 传感器取官方分钟数）",
          coordY2.preview.get("minutes") == 2
          and dataY2.get("preview", {}).get("minutes") == 2
          and clientY.calls["station_preview"] >= 1,
          str(coordY2.preview))
    check("Y10 manifest 版本 = 0.9.32",
          json.load(open(os.path.join(_CC, "manifest.json"), encoding="utf-8"))["version"] == "0.9.32")


    # ============ R. 设备触发器（v0.9.1 起只有「公交到站」） ============
    print("\n[R] 自动化界面：只列「公交到站」一个触发器，全中文")
    dt = importlib.import_module("my_bus.device_trigger")
    check("R0 v0.9.20 重新引入 device_condition.py（v0.9.1 曾整体删除）：现在是「到站状态」的"
          "4 条精确状态条件，不掺阈值条件",
          os.path.exists(os.path.join(_CC, "device_condition.py"))
          and "is_arrived" in open(os.path.join(_CC, "device_condition.py"), encoding="utf-8").read()
          and "is_not_arriving" in open(os.path.join(_CC, "device_condition.py"), encoding="utf-8").read()
          and "threshold" not in open(os.path.join(_CC, "device_condition.py"), encoding="utf-8").read())

    listed = await dt.async_get_triggers(None, "dev1")
    check("R1 v0.9.15 界面列 5 个标准触发器（门窗式 2 个 + 温湿度式 3 个；公交到站已删除），旧类型不再列出",
          [t["type"] for t in listed] == [
              "arrival_arrived", "arrival_arriving",
              "remaining_stops", "remaining_km", "eta"]
          and listed[0]["platform"] == "device" and listed[0]["device_id"] == "dev1"
          and all(t["type"] not in ("remaining_stops_changed", "remaining_km_changed",
                                    "eta_changed", "arrival_status_changed")
                  for t in listed),
          str([t["type"] for t in listed]))

    ok_arrived = True
    try:
        dt.TRIGGER_SCHEMA({
            "platform": "device", "domain": "my_bus", "device_id": "d1",
            "type": "bus_arrived",
        })
        ok_arrived = False
    except Exception:  # noqa: BLE001
        ok_arrived = True
    ok_sensors = True
    for t in ("remaining_stops_changed", "remaining_km_changed",
              "eta_changed", "arrival_status_changed"):
        try:
            dt.TRIGGER_SCHEMA({
                "platform": "device", "domain": "my_bus", "device_id": "d1",
                "type": t,
            })
        except Exception:  # noqa: BLE001
            ok_sensors = False
    ok_legacy = True
    try:
        dt.TRIGGER_SCHEMA({
            "platform": "device", "domain": "my_bus", "device_id": "d1",
            "type": "bus_arriving",
        })
    except Exception:  # noqa: BLE001
        ok_legacy = False
    check("R2 四个标准触发器都过 schema；bus_arrived / bus_arriving 都不再接受（事件体系已删）",
          ok_arrived and ok_sensors and not ok_legacy)

    caps = await dt.async_get_trigger_capabilities(
        None, {"type": "arrival_arrived"}
    )
    check("R3 「公交已到站」没有附加字段（门窗式，选中即生效）",
          caps == {}, str(caps))

    class FakeCoord:
        city, station, line = "厦门市", "县口路站", "615路"
        direction = "1"
        event_entity_id = "event.my_bus_县口路站"
        device_name = "My Bus（厦门市 615路 县口路站）"

    class FakeEvent:
        def __init__(self, state, attrs):
            new_state = type("S", (), {"state": state, "attributes": attrs})()
            self.data = {"new_state": new_state}

    class FakeJobHass:
        def __init__(self):
            self.fired = []

        def async_run_hass_job(self, job, data):
            self.fired.append(data)

    # 拦下 async_track_state_change_event：直接拿到注册的回调来模拟事件实体变化
    captured = {}

    def _fake_track(hass_, entity_ids, cb):
        captured["entity_ids"] = list(entity_ids)
        captured["cb"] = cb
        return lambda: None

    dt.async_track_state_change_event = _fake_track
    dt._coordinator_for = lambda hass, config: coord_holder[0]   # noqa: ARG005
    coord_holder = [FakeCoord()]

    hassR = FakeJobHass()
    arrived_rejected = False
    try:
        await dt.async_attach_trigger(
            hassR,
            {"platform": "device", "domain": "my_bus", "device_id": "d1",
             "type": "bus_arrived"},
            lambda *a, **k: None,
            {"name": "公交到站"},
        )
    except Exception:  # noqa: BLE001
        arrived_rejected = True
    check("R4 v0.9.15 bus_arrived 挂接直接报错（事件实体与事件体系已删除）",
          arrived_rejected and hassR.fired == [])

    firedR2 = []
    rejected = False
    try:
        await dt.async_attach_trigger(
            hassR,
            {"platform": "device", "domain": "my_bus", "device_id": "d1",
             "type": "bus_arriving"},
            lambda data: firedR2.append(data),
            {"name": "公交即将到站"},
        )
    except Exception:  # noqa: BLE001  schema 已不接受 / 触发器类型不存在
        rejected = True
    check("R7 v0.9.8 老 bus_arriving 触发器已彻底删除：挂接直接报错（无效自动化应删除重建）",
          rejected and firedR2 == [], f"rejected={rejected}")

    def all_cjk(*texts) -> bool:
        return all(not re.search(r"[A-Za-z]", t) for t in texts)

    trig_types = [t["type"] for t in listed]
    trig_names = [STRINGS["device_automation"]["trigger_type"][t]["name"]
                  for t in trig_types]
    check("R14 六个界面触发器的名称与说明全是中文（读屏不会念到英文），"
          "「公交即将到站（已停用）」条目已删除；v0.9.20 起 condition_type 存在且全中文",
          all_cjk(*trig_names)
          and all_cjk(*[STRINGS["device_automation"]["trigger_type"][t]["description"]
                        for t in trig_types])
          and "bus_arriving" not in STRINGS["device_automation"]["trigger_type"]
          and sorted(STRINGS["device_automation"]["condition_type"]) == [
              "is_arrived", "is_arriving", "is_no_bus", "is_not_arriving"]
          and all_cjk(*[v["name"].replace("{entity_name}", "")
                        for v in STRINGS["device_automation"]["condition_type"].values()]),
          str(trig_names))
    check("R15 v0.9.15 事件实体的翻译小节已删除（entity 只剩 sensor）",
          "event" not in STRINGS["entity"] and set(STRINGS["entity"]) == {"sensor"},
          str(list(STRINGS["entity"])))

    # ---- v0.9.8：4 个实时传感器的「状态变化」触发器 ----
    class FakeState:
        def __init__(self, state, attrs=None, entity_id="sensor.x"):
            self.state = state
            self.attributes = attrs or {}
            self.entity_id = entity_id

    class FakeStateEvent:
        def __init__(self, new, old):
            self.data = {"new_state": new, "old_state": old}

    coord_holder[0] = type("FakeCoord2", (), {
        "city": "厦门市", "station": "县口路站", "line": "615路",
        "direction": "1", "event_entity_id": "event.x",
        "sensor_entity_ids": {
            "remaining_stops": "sensor.剩余站数",
            "remaining_km": "sensor.剩余公里数",
            "eta": "sensor.预计到达",
            "arrival_status": "sensor.到站状态",
        },
        "device_name": "My Bus（厦门市 615路 县口路站）",
    })()

    hassR3 = FakeJobHass()
    await dt.async_attach_trigger(
        hassR3,
        {"platform": "device", "domain": "my_bus", "device_id": "d1",
         "type": "arrival_status_changed"},
        lambda data: None,
        {"name": "到站状态变化"},
    )
    check("R16 v0.9.8 「到站状态变化」挂在到站状态实体上（entity_id 由传感器登记）",
          captured["entity_ids"] == ["sensor.到站状态"], str(captured["entity_ids"]))
    cb = captured["cb"]
    attrsR3 = {"车牌": "闽D11111", "剩余站数": 3, "剩余距离米": 1332.0,
               "剩余公里数": 1.3, "预计到达分钟": None, "到站状态": "未到站"}
    cb(FakeStateEvent(FakeState("即将到站", attrsR3), FakeState("未到站", attrsR3)))
    check("R17 状态值变了 → 触发，trigger 带新旧值与车牌/剩余站数/方向",
          len(hassR3.fired) == 1 and hassR3.fired[0]["type"] == "arrival_status_changed"
          and hassR3.fired[0]["state"] == "即将到站"
          and hassR3.fired[0]["previous_state"] == "未到站"
          and hassR3.fired[0]["bus_number"] == "闽D11111"
          and hassR3.fired[0]["remaining_stops"] == 3
          and hassR3.fired[0]["direction"] == "上行",
          str(hassR3.fired))
    cb(FakeStateEvent(FakeState("即将到站", {**attrsR3, "车牌": "换了车"}),
                      FakeState("即将到站", attrsR3)))
    check("R18 只有属性变化、状态值没变 → 不触发（避免每轮刷新都打自动化）",
          len(hassR3.fired) == 1, str(len(hassR3.fired)))
    cb(FakeStateEvent(FakeState("已到站", attrsR3), None))
    check("R19 实体刚注册（old_state=None）→ 不触发",
          len(hassR3.fired) == 1, str(len(hassR3.fired)))

    hassR4 = FakeJobHass()
    await dt.async_attach_trigger(
        hassR4,
        {"platform": "device", "domain": "my_bus", "device_id": "d1",
         "type": "eta_changed"},
        lambda data: None,
        {"name": "预计到达变化"},
    )
    check("R20 v0.9.8 「预计到达变化」挂在预计到达实体上",
          captured["entity_ids"] == ["sensor.预计到达"], str(captured["entity_ids"]))
    cb = captured["cb"]
    cb(FakeStateEvent(FakeState("暂无数据"), FakeState(19)))
    cb(FakeStateEvent(FakeState(17), FakeState("暂无数据")))
    check("R21 「预计到达变化」：文案 ↔ 数字之间互变也触发，新值在 trigger.state",
          len(hassR4.fired) == 2 and hassR4.fired[0]["state"] == "暂无数据"
          and hassR4.fired[0]["previous_state"] == 19
          and hassR4.fired[1]["state"] == 17,
          str(hassR4.fired))

    # v0.9.15：「公交到站」触发器与事件实体已删除（原 v0.9.9 真机形态回归 R22~R24 移除）

    # ---- v0.9.10：「到站状态变化」触发器的目标状态下拉框 ----
    caps_status = await dt.async_get_trigger_capabilities(
        None, {"type": "arrival_status_changed"}
    )
    ef = (caps_status.get("extra_fields") or {})
    ef_schema = getattr(ef, "schema", {}) or {}
    to_val = None
    for k, v in (ef_schema.items() if isinstance(ef_schema, dict) else []):
        if k == "to" or getattr(k, "schema", None) == "to":
            to_val = v
    opts = None
    if to_val is not None:
        cfg = getattr(to_val, "config", None)
        opts = getattr(to_val, "options", None) or (cfg or {}).get("options")
    check("R25 v0.9.10 「到站状态变化」capabilities 带「目标状态」下拉框",
          opts == ["未到站", "即将到站", "已到站"],
          str(caps_status))
    for t in ("arrival_arrived", "arrival_arriving",
              "remaining_stops_changed", "remaining_km_changed", "eta_changed"):
        caps_other = await dt.async_get_trigger_capabilities(None, {"type": t})
        if caps_other != {}:
            break
    check("R26 公交到站 / 门窗式 / 旧类型触发器的 capabilities 都为空（界面不加多余输入框）",
          caps_other == {}, str(caps_other))

    # 带下拉过滤的挂接：选了「即将到站」→ 只有变成 即将到站 才触发
    hassR6 = FakeJobHass()
    await dt.async_attach_trigger(
        hassR6,
        {"platform": "device", "domain": "my_bus", "device_id": "d1",
         "type": "arrival_status_changed", "to": "即将到站"},
        lambda data: None,
        {"name": "到站状态变化"},
    )
    check("R27 选了目标状态后仍挂在到站状态实体上",
          captured["entity_ids"] == ["sensor.到站状态"], str(captured["entity_ids"]))
    cb6 = captured["cb"]
    attrs6 = {"车牌": "闽D22222"}
    cb6(FakeStateEvent(FakeState("已到站", attrs6), FakeState("即将到站", attrs6)))
    check("R28 变成「已到站」（不是选中的目标状态）→ 不触发",
          hassR6.fired == [], str(hassR6.fired))
    cb6(FakeStateEvent(FakeState("即将到站", attrs6), FakeState("未到站", attrs6)))
    check("R29 变成选中的「即将到站」→ 触发",
          len(hassR6.fired) == 1 and hassR6.fired[0]["state"] == "即将到站",
          str(hassR6.fired))

    # ---- v0.9.11：TRIGGER_SCHEMA 声明接受 to 字段（真机 HA 基础 schema 是 PREVENT_EXTRA，
    #      0.9.10 不声明的话下拉框选完保存报「not a valid option at 'to'」）----
    schema_keys = set()
    for k in dt.TRIGGER_SCHEMA.schema:
        schema_keys.add(k if isinstance(k, str) else getattr(k, "schema", None))
    check("R30 v0.9.11 TRIGGER_SCHEMA 声明接受 to 字段（否则真机保存 400）",
          "to" in schema_keys, str(schema_keys))
    cfg_to = dt.TRIGGER_SCHEMA({
        "platform": "device", "domain": "my_bus", "device_id": "d1",
        "type": "arrival_status_changed", "to": "已到站",
    })
    check("R31 带 to 的触发器配置校验通过，值原样保留",
          cfg_to.get("to") == "已到站" and cfg_to["type"] == "arrival_status_changed",
          str(cfg_to))
    cfg_no_to = dt.TRIGGER_SCHEMA({
        "platform": "device", "domain": "my_bus", "device_id": "d1",
        "type": "arrival_status_changed",
    })
    check("R32 不带 to 的触发器配置照常校验通过（to 是可选键）",
          "to" not in cfg_no_to and cfg_no_to["type"] == "arrival_status_changed",
          str(cfg_no_to))

    # ---- v0.9.12：translations 的 trigger_type 必须是纯字符串（HA 运行时规范），
    #      否则前端取不到中文标签，设备触发器列表显示英文名或「未知」----
    _tt_expect = {
        # v0.9.23：旧 device_automation 文案与新版触发/条件统一（去掉「公交」前缀）
        "arrival_arrived": "已到站",
        "arrival_arriving": "即将到站",
        "remaining_stops": "剩余站数变化",
        "remaining_km": "剩余公里数变化",
        "eta": "预计到达变化",
        "remaining_stops_changed": "剩余站数变化",
        "remaining_km_changed": "剩余公里数变化",
        "eta_changed": "预计到达变化",
        "arrival_status_changed": "到站状态变化",
    }
    check("R33 v0.9.13 zh-Hans 翻译里 trigger_type 是纯字符串且为中文标签（含新类型）",
          json.load(open(os.path.join(_CC, "translations", "zh-Hans.json"),
                         encoding="utf-8"))["device_automation"]["trigger_type"]
          == _tt_expect, str(_tt_expect))
    # 注意：迭代 dict 得到的是键，必须 .values()（0.9.12 首跑 R34 误报的根因）
    check("R34 strings.json 保留 hassfest 对象形式（name/description，文档用途）",
          all(isinstance(v, dict) and "name" in v and "description" in v
              for v in json.load(open(os.path.join(_CC, "strings.json"),
                                      encoding="utf-8"))["device_automation"]["trigger_type"].values()),
          "name/description 均在")
    _zh_raw = open(os.path.join(_CC, "translations", "zh-Hans.json"), "rb").read()
    _en_raw = open(os.path.join(_CC, "translations", "en.json"), "rb").read()
    check("R35 运行时两份翻译文件逐字节一致（en.json 也是中文，无障碍硬要求；"
          "strings.json 按 hassfest 规范保留对象形式，见 I1）",
          _zh_raw == _en_raw,
          f"zh-Hans {len(_zh_raw)} bytes / en {len(_en_raw)} bytes")

    # ---- v0.9.13：schema 新键 / 阈值 caps / 门窗式与温湿度式挂接 ----
    check("R36 v0.9.13 schema 声明接受 above/below/entity_id（真机前端保存时会带）",
          {"above", "below", "entity_id"} <= schema_keys, str(schema_keys))
    cfg_thr = dt.TRIGGER_SCHEMA({
        "platform": "device", "domain": "my_bus", "device_id": "d1",
        "type": "remaining_stops", "above": 3.5, "below": 1, "entity_id": "reg-abc",
    })
    check("R37 阈值触发器配置校验通过：above/below 转浮点、entity_id 原样保留",
          cfg_thr.get("above") == 3.5 and cfg_thr.get("below") == 1.0
          and cfg_thr.get("entity_id") == "reg-abc", str(cfg_thr))

    def _caps_fields(ttype):
        caps_t = dt.async_get_trigger_capabilities.__wrapped__ if False else None
        return caps_t

    async def _caps_of(ttype):
        return await dt.async_get_trigger_capabilities(None, {"type": ttype})

    caps_stops = await _caps_of("remaining_stops")
    ef_stops = caps_stops.get("extra_fields")
    ef_schema = getattr(ef_stops, "schema", {}) or {}
    found = {}
    for k, v in (ef_schema.items() if isinstance(ef_schema, dict) else []):
        key = k if isinstance(k, str) else getattr(k, "schema", None)
        found[key] = getattr(k, "description", None)
    check("R38 「剩余站数变化」caps：above/below 可选数字框 + 单位后缀「站」（核心传感器同款）",
          set(found) == {"above", "below"}
          and found.get("above") == {"suffix": "站"}
          and found.get("below") == {"suffix": "站"}, str(found))

    caps_km = await _caps_of("remaining_km")
    caps_eta = await _caps_of("eta")
    def _suffixes(caps_t):
        ef_t = caps_t.get("extra_fields")
        sch = getattr(ef_t, "schema", {}) or {}
        return {getattr(k, "schema", None) if not isinstance(k, str) else k:
                (getattr(k, "description", None) or {}).get("suffix")
                for k, v in (sch.items() if isinstance(sch, dict) else [])}
    check("R39 「剩余公里数变化」后缀「公里」；「预计到达变化」后缀「分钟」",
          _suffixes(caps_km) == {"above": "公里", "below": "公里"}
          and _suffixes(caps_eta) == {"above": "分钟", "below": "分钟"},
          f"{_suffixes(caps_km)} / {_suffixes(caps_eta)}")

    # 门窗式：公交已到站 / 公交即将到站
    hassR7 = FakeJobHass()
    await dt.async_attach_trigger(
        hassR7,
        {"platform": "device", "domain": "my_bus", "device_id": "d1",
         "type": "arrival_arrived", "entity_id": "reg-1"},
        lambda data: None,
        {"name": "公交已到站"},
    )
    check("R40 「公交已到站」挂到到站状态实体上（门窗式，无需下拉框）",
          captured["entity_ids"] == ["sensor.到站状态"], str(captured["entity_ids"]))
    cb7 = captured["cb"]
    attrs7 = {"车牌": "闽D33333"}
    cb7(FakeStateEvent(FakeState("已到站", attrs7), FakeState("即将到站", attrs7)))
    check("R41 变「已到站」→ 触发，trigger.type = arrival_arrived",
          len(hassR7.fired) == 1 and hassR7.fired[0]["type"] == "arrival_arrived"
          and hassR7.fired[0]["state"] == "已到站", str(hassR7.fired))
    cb7(FakeStateEvent(FakeState("未到站", attrs7), FakeState("已到站", attrs7)))
    check("R42 变「未到站」→ 不触发（门窗式只认自己的目标状态）",
          len(hassR7.fired) == 1, str(len(hassR7.fired)))

    hassR8 = FakeJobHass()
    await dt.async_attach_trigger(
        hassR8,
        {"platform": "device", "domain": "my_bus", "device_id": "d1",
         "type": "arrival_arriving"},
        lambda data: None,
        {"name": "公交即将到站"},
    )
    cb8 = captured["cb"]
    cb8(FakeStateEvent(FakeState("即将到站", attrs7), FakeState("未到站", attrs7)))
    check("R43 「公交即将到站」：变「即将到站」→ 触发",
          len(hassR8.fired) == 1 and hassR8.fired[0]["type"] == "arrival_arriving",
          str(hassR8.fired))

    # 温湿度式：阈值触发
    hassR9 = FakeJobHass()
    await dt.async_attach_trigger(
        hassR9,
        {"platform": "device", "domain": "my_bus", "device_id": "d1",
         "type": "remaining_stops", "below": 3},
        lambda data: None,
        {"name": "剩余站数变化"},
    )
    check("R44 阈值触发器挂到剩余站数实体上",
          captured["entity_ids"] == ["sensor.剩余站数"], str(captured["entity_ids"]))
    cb9 = captured["cb"]
    cb9(FakeStateEvent(FakeState(2), FakeState(5)))            # 2 < 3 → 触发
    cb9(FakeStateEvent(FakeState(4), FakeState(2)))            # 4 不低于 3 → 不触发
    cb9(FakeStateEvent(FakeState("暂无数据"), FakeState(1)))    # 新值非数字 → 不触发
    cb9(FakeStateEvent(FakeState(1), FakeState("暂无数据")))    # 旧值非数字、新值 1<3 → 触发
    check("R45 「低于 3 站」：5→2 触发；2→4 不触发；→「暂无数据」不触发；「暂无数据」→1 触发",
          len(hassR9.fired) == 2
          and hassR9.fired[0]["state"] == 2 and hassR9.fired[0]["previous_state"] == 5
          and hassR9.fired[1]["state"] == 1 and hassR9.fired[1]["previous_state"] == "暂无数据",
          str(hassR9.fired))

    hassR10 = FakeJobHass()
    await dt.async_attach_trigger(
        hassR10,
        {"platform": "device", "domain": "my_bus", "device_id": "d1",
         "type": "eta", "above": 10},
        lambda data: None,
        {"name": "预计到达变化"},
    )
    cb10 = captured["cb"]
    cb10(FakeStateEvent(FakeState(12), FakeState(19)))  # 12 > 10 → 触发
    cb10(FakeStateEvent(FakeState(8), FakeState(12)))   # 8 不高于 10 → 不触发
    check("R46 「高于 10 分钟」：19→12 触发；12→8 不触发",
          len(hassR10.fired) == 1 and hassR10.fired[0]["state"] == 12,
          str(hassR10.fired))

    hassR11 = FakeJobHass()
    await dt.async_attach_trigger(
        hassR11,
        {"platform": "device", "domain": "my_bus", "device_id": "d1",
         "type": "remaining_km", "above": 1, "below": 2},
        lambda data: None,
        {"name": "剩余公里数变化"},
    )
    cb11 = captured["cb"]
    cb11(FakeStateEvent(FakeState(1.8), FakeState(1.5)))         # 1<1.8<2 → 触发
    cb11(FakeStateEvent(FakeState(0.5), FakeState(1.8)))         # 0.5 不高于 1 → 不触发
    cb11(FakeStateEvent(FakeState("暂无数据"), FakeState(0.5)))   # 新值非数字 → 不触发
    cb11(FakeStateEvent(FakeState(2.5), FakeState(2.0)))         # 2.5 不低于 2 → 不触发
    check("R47 「高于 1 低于 2 公里」（above/below 区间，核心同语义）：1.5→1.8 触发；"
          "1.8→0.5 不触发；→「暂无数据」不触发；2.0→2.5 不触发",
          len(hassR11.fired) == 1 and hassR11.fired[0]["state"] == 1.8,
          str(hassR11.fired))

    hassR12 = FakeJobHass()
    await dt.async_attach_trigger(
        hassR12,
        {"platform": "device", "domain": "my_bus", "device_id": "d1",
         "type": "eta"},
        lambda data: None,
        {"name": "预计到达变化"},
    )
    cb12 = captured["cb"]
    cb12(FakeStateEvent(FakeState(17), FakeState(19)))          # 不设阈值 → 触发
    cb12(FakeStateEvent(FakeState("暂无数据"), FakeState(17)))   # 不设阈值 → 文案也触发
    check("R48 阈值都不填 = 任意变化都触发（与核心「数值」触发器一致）",
          len(hassR12.fired) == 2, str(hassR12.fired))

    print("\n[U] 设备页实时信息：剩余站数 / 剩余公里数 / 预计到达 / 到站状态（只取最近一辆车）")

    # v0.8.7：用户想在设备页看到「3 站 4 分钟 未到站」这类实时信息。
    # HA 的设备页只能展示「该设备的实体」，所以给监控设备加 3 个传感器 --
    # 都只看离监控站台最近的一辆车（属性里给出车牌、当前站、里程等）。
    # v0.8.8：在「剩余站数」与「预计到达」之间再插一个「剩余公里数」。
    entryU = FakeEntry()
    hassU = stub_ha._fake_hass(None, entries=[entryU])
    syncU = make_sync(hassU, FakeClient(), cities=api.filter_cities(FAKE_CITIES))
    coordU = coord_mod.XmBusCoordinator(hassU, entryU, FakeClient(), syncU)
    stops_s = sensor_mod.XmBusRemainingStopsSensor(coordU, entryU)
    km_s = sensor_mod.XmBusRemainingKmSensor(coordU, entryU)
    eta_s = sensor_mod.XmBusEtaSensor(coordU, entryU)
    status_s = sensor_mod.XmBusArrivalStatusSensor(coordU, entryU)

    # 用户举的例子正好是「剩 3 站」-- 1332 ÷ 333 ≈ 4 分钟。
    # v0.9.19 起严格官方：展示值只认 CMD115 官方文案，推算口径已删。
    coordU.arrivals = [
        {"plate": "闽D11111", "current_stop": "火车站", "remaining": 3, "distance_m": 1332.0},
        {"plate": "闽D22222", "current_stop": "体育中心", "remaining": 7, "distance_m": 4200.0},
    ]
    # 官方缺失 → 宁缺勿错：站数「未知」、状态「暂无车辆」（不再用推算顶上）
    check("U0 官方缺失 → 剩余站数「未知」、到站状态「暂无车辆」（v0.9.19 严格官方，宁缺勿错）",
          stops_s.native_value is None
          and status_s.native_value == logic.STATUS_NO_BUS,
          f"{stops_s.native_value} / {status_s.native_value}")
    coordU.preview = {"neartext": "4站", "neardis": "8分钟/1.3公里", "minutes": 8}
    check("U1 剩余站数传感器 = 官方文案口径（官方「4站」→ 显示 4；多车取最近一辆）",
          stops_s.native_value == 4, str(stops_s.native_value))
    check("U2 预计到达传感器：官方给分钟 → 显示官方分钟数（8 分钟）",
          eta_s.native_value == 8, str(eta_s.native_value))
    check("U2b 剩余公里数传感器 = 同一辆车的线路里程换算成公里（1332m → 1.3）",
          km_s.native_value == 1.3, str(km_s.native_value))
    check("U3 到站状态传感器：官方「N站」→ 「未到站」",
          status_s.native_value == logic.STATUS_NOT_ARRIVING,
          str(status_s.native_value))
    attrsU = stops_s.extra_state_attributes
    check("U4 属性带车牌 / 当前站 / 剩余站数（官方 4）/ 内部差（3）/ 剩余里程 / 状态 / 线路",
          attrsU.get("车牌") == "闽D11111"
          and attrsU.get("当前站") == "火车站"
          and attrsU.get("剩余站数") == 4
          and attrsU.get("内部剩余站数") == 3
          and attrsU.get("剩余距离米") == 1332.0
          and attrsU.get("剩余公里数") == 1.3
          and attrsU.get("到站状态") == logic.STATUS_NOT_ARRIVING
          and attrsU.get("线路") == coordU.line
          and attrsU.get("方向") == "上行",
          str(attrsU))
    coordU.preview = {}

    coordU.arrivals = [
        {"plate": "闽D11111", "current_stop": "火车站", "remaining": 2, "distance_m": 800.0},
    ]
    check("U5 CMD104 有车但官方缺失 → 到站状态仍是「暂无车辆」（v0.9.19 严格官方）",
          status_s.native_value == logic.STATUS_NO_BUS
          and stops_s.native_value is None,
          f"{status_s.native_value} / {stops_s.native_value}")
    check("U6 剩 2 站、800 米但官方缺失 → 预计到达仍是「暂无数据」",
          eta_s.native_value == "暂无数据", str(eta_s.native_value))
    check("U6b 属性 eta_minutes = None、eta_source = None（没有官方数据不填数）",
          stops_s.extra_state_attributes.get("预计到达分钟") is None
          and stops_s.extra_state_attributes.get("预计到达来源") is None,
          str(stops_s.extra_state_attributes.get("预计到达来源")))

    coordU.arrivals = [
        {"plate": "闽D11111", "current_stop": "火车站", "remaining": 2, "distance_m": 800.0},
    ]
    coordU.preview = {"neartext": "2分钟/800米", "minutes": 2, "meters": 800.0}
    check("U2c 官方预览存在 → 预计到达用官方分钟数、属性标 official 并带官方文案",
          eta_s.native_value == 2
          and stops_s.extra_state_attributes.get("预计到达来源") == "官方"
          and stops_s.extra_state_attributes.get("官方原文") == "2分钟/800米",
          str(stops_s.extra_state_attributes.get("预计到达来源")))
    # 「N分钟/M米」不是剩余站数文案 → 站数解析不出，严格官方显示「未知」
    check("U2d ETA 原文不是站数文案 → 剩余站数「未知」、状态「暂无车辆」（宁缺勿错）",
          stops_s.native_value is None
          and status_s.native_value == logic.STATUS_NO_BUS,
          f"{stops_s.native_value} / {status_s.native_value}")
    coordU.preview = {}

    coordU.arrivals = [
        {"plate": "闽D11111", "current_stop": "县口路站", "remaining": 0, "distance_m": 0.0},
    ]
    coordU.preview = {"neartext": "已到站", "neardis": "已到站", "minutes": 0}
    check("U7 官方「已到站」→ 状态「已到站」、站数 0、预计到达 0 分钟",
          status_s.native_value == logic.STATUS_ARRIVED
          and eta_s.native_value == 0 and stops_s.native_value == 0,
          f"{status_s.native_value} / {eta_s.native_value} / {stops_s.native_value}")

    coordU.arrivals = [
        {"plate": "闽D44444", "current_stop": "县口路站", "remaining": 0,
         "distance_m": 260.0, "stopped": False},
    ]
    coordU.preview = {"neartext": "即将到站", "neardis": "1分钟/260米", "minutes": 1}
    check("U3b 官方「即将到站」→ 状态「即将到站」（原文采信）",
          status_s.native_value == logic.STATUS_ARRIVING, str(status_s.native_value))
    check("U3c 官方「即将到站」→ 剩余站数显示 1（与 App 完全一致）",
          stops_s.native_value == 1, str(stops_s.native_value))
    coordU.preview = {}

    coordU.arrivals = [
        {"plate": "闽D55555", "current_stop": "火车站", "remaining": 3, "distance_m": None},
    ]
    check("U8 没有分段里程时，剩余公里数显示「未知」而不是 0（0 会被误读成车就在站上）",
          km_s.native_value is None, str(km_s.native_value))

    coordU.arrivals = []
    check("U9 当前没有在途车辆 → 站数 / 公里数为未知、预计到达「暂无数据」、状态「暂无车辆」",
          stops_s.native_value is None and km_s.native_value is None
          and eta_s.native_value == "暂无数据"
          and status_s.native_value == logic.STATUS_NO_BUS,
          f"{stops_s.native_value} / {km_s.native_value} / {eta_s.native_value} / {status_s.native_value}")

    # ============ v0.9.18：剩余站数 / 到站状态官方文案优先（App 同源） ============
    # 探针实测（2026-10-28 快1路）：官方在车进站停稳那一刻就减 1，CMD104 的
    # index 发车才跳 —— 推算总慢「一个停站时间」。展示值优先解析官方 neartext。

    # AA1 纯函数 official_stops：三种官方文案 + 防误显 + 未知文案
    check("AA1 official_stops：「N站」→ N（含 12 站、带空格），与官方文案同源",
          logic.official_stops("3站", 2) == 3
          and logic.official_stops("12站", 11) == 12
          and logic.official_stops(" 6站 ", 5) == 6,
          f"{logic.official_stops('3站', 2)} / {logic.official_stops('12站', 11)}")
    check("AA2 official_stops：「即将到站」→ 1、「已到站」→ 0（车确实到/快到）",
          logic.official_stops("即将到站", 0) == 1
          and logic.official_stops("已到站", 0) == 0
          and logic.official_stops("已到站", 1) == 0,
          f"{logic.official_stops('即将到站', 0)} / {logic.official_stops('已到站', 0)}")
    check("AA3 official_stops 防终点站误显：官方「已到站」但内部差 4 站 → 不采信（None）",
          logic.official_stops("已到站", 4) is None
          and logic.official_stops("已到站", None) is None
          and logic.official_stops("即将到站", 3) is None,
          f"{logic.official_stops('已到站', 4)} / {logic.official_stops('即将到站', 3)}")
    check("AA4 official_stops：非运营时间 / 空 / ETA 原文等未知文案 → None（展示层宁缺勿错）",
          logic.official_stops("非运营时间", 2) is None
          and logic.official_stops("", 2) is None
          and logic.official_stops(None, 2) is None
          and logic.official_stops("2分钟/800米", 2) is None,
          str(logic.official_stops("非运营时间", 2)))
    check("AA5 official_arrival_status：「已到站/即将到站」原文采信、「N站」→ 未到站、"
          "误显防护与未知文案同 official_stops",
          logic.official_arrival_status("已到站", 0) == logic.STATUS_ARRIVED
          and logic.official_arrival_status("即将到站", 0) == logic.STATUS_ARRIVING
          and logic.official_arrival_status("5站", 4) == logic.STATUS_NOT_ARRIVING
          and logic.official_arrival_status("已到站", 4) is None
          and logic.official_arrival_status("非运营时间", 2) is None,
          str(logic.official_arrival_status("5站", 4)))

    # AA6 展示集成：探针第 11 轮的真实场景 —— 车停在卧龙晓城（内部差 3、停站），
    # 官方已显示「3站」，v0.9.17 推算口径会给 4（在途才 +1 的相反偏差），官方优先
    coordU.arrivals = [
        {"plate": "闽D06719", "current_stop": "卧龙晓城站", "remaining": 3,
         "distance_m": 3200.0, "stopped": True},
    ]
    coordU.preview = {"neartext": "3站", "neardis": "5分钟/3.2公里", "minutes": 5}
    check("AA6 官方「3站」+ 车停在前面第 3 站 → 剩余站数显示 3（推算口径会错给 4）",
          stops_s.native_value == 3
          and stops_s.extra_state_attributes.get("剩余站数") == 3,
          str(stops_s.native_value))
    check("AA7 官方「N站」→ 到站状态「未到站」（官方优先于 statusType 推算）",
          status_s.native_value == logic.STATUS_NOT_ARRIVING
          and stops_s.extra_state_attributes.get("到站状态") == logic.STATUS_NOT_ARRIVING,
          str(status_s.native_value))
    check("AA8 internal_remaining 属性仍保留内部原值 3（官方/推算并存，便于排查）",
          stops_s.extra_state_attributes.get("内部剩余站数") == 3,
          str(stops_s.extra_state_attributes.get("内部剩余站数")))

    # AA9 官方「即将到站」：剩 0 站在途 → 站数 1、状态「即将到站」（与 App 一字不差）
    coordU.arrivals = [
        {"plate": "闽D08067D", "current_stop": "火车站（BRT）", "remaining": 0,
         "distance_m": 848.3, "stopped": False},
    ]
    coordU.preview = {"neartext": "即将到站", "neardis": "2分钟/850米", "minutes": 2}
    check("AA9 官方「即将到站」+ 剩 0 站在途 → 站数 1、状态「即将到站」",
          stops_s.native_value == 1
          and status_s.native_value == logic.STATUS_ARRIVING,
          f"{stops_s.native_value} / {status_s.native_value}")

    # AA10 官方「已到站」：车正停在监控站台 → 站数 0、状态「已到站」
    coordU.arrivals = [
        {"plate": "闽D08067D", "current_stop": "火车站（BRT）", "remaining": 0,
         "distance_m": 0.0, "stopped": True},
    ]
    coordU.preview = {"neartext": "已到站", "neardis": "", "minutes": 0}
    check("AA10 官方「已到站」+ 车停在监控站台 → 站数 0、状态「已到站」",
          stops_s.native_value == 0
          and status_s.native_value == logic.STATUS_ARRIVED,
          f"{stops_s.native_value} / {status_s.native_value}")

    # AA11 官方缺失（「非运营时间」）→ 退回 v0.9.17 推算口径（在途 = 内部 + 1）
    coordU.arrivals = [
        {"plate": "闽D11111", "current_stop": "火车站", "remaining": 3,
         "distance_m": 1332.0, "stopped": False},
    ]
    coordU.preview = {"neartext": "非运营时间", "neardis": "预计发车:11:00", "minutes": None}
    check("AA11 官方无法解析（「非运营时间」）→ 严格官方：站数「未知」、状态「暂无车辆」"
          "（v0.9.19 起不再退回推算）",
          stops_s.native_value is None
          and status_s.native_value == logic.STATUS_NO_BUS,
          f"{stops_s.native_value} / {status_s.native_value}")
    coordU.preview = {}

    # AA12 CMD104 一辆车都没给，但官方「5站」→ 照常显示官方站数与未到站
    coordU.arrivals = []
    coordU.preview = {"neartext": "5站", "neardis": "8分钟/4.8公里", "minutes": 8}
    check("AA12 CMD104 无车但官方「5站」→ 站数显示 5、状态「未到站」（官方可独立采信）",
          stops_s.native_value == 5
          and status_s.native_value == logic.STATUS_NOT_ARRIVING,
          f"{stops_s.native_value} / {status_s.native_value}")
    # 官方「已到站」但没有车对得上（无法防误显）→ 不采信，回退「暂无车辆」
    coordU.preview = {"neartext": "已到站", "neardis": "", "minutes": 0}
    check("AA13 CMD104 无车 + 官方「已到站」→ 无法核对防误显，回退「暂无车辆」/ 未知站数",
          stops_s.native_value is None
          and status_s.native_value == logic.STATUS_NO_BUS,
          f"{stops_s.native_value} / {status_s.native_value}")
    coordU.preview = {}

    check("T24 v0.9.18 传感器源码含官方逻辑（official_stops / official_arrival_status）",
          "official_stops" in open(os.path.join(_CC, "sensor.py"), encoding="utf-8").read()
          and "official_arrival_status" in open(os.path.join(_CC, "sensor.py"), encoding="utf-8").read()
          and "def official_stops" in open(os.path.join(_CC, "arrival_logic.py"), encoding="utf-8").read()
          and "def official_arrival_status" in open(os.path.join(_CC, "arrival_logic.py"), encoding="utf-8").read())

    # ============ v0.9.19：严格官方，推算口径整体删除 ============
    _logic_src = open(os.path.join(_CC, "arrival_logic.py"), encoding="utf-8").read()
    _sensor_src19 = open(os.path.join(_CC, "sensor.py"), encoding="utf-8").read()
    check("AA14 v0.9.19 推算函数已删除：app_style_stops / arrival_status 不再存在",
          not hasattr(logic, "app_style_stops")
          and not hasattr(logic, "arrival_status")
          and "def app_style_stops" not in _logic_src
          and "def arrival_status(" not in _logic_src
          and "app_style_stops" not in _sensor_src19
          and "def arrival_status(" not in _sensor_src19)
    check("AA15 官方解析不出 → 站数「未知」而不是推算值（宁缺勿错，用户要求严格官方）",
          stops_s.native_value is None
          and status_s.native_value == logic.STATUS_NO_BUS,
          f"{stops_s.native_value} / {status_s.native_value}")

    coordU.preview = {"minutes": 5, "neardis": "5分钟/1公里", "neartext": "5站"}
    check("U10 四个实时传感器的 unique_id / 翻译键 / 单位都正确",
          stops_s._attr_unique_id == "e1_remaining_stops"
          and km_s._attr_unique_id == "e1_remaining_km"
          and eta_s._attr_unique_id == "e1_eta"
          and status_s._attr_unique_id == "e1_arrival_status"
          and stops_s._attr_translation_key == "remaining_stops"
          and km_s._attr_translation_key == "remaining_km"
          and eta_s._attr_translation_key == "eta"
          and status_s._attr_translation_key == "arrival_status"
          and stops_s._attr_native_unit_of_measurement == "站"
          and km_s._attr_native_unit_of_measurement == "公里"
          and eta_s.native_unit_of_measurement == "分钟",
          f"{stops_s._attr_unique_id} / {km_s._attr_unique_id} / {eta_s._attr_unique_id} / {status_s._attr_unique_id}")
    coordU.preview = {}
    check("U11 四个实时传感器与数据同步传感器挂在同一设备上（设备页同一张卡片）",
          stops_s._attr_device_info["identifiers"] == sensor._attr_device_info["identifiers"]
          and stops_s._attr_device_info["name"] == sensor._attr_device_info["name"]
          and km_s._attr_device_info["name"] == sensor._attr_device_info["name"]
          and eta_s._attr_device_info["name"] == status_s._attr_device_info["name"],
          str(stops_s._attr_device_info))
    check("U12 四个实体名都走翻译且三份语言文件里都有中文名",
          [STRINGS["entity"]["sensor"][k]["name"]
           for k in ("remaining_stops", "remaining_km", "eta", "arrival_status")]
          == ["剩余站数", "剩余公里数", "预计到达", "到站状态"]
          and _strings_norm == ZH == EN,
          str(STRINGS["entity"]["sensor"]))
    # v0.9.2：预计到达改为官方数据（CMD115 neardis），不再标「实验性」。
    check("U12b 「预计到达」实体名不再带「（实验性）」（v0.9.2 起优先官方分钟数）",
          STRINGS["entity"]["sensor"]["eta"]["name"] == "预计到达"
          and "实验性" not in STRINGS["entity"]["sensor"]["eta"]["name"],
          STRINGS["entity"]["sensor"]["eta"]["name"])

    added: list = []
    hassU.data.setdefault(const_mod.DOMAIN, {})[entryU.entry_id] = coordU
    await sensor_mod.async_setup_entry(hassU, entryU, added.extend)
    check("U13 平台启动时一次注册 6 个传感器（数据同步 + 5 个实时，v0.9.28 加车牌）",
          len(added) == 6
          and {getattr(e, "_attr_translation_key", None) for e in added}
          == {"data_sync", "remaining_stops", "remaining_km", "eta", "plate",
              "arrival_status"},
          str([getattr(e, "_attr_translation_key", None) for e in added]))

    # ============ V. 剩余公里数 + 手动同步按钮（v0.8.8） ============
    print("\n[V] v0.8.8：剩余公里数传感器（排在站数与预计到达之间）+ 设备页「立即同步」按钮")

    # ① 米 → 公里的换算（纯函数，与 ETA 一样只在有分段里程时有值）
    check("V1 剩余公里数：米换算成公里保留 1 位小数（1332m → 1.3、0m → 0.0、无数据 → 未知）",
          logic.distance_km(1332.0) == 1.3
          and logic.distance_km(0.0) == 0.0
          and logic.distance_km(None) is None,
          f"{logic.distance_km(1332.0)} / {logic.distance_km(0.0)} / {logic.distance_km(None)}")
    check("V1b 里程异常（负数 / 非数字）按「未知」处理，不显示负公里数",
          logic.distance_km(-5.0) is None and logic.distance_km("abc") is None,
          f"{logic.distance_km(-5.0)} / {logic.distance_km('abc')}")

    # ② 用户要求的位置：夹在「剩余站数」与「预计到达」之间
    order = [getattr(e, "_attr_translation_key", None) for e in added]
    check("V2 设备页实时信息顺序 = 剩余站数 → 剩余公里数 → 预计到达 → 车牌 → 到站状态",
          order == ["data_sync", "remaining_stops", "remaining_km", "eta", "plate",
                    "arrival_status"],
          str(order))
    check("V3 剩余公里数是测量类、单位「公里」、固定显示 1 位小数",
          km_s._attr_state_class == "measurement"
          and km_s._attr_native_unit_of_measurement == "公里"
          and km_s._attr_suggested_display_precision == 1,
          f"{km_s._attr_state_class} / {km_s._attr_native_unit_of_measurement} / "
          f"{km_s._attr_suggested_display_precision}")

    # ③ v0.9.4：「立即同步」按钮已删除 —— 手动同步走 my_bus.sync_data 服务
    # 或选项菜单的「🔄 数据同步」，两个入口在 [N] / [W] 组各有覆盖。
    check("V4 设备页不再有「立即同步」按钮（button 平台已随 0.9.4 移除）",
          not os.path.exists(os.path.join(_CC, "button.py"))
          and all(getattr(x, "value", str(x)) != "button"
                  for x in entry_init.PLATFORMS))
    check("V4b 语言文件已无 entity.button 节（三份一致）",
          "button" not in STRINGS.get("entity", {})
          and _strings_norm == ZH == EN)
    check("V4c 手动同步入口仍在：my_bus.sync_data 服务已注册",
          "my_bus.sync_data" in reg,
          str(sorted(reg)))

    # ============ W. 向导第 6 步「数据同步」（v0.8.9） ============
    print("\n[W] 向导第 6 步「数据同步」：与选项菜单的「数据同步」共用同一套实现")

    # 用户：「在向导的第 5 步和第 6 步之间再加上一步『数据同步』，与选项的『数据同步』
    # 相应。」——所以这一步必须**真的**是选项流那一步：同一个 step_id、同一批按钮、
    # 同一批文案，只是出口多一个「下一步：确认创建」。
    flowW, rW = await walk_to_settings(FakeClient())
    rW = await click(flowW, "to_sync")
    check("W1 第 5 步的下一步按钮进的是第 6 步「数据同步」（不是确认页）",
          rW["step_id"] == "sync" and "第 6 步 / 共 7 步" in text_of(rW),
          f"{rW.get('step_id')} / {text_of(rW).splitlines()[0]}")
    check("W2 第 6 步的按钮与选项流那一步完全一致，只多一个通用的「⏭ 下一步」",
          menu_keys(rW) == [BACK, "sync_now", "sync_interval", "sync_toggle", "to_confirm"]
          and menu_of(rW).get("to_confirm") == "⏭ 下一步",
          str(menu_keys(rW)))
    check("W3 说明区开场白是「创建前可以先同步」（选项流那一步讲的是缓存规模）",
          cf._T["h_sync_setup"] in text_of(rW)
          and cf._T["h_sync_note"].split("{")[0].strip() not in text_of(rW),
          text_of(rW).replace("\n", " / "))
    check("W4 提示里仍然列出上次同步 / 自动同步 / 本地缓存规模",
          all(x in text_of(rW) for x in ("上次同步", "自动同步", "本地缓存")), text_of(rW))
    check("W5 「立即同步」「改间隔」「开关自动同步」三个按钮齐全且都是中文",
          any(x.startswith("🔄 立即同步（上次：") for x in menu_labels(rW))
          and any(x.startswith("⏱ 修改同步间隔（当前：") for x in menu_labels(rW))
          and any(x.startswith("🔄 关闭自动同步") for x in menu_labels(rW))
          and all_chinese_labels(rW),
          str(menu_labels(rW)))

    rW = await click(flowW, "sync_now")
    check("W6 点「立即同步」→ 就地显示同步结果（城市 / 线路 / 站台三个数字）并留在第 6 步",
          rW["step_id"] == "sync" and "同步完成" in text_of(rW)
          and "城市" in text_of(rW) and "线路" in text_of(rW) and "站台" in text_of(rW),
          text_of(rW).replace("\n", " / "))

    flowW2, _ = await walk_to_sync(FakeClient(fail_cities=True))
    rW = await click(flowW2, "sync_now")
    check("W6b 同步失败时只报失败，不显示「同步完成：城市 0、线路 0、站台 0」",
          "同步失败" in text_of(rW) and "同步完成" not in text_of(rW)
          and "城市 0" not in text_of(rW),
          text_of(rW).replace("\n", " / "))

    rW = await click(flowW, "sync_toggle")
    check("W7 点「关闭自动同步」→ 同一位置变成「启用自动同步」（按钮，不是开关）",
          is_menu(rW)
          and "启用自动同步" in menu_of(rW).get("sync_toggle", "")
          and "关闭自动同步" not in menu_of(rW).get("sync_toggle", ""),
          str(menu_of(rW).get("sync_toggle")))
    rW = await click(flowW, "sync_toggle")     # 还原，免得影响后面的断言
    check("W7b 再点一次又变回「关闭自动同步」", "关闭自动同步" in menu_of(rW).get("sync_toggle", ""),
          str(menu_of(rW).get("sync_toggle")))

    rW = await click(flowW, "sync_interval")
    check("W8 「修改同步间隔」是数字表单（单位小时、范围写进字段名），抬头与父页同号（第 6 步）",
          is_form(rW) and rW["step_id"] == "sync_interval"
          and fields_of(rW) == {cf.SYNC_INTERVAL_FIELD}
          and selector_kinds(rW) == {"number"}
          and field_map(rW)[cf.SYNC_INTERVAL_FIELD].config.get("unit_of_measurement") == "小时"
          and "范围 1 到 168" in cf.SYNC_INTERVAL_FIELD
          and "第 6 步 / 共 7 步" in text_of(rW),
          f"{rW.get('step_id')} / {text_of(rW).splitlines()[0]}")
    rW = await flowW.async_step_sync_interval({cf.SYNC_INTERVAL_FIELD: 24})
    check("W9 提交后回到第 6 步并说明「已把自动同步间隔改为每 24 小时」",
          rW["step_id"] == "sync" and "每 24 小时" in text_of(rW), text_of(rW))

    rW = await click(flowW, BACK)
    check("W10 第 6 步点「上一步」回到第 5 步「到站提醒参数」",
          rW["step_id"] == "settings", str(rW.get("step_id")))

    # 与选项流那一步对照：同一个 step_id、同一批按钮，只差入口/出口的文案
    optW, _hassW = new_options(FakeEntry(), FakeClient())
    await optW.async_step_init(None)
    rOptW = await click(optW, "sync")
    check("W11 选项流的「数据同步」与向导同一步：step_id 相同、三个动作按钮相同，"
          "但选项流没有「下一步：确认创建」且上一步回选项菜单",
          rOptW["step_id"] == "sync"
          and menu_keys(rOptW) == [BACK, "sync_now", "sync_interval", "sync_toggle"]
          and menu_of(rOptW).get(BACK) == "⬅ 返回选项菜单",
          str(menu_keys(rOptW)))
    check("W12 选项流的开场白讲缓存口径，且不出现「12.0 小时」这种写法",
          "默认每 12 小时自动同步一次" in text_of(rOptW)
          and "12.0" not in text_of(rOptW),
          text_of(rOptW).splitlines()[0])

    flowW3 = new_flow(FakeClient())
    await flowW3.async_step_user(None)
    await flowW3.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
    await click(flowW3, "mode_station")
    await flowW3.async_step_station_keyword({cf.STATION_KW_FIELD: "县口路站"})
    await click_pick(flowW3, flowW3._station_options.index("县口路站"))
    await click_pick(flowW3, 0)
    await click(flowW3, "to_sync")
    rW = await click(flowW3, "to_confirm")
    rW = await click(flowW3, "finish")
    check("W13 走完整条链（… 参数 → 数据同步 → 确认）仍能正常创建条目",
          rW.get("type") == "create_entry" and rW["data"]["station"] == "县口路站"
          and rW["data"]["station_order"] == 12,
          str(rW.get("data")))

    # v0.9.5：确认页把同步设置也列出来；同步层不可用时如实显示「未启用」
    flowW4 = new_flow(FakeClient())
    flowW4._city, flowW4._line, flowW4._station = "厦门市", "615路", "县口路站"
    flowW4._direction, flowW4._poll_interval = "1", 10
    flowW4._async_sync = None                      # 模拟拿不到同步层
    rW4 = await flowW4.async_step_confirm()
    check("W14 v0.9.5 拿不到同步层时确认页如实显示「自动同步：未启用」，不挡创建",
          rW4["step_id"] == "confirm" and "自动同步：未启用" in text_of(rW4),
          text_of(rW4).replace("\n", " / "))

    flowW5 = new_flow(FakeClient())
    flowW5._city, flowW5._line, flowW5._station = "厦门市", "615路", "县口路站"
    flowW5._direction, flowW5._poll_interval = "1", 10
    syncW5 = await flowW5._async_sync()
    await syncW5.async_set_enabled(False)          # 用户关掉了自动同步
    rW5 = await flowW5.async_step_confirm()
    check("W15 v0.9.5 自动同步关闭时确认页显示「自动同步：已关闭」",
          "自动同步：已关闭" in text_of(rW5), text_of(rW5).replace("\n", " / "))

    # ============ X. v0.9.0：按钮版式统一 + 文案精简 ============
    print("\n[X] v0.9.0：每一页按钮版式一致（返回第一位、检索紧随其后）+ 文案精简")

    # 「整页次序」= 说明区段落数 + 该按钮在按钮列表里的下标。
    #   第 1 步说明区 3 段（欢迎语 / 抬头 / 提示），按钮区第 1 个就是「🔍 检索城市名」；
    #   第 3 步说明区 2 段，按钮区第 1 个是「⬅ 返回上一步」、第 2 个才是检索。
    # 两边算下来「🔍 检索…」都落在整页第 4 个元素上 —— 这就是「位置相同」。
    def page_index(res, key: str) -> int:
        paragraphs = [p for p in text_of(res).split("\n\n") if p.strip()]
        return len(paragraphs) + menu_keys(res).index(key)

    flowX = new_flow(FakeClient())
    rXcity = await flowX.async_step_user(None)
    rXmode = await flowX.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
    rXstation = await click(flowX, "mode_station")
    flowXl = new_flow(FakeClient())
    await flowXl.async_step_user(None)
    await flowXl.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
    rXline = await click(flowXl, "mode_line")

    check("X1 第 1 步是流程起点、没有「⬅ 返回上一步」，由说明区第一行的欢迎语占住那个位置",
          BACK not in menu_keys(rXcity)
          and text_of(rXcity).split("\n\n")[0] == cf._T["welcome"],
          str(menu_keys(rXcity)))
    check("X2 三个「🔍 检索…」按钮落在整页的同一个位置（说明区之后的下一个元素）",
          page_index(rXcity, "city_keyword") == 3
          and page_index(rXstation, "station_keyword") == 3
          and page_index(rXline, "line_keyword") == 3,
          f"城市={page_index(rXcity, 'city_keyword')} / "
          f"站台={page_index(rXstation, 'station_keyword')} / "
          f"线路={page_index(rXline, 'line_keyword')}")
    check("X3 所有带返回按钮的页面，第一个按钮都是同一个「⬅ 返回上一步」（位置与文案都一致）",
          all(menu_keys(r)[0] == BACK for r in (rXmode, rXstation, rXline))
          and {menu_of(r)[BACK] for r in (rXmode, rXstation, rXline)} == {"⬅ 返回上一步"},
          f"{menu_keys(rXmode)} | {menu_keys(rXstation)} | {menu_keys(rXline)}")
    check("X4 「🔍 检索…」在按钮列表里都是第一个动作按钮（返回按钮之后的第一个）",
          [k for k in menu_keys(rXcity) if k != BACK][0] == "city_keyword"
          and [k for k in menu_keys(rXstation) if k != BACK][0] == "station_keyword"
          and [k for k in menu_keys(rXline) if k != BACK][0] == "line_keyword",
          f"{menu_keys(rXcity)[:2]} | {menu_keys(rXstation)[:2]} | {menu_keys(rXline)[:2]}")

    _fx1, rXsettings = await walk_to_settings(FakeClient())
    _fx2, rXsync = await walk_to_sync(FakeClient())
    check("X5 第 5 步与第 6 步的「下一步」都是同一个通用文案「⏭ 下一步」（不再各写目的地）",
          menu_of(rXsettings).get("to_sync") == "⏭ 下一步"
          and menu_of(rXsync).get("to_confirm") == "⏭ 下一步"
          and cf._T["act_next_sync"] == cf._T["act_next_confirm"] == "⏭ 下一步",
          f"{menu_of(rXsettings).get('to_sync')} / {menu_of(rXsync).get('to_confirm')}")

    check("X6 第 5 步文案：步骤名「选择到站参数」+ 提示「选择刷新频率。」",
          cf._T["step_settings"] == "选择到站参数"
          and cf._T["h_settings"] == "选择刷新频率。"
          and text_of(rXsettings).split("\n\n")[-1] == "选择刷新频率。",
          text_of(rXsettings).split("\n\n")[-1])

    _fx3, rXtmp = await walk_to_settings(FakeClient())
    rXparams = await click(_fx3, "settings_params")
    check("X7 参数表单的说明简化成「输入数字。」，字段名括号里一律用「范围 …」",
          text_of(rXparams).split("\n\n")[-1] == "输入数字。"
          and "范围 5 到 120" in cf.POLL_INTERVAL_FIELD
          and "范围 1 到 168" in cf.SYNC_INTERVAL_FIELD
          and all(
              "填 " not in f
              for f in (cf.POLL_INTERVAL_FIELD, cf.SYNC_INTERVAL_FIELD)
          ),
          text_of(rXparams).split("\n\n")[-1])

    check("X8 第 2 步的提示改成「先…然后…」的完整句子",
          cf._T["h_mode"] == "先选站台然后选择停靠线路，或先选线路然后选择途经站台。"
          and text_of(rXmode).split("\n\n")[-1] == cf._T["h_mode"],
          text_of(rXmode).split("\n\n")[-1])

    flowX8 = new_flow(FakeClient())
    await flowX8.async_step_user(None)
    await flowX8.async_step_city_keyword({cf.CITY_KW_FIELD: "厦门市"})
    await click(flowX8, "mode_line")
    rX8 = await flowX8.async_step_line_keyword({cf.LINE_KW_FIELD: "615"})
    if rX8.get("step_id") == "line":
        rX8 = await click_pick(flowX8, 0)
    check("X9 第 4 步「选择站台」的提示只说线路途经多少站（不再问「点要在哪站提醒」）",
          rX8["step_id"] == "line_station"
          and "途经" in text_of(rX8)
          and "点要在哪站提醒" not in text_of(rX8)
          and "途经 {n} 站。" in cf._T["h_line_stations"],
          text_of(rX8).replace("\n", " / "))

    _fx4, rXconfirm = await walk_to_confirm(FakeClient())
    check("X10 第 7 步的提示就是一句「请确认配置」，下面直接列出待创建的配置",
          cf._T["h_confirm"] == "请确认配置"
          and "请确认配置" in text_of(rXconfirm)
          and "确认无误点" not in text_of(rXconfirm)
          and "城市：" in text_of(rXconfirm),
          text_of(rXconfirm).replace("\n", " / "))

    check("X11 语言文件里第 4 / 5 步的标题跟着改名（选择站台 / 选择到站参数），两个 scope 都改",
          STRINGS["config"]["step"]["line_station"]["title"] == "🚏 选择站台"
          and STRINGS["config"]["step"]["settings"]["title"] == "⏱ 选择到站参数"
          and STRINGS["options"]["step"]["line_station"]["title"] == "🚏 选择站台"
          and STRINGS["options"]["step"]["settings"]["title"] == "⏱ 选择到站参数",
          f"{STRINGS['config']['step']['line_station']['title']} / "
          f"{STRINGS['config']['step']['settings']['title']}")

    check("X12 选项流的确认页文案不受影响（它讲的是「保存修改」，不是向导的「完成」）",
          cf._T["h_confirm_opt"].startswith("确认无误点「保存修改」")
          and cf._T["act_finish_opt"] == "✅ 保存修改",
          cf._T["h_confirm_opt"])

    # ============ Z. v0.9.6 美化：标题 emoji 体系 / 确认页分块 / 候选前缀 ============
    z_titles = {
        "config": {
            "city": "📍 选择城市", "city_browse": "🏙 浏览全部城市",
            "city_keyword": "🔍 输入城市名查找", "mode": "🧭 选择检索方式",
            "station": "🚏 选择站台", "station_keyword": "🔍 输入站台名查找",
            "line": "🚌 选择线路", "line_keyword": "🔍 输入线路号查找",
            "line_station": "🚏 选择站台", "settings": "⏱ 选择到站参数",
            "settings_params": "⏱ 修改到站参数", "sync": "🔄 数据同步",
            "confirm": "✅ 确认创建",
        },
        "options": {
            "init": "My Bus 设置", "edit_city": "📍 修改城市",
            "edit_line": "🔁 修改线路 / 站台", "edit_settings": "⏱ 修改到站参数",
            "sync_interval": "⏱ 修改自动同步间隔",
        },
    }
    bad_z1 = [
        f"{scope}.{step}"
        for scope, steps in z_titles.items()
        for step, want in steps.items()
        if STRINGS[scope]["step"][step]["title"] != want
    ]
    check("Z1 v0.9.6 标题 emoji 体系：config / options 两个 scope 的步骤标题都带主题 emoji",
          not bad_z1, str(bad_z1))
    check("Z1b v0.9.6 检索类子页统一 🔍 前缀（城市/站台/线路三个关键词页）",
          all(STRINGS["config"]["step"][k]["title"].startswith("🔍 ")
              for k in ("city_keyword", "station_keyword", "line_keyword")),
          str([STRINGS["config"]["step"][k]["title"]
               for k in ("city_keyword", "station_keyword", "line_keyword")]))

    check("Z2 v0.9.6 向导确认页分块：「── 监控内容 ──」与「── 参数 ──」两块、中间空行",
          cf._T["h_confirm_body"].startswith("── 监控内容 ──")
          and "\n\n── 参数 ──" in cf._T["h_confirm_body"]
          and "自动同步：" in cf._T["h_confirm_body"].split("── 参数 ──")[1],
          cf._T["h_confirm_body"].replace("\n", " / "))
    check("Z3 v0.9.6 选项流确认页同样分块（「修改后将是：」开头 + 两块结构）",
          cf._T["h_confirm_body_opt"].startswith("修改后将是：\n── 监控内容 ──")
          and "\n\n── 参数 ──" in cf._T["h_confirm_body_opt"],
          cf._T["h_confirm_body_opt"].replace("\n", " / "))
    check("Z2b v0.9.6 确认页整页渲染：块标题与条目一起出现在说明区",
          "── 监控内容 ──" in text_of(rXconfirm) and "── 参数 ──" in text_of(rXconfirm),
          text_of(rXconfirm).replace("\n", " / "))

    check("Z4 v0.9.6 站台候选带「🚏 」、线路候选带「🚌 」前缀",
          cf._T["h_pick_station"] == "🚏 {name}"
          and cf._T["h_pick_line"] == "🚌 {label}",
          f"{cf._T['h_pick_station']} / {cf._T['h_pick_line']}")
    check("Z5 v0.9.6 城市候选保持裸名称（563 条太长，不逐条加 emoji）",
          cf._T["h_pick_city"] == "{name}", cf._T["h_pick_city"])

    # ---- v0.9.7：预计到达永远有状态（官方分钟 → 官方 neardis 原文 → 官方 neartext → 暂无数据）
    coordU.preview = {"minutes": 17, "neardis": "17分钟/6.1公里", "neartext": "10站"}
    check("Z6 v0.9.7 官方给了分钟数 → 状态是数字、单位「分钟」",
          eta_s.native_value == 17 and eta_s.native_unit_of_measurement == "分钟",
          f"{eta_s.native_value} / {eta_s.native_unit_of_measurement}")
    coordU.preview = {"minutes": None, "neardis": "预计发车:11:00", "neartext": "等待发车"}
    check("Z7 v0.9.7 车还没发出（官方「预计发车:11:00」）→ 直接显示官方原文、单位为空",
          eta_s.native_value == "预计发车:11:00" and eta_s.native_unit_of_measurement is None,
          f"{eta_s.native_value} / {eta_s.native_unit_of_measurement}")
    coordU.preview = {"minutes": None, "neardis": "", "neartext": "10站"}
    check("Z8 v0.9.7 官方只有到站文案（neardis 空）→ 显示「10站」",
          eta_s.native_value == "10站", str(eta_s.native_value))
    coordU.preview = {"minutes": None, "neardis": "", "neartext": ""}
    check("Z9 v0.9.7 官方什么都没给才显示「暂无数据」",
          eta_s.native_value == "暂无数据", str(eta_s.native_value))
    coordU.preview = {"minutes": 0, "neardis": "", "neartext": "已到站"}
    check("Z10 v0.9.7 官方「已到站」→ 0 分钟（保持 0.9.3 口径）",
          eta_s.native_value == 0 and eta_s.native_unit_of_measurement == "分钟",
          f"{eta_s.native_value} / {eta_s.native_unit_of_measurement}")
    coordU.preview = {}

    # ============ T. 新版触发器体系（v0.9.14） ============
    print("\n[T] 新版触发器体系：trigger.py + triggers.yaml + translations.triggers")

    tg = importlib.import_module("my_bus.trigger")
    trigger_mod = sys.modules["homeassistant.helpers.trigger"]

    check("T1 trigger.py 可导入且 TRIGGERS 恰好九个键"
          "（到站状态四态 + 温湿度式 3 + 数据同步 + 车牌变为；"
          "v0.9.31 删除车牌变化/换车）",
          set(tg.TRIGGERS) == {
              "arrival_arrived", "arrival_arriving", "arrival_not_arriving",
              "arrival_no_bus", "remaining_stops", "remaining_km", "eta", "data_sync",
              "plate_becomes"},
          str(sorted(tg.TRIGGERS)))
    check("T2 async_get_triggers 返回 TRIGGERS 本身",
          (await tg.async_get_triggers(None)) is tg.TRIGGERS)

    aa = tg.TRIGGERS["arrival_arrived"]
    ai = tg.TRIGGERS["arrival_arriving"]
    an = tg.TRIGGERS["arrival_not_arriving"]
    ab = tg.TRIGGERS["arrival_no_bus"]
    check("T3 门窗式四条是目标状态触发器，目标状态分别为 已到站 / 即将到站 / 未到站 / 暂无车辆"
          "（v0.9.23 新增后两条）",
          all(issubclass(c, trigger_mod.EntityTargetStateTriggerBase)
              for c in (aa, ai, an, ab))
          and aa._to_states == {"已到站"} and ai._to_states == {"即将到站"}
          and an._to_states == {"未到站"} and ab._to_states == {"暂无车辆"},
          f"{aa._to_states} / {ai._to_states} / {an._to_states} / {ab._to_states}")
    check("T4 门窗式 domain_specs 只过滤 sensor 域",
          all(c._domain_specs.keys() == {"sensor"} for c in (aa, ai, an, ab)))

    rs = tg.TRIGGERS["remaining_stops"]
    rk = tg.TRIGGERS["remaining_km"]
    et = tg.TRIGGERS["eta"]
    check("T5 温湿度式三条都是数值变化触发器（threshold 可选 任意变化/高于/低于/区间）",
          all(issubclass(c, trigger_mod.EntityNumericalStateChangedTriggerBase)
              for c in (rs, rk, et)))
    check("T6 温湿度式 domain_specs 只过滤 sensor 域",
          rs._domain_specs.keys() == {"sensor"}
          and rk._domain_specs.keys() == {"sensor"}
          and et._domain_specs.keys() == {"sensor"})
    ds_trig = tg.TRIGGERS["data_sync"]
    check("T7 数据同步完成是无状态实体触发器，domain_specs 只过滤 sensor 域",
          issubclass(ds_trig, trigger_mod.StatelessEntityTriggerBase)
          and ds_trig._domain_specs.keys() == {"sensor"})

    class _FakeState:
        def __init__(self, state):
            self.state = state

    rep = lambda *a, **kw: None
    inst_aa = aa(None, trigger_mod.TriggerConfig("my_bus.arrival_arrived", {"entity_id": ["x"]}, {}))
    check("T8 公交已到站：新状态 已到站 有效、未到站/暂无车辆 无效",
          inst_aa.is_valid_state(_FakeState("已到站"), rep)
          and not inst_aa.is_valid_state(_FakeState("未到站"), rep)
          and not inst_aa.is_valid_state(_FakeState("暂无车辆"), rep))
    check("T9 公交已到站：从未到站 → 已到站 触发；已到站 → 已到站 不触发",
          inst_aa.is_valid_change(_FakeState("未到站"), _FakeState("已到站"))
          and not inst_aa.is_valid_change(_FakeState("已到站"), _FakeState("已到站")))
    check("T9b 公交即将到站：未到站/已到站 → 即将到站 触发",
          ai(None, trigger_mod.TriggerConfig("k", {}, {})).is_valid_change(
              _FakeState("未到站"), _FakeState("即将到站"))
          and not ai(None, trigger_mod.TriggerConfig("k", {}, {})).is_valid_change(
              _FakeState("已到站"), _FakeState("已到站")))

    inst_rs = rs(None, trigger_mod.TriggerConfig(
        "my_bus.remaining_stops", {"entity_id": ["x"]}, {"threshold": {"type": "any"}}))
    check("T10 剩余站数：threshold 任意变化时，数值变化有效",
          inst_rs.is_valid_state(_FakeState("5"), rep)
          and inst_rs.is_valid_change(_FakeState("4"), _FakeState("5")))
    check("T11 剩余站数：非数值新值（暂无数据 / 暂无车辆）一律不触发（0.9.13 语义保留）",
          not inst_rs.is_valid_state(_FakeState("暂无数据"), rep)
          and not inst_rs.is_valid_state(_FakeState("暂无车辆"), rep)
          and not inst_rs.is_valid_change(_FakeState("4"), _FakeState("暂无数据")))
    inst_rs_above = rs(None, trigger_mod.TriggerConfig(
        "k", {}, {"threshold": {"type": "above", "value": {"number": 3}}}))
    check("T12 剩余站数：高于 3 → 5 触发、2 不触发（区间/低于语义由同一基类保证）",
          inst_rs_above.is_valid_state(_FakeState("5"), rep)
          and not inst_rs_above.is_valid_state(_FakeState("2"), rep))
    inst_rs_between = rs(None, trigger_mod.TriggerConfig(
        "k", {}, {"threshold": {"type": "between", "value_min": {"number": 1}, "value_max": {"number": 3}}}))
    check("T12b 剩余站数：区间 1..3 → 2 触发、5 不触发",
          inst_rs_between.is_valid_state(_FakeState("2"), rep)
          and not inst_rs_between.is_valid_state(_FakeState("5"), rep))
    inst_et = et(None, trigger_mod.TriggerConfig(
        "my_bus.eta", {"entity_id": ["x"]}, {"threshold": {"type": "any"}}))
    check("T13 预计到达：数字状态有效、官方文案（预计发车:11:00）无效",
          inst_et.is_valid_state(_FakeState("17"), rep)
          and not inst_et.is_valid_state(_FakeState("预计发车:11:00"), rep))
    inst_ds = ds_trig(None, trigger_mod.TriggerConfig("my_bus.data_sync", {"entity_id": ["x"]}, {}))
    check("T14 数据同步完成：时间戳变化即触发，时间戳没变不触发",
          inst_ds.is_valid_change(_FakeState("2026-10-24T10:00:00+00:00"),
                                  _FakeState("2026-10-24T10:00:05+00:00"))
          and not inst_ds.is_valid_change(_FakeState("2026-10-24T10:00:05+00:00"),
                                          _FakeState("2026-10-24T10:00:05+00:00")))

    import yaml as _yaml
    tdesc = _yaml.safe_load(open(os.path.join(_CC, "triggers.yaml"), encoding="utf-8"))
    check("T15 triggers.yaml 键与 TRIGGERS 完全一致",
          set(tdesc) == set(tg.TRIGGERS), str(sorted(tdesc)))
    check("T16 triggers.yaml target 全部限定 integration: my_bus + domain sensor，"
          "并按 device_class 一对一挂载（v0.9.16：数值三条各挂专属自定义 device_class）",
          all(
              tdesc[k]["target"]["entity"] == [{"integration": "my_bus", "domain": "sensor",
                                                "device_class": dc}]
              for k, dc in (("arrival_arrived", "enum"), ("arrival_arriving", "enum"),
                            ("arrival_not_arriving", "enum"), ("arrival_no_bus", "enum"),
                            ("remaining_stops", "stop_count"),
                            ("remaining_km", "remaining_distance"),
                            ("eta", "eta"), ("data_sync", "timestamp"))),
          str({k: tdesc[k]["target"]["entity"] for k in tdesc}))
    check("T17 数值触发器 threshold 字段 = numeric_threshold changed 模式，单位分别 站/公里/分钟",
          all(
              tdesc[k]["fields"]["threshold"]["selector"]["numeric_threshold"]["mode"] == "changed"
              and tdesc[k]["fields"]["threshold"]["selector"]["numeric_threshold"]["number"]["unit_of_measurement"] == u
              for k, u in (("remaining_stops", "站"), ("remaining_km", "公里"), ("eta", "分钟"))),
          str({k: tdesc[k]["fields"]["threshold"]["selector"]["numeric_threshold"]["number"].get("unit_of_measurement")
               for k in ("remaining_stops", "remaining_km", "eta")}))
    check("T17b 门窗式四条与数据同步没有多余字段（fields 不存在或为空）",
          all(not tdesc[k].get("fields")
              for k in ("arrival_arrived", "arrival_arriving", "arrival_not_arriving",
                        "arrival_no_bus", "data_sync")))

    check("T18 strings.json 与两份 translations 都有 triggers 段：八键、name 全中文且与触发器对应",
          set(STRINGS.get("triggers", {})) == set(tg.TRIGGERS)
          and set(ZH.get("triggers", {})) == set(tg.TRIGGERS)
          and all(has_cjk(STRINGS["triggers"][k]["name"]) for k in tg.TRIGGERS)
          and all(has_cjk(ZH["triggers"][k]["name"]) for k in tg.TRIGGERS)
          and EN["triggers"] == ZH["triggers"])
    check("T18b icons.json triggers 八键且图标是 mdi 路径",
          set(json.load(open(os.path.join(_CC, "icons.json"), encoding="utf-8"))["triggers"]) == set(tg.TRIGGERS)
          and all(v["trigger"].startswith("mdi:")
                  for v in json.load(open(os.path.join(_CC, "icons.json"), encoding="utf-8"))["triggers"].values()))
    check("T18c 旧版 device_trigger.py 仍在（老自动化兼容不受影响）",
          os.path.isfile(os.path.join(_CC, "device_trigger.py")))

    # v0.9.23：触发器与条件的文案必须完全统一（同一状态两侧一字不差）
    _pair = [("arrival_arrived", "is_arrived"), ("arrival_arriving", "is_arriving"),
             ("arrival_not_arriving", "is_not_arriving"), ("arrival_no_bus", "is_no_bus")]
    check("T20 v0.9.23 四条到站状态触发器的名称与条件名称完全一致（文案统一）",
          all(STRINGS["triggers"][tk]["name"] == STRINGS["conditions"][ck]["name"]
              and ZH["triggers"][tk]["name"] == ZH["conditions"][ck]["name"]
              for tk, ck in _pair),
          str({tk: STRINGS["triggers"][tk]["name"] for tk, _ in _pair}))
    check("T21 v0.9.23 触发器名称已去掉「公交」前缀与「是「」包裹，且为纯状态原文",
          [ZH["triggers"][tk]["name"] for tk, _ in _pair]
          == [logic.STATUS_ARRIVED, logic.STATUS_ARRIVING,
              logic.STATUS_NOT_ARRIVING, logic.STATUS_NO_BUS]
          and all("公交" not in v and "「" not in v for v in
                  [ZH["triggers"][tk]["name"] for tk, _ in _pair]),
          str([ZH["triggers"][tk]["name"] for tk, _ in _pair]))

    check("T19 v0.9.15 事件体系全部删除：event.py 不存在、无 Platform.EVENT、"
          "coordinator 无 pending_events / event_entity_id",
          not os.path.isfile(os.path.join(_CC, "event.py"))
          and "Platform.EVENT" not in open(os.path.join(_CC, "__init__.py"), encoding="utf-8").read()
          and "pending_events" not in open(os.path.join(_CC, "coordinator.py"), encoding="utf-8").read()
          and "event_entity_id" not in open(os.path.join(_CC, "coordinator.py"), encoding="utf-8").read())
    _sensor_src = open(os.path.join(_CC, "sensor.py"), encoding="utf-8").read()
    check("T20 到站状态传感器声明 enum device_class + options；数据同步不是诊断类",
          "SensorDeviceClass.ENUM" in _sensor_src
          and "STATUS_NOT_ARRIVING" in _sensor_src and "STATUS_NO_BUS" in _sensor_src
          and "EntityCategory" not in _sensor_src)
    check("T21 触发器描述无括号说明；trigger_type 与 entity.event 无 bus_arrived / event 残留",
          "（仿" not in json.dumps(STRINGS["triggers"], ensure_ascii=False)
          and "bus_arrived" not in ZH["device_automation"]["trigger_type"]
          and "bus_arrived" not in STRINGS["device_automation"]["trigger_type"]
          and "event" not in ZH["entity"])

    # ============ v0.9.16：device_class 一对一挂载 + 残留事件实体自动清理 ============
    check("T22 v0.9.16 三个数值传感器声明专属自定义 device_class，五个实体判别符互不重叠"
          "（HA 对未知 device_class 按 None 处理，不触发数值校验；注册表保留原值供匹配）",
          sensor_mod.XmBusRemainingStopsSensor._attr_device_class == "stop_count"
          and sensor_mod.XmBusRemainingKmSensor._attr_device_class == "remaining_distance"
          and sensor_mod.XmBusEtaSensor._attr_device_class == "eta"
          and sensor_mod.XmBusArrivalStatusSensor._attr_device_class == "enum"
          and sensor_mod.XmBusDataSyncSensor._attr_device_class == "timestamp",
          str((sensor_mod.XmBusRemainingStopsSensor._attr_device_class,
               sensor_mod.XmBusRemainingKmSensor._attr_device_class,
               sensor_mod.XmBusEtaSensor._attr_device_class)))
    check("T23 v0.9.16 启动时清理残留事件实体：__init__.py 定义清理函数并在 setup 里调用",
          "_async_remove_orphan_event_entities" in open(os.path.join(_CC, "__init__.py"), encoding="utf-8").read()
          and "async_entries_for_config_entry" in open(os.path.join(_CC, "__init__.py"), encoding="utf-8").read()
          and "_async_remove_orphan_event_entities(hass, entry)" in open(os.path.join(_CC, "__init__.py"), encoding="utf-8").read())

    # 行为验证：注册表里本条目有一个 event.* 残留 + 两个 sensor → 清理只删 event
    er_mod = importlib.import_module("homeassistant.helpers.entity_registry")
    hassC = stub_ha._fake_hass(None)
    regC = hassC._entity_registry
    _mk = lambda eid, dom: types.SimpleNamespace(
        entity_id=eid, domain=dom, config_entry_id="e1")
    regC.entries = [_mk("event.my_bus_gong_jiao_dao_zhan", "event"),
                    _mk("sensor.my_bus_arrival_status", "sensor"),
                    _mk("sensor.my_bus_eta", "sensor")]
    entryC = types.SimpleNamespace(entry_id="e1")
    entry_init._async_remove_orphan_event_entities(hassC, entryC)
    check("T23b 清理函数只删本条目名下的 event.* 实体，传感器与其它条目不动",
          regC.removed == ["event.my_bus_gong_jiao_dao_zhan"]
          and len(regC.entries) == 2
          and all(e.domain == "sensor" for e in regC.entries),
          f"removed={regC.removed} left={[e.entity_id for e in regC.entries]}")
    regC.entries = [_mk("event.other_entry", "event")]
    regC.removed = []
    other_entry = types.SimpleNamespace(entry_id="e2")
    entry_init._async_remove_orphan_event_entities(hassC, other_entry)
    check("T23c 其它条目的 event 实体不清理",
          regC.removed == [] and len(regC.entries) == 1,
          f"removed={regC.removed}")

    # ============ v0.9.20：设备条件（到站状态） ============
    dc = importlib.import_module("my_bus.device_condition")
    dt_mod = importlib.import_module("homeassistant.util.dt")

    def _raises(fn) -> bool:
        try:
            fn()
        except Exception:  # noqa: BLE001  校验失败即抛异常
            return True
        return False

    check("AB1 v0.9.20 设备条件四种类型，界面顺序 = 已到站 / 未到站 / 即将到站 / 暂无车辆",
          dc.CONDITION_TYPES == ["is_arrived", "is_not_arriving", "is_arriving", "is_no_bus"],
          str(dc.CONDITION_TYPES))
    check("AB2 条件类型 → 目标状态是**精确匹配**（不是取反）",
          dc.CONDITION_STATES == {
              "is_arrived": logic.STATUS_ARRIVED,
              "is_not_arriving": logic.STATUS_NOT_ARRIVING,
              "is_arriving": logic.STATUS_ARRIVING,
              "is_no_bus": logic.STATUS_NO_BUS,
          },
          str(dc.CONDITION_STATES))

    hassD = stub_ha._fake_hass(None)
    regD = hassD._entity_registry

    def _mk_cond_entry(entity_id, entry_id, tkey, device_id="dev1", platform="my_bus"):
        return types.SimpleNamespace(
            entity_id=entity_id, id=entry_id, device_id=device_id,
            platform=platform, translation_key=tkey, unique_id=f"my_bus_{tkey}")

    regD.entries = [
        _mk_cond_entry("sensor.my_bus_k1_arrival_status", "regid_status", "arrival_status"),
        _mk_cond_entry("sensor.my_bus_k1_remaining_stops", "regid_stops", "remaining_stops"),
        _mk_cond_entry("sensor.other_arrival_status", "regid_other", "arrival_status",
                       platform="other_integration"),
        _mk_cond_entry("sensor.my_bus_k1_eta", "regid_eta", "eta", device_id="dev2"),
    ]
    condsD = await dc.async_get_conditions(hassD, "dev1")
    check("AB3 只为本集成的「到站状态」实体列出 4 条条件（其它实体/其它集成/其它设备都不列）",
          len(condsD) == 4
          and [c["type"] for c in condsD] == dc.CONDITION_TYPES
          and all(c["entity_id"] == "regid_status" for c in condsD)
          and all(c["condition"] == "device" and c["domain"] == "my_bus"
                  and c["device_id"] == "dev1" for c in condsD),
          str([(c.get("type"), c.get("entity_id"), c.get("domain")) for c in condsD]))

    capsD = await dc.async_get_condition_capabilities(hassD, condsD[0])
    schemaD = capsD["extra_fields"]
    check("AB4 条件界面附加字段只有「持续」时长（for），合法值通过、非法键被拒",
          set(schemaD({}).keys()) == set()
          and schemaD({"for": {"minutes": 5}})["for"] == {"minutes": 5}
          and _raises(lambda: schemaD({"bogus": 1})),
          str(schemaD.schema))

    # 状态判定（含注册表 ID 解析）
    hassS = stub_ha._fake_hass(None)
    hassS._entity_registry.entries = [
        _mk_cond_entry("sensor.my_bus_k1_arrival_status", "regid_status", "arrival_status"),
    ]
    now = dt_mod.utcnow()

    def _put_state(value, seconds_ago=0):
        hassS.states._states["sensor.my_bus_k1_arrival_status"] = types.SimpleNamespace(
            state=value, last_changed=now - timedelta(seconds=seconds_ago))

    def _cfg(ctype, entity="regid_status", for_value=None):
        cfg = {"condition": "device", "domain": "my_bus", "device_id": "dev1",
               "entity_id": entity, "type": ctype}
        if for_value is not None:
            cfg["for"] = for_value
        return cfg

    _put_state(logic.STATUS_ARRIVED)
    arrived_ck = dc.async_condition_from_config(hassS, _cfg("is_arrived"))
    not_arr_ck = dc.async_condition_from_config(hassS, _cfg("is_not_arriving"))
    check("AB5 已到站时：「是已到站」为真、「是未到站」为假（注册表 ID 能解析回 entity_id）",
          arrived_ck(hassS) is True and not_arr_ck(hassS) is False,
          f"{arrived_ck(hassS)} / {not_arr_ck(hassS)}")

    _put_state(logic.STATUS_NOT_ARRIVING)
    check("AB6 未到站时：「是未到站」为真、「是已到站」为假",
          dc.async_condition_from_config(hassS, _cfg("is_not_arriving"))(hassS) is True
          and dc.async_condition_from_config(hassS, _cfg("is_arrived"))(hassS) is False)

    _put_state(logic.STATUS_ARRIVING)
    check("AB7 即将到站时：「是即将到站」为真（与「是未到站」互斥）",
          dc.async_condition_from_config(hassS, _cfg("is_arriving"))(hassS) is True
          and dc.async_condition_from_config(hassS, _cfg("is_not_arriving"))(hassS) is False)

    _put_state(logic.STATUS_NO_BUS)
    check("AB8 暂无车辆时：「是暂无车辆」为真（严格官方口径下解析不出就是它）",
          dc.async_condition_from_config(hassS, _cfg("is_no_bus"))(hassS) is True
          and dc.async_condition_from_config(hassS, _cfg("is_arrived"))(hassS) is False)

    _put_state(logic.STATUS_ARRIVED, seconds_ago=60)
    check("AB9 「持续」判定：状态已持续 60 秒 → for 30 秒为真、for 5 分钟为假",
          dc.async_condition_from_config(
              hassS, _cfg("is_arrived", for_value={"seconds": 30}))(hassS) is True
          and dc.async_condition_from_config(
              hassS, _cfg("is_arrived", for_value={"minutes": 5}))(hassS) is False)

    hassS.states._states.clear()
    check("AB10 实体不存在时条件一律为假（不会因为拿不到状态而放行）",
          dc.async_condition_from_config(hassS, _cfg("is_arrived"))(hassS) is False
          and dc.async_condition_from_config(hassS, _cfg("is_no_bus"))(hassS) is False)

    # schema 校验：合法配置通过、未知类型被拒
    cond_schema = dc.CONDITION_SCHEMA
    ok_cfg = cond_schema({"platform": "device", "domain": "my_bus", "device_id": "dev1",
                          "entity_id": "regid_status", "type": "is_arrived"})
    check("AB11 条件 schema 接受界面保存的形态（注册表 ID + type + 可选 for），未知 type 被拒",
          ok_cfg["type"] == "is_arrived"
          and _raises(lambda: cond_schema({"platform": "device", "domain": "my_bus",
                                           "device_id": "dev1",
                                           "entity_id": "regid_status",
                                           "type": "is_flying"})),
          str(ok_cfg))

    # 语言文件：三份都要有 condition_type，两份 translations 逐字节一致且全中文
    zh_cond = ZH["device_automation"]["condition_type"]
    str_cond = STRINGS["device_automation"]["condition_type"]
    en_cond = EN["device_automation"]["condition_type"]
    check("AB12 三份语言文件都补了 condition_type：strings 为对象形式、translations 为纯字符串，"
          "两份 translations 逐字节一致",
          list(zh_cond) == dc.CONDITION_TYPES
          and list(str_cond) == dc.CONDITION_TYPES
          and all(isinstance(v, dict) and v.get("name") and v.get("description")
                  for v in str_cond.values())
          and all(isinstance(v, str) and v for v in zh_cond.values())
          and zh_cond == en_cond
          and open(os.path.join(_CC, "translations", "zh-Hans.json"), "rb").read()
          == open(os.path.join(_CC, "translations", "en.json"), "rb").read(),
          str(zh_cond))
    check("AB13 条件名称含「已到站 / 未到站」且中文，不带英文残留",
          "已到站" in zh_cond["is_arrived"] and "未到站" in zh_cond["is_not_arriving"]
          and all(re.search(r"[\u4e00-\u9fff]", v) for v in zh_cond.values()))

    # ============ v0.9.21：新版条件注册表（condition.py + conditions.yaml） ============
    print("\n[AC] v0.9.21 新版条件体系：condition.py + conditions.yaml + translations.conditions")
    COND_KEYS = ["is_arrived", "is_not_arriving", "is_arriving", "is_no_bus"]
    cdesc = _yaml.safe_load(open(os.path.join(_CC, "conditions.yaml"), encoding="utf-8"))
    cond_mod = importlib.import_module("my_bus.condition")

    check("AC1 conditions.yaml 前四条为状态条件，键与 CONDITION 注册表完全一致",
          list(cdesc)[:4] == COND_KEYS and set(cdesc) == set(cond_mod.CONDITIONS),
          str(list(cdesc)))
    check("AC2 四条条件 target 全部限定 integration: my_bus + domain sensor + "
          "device_class: enum（只挂「到站状态」，不串到其余四个传感器）",
          all(cdesc[k]["target"]["entity"]
              == [{"integration": "my_bus", "domain": "sensor", "device_class": "enum"}]
              for k in COND_KEYS)
          and all(cdesc[k]["target"]["primary_entities_only"] is False
                  for k in COND_KEYS),
          str({k: cdesc[k]["target"] for k in COND_KEYS}))
    check("AC3 每条都声明 behavior + for 字段（缺任一个前端保存会被 PREVENT_EXTRA 拒绝，"
          "同 0.9.11 触发器漏声明 to 的坑）",
          all(set(cdesc[k]["fields"]) == {"behavior", "for"} for k in COND_KEYS)
          and all(cdesc[k]["fields"]["behavior"]["selector"]["automation_behavior"]["mode"]
                  == "condition" for k in COND_KEYS)
          and all("duration" in cdesc[k]["fields"]["for"]["selector"] for k in COND_KEYS),
          str(cdesc["is_arrived"]["fields"]))
    check("AC4 四条条件的状态值分别是 已到站 / 未到站 / 即将到站 / 暂无车辆",
          [cond_mod.CONDITIONS[k]._state for k in COND_KEYS]
          == [logic.STATUS_ARRIVED, logic.STATUS_NOT_ARRIVING,
              logic.STATUS_ARRIVING, logic.STATUS_NO_BUS],
          str([cond_mod.CONDITIONS[k]._state for k in COND_KEYS]))

    hassC = stub_ha._fake_hass(None)
    matrix_ok = True
    for st in (logic.STATUS_ARRIVED, logic.STATUS_NOT_ARRIVING,
               logic.STATUS_ARRIVING, logic.STATUS_NO_BUS):
        hassC.states._states["sensor.cond"] = types.SimpleNamespace(state=st)
        for key in COND_KEYS:
            inst = cond_mod.CONDITIONS[key](hassC, {"entity_id": ["sensor.cond"]})
            expected = st == cond_mod.CONDITIONS[key]._state
            if bool(inst._async_check()) is not expected:
                matrix_ok = False
    check("AC5 四态判定矩阵：每条条件只对自己那个状态成立（精确匹配，不是取反）",
          matrix_ok)
    check("AC6 async_get_conditions 返回同一份 CONDITIONS 注册表（核心按它加载）",
          await cond_mod.async_get_conditions(hassC) is cond_mod.CONDITIONS)

    check("AC7 三份语言文件都有 conditions 段：八键、name/description 全中文、"
          "两份 translations 逐字节一致",
          set(STRINGS.get("conditions", {})) == set(cdesc)
          and set(ZH.get("conditions", {})) == set(cdesc)
          and EN.get("conditions") == ZH.get("conditions")
          and all(has_cjk(STRINGS["conditions"][k]["name"]) for k in cdesc)
          and all(has_cjk(STRINGS["conditions"][k]["description"]) for k in cdesc)
          and open(os.path.join(_CC, "translations", "zh-Hans.json"), "rb").read()
          == open(os.path.join(_CC, "translations", "en.json"), "rb").read(),
          str(list(ZH.get("conditions", {}))))
    check("AC8 icons.json 有 conditions 段八键且都是 mdi 图标",
          set(json.load(open(os.path.join(_CC, "icons.json"), encoding="utf-8"))["conditions"])
          == set(cdesc)
          and all(v["condition"].startswith("mdi:")
                  for v in json.load(open(os.path.join(_CC, "icons.json"),
                                          encoding="utf-8"))["conditions"].values()))
    _cond_src = open(os.path.join(_CC, "condition.py"), encoding="utf-8").read()
    check("AC9 九条条件 = 4 条状态工厂 + 4 条数值工厂 + 1 条车牌自写类"
          "（v0.9.32 删除车牌不是、车牌是改名车牌变为），"
          "全部 primary_entities_only=False",
          len(cond_mod.CONDITIONS) == 9
          and "make_entity_state_condition" in _cond_src
          and "make_entity_numerical_condition" in _cond_src
          and "primary_entities_only=False" in _cond_src)

    # v0.9.22：用户要求去掉条件文案里的「是「…」」包裹，名称直接是四种状态原文
    _cond_names = [ZH["conditions"][k]["name"] for k in COND_KEYS]
    check("AC10 v0.9.22 条件名称不含「是「」包裹，直接就是状态原文"
          "（已到站 / 未到站 / 即将到站 / 暂无车辆）",
          _cond_names == [logic.STATUS_ARRIVED, logic.STATUS_NOT_ARRIVING,
                          logic.STATUS_ARRIVING, logic.STATUS_NO_BUS]
          and all("「" not in n and "」" not in n for n in _cond_names)
          and [STRINGS["conditions"][k]["name"] for k in COND_KEYS] == _cond_names,
          str(_cond_names))
    check("AC11 v0.9.22 旧 device_condition 的 condition_type 名称同样不含「是「」",
          all("是「" not in v and "」" not in v
              for v in ZH["device_automation"]["condition_type"].values())
          and all("是「" not in v["name"] and "」" not in v["name"]
                  for v in STRINGS["device_automation"]["condition_type"].values()),
          str(ZH["device_automation"]["condition_type"]))

    # ============ v0.9.24：条件补齐到八条（与触发器对称） ============
    print("\n[AD] v0.9.24 条件补齐：剩余站数 / 剩余公里数 / 预计到达 / 数据同步")
    NUM_KEYS = ["remaining_stops", "remaining_km", "eta", "data_sync"]
    NUM_DC = {"remaining_stops": "stop_count", "remaining_km": "remaining_distance",
              "eta": "eta", "data_sync": "timestamp"}
    NUM_UNIT = {"remaining_stops": "站", "remaining_km": "公里",
                "eta": "分钟", "data_sync": "小时"}

    check("AD1 conditions.yaml 共九条 = 4 状态 + 4 数值 + 1 车牌，与注册表完全一致",
          list(cdesc) == COND_KEYS + NUM_KEYS + ["plate_becomes"]
          and set(cond_mod.CONDITIONS) == set(cdesc),
          str(list(cdesc)))
    check("AD2 四条数值条件按 device_class 一对一挂载（stop_count / remaining_distance / "
          "eta / timestamp，只挂自己的实体）",
          all(cdesc[k]["target"]["entity"]
              == [{"integration": "my_bus", "domain": "sensor",
                   "device_class": NUM_DC[k]}] for k in NUM_KEYS)
          and all(cdesc[k]["target"]["primary_entities_only"] is False for k in NUM_KEYS),
          str({k: cdesc[k]["target"]["entity"] for k in NUM_KEYS}))
    check("AD3 数值条件声明 behavior + for + threshold 三字段；threshold 用核心 "
          "numeric_threshold、mode=is（条件语义，触发器那边是 changed），"
          "单位分别是 站 / 公里 / 分钟 / 小时",
          all(set(cdesc[k]["fields"]) == {"behavior", "for", "threshold"} for k in NUM_KEYS)
          and all(cdesc[k]["fields"]["threshold"]["selector"]["numeric_threshold"]["mode"] == "is"
                  for k in NUM_KEYS)
          and all(cdesc[k]["fields"]["threshold"]["selector"]["numeric_threshold"]["number"]
                  ["unit_of_measurement"] == NUM_UNIT[k] for k in NUM_KEYS),
          str(cdesc["remaining_stops"]["fields"]["threshold"]))
    check("AD4 数值条件类的 _domain_specs 与 conditions.yaml 的 device_class 一致",
          all(cond_mod.CONDITIONS[k]._domain_specs["sensor"].device_class == NUM_DC[k]
              for k in NUM_KEYS),
          str({k: cond_mod.CONDITIONS[k]._domain_specs["sensor"].device_class
               for k in NUM_KEYS}))
    check("AD5 数据同步条件比对实体属性 sync_age_hours"
          "（状态是时间戳，float(state) 转不了数字，必须走属性）",
          cond_mod.CONDITIONS["data_sync"]._domain_specs["sensor"].value_source
          == "距上次同步小时数")
    check("AD6 数值条件没传 valid_unit（传 None 会要求实体无单位 ⇒ 条件永不成立）",
          all(getattr(cond_mod.CONDITIONS[k], "_valid_unit", None) is not None
              for k in NUM_KEYS))
    class _FakeSync:
        """只带 _status 的最小替身（借用真实实体的 property 与计算方法）."""

        extra_state_attributes = sensor_mod.XmBusDataSyncSensor.extra_state_attributes
        _sync_age_hours = sensor_mod.XmBusDataSyncSensor._sync_age_hours

        def __init__(self, status):
            self._status = status

    check("AD7 数据同步实体暴露「距上次同步小时数」数字属性（未同步过为 None，条件不成立）",
          "距上次同步小时数" in _FakeSync({}).extra_state_attributes
          and _FakeSync({}).extra_state_attributes["距上次同步小时数"] is None
          and abs(_FakeSync({"last_sync_ts": time.time() - 3600})._sync_age_hours() - 1.0) < 0.05,
          str(_FakeSync({}).extra_state_attributes))
    check("AD8 三份语言文件与 icons 都补齐四条数值条件，名称与触发器呼应",
          [ZH["conditions"][k]["name"] for k in NUM_KEYS]
          == ["剩余站数", "剩余公里数", "预计到达", "数据同步"]
          and [STRINGS["conditions"][k]["name"] for k in NUM_KEYS]
          == [ZH["conditions"][k]["name"] for k in NUM_KEYS]
          and all(k in json.load(open(os.path.join(_CC, "icons.json"),
                                      encoding="utf-8"))["conditions"] for k in NUM_KEYS),
          str([ZH["conditions"][k]["name"] for k in NUM_KEYS]))
    check("AD9 触发器与条件重新对称：各 9 条"
          "（0.9.31 删两条车牌触发器、0.9.32 车牌条件删一并改名后两边都是 9）",
          len(tg.TRIGGERS) == 9 and len(cond_mod.CONDITIONS) == 9,
          str((len(tg.TRIGGERS), len(cond_mod.CONDITIONS))))
    check("AD10 数值条件名 = 同名触发器名去后缀"
          "（剩余站数变化→剩余站数 / 数据同步完成→数据同步）",
          all(ZH["conditions"][k]["name"]
              == ZH["triggers"][k]["name"].replace("变化", "").replace("完成", "")
              for k in NUM_KEYS),
          str({k: (ZH["triggers"][k]["name"], ZH["conditions"][k]["name"]) for k in NUM_KEYS}))

    # ============ v0.9.25：剩余公里数阈值精确到 0.1 ============
    _km_t = tdesc["remaining_km"]["fields"]["threshold"]["selector"]["numeric_threshold"]
    _km_c = cdesc["remaining_km"]["fields"]["threshold"]["selector"]["numeric_threshold"]
    check("AE1 剩余公里数触发器阈值 step = 0.1（可填 1.3 这类小数）",
          _km_t["number"].get("step") == 0.1,
          str(_km_t["number"]))
    check("AE2 剩余公里数条件阈值 step = 0.1，且条件仍是 is 模式",
          _km_c["number"].get("step") == 0.1 and _km_c["mode"] == "is",
          str(_km_c))
    check("AE3 其余数值项不跟着变小：站/分钟保持默认整数步进，同步小时 step = any",
          "step" not in tdesc["remaining_stops"]["fields"]["threshold"]["selector"]
              ["numeric_threshold"]["number"]
          and "step" not in tdesc["eta"]["fields"]["threshold"]["selector"]
              ["numeric_threshold"]["number"]
          and "step" not in cdesc["remaining_stops"]["fields"]["threshold"]["selector"]
              ["numeric_threshold"]["number"]
          and "step" not in cdesc["eta"]["fields"]["threshold"]["selector"]
              ["numeric_threshold"]["number"]
          and cdesc["data_sync"]["fields"]["threshold"]["selector"]
              ["numeric_threshold"]["number"].get("step") == "any",
          "")
    check("AE4 阈值 min 仍为 0（小数不会解除非负限制），单位仍是「公里」",
          _km_t["number"].get("min") == 0 and _km_c["number"].get("min") == 0
          and _km_t["number"].get("unit_of_measurement") == "公里"
          and _km_c["number"].get("unit_of_measurement") == "公里",
          "")
    check("AE5 文案里不再提精度（0.9.26 撤掉「可精确到 0.1 公里」），"
          "三份语言文件与 0.9.24 措辞一致、两份 translations 逐字节一致",
          "0.1" not in STRINGS["triggers"]["remaining_km"]["description"]
          and "0.1" not in STRINGS["conditions"]["remaining_km"]["description"]
          and "0.1" not in STRINGS["triggers"]["remaining_km"]["fields"]["threshold"]["description"]
          and "0.1" not in STRINGS["conditions"]["remaining_km"]["fields"]["threshold"]["description"]
          and STRINGS["conditions"]["remaining_km"]["description"]
          == "最近一辆车还剩几公里。可设高于、低于、区间或等于，单位：公里。"
          and EN == ZH
          and ZH["triggers"]["remaining_km"]["description"]
          == STRINGS["triggers"]["remaining_km"]["description"]
          and ZH["conditions"]["remaining_km"]["description"]
          == STRINGS["conditions"]["remaining_km"]["description"],
          ZH["conditions"]["remaining_km"]["description"])
    _km_src = open(os.path.join(_CC, "sensor.py"), encoding="utf-8").read()
    check("AE6 传感器侧本来就是 1 位小数（suggested_display_precision=1，"
          "distance_km 已 round 1 位），阈值口径与显示一致",
          "_attr_suggested_display_precision = 1" in _km_src
          and "round(meters / 1000.0, 1)"
          in open(os.path.join(_CC, "arrival_logic.py"), encoding="utf-8").read(),
          "")

    # ---- v0.9.27：传感器属性名中文化（「状态已变化」触发器的属性下拉框显示键名） ----
    _sync_keys = set(sensor.extra_state_attributes)
    _live_keys = set(stops_s.extra_state_attributes)
    check("AF1 数据同步传感器属性键全中文（11 个，含「距上次同步小时数」）",
          _sync_keys == {"是否启用", "刷新间隔小时", "上次同步", "耗时秒", "城市数",
                         "线路数", "站台数", "失败次数", "最后错误", "问题",
                         "距上次同步小时数"},
          str(sorted(_sync_keys)))
    _live_allowed = {"城市", "线路", "站台", "方向", "车牌", "当前站", "剩余站数",
                     "内部剩余站数", "剩余距离米", "剩余公里数", "预计到达分钟",
                     "预计到达来源", "官方原文", "官方剩余距离", "到站状态"}
    check("AF2 实时传感器属性键全中文（有车时 15 个；无车时只剩城市/线路/站台/方向）",
          _live_keys <= _live_allowed
          and {"城市", "线路", "站台", "方向"} <= _live_keys,
          str(sorted(_live_keys)))
    check("AF3 没有任何属性键含 ASCII 字母（否则下拉框又会冒英文）",
          all(not any(c.isascii() and c.isalpha() for c in k)
              for k in _sync_keys | _live_keys),
          str([k for k in _sync_keys | _live_keys
               if any(c.isascii() and c.isalpha() for c in k)]))
    _cond_src2 = open(os.path.join(_CC, "condition.py"), encoding="utf-8").read()
    check("AF4 数据同步条件的 value_source 跟着改成中文键（旧 sync_age_hours 全清）",
          'value_source="距上次同步小时数"' in _cond_src2
          and "sync_age_hours" not in _cond_src2, "")
    _dt_src = open(os.path.join(_CC, "device_trigger.py"), encoding="utf-8").read()
    check("AF5 旧「按设备」触发器按新键读属性，事件数据字段名仍是英文（老模板不失效）",
          'attributes.get("车牌")' in _dt_src
          and 'attributes.get("剩余公里数")' in _dt_src
          and 'attributes.get("到站状态")' in _dt_src
          and 'attributes.get("plate")' not in _dt_src
          and '"bus_number": attributes.get("车牌")' in _dt_src, "")
    _sensor_src2 = open(os.path.join(_CC, "sensor.py"), encoding="utf-8").read()
    check("AF6 预计到达来源的值也中文化（官方 / None），属性字典里不再写 official",
          '"预计到达来源": "官方" if minutes is not None else None' in _sensor_src2
          and '"official"' not in _sensor_src2, "")


    # ============ v0.9.28：车牌实体 + 2 触发器 + 2 条件 ============
    print("\n[AG] v0.9.28 车牌传感器 + v0.9.32 车牌变为条件（原车牌是改名，车牌不是已删）")
    PLATE_DC = "license_plate"
    _ENTITY_TRIGGER_BASE = importlib.import_module(
        "homeassistant.helpers.trigger").EntityTriggerBase
    PLATE_KEYS = ["plate_changed", "plate_replaced"]  # v0.9.31 已删除，仅反向断言用
    PLATE_COND_KEYS = ["plate_becomes"]  # v0.9.32：plate_is 改名，plate_is_not 删除
    _setup_src = open(os.path.join(_CC, "sensor.py"), encoding="utf-8").read()
    _icons = json.load(open(os.path.join(_CC, "icons.json"), encoding="utf-8"))

    check("AG1 车牌传感器：translation_key=plate、自定义 device_class=license_plate、"
          "已在 async_setup_entry 里注册",
          sensor_mod.XmBusPlateSensor._attr_translation_key == "plate"
          and sensor_mod.XmBusPlateSensor._attr_device_class == PLATE_DC
          and "XmBusPlateSensor(coordinator, entry)" in _setup_src, "")

    _plate_cls = sensor_mod.XmBusPlateSensor
    _with_bus = types.SimpleNamespace(_bus={"plate": "闽D12345D"})
    _no_bus = types.SimpleNamespace(_bus=None)
    _blank_plate = types.SimpleNamespace(_bus={"plate": ""})
    check("AG2 车牌实体状态：有车取 bus.plate、没车返回 None（界面显示「未知」）、"
          "车牌为空串也当 None",
          _plate_cls.native_value.fget(_with_bus) == "闽D12345D"
          and _plate_cls.native_value.fget(_no_bus) is None
          and _plate_cls.native_value.fget(_blank_plate) is None,
          str(_plate_cls.native_value.fget(_no_bus)))

    check("AG3 v0.9.31 已删除 plate_changed / plate_replaced：注册表与 "
          "triggers.yaml / 翻译 / icons 里都不再有它们",
          all(k not in tg.TRIGGERS for k in ("plate_changed", "plate_replaced"))
          and all(k not in tdesc for k in ("plate_changed", "plate_replaced"))
          and all(k not in ZH["triggers"] for k in ("plate_changed", "plate_replaced"))
          and all(k not in _icons["triggers"]
                  for k in ("plate_changed", "plate_replaced")),
          str(sorted(tg.TRIGGERS)))

    check("AG4 触发器注册表 9 条，车牌只剩「车牌变为」且继承核心实体触发器基类",
          len(tg.TRIGGERS) == 9
          and issubclass(tg.TRIGGERS["plate_becomes"], _ENTITY_TRIGGER_BASE),
          str(sorted(tg.TRIGGERS)))

    _S = lambda value: types.SimpleNamespace(state=value)  # noqa: E731

    check("AG7 conditions.yaml 车牌条件（plate_becomes）：behavior + for + plate"
          "（文本框），target 只挂 device_class: license_plate",
          list(cdesc)[-1:] == PLATE_COND_KEYS
          and all(set(cdesc[k]["fields"]) == {"behavior", "for", "plate"}
                  for k in PLATE_COND_KEYS)
          and all("text" in cdesc[k]["fields"]["plate"]["selector"]
                  for k in PLATE_COND_KEYS)
          and all(cdesc[k]["target"]["entity"]
                  == [{"integration": "my_bus", "domain": "sensor",
                       "device_class": PLATE_DC}] for k in PLATE_COND_KEYS),
          str(cdesc["plate_becomes"]))

    check("AG8 车牌变为（填 闽D12345D）：同一辆车成立、另一辆不成立，"
          "没车（unknown）不成立",
          cond_mod.CONDITIONS["plate_becomes"](
              None, types.SimpleNamespace(
                  options={"plate": "闽D12345D"}, target={})
          ).is_valid_state(_S("闽D12345D")) is True
          and cond_mod.CONDITIONS["plate_becomes"](
              None, types.SimpleNamespace(
                  options={"plate": "闽D12345D"}, target={})
          ).is_valid_state(_S("闽D67890D")) is False
          and cond_mod.CONDITIONS["plate_becomes"](
              None, types.SimpleNamespace(
                  options={"plate": "闽D12345D"}, target={})
          ).check_state(_S("unknown")) is False,
          "")

    check("AG9b v0.9.32 已删除 plate_is / plate_is_not：注册表、conditions.yaml、"
          "translations、strings、icons 全链路消失",
          all(k not in cond_mod.CONDITIONS for k in ("plate_is", "plate_is_not"))
          and all(k not in cdesc for k in ("plate_is", "plate_is_not"))
          and all(k not in ZH["conditions"] for k in ("plate_is", "plate_is_not"))
          and all(k not in STRINGS["conditions"] for k in ("plate_is", "plate_is_not"))
          and all(k not in _icons["conditions"] for k in ("plate_is", "plate_is_not")),
          str(sorted(cond_mod.CONDITIONS)))

    check("AG9 三份语言文件 + icons 补齐车牌实体与车牌条件（车牌变为），"
          "两份 translations 逐字节一致；strings.json 与 zh-Hans 的车牌段一致",
          ZH["entity"]["sensor"]["plate"]["name"] == "车牌"
          and STRINGS["entity"]["sensor"]["plate"]["name"] == "车牌"
          and [ZH["conditions"][k]["name"] for k in PLATE_COND_KEYS] == ["车牌变为"]
          and [STRINGS["conditions"][k]["name"] for k in PLATE_COND_KEYS]
          == [ZH["conditions"][k]["name"] for k in PLATE_COND_KEYS]
          and all(k in _icons["conditions"] for k in PLATE_COND_KEYS)
          and open(os.path.join(_CC, "translations", "zh-Hans.json"), "rb").read()
          == open(os.path.join(_CC, "translations", "en.json"), "rb").read(),
          str([ZH["conditions"][k]["name"] for k in PLATE_COND_KEYS]))

    # ============ v0.9.29：车牌变为触发器 ============
    print("\n[AH] v0.9.29 车牌变为触发器（手填车牌号，交互与条件「车牌变为」一致）")
    _TARGET_STATE_BASE = importlib.import_module(
        "homeassistant.helpers.trigger").EntityTargetStateTriggerBase

    check("AH1 triggers.yaml 补 plate_becomes：target 只挂 license_plate，"
          "fields 只有 plate（文本框）",
          list(tdesc)[-1] == "plate_becomes"
          and tdesc["plate_becomes"]["target"]["entity"]
          == [{"integration": "my_bus", "domain": "sensor",
               "device_class": PLATE_DC}]
          and set(tdesc["plate_becomes"]["fields"]) == {"plate"}
          and "text" in tdesc["plate_becomes"]["fields"]["plate"]["selector"],
          str(tdesc["plate_becomes"]))

    check("AH2 plate_becomes 已注册且继承核心 EntityTargetStateTriggerBase，"
          "排除规则与「车牌变化」一致（只排除 unavailable）",
          tg.TRIGGERS["plate_becomes"] is tg.PlateBecomesTrigger
          and issubclass(tg.TRIGGERS["plate_becomes"], _TARGET_STATE_BASE)
          and tg.TRIGGERS["plate_becomes"]._excluded_states
          == frozenset({"unavailable"})
          and tg.TRIGGERS["plate_becomes"]._excluded_from_states
          == frozenset({"unavailable"}),
          str(tg.TRIGGERS["plate_becomes"].__mro__[:3]))

    _t_becomes = tg.TRIGGERS["plate_becomes"](
        None, types.SimpleNamespace(
            options={"plate": " 闽D12345D "}, target=None))
    check("AH3 车牌变为（填 闽D12345D）：unknown→目标车 ✅（首班车就是它）、"
          "别车→目标车 ✅、目标车→别车/unknown ❌、目标车→目标车 ❌、"
          "unavailable→目标车 ❌（设备掉线不触发）",
          _t_becomes.is_valid_change(_S("unknown"), _S("闽D12345D")) is True
          and _t_becomes.is_valid_change(_S("闽D67890D"), _S("闽D12345D")) is True
          and _t_becomes.is_valid_change(_S("闽D12345D"), _S("闽D67890D")) is False
          and _t_becomes.is_valid_change(_S("闽D12345D"), _S("unknown")) is False
          and _t_becomes.is_valid_change(_S("闽D67890D"), _S("闽D67890D")) is False
          and _t_becomes.is_valid_change(_S("unavailable"), _S("闽D12345D")) is False,
          "")
    check("AH4 options.plate 两端去空白后比对（填「 闽D12345D 」等价于「闽D12345D」）；"
          "plate 为空串时永不触发",
          _t_becomes.is_valid_change(_S("闽D67890D"), _S("闽D12345D")) is True
          and _t_becomes.is_valid_state(_S("闽D12345D")) is True
          and tg.TRIGGERS["plate_becomes"](
              None, types.SimpleNamespace(options={"plate": ""}, target=None)
          ).is_valid_change(_S("unknown"), _S("闽D12345D")) is False,
          "")

    check("AH5 三份语言文件 + icons 补齐 plate_becomes，两份 translations 逐字节一致",
          ZH["triggers"]["plate_becomes"]["name"] == "车牌变为"
          and STRINGS["triggers"]["plate_becomes"]["name"] == "车牌变为"
          and STRINGS["triggers"]["plate_becomes"]
          == ZH["triggers"]["plate_becomes"]
          and _icons["triggers"]["plate_becomes"]["trigger"].startswith("mdi:")
          and open(os.path.join(_CC, "translations", "zh-Hans.json"), "rb").read()
          == open(os.path.join(_CC, "translations", "en.json"), "rb").read(),
          str(ZH["triggers"]["plate_becomes"]["name"]))

    # ============ v0.9.30：车牌通配符匹配 ============
    print("\n[AI] v0.9.30 车牌通配符匹配（plate_match：* 任意多个字 / ? 一个字）")

    check("AI1 plate_match 纯函数：不含通配符=精确匹配（与 0.9.28 行为一致）、"
          "* 前缀 / ? 单字、两端去空白且忽略大小写、pattern 为空不成立、"
          "unknown / unavailable（没车）一律不成立",
          logic.plate_match("闽D12345D", "闽D12345D") is True
          and logic.plate_match("闽D12345D", "闽D67890D") is False
          and logic.plate_match("闽D06*", "闽D0616D") is True
          and logic.plate_match("闽D06*", "闽D67890D") is False
          and logic.plate_match("闽D?616D", "闽D0616D") is True
          and logic.plate_match("闽D?616D", "闽D06161D") is False
          and logic.plate_match("闽D*16D", "闽D616D") is True
          and logic.plate_match("*", "任意内容") is True
          and logic.plate_match(" 闽d06* ", "闽D0616D") is True
          and logic.plate_match("闽D06*", " 闽d0616d ") is True
          and logic.plate_match("", "闽D12345D") is False
          and logic.plate_match("*", "unknown") is False
          and logic.plate_match("闽D*", "unavailable") is False,
          "")

    _t_wild = tg.TRIGGERS["plate_becomes"](
        None, types.SimpleNamespace(options={"plate": "闽D06*"}, target=None))
    check("AI2 触发器「车牌变为 闽D06*」：unknown→闽D0616D ✅（首班车）、"
          "闽D0611D→闽D0616D ❌（起点已在目标集内）、"
          "闽D67890D→闽D0616D ✅、闽D0699D→unknown ❌、"
          "精确填法（闽D12345D）行为与 0.9.29 完全一致",
          _t_wild.is_valid_change(_S("unknown"), _S("闽D0616D")) is True
          and _t_wild.is_valid_change(_S("闽D0611D"), _S("闽D0616D")) is False
          and _t_wild.is_valid_change(_S("闽D67890D"), _S("闽D0616D")) is True
          and _t_wild.is_valid_change(_S("闽D0699D"), _S("unknown")) is False
          and tg.TRIGGERS["plate_becomes"](
              None, types.SimpleNamespace(options={"plate": "闽D12345D"}, target=None)
          ).is_valid_change(_S("unknown"), _S("闽D12345D")) is True
          and tg.TRIGGERS["plate_becomes"](
              None, types.SimpleNamespace(options={"plate": "闽D12345D"}, target=None)
          ).is_valid_change(_S("unknown"), _S("闽D67890D")) is False,
          "")

    _cw_is = cond_mod.CONDITIONS["plate_becomes"](
        None, types.SimpleNamespace(options={"plate": "闽D06*"}, target={}))
    check("AI3 条件通配符：车牌变为 闽D06* —— 闽D0616D 成立、闽D67890D 不成立、"
          "unknown 不成立",
          _cw_is.is_valid_state(_S("闽D0616D")) is True
          and _cw_is.is_valid_state(_S("闽D67890D")) is False
          and _cw_is.check_state(_S("unknown")) is False,
          "")

    check("AI4 三份语言文件的车牌条目描述都写明通配符规则，"
          "strings.json 与 zh-Hans 一致，两份 translations 逐字节一致",
          all("通配符" in ZH["triggers"]["plate_becomes"]["description"]
              and "通配符" in ZH["triggers"]["plate_becomes"]["fields"]["plate"]["description"]
              and "通配符" in ZH["conditions"]["plate_becomes"]["description"]
              and "通配符" in ZH["conditions"]["plate_becomes"]["fields"]["plate"]["description"]
              and STRINGS["triggers"]["plate_becomes"]
              == ZH["triggers"]["plate_becomes"]
              and STRINGS["conditions"]["plate_becomes"]
              == ZH["conditions"]["plate_becomes"]
              and open(os.path.join(_CC, "translations", "zh-Hans.json"), "rb").read()
              == open(os.path.join(_CC, "translations", "en.json"), "rb").read()
              for _ in (1,)),
          str(ZH["triggers"]["plate_becomes"]["description"]))

    # ============ 汇总 ============
    print(f"\n===== 通过 {len(PASS)} / {len(PASS) + len(FAIL)} =====")
    if FAIL:
        print("失败项:")
        for name in FAIL:
            print("  -", name)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
