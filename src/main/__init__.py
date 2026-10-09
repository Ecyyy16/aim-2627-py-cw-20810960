# -*- coding: utf-8 -*-
"""AIM 2627 Python Coursework —— 哨兵 Sentry 控制模块（学生骨架）。

你的全部作业都在本文件里：按题面（题面.pdf）各题的规范补全每个标有 TODO 的函数。
- 骨架已提供：Facing / SentryState 枚举、SentryGrid 的构造与只读属性、
  渲染函数 render_frame（demo 用，不进测试）。
- 你要实现：Q1-Q6 与 Bonus 的全部 TODO，以及 SentryGrid 的
  四个方法（current_pos 的 setter、move_forward、turn_left、turn_right）。
- 未实现的函数 raise NotImplementedError：可见测试会自动 skip，
  CI 一开始就是绿的；实现一个，对应测试亮一个。
- `python main.py`（或 PYTHONPATH=src python -m main）可看 ASCII 演示。
"""
import json
from enum import Enum


# ---------------------------------------------------------------------------
# 仿真世界基础（已提供，勿改）
# ---------------------------------------------------------------------------
class Facing(Enum):
    """朝向枚举。世界坐标 (x, y)：x 向右增长，y 向上增长（数学系）。"""

    UP = (0, 1)
    DOWN = (0, -1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def delta(self):
        """该朝向的单位位移向量 (dx, dy)。"""
        return self.value[0], self.value[1]


# ---------------------------------------------------------------------------
# Q1 机器人自检（题面 Q1·自检状态计算与报告生成）
# ---------------------------------------------------------------------------
def hp_ratio(hp, max_hp):
    """血量百分比，返回0-100的int"""
    if max_hp <= 0:
        if hp > 0:
            return 100
        else:
            return 0
    pct = int(round(hp * 100 / max_hp))
    return max(0, min(100, pct))


def status_report(name, robot_type, hp, max_hp, battery):
    """自检报告:假定 >=50 为 OK、 >=20 为 WARNING、其余为 LOW
    """
    pct = hp_ratio(hp, max_hp)
    if battery >= 50:
        tip = "OK"
    elif battery >= 20:
        tip = "WARNING"
    else:
        tip = "LOW"
    return f"{name:<10}|{robot_type:^10}|HP {pct:>3}%|BAT {battery:>3}%|{tip}"


# ---------------------------------------------------------------------------
# Q2 战斗日志分析（题面 Q2·多源日志解析与统计）
# ---------------------------------------------------------------------------
_ARMOR_BY_CODE = {"F": "front", "L": "left", "R": "right"}


def _parse_sensor_line(text):
    """解析传感器行，返回 [(部位, 伤害), ...]；任一段非法则整行按脏行处理。"""
    events = []
    for seg in text.split(","):
        parts = seg.strip().split(":")
        # 分长度，字母，数字（整数正数检测）
        if len(parts) != 2:
            return None
        armor = _ARMOR_BY_CODE.get(parts[0].strip())
        if armor is None:
            return None
        try:
            damage = int(parts[1].strip())
        except ValueError:
            return None
        if damage <= 0:
            return None
        events.append((armor, damage))
    return events


def _parse_json_line(text, seen_ids):
    """解析 JSON 行，返回 [(部位, 伤害), ...]；脏行或重复 id 返回 None。"""
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    armor = obj.get("armor")
    if armor not in ("front", "left", "right"):
        return None
    damage = obj.get("damage")
    if isinstance(damage, bool) or not isinstance(damage, int) or damage <= 0:
        return None
    if "id" in obj and obj["id"] is not None:
        key = obj["id"]
        try:
            if key in seen_ids:
                return None
            seen_ids.add(key)
        except TypeError:
            return None
    return [(armor, damage)]


def analyze_damage_log(lines):
    """解析混合格式伤害日志，
       输出契约固定：total 为有效事件伤害总和；
       by_armor 按三部位分桶累计，三个部位键在任何情况下恒存在，未受击为 0；
       most_hit 为受击伤害最大的部位，无有效事件时为 None；
       空日志0.0
    """
    total = 0
    by_armor = {"front": 0, "left": 0, "right": 0}
    event_count = 0
    seen_ids = set()
    for raw in lines:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        try:
            if text.startswith("{"):
                parsed = _parse_json_line(text, seen_ids)
            else:
                parsed = _parse_sensor_line(text)
        except Exception:
            continue
        if not parsed:
            continue
        for armor, damage in parsed:
            total += damage
            by_armor[armor] += damage
            event_count += 1
    return {
        "total": total,
        "by_armor": by_armor,
        "most_hit": max(by_armor, key=by_armor.get) if event_count else None,
        "avg": round(total / event_count, 2) if event_count else 0.0,
    }


# ---------------------------------------------------------------------------
# Q3 SentryGrid（题面 Q3·载体物理规则）
# ---------------------------------------------------------------------------
class SentryGrid:
    """哨兵仿真载体（构造与只读属性已提供；四个 TODO 方法由你实现）。"""

    def __init__(self, width, height, obstacles, enemy_pos,
                 start_pos=(0, 0), facing=Facing.UP, fuel=100):
        self._width = int(width)
        self._height = int(height)
        if self._width <= 0 or self._height <= 0:
            raise ValueError("地图尺寸必须为正")
        # 障碍坐标存入 set，查询 O(1)——已有实现，勿改。
        self._obstacles = set()
        for ob in obstacles:
            x, y = ob
            self._obstacles.add((int(x), int(y)))
        if not isinstance(enemy_pos, (tuple, list)) or len(enemy_pos) != 2:
            raise TypeError("enemy_pos 需要长度为 2 的 tuple/list")
        self._enemy_pos = self._clamp_cell(enemy_pos)
        if self._enemy_pos in self._obstacles:
            raise ValueError("enemy_pos 不能位于障碍物上")
        if not isinstance(facing, Facing):
            facing = Facing.UP
        self._facing = facing
        self._fuel = int(fuel)
        self._collision_count = 0
        self._pos = self._clamp_cell(start_pos)
        if self._pos in self._obstacles:
            raise ValueError("start_pos 不能位于障碍物上")

    def _clamp_cell(self, cell):
        """已提供：元素转 int 并夹回地图范围（供 __init__ 使用）。"""
        x = int(cell[0])
        y = int(cell[1])
        x = max(0, min(self._width - 1, x))
        y = max(0, min(self._height - 1, y))
        return (x, y)

    # -- 只读属性（已提供，勿改） ------------------------------------------
    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def enemy_pos(self):
        return self._enemy_pos

    @property
    def facing(self):
        return self._facing

    @property
    def fuel(self):
        return self._fuel

    @property
    def collision_count(self):
        return self._collision_count

    @property
    def obstacles(self):
        """障碍集合的只读视图（内部 set 引用，不要修改它）。"""
        return self._obstacles

    @property
    def found_enemy(self):
        return self._pos == self._enemy_pos

    def is_blocked(self, x, y):
        """已提供：坐标是否为障碍或越界（O(1)）。"""
        return ((x, y) in self._obstacles
                or not (0 <= x < self._width and 0 <= y < self._height))

    # -- 你要实现的部分 ------------------------------------------------------
    @property
    def current_pos(self):
        """当前位置 (x, y) 的 tuple。"""
        return self._pos

    @current_pos.setter
    def current_pos(self, value):
        """
        位置 setter：只接受长度为 2 的 tuple/list，否则 TypeError；
        元素经规范化后以 tuple 存储
        """
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise TypeError("current_pos 需要长度为 2 的 tuple/list")
        self._pos = self._clamp_cell(value)

    def move_forward(self):
        """
        - 前方为障碍时，位置和朝向不变，collision_count 加 1。
        - 前方可通行时，移动到该格。
        - 前进消耗 1 单位电量。
        - 电量 <= 0 时，前进尝试不再产生位移。
        """
        if self._fuel > 0:
            self._fuel -= 1
            nx = self._pos[0] + self._facing.delta[0]
            ny = self._pos[1] + self._facing.delta[1]
            if self.is_blocked(nx, ny):
                self._collision_count += 1
            else:
                self._pos = (nx, ny)
        return self._pos

    def turn_left(self):
        """原地左转 90°，返回新的 Facing（不耗电）。"""

        if self._facing is Facing.UP:
            self._facing = Facing.LEFT
        elif self._facing is Facing.LEFT:
            self._facing = Facing.DOWN
        elif self._facing is Facing.DOWN:
            self._facing = Facing.RIGHT
        else:
            self._facing = Facing.UP
        return self._facing

    def turn_right(self):
        """原地右转 90°，返回新的 Facing（不耗电）。"""

        if self._facing is Facing.UP:
            self._facing = Facing.RIGHT
        elif self._facing is Facing.RIGHT:
            self._facing = Facing.DOWN
        elif self._facing is Facing.DOWN:
            self._facing = Facing.LEFT
        else:  # self._facing is Facing.LEFT
            self._facing = Facing.UP
        return self._facing

# ---------------------------------------------------------------------------
# Q4 贪心导航（题面 Q4·单步贪心导航策略）
# ---------------------------------------------------------------------------


def next_step_toward(pos, target, obstacles, current_facing=Facing.UP):
    """TODO(Q4)：返回下一步应朝向的 Facing；
    候选判定、优先级与回退规则见题面 Q4 规范。"""
    raise NotImplementedError("Q4 next_step_toward：题面 Q4·贪心策略与回退")


# ---------------------------------------------------------------------------
# Q5 哨兵决策机（题面 Q5·裁判系统决策规则表）
# ---------------------------------------------------------------------------
class SentryState(Enum):
    """哨兵状态机（已提供，勿改）。"""

    PATROL = "PATROL"
    SUSPECT = "SUSPECT"
    ENGAGE = "ENGAGE"
    RETREAT = "RETREAT"
    RETURN = "RETURN"


def decide(sensor, state, hp, heat):
    """TODO(Q5)：纯函数决策，返回 (action: str, new_state: SentryState)；
    sensor 字段契约、R1-R7 规则表与非法输入处理见题面 Q5 规范。"""
    raise NotImplementedError("Q5 decide：题面 Q5·决策规则表 R1-R7")


# ---------------------------------------------------------------------------
# Q6 巡逻任务（题面 Q6·巡逻契约与验收阈值）
# ---------------------------------------------------------------------------
def run_patrol(grid, max_steps=500):
    """TODO(Q6)：sense → decide → act 主循环；
    循环结构、终止条件、脱困自由度与统计返回契约见题面 Q6 规范。"""
    raise NotImplementedError("Q6 run_patrol：题面 Q6·主循环与统计契约")


def report_to_json(stats):
    """TODO(Q6)：把 stats 序列化为确定性的 JSON 字符串，见题面 Q6 规范。"""
    raise NotImplementedError("Q6 report_to_json：题面 Q6·报告序列化")


# ---------------------------------------------------------------------------
# Bonus：BFS 全局最短路（题面 Bonus·BFS 语义与排行榜）
# ---------------------------------------------------------------------------
def bfs_path_length(start, target, obstacles):
    """TODO(Bonus)：BFS 全局最短路步数；返回语义与边界职责见题面 Bonus 规范。"""
    raise NotImplementedError("Bonus bfs_path_length")


# ---------------------------------------------------------------------------
# 渲染（已提供，demo 专用，不进测试）
# ---------------------------------------------------------------------------
def render_frame(grid, trail=()):
    """ASCII 渲染一帧战场；trail 为走过的格子集合。返回 list[str]。"""
    trail = set(trail)
    rows = []
    for y in range(grid.height - 1, -1, -1):
        row = []
        for x in range(grid.width):
            if (x, y) == grid.current_pos:
                row.append("◉")
            elif (x, y) == grid.enemy_pos:
                row.append("▲")
            elif (x, y) in grid.obstacles:
                row.append("█")
            elif (x, y) in trail:
                row.append("·")
            else:
                row.append(".")
        rows.append("".join(row))
    return rows
