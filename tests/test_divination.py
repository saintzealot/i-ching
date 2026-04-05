from __future__ import annotations

import dataclasses
from typing import Any

import pytest


# 八卦名称的接口契约
TRIGRAM_NAMES = {"乾", "坤", "震", "巽", "坎", "离", "艮", "兑"}


def _fail(message: str) -> None:
    """统一输出更清晰的测试失败信息。"""
    pytest.fail(message, pytrace=False)


def _import_divination_module():
    """延迟导入算卦模块，避免在收集阶段直接报错。"""
    try:
        import backend.divination as divination
    except ModuleNotFoundError as exc:
        _fail(f"无法导入 `backend.divination`：{exc}")
    except Exception as exc:  # pragma: no cover - 用于提供更清晰的错误信息
        _fail(f"导入 `backend.divination` 失败：{exc}")
    return divination


def _import_hexagrams_data_module():
    """延迟导入卦象数据模块。"""
    try:
        import backend.hexagrams_data as hexagrams_data
    except ModuleNotFoundError as exc:
        _fail(f"无法导入 `backend.hexagrams_data`：{exc}")
    except Exception as exc:  # pragma: no cover - 用于提供更清晰的错误信息
        _fail(f"导入 `backend.hexagrams_data` 失败：{exc}")
    return hexagrams_data


def _import_main_module():
    """延迟导入 FastAPI 应用模块。"""
    try:
        import backend.main as main
    except ModuleNotFoundError as exc:
        _fail(f"无法导入 `backend.main`：{exc}")
    except Exception as exc:  # pragma: no cover - 用于提供更清晰的错误信息
        _fail(f"导入 `backend.main` 失败：{exc}")
    return main


def _get_field(obj: Any, field_name: str) -> Any:
    """兼容 dataclass / Pydantic / 普通对象 / dict 的字段读取。"""
    if isinstance(obj, dict):
        if field_name not in obj:
            raise AssertionError(f"缺少字段 `{field_name}`")
        return obj[field_name]

    if dataclasses.is_dataclass(obj):
        return getattr(obj, field_name)

    model_dump = getattr(obj, "model_dump", None)
    if callable(model_dump):
        data = model_dump()
        if field_name in data:
            return data[field_name]

    to_dict = getattr(obj, "dict", None)
    if callable(to_dict):
        data = to_dict()
        if field_name in data:
            return data[field_name]

    if hasattr(obj, field_name):
        return getattr(obj, field_name)

    raise AssertionError(f"缺少字段 `{field_name}`")


def _get_collection(module: Any, *names: str) -> Any:
    """从模块中读取约定的数据集合。"""
    for name in names:
        if hasattr(module, name):
            return getattr(module, name)
    _fail(f"模块 `{module.__name__}` 中缺少数据集合：{', '.join(names)}")


def _collection_values(collection: Any) -> list[Any]:
    """将 list / tuple / dict 等集合统一为值列表。"""
    if isinstance(collection, dict):
        return list(collection.values())
    if isinstance(collection, (list, tuple, set)):
        return list(collection)
    _fail(f"不支持的数据集合类型：{type(collection)!r}")


def _get_hexagrams(data_module: Any) -> list[Any]:
    """读取 64 卦数据。"""
    collection = _get_collection(data_module, "HEXAGRAMS", "hexagrams")
    return _collection_values(collection)


def _get_trigrams(data_module: Any) -> list[Any]:
    """读取八卦数据。如果是 dict（key=卦名），自动将 key 注入 value 的 'name' 字段。"""
    collection = _get_collection(data_module, "TRIGRAMS", "trigrams")
    if isinstance(collection, dict):
        result = []
        for name, value in collection.items():
            if isinstance(value, dict):
                entry = {**value, "name": name}
            else:
                entry = value
            result.append(entry)
        return result
    return _collection_values(collection)


def _get_coin_toss(divination_module: Any) -> tuple[str, Any]:
    """查找单次摇爻函数。"""
    for name in ("coin_toss", "toss_coins", "toss_coin", "throw_coins", "cast_line"):
        func = getattr(divination_module, name, None)
        if callable(func):
            return name, func
    _fail(
        "`backend.divination` 需要暴露单次摇爻函数，"
        "例如 `coin_toss()`，以便验证铜钱结果范围。"
    )


def _get_lookup_func(divination_module: Any):
    """查找根据上下卦定位六十四卦的函数。"""
    for name in (
        "lookup_hexagram",
        "get_hexagram_by_trigrams",
        "find_hexagram_by_trigrams",
        "hexagram_lookup",
    ):
        func = getattr(divination_module, name, None)
        if callable(func):
            return func
    _fail(
        "`backend.divination` 需要暴露按上下卦查找卦象的函数，"
        "例如 `lookup_hexagram(upper, lower)`。"
    )


