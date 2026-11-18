"""针对历史修复点的定向验证（脱离真实 HA 运行）.

修复点:
1. 网络超时/非 JSON 不再冒泡成前端 "Unknown error occurred"，
   而是转为 XmBusApiError，配置流显示中文提示。
2. 检索结果必须把关键词回显给用户（原 MISSING_VALUE 类问题的守卫）。
3. CMD108（按坐标反查城市）会随机返回 ``{"status":-1}``（实测同一坐标连发 6 次常有
   一半左右是 -1；换请求头 / 带 Cookie / 拉长间隔 / 微抖坐标都不改善，是纯服务端抖动）。
   旧实现把它当成「不在服务范围」，于是「用家庭位置识别城市」按钮约一半概率给出
   **错误**提示。现在重试多次，只有拿到 ``status=2`` 才认定该坐标确实没有服务城市，
   重试耗尽则抛异常让界面提示「稍后重试」。

注: v0.2.0 起接口客户端按城市实例化（hass.data["my_bus"]["client::<城市>"]）；
v0.3.0 起结构数据统一走数据同步层（hass.data["my_bus"]["sync"]）；
v0.5.0 起配置流改为「菜单按钮式」向导（候选与「上一步」都是真实按钮，
只有需要键盘输入的检索/参数用表单，`async_step_station_keyword` 等）。
本脚本已同步这些改动。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(__file__))

import stub_ha  # noqa: E402

HOMEASSISTANT_AVAILABLE = False


# ---------------------------------------------------------------------------
# 伪造一个会超时的 session
# ---------------------------------------------------------------------------
class _TimeoutContext:
    async def __aenter__(self):
        raise asyncio.TimeoutError()

    async def __aexit__(self, *exc):
        return False


class _TimeoutSession:
    """模拟请求超时（NAS 访问公交接口偏慢时的真实场景）."""

    def __init__(self):
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        return _TimeoutContext()


class _BadJsonContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def status(self):
        return 200

    async def read(self):
        return b"<html>access denied (rate limited)</html>"


class _BadJsonSession:
    """模拟风控返回非 JSON 内容."""

    def __init__(self):
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        return _BadJsonContext()


def _load_client_class():
    stub_ha.install()
    pkg = types.ModuleType("my_bus")
    pkg.__path__ = [
        os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "custom_components", "my_bus")
        )
    ]
    sys.modules["my_bus"] = pkg
    import importlib

    api = importlib.import_module("my_bus.api")
    return api


async def test_timeout_client() -> bool:
    api = _load_client_class()
    session = _TimeoutSession()
    client = api.XmBusClient(session)
    try:
        await client._post({"CMD": "110", "KEYWORD": "同安"})
    except api.XmBusApiError as err:
        print(f"[超时]  已转为 XmBusApiError: {err}")
        print(f"[超时]  实际发起请求 {session.calls} 次（含 1 次自动重试）")
        return session.calls == 2
    except BaseException as err:  # noqa: BLE001
        print(f"[超时]  ❌ 异常未被捕获，冒泡成 {type(err).__name__}: {err}")
        return False
    print("[超时]  ❌ 未抛出任何异常")
    return False


async def test_bad_json_client() -> bool:
    api = _load_client_class()
    session = _BadJsonSession()
    client = api.XmBusClient(session)
    try:
        await client._post({"CMD": "110", "KEYWORD": "同安"})
    except api.XmBusApiError as err:
        print(f"[非JSON] 已识别为接口异常: {err}")
        return session.calls == 2
    except BaseException as err:  # noqa: BLE001
        print(f"[非JSON] ❌ 未捕获，冒泡成 {type(err).__name__}: {err}")
        return False
    print("[非JSON] ❌ 未抛出异常")
    return False


class _JsonContext:
    """把 dict 当成 aiohttp 响应返回（供 CMD108 重试逻辑做离线验证）."""

    def __init__(self, payload):
        self._payload = payload
        self.status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self):
        return json.dumps(self._payload).encode()


class _FlakyLocateSession:
    """按脚本依次返回响应；脚本用完后一直重复最后一条（模拟接口抖动）."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.params: list[dict] = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls += 1
        self.params.append(dict(data or {}))
        payload = self.script[min(self.calls - 1, len(self.script) - 1)]
        return _JsonContext(payload)


