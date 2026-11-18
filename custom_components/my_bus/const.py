"""My Bus 集成常量."""

DOMAIN = "my_bus"
MANUFACTURER = "My Bus"

# 默认城市（旧条目没有 city 字段时回退到这里，保持向后兼容）
DEFAULT_CITY = "厦门市"

CONF_CITY = "city"
CONF_STATION = "station"
CONF_LINE = "line"
CONF_DIRECTION = "direction"
CONF_STATION_ORDER = "station_order"

CONF_POLL_INTERVAL = "poll_interval"

DEFAULT_POLL_INTERVAL = 10
MIN_POLL_INTERVAL = 5
MAX_POLL_INTERVAL = 120

# ---------------------------------------------------------------------------
# 数据同步：城市 / 线路 / 站台等结构数据与掌上公交保持一致
# ---------------------------------------------------------------------------

# hass.data[DOMAIN] 中数据同步对象的键
DATA_SYNC_KEY = "sync"

# 持久化文件：<config>/.storage/my_bus.data
SYNC_STORAGE_KEY = "my_bus.data"
SYNC_STORAGE_VERSION = 1
# 延迟写盘时间（秒），减少磁盘写入
SYNC_SAVE_DELAY = 10

# 定期自动同步的间隔（秒）：默认 12 小时，可在选项里调整
CONF_SYNC_INTERVAL = "sync_interval"
CONF_SYNC_ENABLED = "sync_enabled"
DEFAULT_SYNC_INTERVAL = 12 * 60 * 60
MIN_SYNC_INTERVAL = 1 * 60 * 60        # 1 小时
MAX_SYNC_INTERVAL = 7 * 24 * 60 * 60   # 7 天
DEFAULT_SYNC_ENABLED = True

# 各类结构数据的本地缓存有效期（秒）。
# 定期同步任务会按其间隔强制刷新；未到同步周期但缓存已过期时按需重新拉取。
CITY_CACHE_TTL = 7 * 24 * 60 * 60        # 城市列表（很少变动）
LINE_STATIONS_TTL = 7 * 24 * 60 * 60     # 线路站点拓扑（基本静态）
STATION_LINES_TTL = 24 * 60 * 60         # 站台停靠线路
LINE_ENDPOINTS_TTL = 24 * 60 * 60        # 线路起终点
SEARCH_CACHE_TTL = 2 * 60                # 关键词搜索结果（仅内存）

# 长期未使用（且不属于已配置监控）的缓存条目清理阈值（秒）
PRUNE_UNUSED_AFTER = 30 * 24 * 60 * 60
