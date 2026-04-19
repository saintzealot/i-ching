"""
前端 JS 纯函数单元测试

通过 Python 子进程调用 node，加载 frontend/assets/iching-core.js 并执行
断言脚本；若本机没有 node 可执行，整个文件 skip（不算失败）。

测试范围：
- computeBianLines — 老阳/老阴互换
- coinsForLine — 爻值 → 三枚铜钱数量对
- seededLayout — 伪随机扰动布局
- pinyinOf — 卦名 → 拼音
- linesVisualClass — 爻视觉类名

运行：
    pytest tests/test_frontend_js.py -v
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE_JS = ROOT / "frontend" / "assets" / "iching-core.js"

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node 不可用，跳过 JS 纯函数测试")


def run_node(script: str):
    """在 ROOT 目录运行一段 node 脚本，把 stdout 里的 JSON 解出来。"""
    if NODE is None:
        pytest.skip("node 不可用")
    completed = subprocess.run(
        [NODE, "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(
            "node 执行失败\nstderr:\n"
            + completed.stderr
            + "\nstdout:\n"
            + completed.stdout
        )
    try:
        return json.loads(completed.stdout.strip())
    except json.JSONDecodeError as e:
        pytest.fail(
            f"无法解析 node 输出: {e}\nstdout: {completed.stdout!r}\nstderr: {completed.stderr!r}"
        )


LOAD = """const core = require("./frontend/assets/iching-core.js");"""


def _probe(expr: str):
    """在 node 里 require 模块、求表达式并 JSON.stringify 到 stdout。"""
    return run_node(f"{LOAD} process.stdout.write(JSON.stringify({expr}));")


# ============================================================
# computeBianLines
# ============================================================


def test_bian_mixed():
    assert _probe("core.computeBianLines([7,8,9,6,7,8])") == [7, 8, 8, 7, 7, 8]


def test_bian_no_changing():
    assert _probe("core.computeBianLines([7,8,7,8,7,8])") == [7, 8, 7, 8, 7, 8]


def test_bian_all_changing():
    assert _probe("core.computeBianLines([6,9,6,9,6,9])") == [7, 8, 7, 8, 7, 8]


def test_bian_preserves_length():
    for arr in ([], [7], [6, 9], [6, 7, 8, 9, 6, 7]):
        arr_js = json.dumps(arr)
        assert len(_probe(f"core.computeBianLines({arr_js})")) == len(arr)


# ============================================================
# coinsForLine
# ============================================================


@pytest.mark.parametrize(
    "line_val,expected",
    [
        (6, [False, False, False]),  # 老阴：0 字 3 花
        (7, [True, False, False]),  # 少阳：1 字 2 花
        (8, [True, True, False]),  # 少阴：2 字 1 花
        (9, [True, True, True]),  # 老阳：3 字 0 花
    ],
)
def test_coins_for_line(line_val: int, expected: list[bool]):
    assert _probe(f"core.coinsForLine({line_val})") == expected


def test_coins_sum_matches_line_val():
    """字=3, 花=2；3 枚之和应与爻值相等。"""
    for v in (6, 7, 8, 9):
        faces = _probe(f"core.coinsForLine({v})")
        total = sum(3 if f else 2 for f in faces)
        assert total == v, f"爻值 {v} 对应的铜钱面值和应为 {v}，实得 {total}"


# ============================================================
# seededLayout
# ============================================================


def test_seeded_layout_is_deterministic():
    a = _probe("core.seededLayout(42)")
    b = _probe("core.seededLayout(42)")
    assert a == b, "同 seed 应返回严格一致的布局"


def test_seeded_layout_shape():
    r = _probe("core.seededLayout(7)")
    assert len(r) == 3
    for p in r:
        assert set(p.keys()) == {"x", "y", "rot"}
        assert isinstance(p["x"], (int, float))
        assert isinstance(p["y"], (int, float))
        assert isinstance(p["rot"], (int, float))


def test_seeded_layout_perturbation_bounded():
    """扰动幅度：x/y 在基点 ±18 范围内，rot 在 ±13° 范围内。"""
    r = _probe("core.seededLayout(1234)")
    base = [(20, 45), (90, 25), (160, 50)]
    for (bx, by), p in zip(base, r):
        assert abs(p["x"] - bx) <= 18, f"x 扰动超出预期: {p['x']} 偏离 {bx}"
        assert abs(p["y"] - by) <= 18, f"y 扰动超出预期: {p['y']} 偏离 {by}"
        assert abs(p["rot"]) <= 13, f"rot 扰动超出预期: {p['rot']}"


def test_seeded_layout_varies_across_seeds():
    a = _probe("core.seededLayout(1)")
    b = _probe("core.seededLayout(2)")
    # 不同种子至少有一组 (x,y) 差异超过 1px（弱但稳定的保证）
    diffs = [
        (abs(a[i]["x"] - b[i]["x"]) + abs(a[i]["y"] - b[i]["y"])) for i in range(3)
    ]
    assert max(diffs) > 1, f"不同 seed 产出布局差异太小: {diffs}"


# ============================================================
# formatCoinResult — 铜钱正反面 → "字 · 花 · 花" 展示文案
# ============================================================


@pytest.mark.parametrize(
    "faces,expected",
    [
        ([True, False, False], "字 · 花 · 花"),
        ([True, True, False], "字 · 字 · 花"),
        ([False, False, False], "花 · 花 · 花"),
        ([True, True, True], "字 · 字 · 字"),
        ([True], "字"),
        ([], ""),
    ],
)
def test_format_coin_result(faces: list[bool], expected: str):
    faces_js = json.dumps(faces)
    assert _probe(f"core.formatCoinResult({faces_js})") == expected


def test_format_coin_result_non_array():
    """非数组输入不得抛异常，返回空串即可"""
    assert _probe("core.formatCoinResult(null)") == ""
    assert _probe("core.formatCoinResult(undefined)") == ""
    assert _probe("core.formatCoinResult('not-array')") == ""


# ============================================================
# pinyinOf
# ============================================================


@pytest.mark.parametrize(
    "name,expected",
    [
        ("乾", "qián"),
        ("坤", "kūn"),
        ("大畜", "dà xù"),
        ("山天大畜", "dà xù"),  # 取尾 2 字
        ("损", "sǔn"),
        ("未知卦", ""),  # 未命中
        ("", ""),
    ],
)
def test_pinyin_of(name: str, expected: str):
    name_js = json.dumps(name)
    assert _probe(f"core.pinyinOf({name_js})") == expected


# ============================================================
# linesVisualClass
# ============================================================


@pytest.mark.parametrize(
    "val,changing,expected",
    [
        (7, False, "h-line"),
        (9, False, "h-line"),
        (8, False, "h-line yin"),
        (6, False, "h-line yin"),
        (9, True, "h-line changing"),
        (6, True, "h-line yin changing"),
    ],
)
def test_lines_visual_class(val: int, changing: bool, expected: str):
    c_arg = "true" if changing else "false"
    assert _probe(f"core.linesVisualClass({val}, {c_arg})") == expected


# ============================================================
# classifyStreamEnd（AI 解读 WebSocket 状态机分类）
# ============================================================


@pytest.mark.parametrize(
    "state,expected",
    [
        # success：done 且收到过实质 content；error 优先级低于 success（done+content+error 仍算成功）
        ({"doneReceived": True, "hadError": False, "hasContent": True}, "success"),
        ({"doneReceived": True, "hadError": True, "hasContent": True}, "success"),
        # no-content：done 但无 content（LLM 整段只走 reasoning / 空响应 —— Codex F1 场景）
        ({"doneReceived": True, "hadError": False, "hasContent": False}, "no-content"),
        # error：有 error 且无 success 条件
        ({"doneReceived": True, "hadError": True, "hasContent": False}, "error"),
        ({"doneReceived": False, "hadError": True, "hasContent": True}, "error"),
        ({"doneReceived": False, "hadError": True, "hasContent": False}, "error"),
        # no-content：既无 done/error 也没收到过任何 content
        ({"doneReceived": False, "hadError": False, "hasContent": False}, "no-content"),
        # interrupted：有部分 content 但未 done 且无显式 error
        ({"doneReceived": False, "hadError": False, "hasContent": True}, "interrupted"),
    ],
)
def test_classify_stream_end(state: dict, expected: str):
    state_js = json.dumps(state)
    assert _probe(f"core.classifyStreamEnd({state_js})") == expected


def test_classify_stream_end_handles_missing_fields():
    # 空对象 / undefined 应被视为 no-content 而非抛错
    assert _probe("core.classifyStreamEnd({})") == "no-content"
    assert _probe("core.classifyStreamEnd()") == "no-content"


# ============================================================
# ganzhi 干支纪年 / 纪月 / 纪日
# ============================================================


def _date_probe(fn: str, iso: str):
    """用本地日期构造 Date，避免 UTC 时区漂移。"""
    y, m, d = iso.split("-")
    return _probe(f"core.{fn}(new Date({y}, {int(m) - 1}, {int(d)}))")


@pytest.mark.parametrize(
    "iso,year,month_day_label",
    [
        # 关键用例：节气边界、锚点、今日
        # 2000-01-01：立春前（算 1999 己卯）；小寒前（1/6）是子月；epoch 本身戊午日
        ("2000-01-01", "己卯", "丙子月 · 戊午日"),
        # 2000-02-04：立春当天切换到庚辰年 + 寅月起点
        ("2000-02-04", "庚辰", "戊寅月 · 壬辰日"),
        # 2024-02-10：甲辰春节（甲辰年已开）
        ("2024-02-10", "甲辰", "丙寅月 · 甲辰日"),
        # 2025-01-29：农历乙巳春节当天，但节气年看立春（2/3）仍是甲辰
        ("2025-01-29", "甲辰", "丁丑月 · 戊戌日"),
        # 2026-04-19：今天（清明后、立夏前 → 辰月）
        ("2026-04-19", "丙午", "壬辰月 · 癸亥日"),
    ],
)
def test_ganzhi_known_dates_simplified_model(iso: str, year: str, month_day_label: str):
    """锁定的是**当前简化模型**的期望输出（立春固定 2/4、节气平均日），
    **不等同于天文历精确值**。详见 iching-core.js 算法头精度说明。

    若将来升级到精确节气表（sxtwl / 寿星天文历），2025-02-03 22:10 等
    "节气时刻前后同一公历日"的用例需要参数化到分钟级并分叉预期。
    （Codex 第九轮 B-M1 采纳）"""
    assert _date_probe("ganzhiOfYear", iso) == year
    assert _date_probe("ganzhiDateLabel", iso) == month_day_label


def test_ganzhi_label_format():
    """装饰性格式：'X 月 · X 日'（中间圆点分隔，"月""日"直接拼在干支后）"""
    label = _date_probe("ganzhiDateLabel", "2026-04-19")
    assert "月 · " in label, "干支标签应含 '月 · ' 分隔"
    assert label.endswith("日"), "干支标签应以 '日' 结尾"
    # 形如 "壬辰月 · 癸亥日" —— 共 9 字符（2 干支 + '月 · ' + 2 干支 + '日'）
    assert len(label) == 9, f"期望标签长 9 字符，实际 {len(label)!r}"


def test_ganzhi_year_crosses_lichun():
    """年柱在立春（~2/4）切换，不是元旦：2026-02-03 仍是乙巳，2026-02-04 切丙午"""
    assert _date_probe("ganzhiOfYear", "2026-02-03") == "乙巳"
    assert _date_probe("ganzhiOfYear", "2026-02-04") == "丙午"


_SIXTY_JIAZI = [
    s + b
    for i, (s, b) in enumerate(
        zip("甲乙丙丁戊己庚辛壬癸" * 6, "子丑寅卯辰巳午未申酉戌亥" * 5)
    )
    if i < 60
]


def _ganzhi_index(gz: str) -> int:
    """给定干支名 → 60 甲子序号（甲子=0, …, 癸亥=59）。"""
    stems = "甲乙丙丁戊己庚辛壬癸"
    branches = "子丑寅卯辰巳午未申酉戌亥"
    stem, branch = stems.index(gz[0]), branches.index(gz[1])
    # 找 i 使 i%10==stem 且 i%12==branch（60 中有且仅一个）
    for i in range(60):
        if i % 10 == stem and i % 12 == branch:
            return i
    raise ValueError(f"非法干支 {gz!r}")


@pytest.mark.parametrize(
    "iso_cur,iso_next,label",
    [
        # 平凡相邻
        ("2026-04-19", "2026-04-20", "plain"),
        # 跨月（月末 → 下月 1 号）
        ("2026-04-30", "2026-05-01", "month-boundary"),
        # 跨年（12/31 → 1/1）
        ("2025-12-31", "2026-01-01", "year-boundary"),
        # 闰日（2028 是闰年：2/29 → 3/1）
        ("2028-02-29", "2028-03-01", "leap-day"),
        # 非闰年 2/28 → 3/1（相邻但 cur 索引不特殊）
        ("2027-02-28", "2027-03-01", "non-leap-feb-end"),
    ],
)
def test_ganzhi_day_advances_exactly_one_step(iso_cur: str, iso_next: str, label: str):
    """日柱必须严格前进 1 位 60 甲子（Codex 第九轮 B-M2 采纳：
    原 `d1 != d2` 断言太弱，跳两位或随机亦能过）。"""
    cur = _date_probe("ganzhiOfDay", iso_cur)
    nxt = _date_probe("ganzhiOfDay", iso_next)
    assert cur in _SIXTY_JIAZI, f"非 60 甲子：{cur!r}"
    assert nxt in _SIXTY_JIAZI, f"非 60 甲子：{nxt!r}"
    expected = _SIXTY_JIAZI[(_ganzhi_index(cur) + 1) % 60]
    assert nxt == expected, (
        f"[{label}] {iso_cur}({cur}) → {iso_next} 期望 {expected}，实际 {nxt}"
    )


def test_ganzhi_handles_invalid_input():
    """非 Date / NaN Date 不应抛异常，返回空串"""
    assert _probe("core.ganzhiDateLabel(null)") == ""
    assert _probe("core.ganzhiDateLabel('2026-04-19')") == ""
    assert _probe("core.ganzhiDateLabel(new Date('not a date'))") == ""
    assert _probe("core.ganzhiOfYear(undefined)") == ""
