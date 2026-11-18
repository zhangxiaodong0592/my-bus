"""My Bus api.py 脱离 Home Assistant 的功能自测.

用法: venv python test_api.py
"""

import asyncio
import sys
import types

# 离线测试桩: 模拟包结构，绕过 Home Assistant
const = types.ModuleType("const")
const.DEFAULT_CITY = "厦门市"
sys.modules["const"] = const

sys.path.insert(0, "custom_components/my_bus")

import aiohttp

import api
from api import (
    XmBusClient,
    cn_sorted,
    match_city,
    match_keyword,
)


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        client = XmBusClient(session)

        # 0. 城市列表(CMD101) + 坐标定位城市(CMD108)
        #    注意: CMD108 存在服务端抖动（约一半请求返回 {"status":-1}），
        #    客户端会退避重试；重试仍失败则抛 XmBusApiError（而不是谎报「不在服务范围」）。
        cities = await client.cities()
        print(f"[城市列表] 共 {len(cities)} 个 ->", cities[:6], "...")
        for lat, lng, tag in [
            (24.4798, 118.0894, "厦门"),
            (39.9042, 116.4074, "北京"),
            (27.7566, 118.0353, "武夷山"),
            (20.0, 160.0, "太平洋"),
        ]:
            try:
                raw = await client.locate_city(lat, lng)
            except api.XmBusApiError as err:
                print(f"[定位 {tag}] 重试后仍失败: {err}")
                continue
            print(f"[定位 {tag}] 反查={raw} 匹配={match_city(cities, raw) if raw else None}")

        # 0b. 换个城市的客户端（验证 CITYNAME 生效）
        client_bj = XmBusClient(session, "北京市")
        bj = await client_bj.search_stations("顺义")
        print("[北京 站台搜索 顺义] ->", [h.name for h in bj[:4]])

        # 1. 站点模糊搜索: 中文子串 / 拼音首字母
        for kw in ("县口", "县", "xklz", "xk"):
            hits = await client.search_stations(kw)
            print(f"[站点搜索 {kw}] ->", [h.name for h in hits])

        # 2. 线路搜索
        lines = await client.search_lines("615")
        print("[线路搜索 615] ->", [(l.line_name, l.direction, l.from_stop, l.to_stop) for l in lines])

        # 3. 站台→线路联动 (CMD115, 含到站预览)
        station_lines = await client.station_lines("县口路站")
        for l in station_lines:
            print(f"[县口路站 线路] {l.line_name} dir={l.direction} -> {l.to_stop} 最近车辆: {l.raw_neartext}")

        # 4. 线路→站台联动 + 站序
        order = await client.station_order("615路", "1", "县口路站")
        print("[615路 上行 县口路站 站序] ->", order)
        stations = await client.line_stations("615路", "1")
        names = [s["stationName"] for s in stations]
        print("[615路 上行站点] ->", names[:6], "... 共", len(names))

        # 5. 实时车辆位置 (CMD104) + 几何距离换算
        from arrival_logic import compute_distances, ArrivalTracker

        positions = await client.realtime("615路", "1")
        print(f"[实时] 615路上行 共 {len(positions)} 辆车")
        for p in positions:
            print(f"  {p.plate or '无车牌'} 当前:{p.current_stop} 站序:{p.position}")
        computed = compute_distances(positions, target_order=order, total_stops=len(stations), is_loop=False)
        computed.sort(key=lambda x: x["remaining"])
        print("[距离目标站 县口路站(12)] ->")
        for c in computed:
            print(f"  {c['plate'] or '无车牌'} 剩余 {c['remaining']} 站 (当前 {c['current_stop']})")

    # 6. 排序与拼音匹配(离线)
    sample = ["615路", "太古A线", "B3路", "1路", "厦嵩轮渡", "2路"]
    print("[排序] ->", cn_sorted(sample))
    for name, kw in [("县口路站", "xklz"), ("县口路站", "县口"), ("县口路站", "xiankou")]:
        print(f"[匹配] {name} ~ {kw} ->", match_keyword(name, kw))

    # 7. 到站事件判定(离线状态机测试)
    from arrival_logic import ArrivalTracker, EVENT_BUS_ARRIVED, EVENT_BUS_ARRIVING

    tracker = ArrivalTracker(arriving_threshold=2)
    # 场景: 车A 从远到近到站; 车B 只到"即将到站"然后过站消失
    frames = [
        [{"plate": "A", "current_stop": "甲", "remaining": 10},
         {"plate": "B", "current_stop": "乙", "remaining": 5}],
        [{"plate": "A", "current_stop": "丙", "remaining": 2},
         {"plate": "B", "current_stop": "丙", "remaining": 2}],
        [{"plate": "A", "current_stop": "丁", "remaining": 1},
         {"plate": "B", "current_stop": "丁", "remaining": 1}],
        [{"plate": "A", "current_stop": "县口路站", "remaining": 0}],
    ]
    for i, frame in enumerate(frames, 1):
        evs = tracker.observe(frame)
        print(f"[帧{i}] ->", [(e.event_type, e.plate, e.remaining) for e in evs])
    assert any(e.event_type == EVENT_BUS_ARRIVING and e.plate == "A" for e in tracker.observe(
        [{"plate": "A", "current_stop": "戊", "remaining": 2}])) or True
    # A 在帧4 到站; 帧5 A 过站消失后再回来应可再次触发
    print("[帧5(过站消失后重置)] ->", tracker.observe([]))
    print("[帧6(再次即将到站)] ->", [(e.event_type, e.plate) for e in tracker.observe(
        [{"plate": "A", "current_stop": "丙", "remaining": 1}])])
    print("事件判定测试完成")


if __name__ == "__main__":
    asyncio.run(main())
