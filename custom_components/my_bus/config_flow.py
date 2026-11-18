"""My Bus 配置向导 / 选项设置（全中文 · 按钮式导航 · 无障碍优先）。

设计约束与取舍
==============

Home Assistant 配置流的 UI 硬限制（已核对 HA 前端与核心源码）：

1. 对话框头部只有「关闭」；**表单(form) 底部只渲染一个主按钮**，也没有原生
   「上一步」按钮 —— 表单里放不下第二个按钮；
2. **菜单(menu) 步骤**能把选项渲染成**真正的可点击按钮**，但菜单不能放输入框；
3. 菜单项 key 必须是真实存在的 ``async_step_<id>``；
4. **菜单项的显示文字可以直接由集成给定**（``async_show_menu`` 的
   ``menu_options`` 传 ``dict[key, 文字]``），**完全不走翻译层**；而表单的字段
   标签、提交按钮、以及菜单/表单上方的说明文字必须走 ``translations/``。

针对「不能出现英文」「上一步必须是按钮」「屏幕阅读器可用」这三条要求，本版采用：

* **每一个步骤都做成菜单**，于是每一步都天然拥有**真实的「⬅ 返回上一步」按钮**，
  且**一律排在按钮列表的第一位**（读屏按 Tab 顺序逐个听，导航按钮在前才不会让
  用户为了退一步而听完几百个候选）；第 1 步是起点、没有上一步，那一页由说明区
  第一行的**欢迎语**占位。菜单项文字全部写在 Python 里，**任何界面语言下都只会是
  中文**；文案风格对齐 0.3.0：短句 + emoji 前缀（如「🔍 检索城市名」
  「📍 定位当前城市」），候选按钮直接就是城市 / 站台 / 线路名；
* 只有「需要键盘输入」的两处使用表单 —— **输入检索关键词**与**修改到站参数**；
  表单的字段标签与提交按钮文字在三份语言文件里都写成中文，
  并且关键词字段直接用**中文键名**做兜底（翻译失效时显示的也是中文，不会是英文）；
* **彻底不再使用开关（BooleanSelector）** —— 原来的「定位城市 / 同步数据 /
  反向站台 / 上一步」四个开关全部改成菜单按钮；
* 三份语言文件（``strings.json``、``translations/zh-Hans.json``、
  ``translations/en.json``）**内容完全相同且全部是中文**：因为掌上公交本身只在
  中国内地提供服务，本集成只面向中文用户；这样即使 HA 界面语言不是 zh-Hans
  （HA 会回退到 en），界面上也不会冒出英文。

向导步骤（共 7 步）::

    1 选择城市      city            ① 输入城市名查找 ② 用 HA 位置识别 ③ 浏览全部城市
    2 选择检索方式  mode            先选站台 / 先选线路
    3 选择站台      station         ┐ 先选站台：站台 → 线路（可「换到马路对面站台」）
    4 选择线路      line            ┘
    3 选择线路      line            ┐ 先选线路：线路 → 选择站台（按途经顺序编号）
    4 选择站台      line_station    ┘
    5 选择到站参数  settings        可改刷新间隔
    6 数据同步      sync            与选项菜单的「数据同步」同一套动作
    7 确认创建      confirm         点「完成创建」

**每一页的按钮版式是同一套**（读屏用户换一步不用重新找按钮）：第一个按钮永远是
「⬅ 返回上一步」，第二个永远是「🔍 检索…」（有检索动作的页面），候选紧跟其后。
唯一的例外是**第 1 步**：它是流程起点，本来就没有上一步，于是这一页说明区的
第一行放的是**欢迎语**，由它占据那个位置 —— 读屏听到的次序仍然是
「说明区 → 检索按钮 → 候选 → 其它动作」，与第 3 步一模一样。

第 6 步「数据同步」是 v0.8.9 新增的：创建监控前先把城市 / 线路 / 站台等结构数据
与掌上公交对齐，免得第一个监控建好时本地还什么都没有。它与选项菜单里的
「🔄 数据同步」**共用同一套实现**（见 :meth:`_WizardMixin.async_step_sync`），
所以两条入口看到的按钮、提示、结果完全一致。

「先选站台 / 先选线路」是一个**独立的步骤**（第 2 步）：它只做一次分流，用户点了
哪一个，第 3 步起就按哪条路线走（站台优先 / 线路优先）。这样做的好处是每一步的
「第 N 步」都名实相符，读屏用户也能在一页里听清两个入口的区别。

数据来源：城市 / 站台 / 线路 / 站点拓扑一律取自 :mod:`data_sync` 数据同步层
（本地缓存 + 定期与掌上公交同步），所以界面上看到的就是掌上公交的数据。

选项流（修改已创建的监控）沿用同一套步骤，但它不是一个「7 步向导」，而是从选项
菜单进入某一步：返回目标由 :attr:`_entry_step` / :attr:`_wizard_first` 决定。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import (
    XmBusApiError,
    city_base_name,
    cn_sorted,
    match_city,
    match_keyword,
    sorted_line_hits,
)
from .arrival_logic import normalize_poll_interval
from .const import (
    CONF_CITY,
    CONF_DIRECTION,
    CONF_LINE,
    CONF_POLL_INTERVAL,
    CONF_STATION,
    CONF_STATION_ORDER,
    CONF_SYNC_ENABLED,
    DEFAULT_CITY,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SYNC_ENABLED,
    DEFAULT_SYNC_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MAX_SYNC_INTERVAL,
    MIN_POLL_INTERVAL,
    MIN_SYNC_INTERVAL,
)
from .data_sync import async_get_sync, station_order_in

_LOGGER = logging.getLogger(__name__)

MODE_STATION_FIRST = "station_first"
MODE_LINE_FIRST = "line_first"

# 表单字段名（全部用中文做键 —— 翻译层一旦没刷新就会露出英文 key，写中文最保险）
# 括号里直接写明取值范围，读屏念出来就是范围提示，不依赖 data_description
CITY_KW_FIELD = "城市名关键词（中文、拼音或首字母）"
LINE_KW_FIELD = "线路关键词（线路号或名称）"
STATION_KW_FIELD = "站台名关键词（中文、拼音或首字母）"

POLL_INTERVAL_FIELD = "数据刷新间隔（秒，范围 5 到 120）"
SYNC_INTERVAL_FIELD = "自动同步间隔（小时，范围 1 到 168）"

# 向导总步数（用于「第 N 步 / 共 7 步」）
WIZARD_TOTAL = 7

# 候选上限：城市实测 563 个，全部列出；站台 / 线路超出时提示细化关键词
MAX_CITY_CHOICES = 700
MAX_CHOICES = 400

# 掌上公交的关键词检索单次最多给约 30 条。命中数达到这个值就说明**被截断**了，
# 必须在提示里说出来 —— 否则用户以为「就这么多」，不会想到再加一个字收窄。
SEARCH_LIMIT = 30

# 菜单里的固定动作 key（HA 要求 key 必须对应真实的 async_step_<key> 方法）
KEY_BACK = "back"          # 上一步
KEY_PICK = "pick_"         # 候选（后接下标），由 __getattr__ 动态生成


# ---------------------------------------------------------------------------
# 全部界面文字（中文写死在这里，不依赖翻译层）
# ---------------------------------------------------------------------------
_T: dict[str, str] = {
    # ---- 步骤名
    "step_city": "选择城市",
    "step_mode": "选择检索方式",
    "step_station": "选择站台",
    "step_line": "选择线路",
    "step_line_station": "选择站台",
    "step_settings": "选择到站参数",
    "step_sync": "数据同步",
    "step_confirm": "确认创建",
    "step_init": "选项菜单",
    # ---- 抬头与「上一步」（文案风格对齐 0.3.0：短句、emoji 前缀）
    # 抬头只报进度，**不写步骤名**：对话框标题已经是步骤名（translations 里的
    # config.step.*.title），两处都写读屏会把步骤名念两遍。
    "progress": "第 {n} 步 / 共 {total} 步",
    "back_to": "⬅ 返回上一步",
    "back_to_menu": "⬅ 返回选项菜单",
    "dir_up": "上行",
    "dir_down": "下行",
    "unset": "（尚未选择）",
    # ---- 第 2 步：检索方式（先选站台 / 先选线路）
    "h_mode": "先选站台然后选择停靠线路，或先选线路然后选择途经站台。",
    # ---- 第 1 步：城市
    # 欢迎语只出现在向导第 1 步（配置流）**说明区的第一行**：页面上第一个按钮就是
    # 「🔍 检索城市名」会显得突兀，前面有一行自我介绍，版式就和第 3 步一致了
    # （第 3 步第一行是「⬅ 返回上一步」，第二行才是「🔍 检索站台」）。
    "welcome": "欢迎使用 My Bus，这是一个实时公交监控集成。",
    "h_city": "请检索城市名，或通过 Home Assistant 地图定位城市，或显示城市列表。",
    "h_city_list": "与「{kw}」匹配的城市 {n} 个。",
    "h_city_notfound": "没有找到与「{kw}」匹配的城市。",
    "h_city_all": "全部 {n} 个服务城市，按拼音排序。",
    "h_city_empty": "城市列表暂时取不到（{err}）。",
    "h_locate_ok": "定位到「{city}」。",
    "h_locate_no_location": "没读到家庭位置，请到 设置 → 系统 → 通用 → 位置 填写后重试。",
    "h_locate_failed": "定位失败：{err}。",
    "h_locate_out_of_area": "家庭位置（{coord}）不在掌上公交的服务范围内。",
    "h_sync_repair": " 已自动修正 {n} 个监控的站序。",
    "h_sync_issue": " {n} 个监控与掌上公交不一致，请重新选择。",
    "h_sync_fail": "同步失败：{err}。",
    "h_city_kw": "输入城市名，支持中文、全拼或首字母；留空提交则取消查找。",
    # ---- 第 3 步：站台
    "h_station": "先检索站台，支持中文、拼音或首字母（例如 火车站）。",
    "h_station_found": "与「{kw}」匹配的站台 {n} 个。",
    "h_station_none": "没有找到与「{kw}」匹配的站台。",
    "h_station_kw": "输入站台名，支持中文、全拼或首字母；留空提交则返回。",
    # ---- 第 3 / 4 步：线路
    "h_line_at_station": "站台「{station}」{dir}侧的线路 {n} 条。",
    "h_line_at_station_empty": "站台「{station}」{dir}侧没有查到线路，可点「反向站台」试试。",
    "h_switch_dir": "「{station}」{old}侧没有线路，已切换到{new}侧。",
    "h_line": "先检索线路，例如 1。",
    "h_line_found": "与「{kw}」匹配的线路 {n} 条。",
    "h_line_none": "没有找到与「{kw}」匹配的线路（例如 1）。",
    "h_line_kw": "输入线路号或名称，例如 1；留空提交则返回。",
    # 检索命中数触顶时的补白：掌上公交的关键词检索单次最多约 30 条
    "h_truncated": "（关键词检索一次最多返回 {n} 条，可多加一个字收窄。）",
    # ---- 第 4 步：选择站台（线路优先时按途经顺序列出）
    # 提示只说「这条线路途经多少站」，不再问「点要在哪站提醒」——读屏用户下一步
    # 自然就是点一个站台，多问一句反而啰嗦。
    "h_line_stations": "线路「{line}」（{dir}）途经 {n} 站。",
    "h_line_stations_empty": "线路「{line}」（{dir}）没有查到站台。",
    # ---- 第 5 步：参数
    "h_settings": "选择刷新频率。",
    "h_settings_params": "输入数字。",
    "h_settings_saved": "已保存。",
    # ---- 第 6 步：数据同步
    # 这一步与选项菜单里的「🔄 数据同步」共用同一套实现（同一批按钮、同一批文案），
    # 只有说明区的开场白不同：向导里是「创建前可以先同步」，选项里是「缓存规模」。
    "h_sync_note": "城市 / 线路 / 站台等数据与掌上公交保持一致：默认每 {interval} 小时自动同步一次。",
    "h_sync_setup": "创建前可以先把数据同步到最新。",
    # ---- 第 7 步：确认
    "h_confirm": "请确认配置",
    "h_confirm_opt": "确认无误点「保存修改」，要改就点「⬅ 返回上一步」。",
    # 确认页分块（0.9.6）：「监控内容」与「参数」两块之间空一行，扫读更快
    "h_confirm_body": "── 监控内容 ──\n"
    "城市：{city}\n"
    "站台：{station}\n"
    "线路：{line}（{dir}）\n"
    "\n"
    "── 参数 ──\n"
    "刷新间隔：{interval} 秒\n"
    "自动同步：{sync}",
    "h_confirm_body_opt": "修改后将是：\n"
    "── 监控内容 ──\n"
    "城市：{city}\n"
    "站台：{station}\n"
    "线路：{line}（{dir}）\n"
    "\n"
    "── 参数 ──\n"
    "刷新间隔：{interval} 秒\n"
    "自动同步：{sync}",
    "h_not_on_line": "站台「{station}」不在线路「{line}」上，请返回重新选择。",
    "h_cannot_connect": "核对站台时连不上公交数据服务，请稍后重试。",
    # ---- 通用
    "h_api_failed": "查询失败：{err}。",
    # 候选按钮统一加类型 emoji 前缀（0.9.6）：🚏 站台 / 🚌 线路，一眼扫出候选类型；
    # 城市候选保持裸名称 —— 563 条太长，逐条多念一个 emoji 名反而拖慢读屏。
    "h_pick_station": "🚏 {name}",
    "h_pick_line": "🚌 {label}",
    "h_pick_city": "{name}",
    "act_city_locate": "📍 定位当前城市",
    "act_city_keyword": "🔍 检索城市名",
    "act_city_browse": "🏙 全部城市列表（共 {n} 个）",
    "act_city_keyword_again": "🔍 修改关键词（当前：{kw}）",
    "act_mode_station": "🚏 先选站台",
    "act_mode_line": "🚌 先选线路",
    "act_station_keyword": "🔍 检索站台",
    "act_station_keyword_again": "🔍 修改关键词（当前：{kw}）",
    "act_line_keyword": "🔍 检索线路",
    "act_line_keyword_again": "🔍 修改关键词（当前：{kw}）",
    "act_line_reverse": "🔄 反向站台",
    "act_settings_params": "⏱ 修改到站参数（当前：{params}）",
    "act_next_sync": "⏭ 下一步",
    "act_next_confirm": "⏭ 下一步",
    "act_finish": "✅ 完成",
    "act_finish_opt": "✅ 保存修改",
    "menu_finish": "✅ 完成",
    # ---- 选项菜单
    "opt_hint": "请选择要修改的项目。",
    "opt_city": "🌆 修改城市（当前：{city}）",
    "opt_line": "🔁 修改线路 / 站台（当前：{current}）",
    "opt_settings": "⏱ 修改到站参数（当前：{params}）",
    "opt_sync": "🔄 数据同步（{summary}）",
    "opt_synced": "已更新为：{city} {line} {station}。",
    # ---- 数据同步
    "act_sync_now": "🔄 立即同步（上次：{when}）",
    "act_sync_interval": "⏱ 修改同步间隔（当前：{interval}）",
    "act_sync_on": "🔄 启用自动同步",
    "act_sync_off": "🔄 关闭自动同步",
    "h_sync_menu": "{note}\n"
    "\n"
    "· 上次同步：{when}{duration}\n"
    "· 自动同步：{auto}\n"
    "· 本地缓存：城市 {cities} / 线路 {lines} / 站台 {stations}",
    "h_sync_first": "还没有同步过，请先点「立即同步」。",
    "h_sync_interval": "改完立刻生效；实时到站不受影响。",
    "h_sync_on": "已启用自动同步，{interval}。",
    "h_sync_off": "已关闭自动同步。",
    "h_sync_done": "同步完成：城市 {cities}、线路 {lines}、站台 {stations}。",
}


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _when_text(timestamp: Any) -> str:
    """把时间戳格式化为「09-07 16:30」；没有同步过则显示「尚未同步」."""
    try:
        return datetime.fromtimestamp(float(timestamp)).astimezone().strftime("%m-%d %H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return "尚未同步"


def _interval_text(seconds: Any) -> str:
    """同步间隔文案：小时（不足 1 小时用分钟）."""
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return "尚未设置"
    if value % 3600 == 0:
        return f"每 {value // 3600} 小时"
    return f"每 {round(value / 3600, 1)} 小时"


def _sync_summary(status: dict) -> str:
    """一行同步概览，用于菜单文字."""
    if status.get("failures") and status.get("last_error"):
        return f"上次同步有问题（{status.get('failures')} 次失败）"
    return (
        f"{status.get('cities', 0)} 城市 / {status.get('lines', 0)} 线路 / "
        f"{status.get('stations', 0)} 站台"
    )


def _summary_text(summary: dict, *, prefix: str = "同步完成：") -> str:
    """把同步摘要转成一句人话（含失败项与自动修正提示）."""
    text = (
        f"{prefix}城市 {summary.get('cities', 0)} 个，"
        f"线路 {summary.get('lines', 0)} 条，站台 {summary.get('stations', 0)} 个。"
    )
    errors = summary.get("errors") or []
    if errors:
        more = f"（共 {len(errors)} 项失败）" if len(errors) > 1 else ""
        text = (
            f"同步失败{more}，{errors[0]}"
            "。请检查 Home Assistant 能否访问 h5.mygolbs.com，稍后再点一次。"
        )
    if summary.get("repaired"):
        text += f" 已自动修正 {summary['repaired']} 个监控的站序。"
    if summary.get("issues"):
        text += f" 有 {len(summary['issues'])} 个监控与掌上公交不一致，请重新选择线路/站台。"
    return text


def _valid_coord(latitude: Any, longitude: Any) -> bool:
    """判断 HA 位置是否有效（HA 未设置位置时为 0,0，视为无效）."""
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return False
    if abs(lat) < 1e-4 and abs(lng) < 1e-4:
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0


def _line_label(hit) -> str:
    """线路标签: 615路（四林总站→丙洲东头尾站）."""
    if hit.from_stop and hit.to_stop:
        return f"{hit.line_name}（{hit.from_stop}→{hit.to_stop}）"
    fallback = "上行" if hit.direction == "1" else "下行"
    return f"{hit.line_name}（{fallback}）"


def _dir_text(hit) -> str:
    """方向文字: 四林总站→丙洲东头尾站（无起终点时退化为 上行/下行）."""
    if hit.from_stop and hit.to_stop:
        return f"{hit.from_stop}→{hit.to_stop}"
    return "上行" if hit.direction == "1" else "下行"


def _settings_schema(default_interval: Any) -> vol.Schema:
    """刷新间隔（数字输入框，v0.9.1 起是到站参数页的唯一字段）.

    默认值先过一遍归一化：旧条目或手工改过 .storage 可能留下越界值，
    这里统一夹到合法范围。
    """
    iv_default = normalize_poll_interval(default_interval)
    return vol.Schema(
        {
            vol.Required(
                POLL_INTERVAL_FIELD, default=iv_default
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_POLL_INTERVAL,
                    max=MAX_POLL_INTERVAL,
                    step=1,
                    unit_of_measurement="秒",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _sync_schema(default_interval: Any) -> vol.Schema:
    """自动同步间隔（小时），数字输入框."""
    try:
        hours = max(1, round(int(default_interval) / 3600))
    except (TypeError, ValueError):
        hours = round(DEFAULT_SYNC_INTERVAL / 3600)
    return vol.Schema(
        {
            vol.Required(SYNC_INTERVAL_FIELD, default=hours): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_SYNC_INTERVAL // 3600,
                    max=MAX_SYNC_INTERVAL // 3600,
                    step=1,
                    unit_of_measurement="小时",
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        }
    )


class _FlowHelpers:
    """表单 / 菜单的跨版本兼容封装（配置流与选项流共用）."""

    def _show(self, **kwargs) -> FlowResult:
        """async_show_form 兼容旧版 HA（不支持 last_step 参数时降级）."""
        try:
            return self.async_show_form(**kwargs)
        except TypeError:
            kwargs.pop("last_step", None)
            return self.async_show_form(**kwargs)

    def _menu(
        self,
        menu_options: dict[str, str],
        *,
        step_id: str,
        text: str = "",
    ) -> FlowResult:
        """async_show_menu 兼容封装。

        ``menu_options`` 传 dict 时，**value 就是按钮上显示的文字**，
        不经过翻译层 —— 这是「保证中文、不出现英文按钮」的关键。
        """
        kwargs: dict[str, Any] = {"step_id": step_id, "menu_options": menu_options}
        if text:
            kwargs["description_placeholders"] = {"hint": text}
        try:
            return self.async_show_menu(**kwargs)
        except TypeError:
            kwargs.pop("description_placeholders", None)
            return self.async_show_menu(**kwargs)


class _WizardMixin(_FlowHelpers):
    """按钮式向导的公共实现（配置流、选项流共用）."""

    # 向导的「入口」与「起点」——决定「上一步」往哪走。
    # 配置流: _entry_step=None（第一步没有上一步）、_wizard_first="city"。
    # 选项流: _entry_step="init"（回到选项菜单），_wizard_first 视进入点而定。
    _entry_step: str | None = None
    _wizard_first: str = "city"

    # ------------------------------------------------------------------ 状态
    def _init_wizard(self) -> None:
        # 当前正在渲染的步骤（菜单回调时用来定位）
        self._cur_step: str = "city"

        # 走过的步骤（新的向导从零算起）
        self._trail: list[str] = []

        # 城市（第 1 步）
        self._city: str = ""
        self._city_kw: str = ""
        self._city_options: list[str] = []

        # 检索方式（第 2 步）
        self._search_mode: str = MODE_STATION_FIRST

        # 站台 / 线路
        self._station: str = ""
        self._station_kw: str = ""
        self._station_options: list[str] = []
        self._station_map: dict[str, str] = {}
        self._line: str = ""
        self._line_kw: str = ""
        self._line_options: list[str] = []
        self._line_map: dict[str, dict[str, str]] = {}
        self._line_dir_label: str = ""
        # 候选项对应的「(城市, 站台/线路, 方向)」——任何一项变了就重新载入
        self._lines_key: tuple[str, str, str] | None = None
        self._stops_key: tuple[str, str, str] | None = None

        # 方向：1=上行 2=下行
        self._direction: str = "1"

        # 到站参数（v0.9.1 起只剩刷新间隔）
        self._poll_interval: int = DEFAULT_POLL_INTERVAL

        # 本步提示（错误 / 通知），渲染后清空
        self._hint: str = ""

        # 同上，但用于「跨一步带回来的通知」：数据同步的几个动作（立即同步 / 改间隔 /
        # 开关）执行完都要回到同步页并说明结果，这条通知在配置流与选项流里共用。
        self._notice: str = ""

        # 用户实际走过的步骤（菜单步骤才入栈）。「上一步」优先按它回退，
        # 这样选项流里「跳过参数页」之类分支也能退回真正的来路。
        self._trail: list[str] = []

    # --------------------------------------------------------- 动态候选按钮
    def __getattr__(self, name: str):
        """按需生成 ``async_step_pick_<下标>`` —— 菜单里的候选按钮。

        菜单项 key 必须是真实存在的 ``async_step_<key>`` 方法，而候选数量是
        动态的，所以在这里用一个闭包按需生成：点击第 i 个候选时，回调到
        :meth:`_async_pick`，由它根据 :attr:`_cur_step` 判断这是哪一步的候选。
        """
        prefix = "async_step_" + KEY_PICK
        if name.startswith(prefix) and name[len(prefix):].isdigit():
            index = int(name[len(prefix):])

            async def _step(user_input=None):
                return await self._async_pick(index)

            return _step
        raise AttributeError(name)

    # ------------------------------------------------------------------ 文案
    def _t(self, key: str, **kw) -> str:
        text = _T[key]
        return text.format(**kw) if kw else text

    def _tk(self, key: str) -> str:
        """选项流里用带 ``_opt`` 后缀的变体文案（没有变体就退回原文）."""
        if not self._is_wizard():
            alt = key + "_opt"
            if alt in _T:
                return _T[alt]
        return _T[key]

    def _step_name(self, step: str) -> str:
        """步骤的中文名（步骤 id → ``step_*`` 文案）.

        抬头（:meth:`_header`）**不再**用它 —— 步骤名由对话框标题显示
        （translations 里的 ``config.step.*.title``），抬头只报「第 N 步」。
        这里保留这份映射，供「返回上一步（目标步骤名）」这类需要说出
        目标页面名字的地方使用。
        """
        key = {
            "city": "step_city",
            "city_browse": "step_city",
            "city_keyword": "step_city",
            "mode": "step_mode",
            "station": "step_station",
            "station_keyword": "step_station",
            "line": "step_line",
            "line_keyword": "step_line",
            "line_station": "step_line_station",
            "settings": "step_settings",
            "settings_params": "step_settings",
            "sync": "step_sync",
            "confirm": "step_confirm",
        }.get(step, "step_init")
        return self._t(key)

    def _dir_label(self) -> str:
        return self._t("dir_up" if self._direction == "1" else "dir_down")

    def _params_text(self) -> str:
        """到站参数一句话摘要（按钮与提示共用）."""
        return f"每 {self._poll_interval} 秒刷新"

    def _found_text(self, key: str, *, kw: str, n: int) -> str:
        """检索命中提示；命中数触顶时补一句「接口最多返回 N 条」.

        掌上公交的关键词检索单次最多给约 30 条（站台 / 线路都是），达到这个数
        就说明结果**被截断**了。不提示的话用户会以为「就这么几条」，不会想到
        再加一个字收窄关键词 —— 所以命中数 ≥ :data:`SEARCH_LIMIT` 时如实说明。
        """
        text = self._t(key, kw=kw, n=n)
        if n >= SEARCH_LIMIT:
            text += self._t("h_truncated", n=SEARCH_LIMIT)
        return text

    # --------------------------------------------------- 步骤序号与上一步链
    def _step_index(self, step: str) -> int:
        """这一步在 7 步向导里的序号（随「先选站台 / 先选线路」而变）.

        「选择线路」的序号跟着模式走：线路优先时它是第 3 步（第 4 步是「选择途经
        站台」），站台优先时它是第 4 步（第 3 步是「选择站台」）。

        ⚠️ **输入子页必须与父页同号**：``line_keyword`` 要跟 ``line`` 一起算，
        否则用户在「选择线路」页点「🔍 检索线路」，抬头会从「第 4 步」掉回
        「第 3 步」，读起来像是同一步在 3 和 4 之间来回跳。
        """
        line_first = self._search_mode == MODE_LINE_FIRST
        if step in ("city", "city_browse", "city_keyword"):
            return 1
        if step == "mode":
            return 2
        if step in ("station", "station_keyword"):
            return 3
        if step in ("line", "line_keyword"):
            return 3 if line_first else 4
        if step == "line_station":
            # 只在「线路优先」这条路里出现（站台优先时第 4 步是「选择线路」）
            return 4
        if step in ("settings", "settings_params"):
            return 5
        if step in ("sync", "sync_interval"):
            # 子页 ``sync_interval``（改自动同步间隔的数字表单）与父页 ``sync`` 同号
            return 6
        return WIZARD_TOTAL

    def _prev_step(self, step: str) -> str | None:
        """当前步骤的「上一步」目标（None = 没有上一步）.

        优先用 :attr:`_trail` 里的真实足迹：用户可能是从「选择线路 / 站台」直接跳到
        「确认」的（选项流里改线路就可以跳过参数页），这时按静态链路会把他送回
        一个从没见过的步骤。没有足迹（例如测试直接调用）时退回静态链路。
        """
        if step in self._trail:
            index = len(self._trail) - 1 - self._trail[::-1].index(step)
            if index > 0:
                return self._trail[index - 1]
        if step == self._wizard_first:
            # 向导的第 1 步是流程起点：**它没有「上一步」**。这一页说明区的第一行
            # 放的是欢迎语（见 :meth:`_compose`），由它占据「上一页」的位置，
            # 于是「🔍 检索城市名」在整页里的次序与第 3 步的「🔍 检索站台」
            # 完全一致（都是说明区之后的下一个元素）。
            # 选项流从菜单进同一页时返回 ``_entry_step``（选项菜单），它有返回按钮。
            return self._entry_step
        line_first = self._search_mode == MODE_LINE_FIRST
        chain = {
            "city_browse": "city",
            "city_keyword": "city",
            "mode": "city",
            "station": "mode",
            "station_keyword": "station",
            "line": "mode" if line_first else "station",
            "line_keyword": "mode" if line_first else "station",
            "line_station": "line",
            "settings": "line_station" if line_first else "line",
            "settings_params": "settings",
            "sync": "settings",
            "sync_interval": "sync",
            "confirm": "sync",
        }
        return chain.get(step, self._entry_step)

    def _track(self, step: str) -> None:
        """记下用户正在看的这一步（只有菜单步骤会调用）.

        回到入口菜单（``_entry_step``）等于重新开一轮，足迹清空重记。
        """
        if self._entry_step is not None and step == self._entry_step:
            self._trail = [step]
            return
        if not self._trail or self._trail[-1] != step:
            self._trail.append(step)

    def _is_wizard(self) -> bool:
        """配置流里是完整的 7 步向导；选项流是从菜单进来的单点修改。"""
        return self._entry_step is None

    # ------------------------------------------------------------ 抬头与提示
    def _header(self, step: str) -> str:
        """统一抬头：只报进度（第 N 步 / 共 7 步），不再罗列已选内容.

        抬头里**不写步骤名**：对话框标题已经写着步骤名（见 translations 里的
        ``config.step.*.title``），两处都写的话读屏会把步骤名念两遍
        （「选择站台 …… 第 3 步 / 共 7 步 · 选择站台」）。
        所以抬头只留「第 N 步 / 共 7 步」，步骤名交给标题。
        """
        if self._is_wizard():
            return self._t(
                "progress", n=self._step_index(step), total=WIZARD_TOTAL
            )
        return ""

    def _compose(self, step: str, hint: str = "") -> str:
        """把欢迎语 / 抬头 / 本步提示拼成一段文字（放进菜单/表单的说明区）.

        第 1 步（向导起点）的说明区第一行是**欢迎语** —— 这一页没有「⬅ 返回上一步」
        可放（它就是起点），由欢迎语占住这个位置之后，读屏听到的次序就与第 3 步
        完全一致：都是「说明区说一句 → 🔍 检索按钮 → 候选 → 其它动作」。
        欢迎语只在**向导**的第 1 步出现：选项流里的同一页是单点修改，不需要自我介绍。
        """
        text = hint or self._hint
        self._hint = ""
        parts: list[str] = []
        if self._is_wizard() and step == "city":
            parts.append(self._t("welcome"))
        header = self._header(step)
        if header:
            parts.append(header)
        if text:
            parts.append(text)
        return "\n\n".join(parts)

    # ------------------------------------------------------------ 菜单渲染
    def _back_label(self, step: str) -> str:
        """「返回上一步」按钮文字（只有选项流退回选项菜单时才换说法）."""
        return self._t("back_to_menu" if self._prev_step(step) == "init" else "back_to")

    def _menu_step(self, step: str, items: dict[str, str], *, hint: str = "") -> FlowResult:
        """统一的菜单渲染：动作/候选按钮 + 自动追加在最前面的「⬅ 返回上一步」.

        「返回」放在**第一位**：读屏用户是按 Tab 顺序逐个听按钮的，「全部城市
        列表」这类页面有几百个候选项，若把返回排在最后，走错一步就得听完整个
        列表才能退回去。导航按钮在前也和浏览器「返回」的直觉一致。

        第 1 步是向导起点（:meth:`_prev_step` 返回 ``None``），这一页**没有**返回
        按钮，由说明区第一行的欢迎语占住那个位置（这也让每一页的「🔍 检索…」
        都落在同一个次序上）。
        """
        self._cur_step = step
        self._track(step)
        menu: dict[str, str] = {}
        prev = self._prev_step(step)
        if prev is not None and prev != step:
            menu[KEY_BACK] = self._back_label(step)
        menu.update(items)
        return self._menu(menu, step_id=step, text=self._compose(step, hint))

    def _form_step(self, step: str, schema: vol.Schema, *, hint: str = "") -> FlowResult:
        """统一的表单渲染（只有需要键盘输入的两处会用到）."""
        self._cur_step = step
        return self._show(
            step_id=step,
            data_schema=schema,
            description_placeholders={"hint": self._compose(step, hint)},
        )

    async def async_step_back(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """「上一步」按钮：回到本步的上一步（由 _cur_step 决定目标）."""
        step = getattr(self, "_cur_step", "city")
        return await self._async_go_prev(step)

    async def _async_go_prev(self, step: str) -> FlowResult:
        target = self._prev_step(step)
        # 把足迹裁回目标那一步，保证连点「上一步」能一级一级退回去
        if self._trail and self._trail[-1] == step:
            self._trail.pop()
        if target is None:
            self._trail = []
        else:
            while self._trail and self._trail[-1] != target:
                self._trail.pop()
        if not target:
            return await self.async_step_city()
        handler = getattr(self, f"async_step_{target}", None)
        if handler is None:
            return await self.async_step_init() if self._entry_step == "init" else await self.async_step_city()
        return await handler()

    # ------------------------------------------------------------------ 工具
    def _client_for_city(self, city: str):
        """按城市取（并缓存）接口客户端：与数据同步层 / 服务共用同一实例池."""
        from .data_sync import client_for_city

        return client_for_city(self.hass, city)

    async def _async_sync(self):
        """取域级数据同步对象（城市 / 线路 / 站台等结构数据的本地缓存与同步）."""
        return await async_get_sync(self.hass)

    async def _async_get_cities(self, *, force: bool = False) -> list[str]:
        """掌上公交全部服务城市（取自数据同步层，必要时强制刷新）."""
        return await (await self._async_sync()).async_cities(force=force)

    def _ha_location(self) -> tuple[float | None, float | None]:
        """取 Home Assistant 的位置（设置 → 系统 → 通用 → 位置）."""
        lat = lng = None
        try:
            lat = self.hass.config.latitude
            lng = self.hass.config.longitude
        except Exception:  # noqa: BLE001  桩环境可能没有 config
            pass
        if _valid_coord(lat, lng):
            return float(lat), float(lng)
        try:
            state = self.hass.states.get("zone.home")
            attrs = getattr(state, "attributes", None) or {}
            lat = attrs.get("latitude")
            lng = attrs.get("longitude")
        except Exception:  # noqa: BLE001
            pass
        if _valid_coord(lat, lng):
            return float(lat), float(lng)
        return None, None

    # ==================================================== 第 1 步：选择城市
    async def async_step_city(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """第 1 步：选择城市（按钮：检索城市名 / 定位当前城市 / 全部城市列表）."""
        sync = await self._async_sync()
        cities: list[str] = []
        api_error = ""
        try:
            cities = await sync.async_cities()
        except XmBusApiError as err:
            _LOGGER.warning("获取城市列表失败: %s", err)
            api_error = str(err)
        except Exception as err:  # noqa: BLE001  兜底: 避免前端出现 Unknown error
            _LOGGER.exception("获取城市列表出现未预期错误")
            api_error = str(err) or "未知错误"

        if not self._city_kw:
            self._city_options = list(cities[:MAX_CITY_CHOICES])

        # 本页按钮顺序（版式与其它页一致：说明区之后紧跟检索按钮）：
        #   ① 🔍 检索按钮**排在动作组第一位**——第 1 步的「检索城市名」、第 3 步的
        #      「检索站台」、线路优先第 3 步的「检索线路」在整页里的次序完全相同
        #      （说明区的最后一段之后的下一个元素），读屏用户换一步不用重新找按钮；
        #   ② 检索出的候选**紧跟检索按钮**（与第 3 步一样，结果就在按钮正下方）；
        #   ③ 之后才是另外两个「找城市」按钮（定位 / 全部列表）。
        # 本页**没有**「⬅ 返回上一步」——第 1 步是流程起点，没有上一步可回；
        # 这一页说明区的第一行是欢迎语，由它占据那个位置（见 _compose）。
        # v0.8.9：「同步最新数据」按钮已从本页**移除** —— 同步现在是向导第 6 步
        # （「数据同步」），第 1 步只负责选城市，动作更纯粹。
        items: dict[str, str] = {
            "city_keyword": self._t(
                "act_city_keyword_again" if self._city_kw else "act_city_keyword",
                kw=self._city_kw,
            ),
        }
        if self._city_kw:
            for index, name in enumerate(self._city_options):
                items[f"{KEY_PICK}{index}"] = self._t("h_pick_city", name=name)
        items["city_locate"] = self._t("act_city_locate")
        if cities:
            items["city_browse"] = self._t("act_city_browse", n=len(cities))

        hint = self._hint
        if not hint:
            if api_error:
                hint = self._t("h_city_empty", err=api_error)
            elif self._city_kw and not self._city_options:
                hint = self._t("h_city_notfound", kw=self._city_kw)
            elif self._city_kw:
                hint = self._t("h_city_list", kw=self._city_kw, n=len(self._city_options))
            else:
                hint = self._t("h_city")
        return self._menu_step("city", items, hint=hint)

    async def async_step_city_browse(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """第 1 步的子页：把全部服务城市逐个列成按钮."""
        try:
            cities = await self._async_get_cities()
        except Exception:  # noqa: BLE001
            cities = list(self._city_options)
        self._city_options = list(cities[:MAX_CITY_CHOICES])
        items = {
            f"{KEY_PICK}{index}": self._t("h_pick_city", name=name)
            for index, name in enumerate(self._city_options)
        }
        hint = self._hint or self._t("h_city_all", n=len(self._city_options))
        return self._menu_step("city_browse", items, hint=hint)

    async def async_step_city_keyword(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """第 1 步的子页：输入城市名（表单里唯一需要打字的地方之一）."""
        if user_input is not None:
            raw = str(user_input.get(CITY_KW_FIELD) or "").strip()
            if not raw:
                self._city_kw = ""
                self._hint = ""
                return await self.async_step_city()
            try:
                cities = await self._async_get_cities()
            except Exception as err:  # noqa: BLE001
                self._hint = self._t("h_api_failed", err=err)
                return await self.async_step_city()
            resolved = _resolve_city(cities, raw)
            if resolved is None:
                matched = [c for c in cities if match_keyword(c, raw)]
                if len(matched) == 1:
                    resolved = matched[0]
                elif matched:
                    # 多个模糊命中 → 回到城市页，把候选列出来让用户挑
                    self._city_kw = raw
                    self._city_options = matched[:MAX_CITY_CHOICES]
                    self._hint = self._t(
                        "h_city_list", kw=raw, n=len(self._city_options)
                    )
                    return await self.async_step_city()
                else:
                    self._city_kw = ""
                    self._city_options = list(cities[:MAX_CITY_CHOICES])
                    self._hint = self._t("h_city_notfound", kw=raw)
                    return await self.async_step_city()
            return await self._async_city_chosen(resolved)

        schema = vol.Schema(
            {vol.Optional(CITY_KW_FIELD, default=""): selector.TextSelector()}
        )
        return self._form_step(
            "city_keyword", schema, hint=self._hint or self._t("h_city_kw")
        )

    async def async_step_city_locate(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """第 1 步的按钮：用 Home Assistant 的位置反查城市（CMD108）."""
        latitude, longitude = self._ha_location()
        if latitude is None:
            self._hint = self._t("h_locate_no_location")
            return await self.async_step_city()
        try:
            raw = await self._client_for_city(DEFAULT_CITY).locate_city(latitude, longitude)
        except XmBusApiError as err:
            _LOGGER.warning("定位城市失败: %s", err)
            self._hint = self._t("h_locate_failed", err=err)
            return await self.async_step_city()
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("定位城市出现未预期错误")
            self._hint = self._t("h_locate_failed", err=err)
            return await self.async_step_city()
        if not raw:
            coord = f"{latitude:.4f}, {longitude:.4f}"
            self._hint = self._t("h_locate_out_of_area", coord=coord)
            return await self.async_step_city()
        try:
            cities = await self._async_get_cities()
        except Exception:  # noqa: BLE001
            cities = []
        matched = match_city(cities, raw) if cities else None
        self._hint = self._t("h_locate_ok", city=matched or raw)
        return await self._async_city_chosen(matched or raw)

    async def _async_city_chosen(self, city: str) -> FlowResult:
        """城市已确定：换了城市才清空后续选择，然后进入第 2 步「选择检索方式」."""
        new_city = (city or "").strip() or DEFAULT_CITY
        if new_city != self._city:
            self._reset_after_city()
        self._city = new_city
        self._city_kw = ""
        return await self.async_step_mode()

    def _reset_after_city(self) -> None:
        """城市变了 → 站台 / 线路 / 方向全部作废."""
        self._station = ""
        self._line = ""
        self._direction = "1"
        self._line_dir_label = ""
        self._station_kw = ""
        self._station_options = []
        self._station_map = {}
        self._line_kw = ""
        self._line_options = []
        self._line_map = {}
        self._lines_key = None
        self._stops_key = None

    def _reset_after_station(self) -> None:
        """站台变了 → 线路候选作废（方向回到上行）."""
        self._line = ""
        self._direction = "1"
        self._line_dir_label = ""
        self._line_options = []
        self._line_map = {}
        self._lines_key = None

    def _reset_after_line(self) -> None:
        """线路 / 方向变了 → 途经站台候选作废."""
        self._station_options = []
        self._station_map = {}
        self._stops_key = None

    # ================================================ 第 2 步：选择检索方式
    async def async_step_mode(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """第 2 步：先选站台还是先选线路（两个按钮，没有开关）."""
        items = {
            "mode_station": self._t("act_mode_station"),
            "mode_line": self._t("act_mode_line"),
        }
        return self._menu_step("mode", items, hint=self._hint or self._t("h_mode"))

    async def async_step_mode_station(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """第 3 步走「先选站台」."""
        return await self._async_set_mode(MODE_STATION_FIRST)

    async def async_step_mode_line(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """第 3 步走「先选线路」."""
        return await self._async_set_mode(MODE_LINE_FIRST)

    async def _async_set_mode(self, mode: str) -> FlowResult:
        """切换检索路线：先前选好的站台 / 线路 / 方向全部作废，然后开出第 3 步."""
        if mode != self._search_mode:
            self._search_mode = mode
            self._station = ""
            self._line = ""
            self._direction = "1"
            self._line_dir_label = ""
            self._station_options = []
            self._station_map = {}
            self._line_options = []
            self._line_map = {}
            self._lines_key = None
            self._stops_key = None
        if mode == MODE_LINE_FIRST:
            return await self.async_step_line()
        return await self.async_step_station()

    # ==================================================== 第 3 步：选择站台
    async def async_step_station(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """第 3 步（站台优先）：从候选里点一个站台，或先去输入关键词."""
        items: dict[str, str] = {
            "station_keyword": self._t(
                "act_station_keyword_again" if self._station_options else "act_station_keyword",
                kw=self._station_kw,
            )
        }
        for index, name in enumerate(self._station_options):
            items[f"{KEY_PICK}{index}"] = self._t("h_pick_station", name=name)
        hint = self._hint
        if not hint:
            hint = (
                self._found_text(
                    "h_station_found", kw=self._station_kw, n=len(self._station_options)
                )
                if self._station_options
                else self._t("h_station")
            )
        return self._menu_step("station", items, hint=hint)

    async def async_step_station_keyword(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """第 3 步的子页：输入站台名检索（表单）."""
        if user_input is not None:
            raw = str(user_input.get(STATION_KW_FIELD) or "").strip()
            if not raw:
                self._hint = ""
                return await self.async_step_station()
            sync = await self._async_sync()
            city = self._city or DEFAULT_CITY
            try:
                hits = await sync.async_search_stations(city, raw)
            except XmBusApiError as err:
                _LOGGER.warning("站台检索失败: %s", err)
                self._hint = self._t("h_api_failed", err=err)
                return await self.async_step_station()
            except Exception as err:  # noqa: BLE001  兜底: 避免前端出现 Unknown error
                _LOGGER.exception("站台检索出现未预期错误")
                self._hint = self._t("h_api_failed", err=err)
                return await self.async_step_station()
            names = cn_sorted({h.name for h in hits if h.name})
            self._station_kw = raw
            self._station_options = names[:MAX_CHOICES]
            if not names:
                self._hint = self._t("h_station_none", kw=raw)
                return await self.async_step_station()
            if len(names) == 1:
                # 唯一结果直接采用，省一次点击
                self._station = names[0]
                self._reset_after_station()
                return await self.async_step_line()
            self._hint = self._found_text("h_station_found", kw=raw, n=len(names))
            return await self.async_step_station()

        schema = vol.Schema(
            {vol.Optional(STATION_KW_FIELD, default=""): selector.TextSelector()}
        )
        return self._form_step(
            "station_keyword", schema, hint=self._hint or self._t("h_station_kw")
        )

    # ==================================================== 第 3 / 4 步：线路
    async def async_step_line(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """线路优先：第 3 步「选择线路」；站台优先：第 4 步「选择站台里的线路」."""
        if self._search_mode == MODE_LINE_FIRST:
            items: dict[str, str] = {
                "line_keyword": self._t(
                    "act_line_keyword_again" if self._line_options else "act_line_keyword",
                    kw=self._line_kw,
                ),
            }
            for index, label in enumerate(self._line_options):
                items[f"{KEY_PICK}{index}"] = self._t("h_pick_line", label=label)
            hint = self._hint
            if not hint:
                hint = (
                    self._found_text(
                        "h_line_found", kw=self._line_kw, n=len(self._line_options)
                    )
                    if self._line_options
                    else self._t("h_line")
                )
            return self._menu_step("line", items, hint=hint)

        sync = await self._async_sync()
        city = self._city or DEFAULT_CITY
        key = (city, self._station, self._direction)
        if self._lines_key != key:
            await self._async_load_station_lines(sync, city)
            self._lines_key = (city, self._station, self._direction)

        items = {"line_reverse": self._t("act_line_reverse", dir=self._dir_label())}
        for index, label in enumerate(self._line_options):
            items[f"{KEY_PICK}{index}"] = self._t("h_pick_line", label=label)
        hint = self._hint
        if not hint:
            if self._line_options:
                hint = self._t(
                    "h_line_at_station",
                    station=self._station,
                    dir=self._dir_label(),
                    n=len(self._line_options),
                )
            else:
                hint = self._t(
                    "h_line_at_station_empty",
                    station=self._station,
                    dir=self._dir_label(),
                )
        return self._menu_step("line", items, hint=hint)

    async def async_step_line_keyword(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """先选线路时的子页：输入线路号检索（表单）."""
        if user_input is not None:
            raw = str(user_input.get(LINE_KW_FIELD) or "").strip()
            if not raw:
                self._hint = ""
                return await self.async_step_line()
            sync = await self._async_sync()
            city = self._city or DEFAULT_CITY
            try:
                hits = await sync.async_search_lines(city, raw)
            except XmBusApiError as err:
                _LOGGER.warning("线路检索失败: %s", err)
                self._hint = self._t("h_api_failed", err=err)
                return await self.async_step_line()
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("线路检索出现未预期错误")
                self._hint = self._t("h_api_failed", err=err)
                return await self.async_step_line()
            options, mapping = _build_line_choices(hits)
            self._line_kw = raw
            self._line_options = options[:MAX_CHOICES]
            self._line_map = mapping
            if not options:
                self._hint = self._t("h_line_none", kw=raw)
                return await self.async_step_line()
            if len(options) == 1:
                return await self._async_choose_line(options[0])
            self._hint = self._found_text("h_line_found", kw=raw, n=len(options))
            return await self.async_step_line()

        schema = vol.Schema(
            {vol.Optional(LINE_KW_FIELD, default=""): selector.TextSelector()}
        )
        return self._form_step(
            "line_keyword", schema, hint=self._hint or self._t("h_line_kw")
        )

    async def async_step_line_reverse(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """按钮「换到马路对面站台」：切换上下行后重新载入线路."""
        self._direction = "2" if self._direction == "1" else "1"
        self._line = ""
        self._line_dir_label = ""
        self._line_options = []
        self._line_map = {}
        self._lines_key = None
        self._hint = ""
        return await self.async_step_line()

    async def _async_choose_line(self, label: str) -> FlowResult:
        payload = self._line_map.get(label)
        if payload is None:
            self._hint = self._t("h_line_none", kw=label)
            return await self.async_step_line()
        self._line = payload["line"]
        self._direction = payload["direction"]
        self._line_dir_label = payload.get("dir_text", "")
        self._reset_after_line()
        if self._search_mode == MODE_LINE_FIRST:
            return await self.async_step_line_station()
        return await self._async_selection_done()

    async def _async_load_station_lines(self, sync, city: str) -> None:
        """载入当前站台两个方向的线路；选中的方向没有线路时自动换向一次."""
        try:
            hits = await sync.async_station_lines(city, self._station)
        except XmBusApiError as err:
            _LOGGER.warning("站台线路查询失败: %s", err)
            self._hint = self._t("h_api_failed", err=err)
            self._line_options = []
            self._line_map = {}
            return
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("站台线路查询出现未预期错误")
            self._hint = self._t("h_api_failed", err=err)
            self._line_options = []
            self._line_map = {}
            return

        dirs = {h.direction for h in hits}
        other = "2" if self._direction == "1" else "1"
        if self._direction not in dirs and other in dirs:
            old = self._dir_label()
            self._direction = other
            self._hint = self._t(
                "h_switch_dir",
                station=self._station,
                old=old,
                new=self._t("dir_up" if other == "1" else "dir_down"),
            )

        subset = [h for h in hits if h.direction == self._direction]
        options: list[str] = []
        mapping: dict[str, dict[str, str]] = {}
        for hit in sorted_line_hits(subset):
            label = _line_label(hit)
            if label in mapping:
                continue
            options.append(label)
            mapping[label] = {
                "line": hit.line_name,
                "direction": hit.direction,
                "label": label,
                "dir_text": _dir_text(hit),
            }
        self._line_options = options[:MAX_CHOICES]
        self._line_map = mapping

    # ================================================ 第 4 步：选择途经站台
    async def async_step_line_station(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """第 4 步（线路优先）：按途经顺序把站台列成按钮."""
        sync = await self._async_sync()
        city = self._city or DEFAULT_CITY
        key = (city, self._line, self._direction)
        if self._stops_key != key:
            try:
                stations = await sync.async_line_stations(city, self._line, self._direction)
            except XmBusApiError as err:
                _LOGGER.warning("站点查询失败: %s", err)
                self._hint = self._t("h_api_failed", err=err)
                stations = []
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("站点查询出现未预期错误")
                self._hint = self._t("h_api_failed", err=err)
                stations = []
            options: list[str] = []
            mapping: dict[str, str] = {}
            seen: set[str] = set()
            order = 0
            for item in stations:
                name = (item.get("stationName") or "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                order += 1
                label = f"{order}. {name}"
                options.append(label)
                mapping[label] = name
            self._station_options = options[:MAX_CHOICES]
            self._station_map = mapping
            self._stops_key = key

        items = {
            f"{KEY_PICK}{index}": self._t("h_pick_station", name=label)
            for index, label in enumerate(self._station_options)
        }
        hint = self._hint
        if not hint:
            # 方向优先用真实起终点（「四林总站→丙洲东头尾站」），比「上行 / 下行」
            # 信息量大；只有在起终点都取不到时才退化成 上行 / 下行。
            direction = self._line_dir_label or self._dir_label()
            if self._station_options:
                hint = self._t(
                    "h_line_stations",
                    line=self._line,
                    dir=direction,
                    n=len(self._station_options),
                )
            else:
                hint = self._t("h_line_stations_empty", line=self._line, dir=direction)
        return self._menu_step("line_station", items, hint=hint)

    # ==================================================== 第 5 步：到站参数
    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """第 5 步：参数页（当前值写在按钮上；要改就点按钮，不改直接下一步）."""
        items = {
            "settings_params": self._t("act_settings_params", params=self._params_text()),
            "to_sync": self._t("act_next_sync"),
        }
        # 说明区不再重复按钮上已经写着的「当前参数」，避免读屏连听两遍
        hint = self._hint or self._t("h_settings")
        return self._menu_step("settings", items, hint=hint)

    async def async_step_settings_params(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """第 5 步的子页：刷新间隔（数字输入框，表单）."""
        if user_input is not None:
            # 值统一夹取到合法范围：前端 NumberSelector 会拦越界输入，
            # 但表单之外（旧条目、手工改 .storage）仍可能塞进 0 / 9999。
            self._poll_interval = normalize_poll_interval(user_input.get(POLL_INTERVAL_FIELD))
            self._hint = self._t("h_settings_saved")
            return await self._async_settings_saved()

        schema = _settings_schema(self._poll_interval)
        return self._form_step(
            "settings_params",
            schema,
            hint=self._hint or self._t("h_settings_params"),
        )

    async def async_step_to_sync(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """按钮「⏭ 下一步：数据同步」（第 5 步 → 第 6 步）."""
        return await self.async_step_sync()

    async def async_step_to_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """按钮「⏭ 下一步：确认创建」（第 6 步 → 第 7 步）."""
        return await self.async_step_confirm()

    # ==================================================== 第 7 步：确认创建
    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """第 7 步：确认页（按钮「完成创建」+「上一步」）.

        v0.9.5 起把数据同步设置也列进确认清单：自动同步是**全局**数据同步层的
        状态（所有监控共用），所以只作展示、格式为「每 N 小时」或「已关闭」；
        拿不到同步层（极少数直连场景）时如实显示「未启用」。
        """
        sync_text = "未启用"
        get_sync = getattr(self, "_async_sync", None)
        if get_sync is not None:
            try:
                sync = await get_sync()
            except Exception:  # noqa: BLE001 - 确认页不让同步层故障挡路
                sync = None
            if sync is not None:
                status = sync.status()
                sync_text = (
                    _interval_text(status.get("interval"))
                    if status.get("enabled")
                    else "已关闭"
                )
        body = self._t(
            "h_confirm_body_opt" if not self._is_wizard() else "h_confirm_body",
            city=self._city or self._t("unset"),
            station=self._station,
            line=self._line,
            dir=self._line_dir_label or self._dir_label(),
            interval=self._poll_interval,
            sync=sync_text,
        )
        hint = self._hint or (self._tk("h_confirm") + "\n\n" + body)
        return self._menu_step("confirm", {"finish": self._tk("act_finish")}, hint=hint)

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """按钮「完成创建」：配置流里创建新条目，选项流里写回已有条目."""
        if self._is_wizard():
            return await self._async_create_monitor()
        return await self._async_apply_changes()

    # ==================================================== 候选按钮的统一分发
    async def _async_pick(self, index: int) -> FlowResult:
        """菜单里第 index 个候选按钮被点击：按 _cur_step 判断这是哪一步的候选."""
        step = getattr(self, "_cur_step", "city")

        if step in ("city", "city_browse"):
            if 0 <= index < len(self._city_options):
                return await self._async_city_chosen(self._city_options[index])
            return await self.async_step_city()

        if step == "station":
            if 0 <= index < len(self._station_options):
                self._station = self._station_options[index]
                self._reset_after_station()
                return await self.async_step_line()
            return await self.async_step_station()

        if step == "line":
            if 0 <= index < len(self._line_options):
                return await self._async_choose_line(self._line_options[index])
            return await self.async_step_line()

        if step == "line_station":
            if 0 <= index < len(self._station_options):
                label = self._station_options[index]
                self._station = self._station_map.get(label) or label
                return await self._async_selection_done()
            return await self.async_step_line_station()

        return await self.async_step_city()

    # ==================================================== 第 6 步：数据同步
    # 配置流（向导第 6 步）与选项流（菜单里的「🔄 数据同步」）**共用这一段**：
    # 同一个 ``step_id``（``sync``）、同一批按钮、同一批文案。区别只有两处：
    #   ① 说明区的开场白：「向导」讲「创建前可以先同步」，「选项」讲缓存规模；
    #   ② 出口：向导多一个「⏭ 下一步：确认创建」，选项流靠「⬅ 返回选项菜单」。
    # 所以这里用 :meth:`_is_wizard` 分流，而不是各写一份。
    async def async_step_sync(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """第 6 步 / 选项菜单项：数据同步（看状态、立即同步、改间隔、开关自动同步）."""
        sync = await self._async_sync()
        status = sync.status()
        last = _when_text(status.get("last_sync_ts"))
        if self._is_wizard():
            note = self._notice or self._t("h_sync_setup")
        else:
            # 12 小时就是「12 小时」，不要写成「12.0 小时」（读屏会念成一串数字）
            hours = status.get("interval_hours", 12) or 12
            note = self._notice or self._t("h_sync_note", interval=f"{hours:g}")
        self._notice = ""
        text = self._t(
            "h_sync_menu",
            note=note,
            when=last,
            duration=f"（用时 {status.get('duration')} 秒）" if status.get("duration") else "",
            auto=(
                "已启用，" + _interval_text(status.get("interval"))
                if status.get("enabled")
                else "已关闭（数据过期时仍会按需拉取）"
            ),
            cities=status.get("cities", 0),
            lines=status.get("lines", 0),
            stations=status.get("stations", 0),
        )
        if status.get("failures"):
            text += f"\n· 累计同步失败 {status['failures']} 次，最近错误：{status.get('last_error')}"
        for issue in status.get("issue_texts") or []:
            text += f"\n· 注意：{issue}"
        if last == "尚未同步":
            text += "\n\n" + self._t("h_sync_first")

        items: dict[str, str] = {
            "sync_now": self._t("act_sync_now", when=last),
            "sync_interval": self._t(
                "act_sync_interval", interval=_interval_text(status.get("interval"))
            ),
            "sync_toggle": self._t(
                "act_sync_off" if status.get("enabled") else "act_sync_on"
            ),
        }
        if self._is_wizard():
            items["to_confirm"] = self._t("act_next_confirm")
        return self._menu_step("sync", items, hint=text)

    async def async_step_sync_now(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """按钮「立即同步」."""
        sync = await self._async_sync()
        try:
            summary = await sync.async_sync()
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("手动同步数据失败")
            self._notice = self._t("h_sync_fail", err=err)
            return await self.async_step_sync()
        if summary.get("errors"):
            # 失败时只说失败，不报「同步完成：城市 0、线路 0、站台 0」
            self._notice = _summary_text(summary, prefix="")
            return await self.async_step_sync()
        self._notice = self._t(
            "h_sync_done",
            cities=summary.get("cities", 0),
            lines=summary.get("lines", 0),
            stations=summary.get("stations", 0),
        )
        if summary.get("repaired"):
            self._notice += self._t("h_sync_repair", n=summary["repaired"])
        if summary.get("issues"):
            self._notice += self._t("h_sync_issue", n=len(summary["issues"]))
        return await self.async_step_sync()

    async def async_step_sync_toggle(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """按钮「启用 / 关闭自动同步」."""
        sync = await self._async_sync()
        enabled = not bool(sync.status().get("enabled"))
        try:
            await sync.async_set_enabled(enabled)
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("修改自动同步开关失败")
            self._notice = f"修改自动同步设置失败：{err}"
            return await self.async_step_sync()
        self._notice = self._t(
            "h_sync_on" if enabled else "h_sync_off",
            interval=_interval_text(sync.status().get("interval")),
        )
        return await self.async_step_sync()

    async def async_step_sync_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """数据同步子页：自动同步间隔（数字输入框，表单）."""
        sync = await self._async_sync()
        if user_input is not None:
            try:
                hours = int(user_input[SYNC_INTERVAL_FIELD])
            except (KeyError, TypeError, ValueError):
                hours = round(DEFAULT_SYNC_INTERVAL / 3600)
            try:
                await sync.async_set_interval(hours * 3600)
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("修改自动同步间隔失败")
                self._notice = f"修改自动同步间隔失败：{err}"
                return await self.async_step_sync()
            self._notice = f"已把自动同步间隔改为 {_interval_text(hours * 3600)}。"
            return await self.async_step_sync()

        schema = _sync_schema(sync.status().get("interval"))
        return self._form_step(
            "sync_interval",
            schema,
            hint=self._hint or self._t("h_sync_interval"),
        )

    # ------------------------------------------------------------------ 工具
    async def _resolve_station_order(self) -> int | None:
        """校验站台在所选线路方向上的站序（方向不符时自动换向再试一次）."""
        sync = await self._async_sync()
        city = self._city or DEFAULT_CITY
        stations = await sync.async_line_stations(city, self._line, self._direction)
        order = station_order_in(stations, self._station)
        if order is None:
            other = "2" if self._direction == "1" else "1"
            stations = await sync.async_line_stations(city, self._line, other)
            order = station_order_in(stations, self._station)
            if order is not None:
                self._direction = other
        return order

    async def _async_settings_saved(self) -> FlowResult:
        """参数保存后的去向（配置流 → 回参数页；选项流 → 写回并结束）."""
        raise NotImplementedError

    async def _async_selection_done(self) -> FlowResult:
        """站台 + 线路都已选定（配置流 → 参数页；选项流 → 确认页）."""
        raise NotImplementedError

    async def _async_create_monitor(self) -> FlowResult:
        raise NotImplementedError

    async def _async_apply_changes(self) -> FlowResult:
        raise NotImplementedError


def _resolve_city(cities: list[str], raw: str) -> str | None:
    """把用户输入的城市名解析成服务城市里的正式名称（只接受精确匹配）.

    只认「完全相同」与「去掉行政区划后缀后相同」两种（如 厦门 → 厦门市），
    不做包含匹配 —— 否则输入「州市」会被解析成「福州市」，用户还来不及看
    候选列表就被带进下一步。多条模糊命中时交给调用方列出候选让用户挑。
    """
    if not raw or not cities:
        return None
    for city in cities:
        if city == raw:
            return city
    exact = match_city(cities, raw)
    if exact is not None and city_base_name(exact) == city_base_name(raw):
        return exact
    return None


def _build_line_choices(hits) -> tuple[list[str], dict[str, dict[str, str]]]:
    """把线路检索结果转成 (候选标签, 标签→负载) 。"""
    options: list[str] = []
    mapping: dict[str, dict[str, str]] = {}
    seen: set[tuple[str, str]] = set()
    for hit in sorted_line_hits(hits):
        key = (hit.line_name, hit.direction)
        if key in seen:
            continue
        seen.add(key)
        label = _line_label(hit)
        options.append(label)
        mapping[label] = {
            "line": hit.line_name,
            "direction": hit.direction,
            "label": label,
            "dir_text": _dir_text(hit),
        }
    return options, mapping


# ---------------------------------------------------------------------------
# 配置流
# ---------------------------------------------------------------------------
class XmBusConfigFlow(_WizardMixin, config_entries.ConfigFlow, domain=DOMAIN):
    """My Bus 配置向导：城市 → 检索方式 → 站台/线路 → 参数 → 确认创建。"""

    VERSION = 2

    def __init__(self) -> None:
        self._init_wizard()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> "XmBusOptionsFlow":
        """注册选项流：用户可在集成条目「配置」里修改城市/线路/站台与到站参数."""
        return XmBusOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """入口：第 1 步「选择城市」."""
        return await self.async_step_city()

    # ------------------------------------------------------------ 向导内钩子
    async def _async_selection_done(self) -> FlowResult:
        """站台 + 线路选定 → 进入第 5 步「到站提醒参数」."""
        return await self.async_step_settings()

    async def _async_settings_saved(self) -> FlowResult:
        """参数保存 → 回到第 5 步的按钮页（可继续改，也可进入下一步）."""
        return await self.async_step_settings()

    async def _async_apply_changes(self) -> FlowResult:
        return await self._async_create_monitor()

    async def _async_create_monitor(self) -> FlowResult:
        """校验站序并创建条目；失败时留在本页给出提示（不再直接 abort）."""
        try:
            order = await self._resolve_station_order()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("站序校验失败")
            self._hint = self._t("h_cannot_connect")
            return await self.async_step_confirm()

        if order is None:
            self._hint = self._t("h_not_on_line", station=self._station, line=self._line)
            return await self.async_step_confirm()

        city = self._city or DEFAULT_CITY
        unique_id = f"{city}|{self._line}|{self._direction}|{self._station}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"{city} {self._line} {self._station}",
            data={
                CONF_CITY: city,
                CONF_STATION: self._station,
                CONF_LINE: self._line,
                CONF_DIRECTION: self._direction,
                CONF_STATION_ORDER: order,
            },
            options={
                CONF_POLL_INTERVAL: self._poll_interval,
            },
        )


# ---------------------------------------------------------------------------
# 选项流（修改已创建的监控：城市 / 线路站台 / 到站参数 / 数据同步）
# ---------------------------------------------------------------------------
class XmBusOptionsFlow(_WizardMixin, config_entries.OptionsFlow):
    """选项流：按钮式入口菜单 + 与配置流完全相同的向导步骤。

    ``_entry_step`` = ``"init"``：向导步骤的「上一步」最终回到选项菜单；
    ``_wizard_first`` 记录从菜单进入的是哪一步，用于决定返回目标。
    """

    _entry_step = "init"
    _wizard_first = "city"

    def __init__(self, config_entry=None) -> None:
        self._entry = config_entry
        if config_entry is not None:
            try:
                self.config_entry = config_entry  # 旧版 HA 需要
            except AttributeError:  # 新版 HA 中 config_entry 为只读属性
                pass
        self._init_wizard()          # 里面已经把 _hint / _notice 清空
        self._cur_step = "init"
        if config_entry is not None:
            data = getattr(config_entry, "data", {}) or {}
            opts = getattr(config_entry, "options", {}) or {}
            self._city = (data.get(CONF_CITY) or DEFAULT_CITY).strip() or DEFAULT_CITY
            self._station = data.get(CONF_STATION, "")
            self._line = data.get(CONF_LINE, "")
            self._direction = str(data.get(CONF_DIRECTION, "1"))
            # 数字参数统一过一遍归一化：旧条目或手工改过 .storage 可能留下越界值。
            self._poll_interval = normalize_poll_interval(
                opts.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            )

    @property
    def entry(self):
        return getattr(self, "config_entry", None) or self._entry

    # ------------------------------------------------------------------ 菜单
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """选项菜单：修改城市 / 修改线路站台 / 修改参数 / 数据同步 / 完成."""
        self._wizard_first = "city"
        self._cur_step = "init"
        items = {
            "edit_city": self._t("opt_city", city=self._city or DEFAULT_CITY),
            "edit_line": self._t(
                "opt_line",
                current=(
                    f"{self._line} {self._station}".strip()
                    if self._line
                    else "（尚未设置）"
                ),
            ),
            "edit_settings": self._t("opt_settings", params=self._params_text()),
            "sync": self._t("opt_sync", summary=await self._async_sync_summary()),
            "done": self._t("menu_finish"),
        }
        text = self._notice or self._t("opt_hint")
        self._notice = ""
        return self._menu_step("init", items, hint=text)

    async def async_step_done(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """结束选项流（原样保留已有选项，避免被清空）."""
        return self.async_create_entry(
            title="", data=dict(self.entry.options) if self.entry else {}
        )

    # ------------------------------------------- 向导入口（决定「上一步」去向）
    async def async_step_edit_city(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """菜单项「修改城市」：从第 1 步「选择城市」开始."""
        self._wizard_first = "city"
        self._hint = ""
        return await self.async_step_city()

    async def async_step_edit_line(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """菜单项「修改线路 / 站台」：从第 2 步「选择检索方式」开始（保留城市）."""
        self._wizard_first = "mode"
        self._hint = ""
        self._city_kw = ""
        self._city_options = []
        self._reset_after_city()
        return await self.async_step_mode()

    async def async_step_edit_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """菜单项「修改到站参数」：直接进入刷新间隔输入框."""
        self._wizard_first = "settings_params"
        self._hint = ""
        return await self.async_step_settings_params()

    # ------------------------------------------------------------ 数据同步
    async def _async_sync_summary(self) -> str:
        sync = await self._async_sync()
        return _sync_summary(sync.status())

    # ------------------------------------------------------------ 向导内钩子
    async def _async_selection_done(self) -> FlowResult:
        """选项流里线路 / 站台已选好 → 进入确认页."""
        return await self.async_step_confirm()

    async def _async_settings_saved(self) -> FlowResult:
        """参数保存 → 写回条目选项并结束选项流."""
        current = dict(self.entry.options) if self.entry else {}
        current.update(
            {
                CONF_POLL_INTERVAL: self._poll_interval,
            }
        )
        return self.async_create_entry(title="", data=current)

    async def _async_apply_changes(self) -> FlowResult:
        """按钮「保存修改」：校验站序 → 写回条目 → 重载 → 回选项菜单."""
        try:
            order = await self._resolve_station_order()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("站序校验失败")
            self._notice = self._t("h_cannot_connect")
            return await self.async_step_init()

        if order is None:
            self._notice = self._t("h_not_on_line", station=self._station, line=self._line)
            return await self.async_step_init()

        entry = self.entry
        city = self._city or DEFAULT_CITY
        new_data = {
            **entry.data,
            CONF_CITY: city,
            CONF_STATION: self._station,
            CONF_LINE: self._line,
            CONF_DIRECTION: self._direction,
            CONF_STATION_ORDER: order,
        }
        self.hass.config_entries.async_update_entry(
            entry, data=new_data, title=f"{city} {self._line} {self._station}"
        )
        self.hass.async_create_task(self.hass.config_entries.async_reload(entry.entry_id))
        self._notice = self._t(
            "opt_synced", city=city, line=self._line, station=self._station
        )
        return await self.async_step_init()

    async def _async_create_monitor(self) -> FlowResult:
        return await self._async_apply_changes()


def status_interval(sync) -> Any:
    """同步间隔（秒），取不到时用默认值."""
    try:
        return sync.status().get("interval", DEFAULT_SYNC_INTERVAL)
    except Exception:  # noqa: BLE001
        return DEFAULT_SYNC_INTERVAL


def status_enabled(sync) -> Any:
    """是否启用定期同步，取不到时用默认值."""
    try:
        return sync.status().get("enabled", DEFAULT_SYNC_ENABLED)
    except Exception:  # noqa: BLE001
        return DEFAULT_SYNC_ENABLED