def _lookup_hexagram(divination_module: Any, upper: str, lower: str) -> Any:
    """兼容不同参数写法调用卦象查找函数。"""
    lookup = _get_lookup_func(divination_module)

    try:
        return lookup(upper=upper, lower=lower)
    except TypeError:
        try:
            return lookup(upper, lower)
        except TypeError as exc:
            _fail(f"卦象查找函数调用失败：{exc}")


def _get_divine_func(divination_module: Any):
    """读取主算卦函数，优先使用 perform_divination（返回完整结果）。"""
    for name in ("perform_divination", "divine"):
        func = getattr(divination_module, name, None)
        if callable(func):
            return func
    _fail("`backend.divination` 中缺少 `divine()` 或 `perform_divination()` 函数。")


def _call_divine(divination_module: Any, question: str | None = None) -> Any:
    """兼容是否接收 question 参数的 divine() 调用。"""
    divine = _get_divine_func(divination_module)

    if question is None:
        try:
            return divine()
        except TypeError:
            return divine("")

    try:
        return divine(question=question)
    except TypeError:
        try:
            return divine(question)
        except TypeError as exc:
            _fail(f"`divine()` 调用失败：{exc}")


def _patch_coin_sequence(monkeypatch: pytest.MonkeyPatch, divination_module: Any, sequence: list[int]) -> None:
    """将随机摇卦替换为固定爻序列，确保测试稳定。"""
    func_name, _ = _get_coin_toss(divination_module)
    values = iter(sequence)

    def fake_coin_toss() -> int:
        try:
            return next(values)
        except StopIteration:
            _fail("固定摇卦序列已耗尽，说明 `divine()` 调用次数超过 6 次。")

    monkeypatch.setattr(divination_module, func_name, fake_coin_toss)


def _get_result_lines(result: Any) -> list[int]:
    """从 DivinationResult 中读取六爻值。"""
    # perform_divination 返回嵌套结构: result["hexagram"]["lines"]
    if isinstance(result, dict) and "hexagram" in result:
        hexagram = result["hexagram"]
        if isinstance(hexagram, dict) and "lines" in hexagram:
            return hexagram["lines"]
    lines = _get_field(result, "lines")
    assert isinstance(lines, list), "DivinationResult.lines 必须是 list"
    return lines


def _get_result_changing_lines(result: Any) -> list[int]:
    """读取动爻位置列表。"""
    changing_lines = _get_field(result, "changing_lines")
    assert isinstance(changing_lines, list), "DivinationResult.changing_lines 必须是 list"
    return changing_lines


def _get_result_changed_hexagram(result: Any) -> Any:
    """读取变卦。"""
    return _get_field(result, "changed_hexagram")


def _assert_hexagram_fields(hexagram: Any) -> None:
    """校验 Hexagram 数据模型必备字段。"""
    number = _get_field(hexagram, "number")
    name = _get_field(hexagram, "name")
    symbol = _get_field(hexagram, "symbol")
    upper_trigram = _get_field(hexagram, "upper_trigram")
    lower_trigram = _get_field(hexagram, "lower_trigram")
    judgment = _get_field(hexagram, "judgment")
    image = _get_field(hexagram, "image")
    lines = _get_field(hexagram, "lines")

    assert isinstance(number, int) and 1 <= number <= 64
    assert isinstance(name, str) and name
    assert isinstance(symbol, str) and symbol
    assert isinstance(upper_trigram, str) and upper_trigram in TRIGRAM_NAMES
    assert isinstance(lower_trigram, str) and lower_trigram in TRIGRAM_NAMES
    assert isinstance(judgment, str) and judgment
    assert isinstance(image, str) and image
    assert isinstance(lines, list) and len(lines) == 6
    assert all(isinstance(line, str) and line for line in lines)


def _assert_trigram_fields(trigram: Any) -> None:
    """校验 Trigram 数据模型必备字段。"""
    name = _get_field(trigram, "name")
    symbol = _get_field(trigram, "symbol")
    nature = _get_field(trigram, "nature")

    assert isinstance(name, str) and name in TRIGRAM_NAMES
    assert isinstance(symbol, str) and symbol
    assert isinstance(nature, str) and nature