async def test_locate_city_retry() -> bool:
    """CMD108 抖动时退避重试；只有 status=2 才认定「没有服务城市」."""
    api = _load_client_class()
    ok = True

    # 1) 抖动 3 次后命中 → 应当重试到成功（旧实现会谎报「不在服务范围」）
    flaky = _FlakyLocateSession(
        [{"status": -1}, {"status": -1}, {"status": -1}, {"status": 1, "msg": "厦门市"}]
    )
    client = api.XmBusClient(flaky)
    client.LOCATE_BACKOFF = 0  # 测试里不等退避
    got = await client.locate_city(24.4798, 118.0894)
    ok1 = got == "厦门市" and flaky.calls == 4
    print(f"[定位重试] 抖动 3 次后命中 -> {got!r}（共 {flaky.calls} 次请求）")
    ok = ok and ok1

    # 2) 请求参数同时带 LAT/LNG 与 MYLAT/MYLNG（缺 MY 时接口更容易返回 -1）
    ok2 = all({"LAT", "LNG", "MYLAT", "MYLNG"} <= set(p) for p in flaky.params)
    print(f"[定位参数] {sorted(k for k in flaky.params[0] if k not in ('CITYNAME', 'CITYKEY'))}")
    ok = ok and ok2

    # 3) status=2 = 该坐标确实没有服务城市（境外坐标实测如此）→ 直接 None，不浪费重试
    outside = _FlakyLocateSession([{"status": 2, "msg": "Nakano"}])
    client_out = api.XmBusClient(outside)
    client_out.LOCATE_BACKOFF = 0
    got_out = await client_out.locate_city(35.6895, 139.6917)
    ok3 = got_out is None and outside.calls == 1
    print(f"[定位范围外] 返回 {got_out!r}（共 {outside.calls} 次请求）")
    ok = ok and ok3

    # 4) 一直抖动 → 抛 XmBusApiError，让界面提示「稍后重试」而不是「不在服务范围」
    always = _FlakyLocateSession([{"status": -1}])
    client_bad = api.XmBusClient(always)
    client_bad.LOCATE_BACKOFF = 0
    raised = False
    try:
        await client_bad.locate_city(24.4798, 118.0894)
    except api.XmBusApiError as err:
        raised = True
        print(f"[定位一直抖动] 已转为 XmBusApiError: {err}")
    ok4 = raised and always.calls == api.XmBusClient.LOCATE_ATTEMPTS
    ok = ok and ok4

    print(f"[定位重试] {'✅ 抖动重试 / 范围外直返 / 失败转异常 全部正确' if ok else '❌ 行为不符合预期'}")
    return ok


def _make_flow(client, cities=("厦门市", "北京市")):
    import importlib
    import time

    stub_ha.install()
    cf = stub_ha._load_config_flow()
    ds = importlib.import_module("my_bus.data_sync")

    flow = cf.XmBusConfigFlow()
    hass = stub_ha._fake_hass(None)
    sync = ds.XmBusDataSync(hass, lambda city: client)
    sync._loaded = True
    sync._put(ds.KEY_CITIES, list(cities))
    sync._last_sync = time.time()
    hass.data.setdefault("my_bus", {})["sync"] = sync
    for name in cities:
        hass.data["my_bus"].setdefault(f"client::{name}", client)
    flow.hass = hass
    return flow


async def test_flow_timeout_ui() -> bool:
    """站台检索超时时，应回到站台页给出中文提示，而不是抛出 Unknown error."""
    import importlib

    api = importlib.import_module("my_bus.api")
    cf = stub_ha._load_config_flow()

    class TimeoutClient:
        async def search_stations(self, keyword):
            raise api.XmBusApiError("请求超时（TimeoutError）")

    flow = _make_flow(TimeoutClient())
    flow._city = "厦门市"
    flow._search_mode = cf.MODE_STATION_FIRST
    res = await flow.async_step_station_keyword({cf.STATION_KW_FIELD: "同安"})

    hint = (res.get("placeholders") or {}).get("hint", "")
    ok = res.get("type") == "menu" and res.get("step_id") == "station" and "查询失败" in hint
    print(f"[配置流超时] 返回 type={res.get('type')} step={res.get('step_id')}")
    print(f"[配置流超时] 提示={hint}")
    print(f"[配置流超时] {'✅ 显示中文提示并停留在本步，未冒泡' if ok else '❌ 未正确处理'}")
    return ok


async def test_placeholder() -> bool:
    """检索结果必须把关键词回显给用户（原 MISSING_VALUE 类问题的守卫）."""
    import importlib

    api = importlib.import_module("my_bus.api")
    cf = stub_ha._load_config_flow()

    class FakeClient:
        async def search_stations(self, keyword):
            return [api.StationHit(name="同安一中站"), api.StationHit(name="同安汽车站")]

    flow = _make_flow(FakeClient())
    flow._city = "厦门市"
    flow._search_mode = cf.MODE_STATION_FIRST
    res = await flow.async_step_station_keyword({cf.STATION_KW_FIELD: "同安"})

    hint = (res.get("placeholders") or {}).get("hint", "")
    labels = list((res.get("menu_options") or {}).values())
    ok = (
        "同安" in hint
        and "同安一中站" in str(flow._station_options)
        and any("同安一中站" in x for x in labels)   # 候选渲染成按钮
        and cf.KEY_BACK in (res.get("menu_options") or {})  # 按钮式「上一步」
    )
    print(f"[关键词回显] hint={hint}")
    print(f"[关键词回显] 候选={flow._station_options}")
    print(f"[关键词回显] 按钮={labels}")
    print(f"[关键词回显] {'✅ 关键词已回显、候选已列成按钮、上一步是按钮' if ok else '❌ 未回显关键词'}")
    return ok


async def main() -> None:
    print("=" * 60)
    results = []
    results.append(await test_timeout_client())
    results.append(await test_bad_json_client())
    results.append(await test_locate_city_retry())
    results.append(await test_flow_timeout_ui())
    results.append(await test_placeholder())
    print("=" * 60)
    print("通过" if all(results) else "存在失败项", f"({sum(results)}/{len(results)})")


if __name__ == "__main__":
    asyncio.run(main())