def _assert_divine_api_response(payload: dict[str, Any]) -> None:
    """校验 POST /api/divine 的响应结构。"""
    assert isinstance(payload, dict)

    required_top_level_fields = {
        "hexagram",
        "judgment",
        "interpretation",
        "changing_lines",
        "changed_hexagram",
        "lines_text",
        "question",
    }
    assert required_top_level_fields.issubset(payload.keys())

    hexagram = payload["hexagram"]
    assert isinstance(hexagram, dict)
    assert {"number", "name", "symbol", "lines", "upper_trigram", "lower_trigram"}.issubset(hexagram.keys())
    assert isinstance(hexagram["number"], int) and 1 <= hexagram["number"] <= 64
    assert isinstance(hexagram["name"], str) and hexagram["name"]
    assert isinstance(hexagram["symbol"], str) and hexagram["symbol"]
    assert isinstance(hexagram["upper_trigram"], str) and hexagram["upper_trigram"] in TRIGRAM_NAMES
    assert isinstance(hexagram["lower_trigram"], str) and hexagram["lower_trigram"] in TRIGRAM_NAMES
    assert isinstance(hexagram["lines"], list) and len(hexagram["lines"]) == 6
    assert all(line in {6, 7, 8, 9} for line in hexagram["lines"])

    assert isinstance(payload["judgment"], str) and payload["judgment"]
    assert isinstance(payload["interpretation"], str) and payload["interpretation"]
    assert isinstance(payload["changing_lines"], list)
    assert all(isinstance(pos, int) and 1 <= pos <= 6 for pos in payload["changing_lines"])

    changed_hexagram = payload["changed_hexagram"]
    if changed_hexagram is not None:
        assert isinstance(changed_hexagram, dict)
        assert {"number", "name", "symbol"}.issubset(changed_hexagram.keys())
        assert isinstance(changed_hexagram["number"], int) and 1 <= changed_hexagram["number"] <= 64
        assert isinstance(changed_hexagram["name"], str) and changed_hexagram["name"]
        assert isinstance(changed_hexagram["symbol"], str) and changed_hexagram["symbol"]

    assert isinstance(payload["lines_text"], list) and len(payload["lines_text"]) == 6
    assert all(isinstance(text, str) and text for text in payload["lines_text"])
    assert isinstance(payload["question"], str)


@pytest.fixture(scope="module")
def divination_module():
    """提供 backend.divination 模块。"""
    return _import_divination_module()


@pytest.fixture(scope="module")
def hexagrams_data_module():
    """提供 backend.hexagrams_data 模块。"""
    return _import_hexagrams_data_module()


@pytest.fixture(scope="module")
def main_module():
    """提供 backend.main 模块。"""
    return _import_main_module()


@pytest.fixture()
def client(main_module):
    """创建 FastAPI TestClient。"""
    from fastapi.testclient import TestClient

    app = getattr(main_module, "app", None)
    if app is None:
        _fail("`backend.main` 中缺少 FastAPI 实例 `app`。")
    return TestClient(app)


# ----------------------------
# 算卦逻辑测试
# ----------------------------


def test_coin_toss(divination_module):
    """铜钱投掷结果必须落在 6/7/8/9 范围内。"""
    _, coin_toss = _get_coin_toss(divination_module)
    results = [coin_toss() for _ in range(100)]

    assert results, "coin_toss() 应至少返回一个结果"
    assert all(result in {6, 7, 8, 9} for result in results)


def test_divine_returns_six_lines(divination_module):
    """divine() 应返回 6 个爻值。"""
    result = _call_divine(divination_module)
    lines = _get_result_lines(result)

    assert len(lines) == 6


def test_line_values_valid(divination_module):
    """每爻值都必须是 6/7/8/9。"""
    result = _call_divine(divination_module)
    lines = _get_result_lines(result)

    assert all(line in {6, 7, 8, 9} for line in lines)


def test_changing_lines_identified(divination_module, monkeypatch):
    """6 和 9 必须被识别为动爻，且位置按自下而上从 1 开始计数。"""
    expected_lines = [6, 7, 8, 9, 8, 7]
    _patch_coin_sequence(monkeypatch, divination_module, expected_lines)

    result = _call_divine(divination_module, question="测试动爻识别")
    lines = _get_result_lines(result)
    changing_lines = _get_result_changing_lines(result)
    changed_hexagram = _get_result_changed_hexagram(result)

    assert lines == expected_lines
    assert changing_lines == [1, 4]
    assert changed_hexagram is not None


def test_no_changing_lines(divination_module, monkeypatch):
    """没有 6/9 时，不应生成变卦。"""
    expected_lines = [7, 8, 7, 8, 7, 8]
    _patch_coin_sequence(monkeypatch, divination_module, expected_lines)

    result = _call_divine(divination_module, question="测试无动爻")
    changing_lines = _get_result_changing_lines(result)
    changed_hexagram = _get_result_changed_hexagram(result)

    assert changing_lines == []
    assert changed_hexagram is None


def test_hexagram_lookup(divination_module):
    """乾上乾下应查到第一卦乾卦。"""
    hexagram = _lookup_hexagram(divination_module, upper="乾", lower="乾")

    assert hexagram is not None
    assert _get_field(hexagram, "number") == 1
    assert _get_field(hexagram, "name") == "乾"
    assert _get_field(hexagram, "upper_trigram") == "乾"
    assert _get_field(hexagram, "lower_trigram") == "乾"


def test_all_trigram_combinations(divination_module, hexagrams_data_module):
    """8x8 的所有上下卦组合都必须能查到对应卦象。"""
    trigrams = _get_trigrams(hexagrams_data_module)
    trigram_names = {_get_field(trigram, "name") for trigram in trigrams}
    seen_numbers = set()

    assert trigram_names == TRIGRAM_NAMES

    for upper in trigram_names:
        for lower in trigram_names:
            hexagram = _lookup_hexagram(divination_module, upper=upper, lower=lower)
            assert hexagram is not None, f"未找到上卦={upper}、下卦={lower} 的卦象"
            assert _get_field(hexagram, "upper_trigram") == upper
            assert _get_field(hexagram, "lower_trigram") == lower
            seen_numbers.add(_get_field(hexagram, "number"))

    assert len(seen_numbers) == 64


# ----------------------------
# API 端点测试
# ----------------------------


def test_divine_endpoint(client):
    """POST /api/divine 应返回符合契约的算卦结果。"""
    response = client.post("/api/divine", json={})

    assert response.status_code == 200
    _assert_divine_api_response(response.json())


def test_divine_with_question(client):
    """带问题发起算卦时，响应中应保留原问题。"""
    question = "今年事业如何？"
    response = client.post("/api/divine", json={"question": question})

    assert response.status_code == 200
    payload = response.json()
    _assert_divine_api_response(payload)
    assert payload["question"] == question


def test_hexagrams_list(client):
    """GET /api/hexagrams 应返回 64 卦列表。"""
    response = client.get("/api/hexagrams")

    assert response.status_code == 200
    payload = response.json()

    assert isinstance(payload, list)
    assert len(payload) == 64

    numbers = set()
    for item in payload:
        assert {"number", "name", "symbol", "judgment"}.issubset(item.keys())
        assert isinstance(item["number"], int) and 1 <= item["number"] <= 64
        assert isinstance(item["name"], str) and item["name"]
        assert isinstance(item["symbol"], str) and item["symbol"]
        assert isinstance(item["judgment"], str) and item["judgment"]
        numbers.add(item["number"])

    assert numbers == set(range(1, 65))


def test_hexagram_detail(client):
    """GET /api/hexagrams/1 应返回乾卦详情。"""
    response = client.get("/api/hexagrams/1")

    assert response.status_code == 200
    payload = response.json()

    assert payload["number"] == 1
    assert payload["name"] == "乾"
    assert payload["upper_trigram"] == "乾"
    assert payload["lower_trigram"] == "乾"
    assert isinstance(payload["symbol"], str) and payload["symbol"]
    assert isinstance(payload["judgment"], str) and payload["judgment"]
    assert isinstance(payload["image"], str) and payload["image"]
    assert isinstance(payload["lines"], list) and len(payload["lines"]) == 6


def test_hexagram_not_found(client):
    """不存在的卦序号应返回 404。"""
    response = client.get("/api/hexagrams/99")

    assert response.status_code == 404


# ----------------------------
# 数据完整性测试
# ----------------------------


def test_64_hexagrams_exist(hexagrams_data_module):
    """必须提供完整 64 卦数据。"""
    hexagrams = _get_hexagrams(hexagrams_data_module)
    numbers = {_get_field(hexagram, "number") for hexagram in hexagrams}

    assert len(hexagrams) == 64
    assert numbers == set(range(1, 65))


def test_hexagram_has_required_fields(hexagrams_data_module):
    """每一卦都必须包含接口契约定义的必备字段。"""
    hexagrams = _get_hexagrams(hexagrams_data_module)

    for hexagram in hexagrams:
        _assert_hexagram_fields(hexagram)


def test_trigrams_complete(hexagrams_data_module):
    """八卦数据必须完整，且字段齐全。"""
    trigrams = _get_trigrams(hexagrams_data_module)
    names = set()

    assert len(trigrams) == 8

    for trigram in trigrams:
        _assert_trigram_fields(trigram)
        names.add(_get_field(trigram, "name"))

    assert names == TRIGRAM_NAMES
