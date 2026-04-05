"""
周易铜钱摇卦算法

铜钱法规则：
- 模拟投掷三枚铜钱，共投掷6次（从初爻到上爻）
- 正面(字)=3，反面(花)=2
- 三枚铜钱之和：6=老阴(变), 7=少阳, 8=少阴, 9=老阳(变)
- 老阴(6)和老阳(9)为动爻，会产生变卦
- 阳爻(7,9)对应二进制1，阴爻(6,8)对应二进制0
"""

import random
from .hexagrams_data import (
    TRIGRAMS,
    lookup_hexagram_number,
    get_hexagram_by_number,
)


def coin_toss() -> int:
    """
    模拟投掷三枚铜钱
    每枚铜钱：正面(字)=3, 反面(花)=2
    返回三枚铜钱之和：6(老阴), 7(少阳), 8(少阴), 9(老阳)
    """
    coins = [random.choice([2, 3]) for _ in range(3)]
    return sum(coins)


def divine() -> dict:
    """
    完整的摇卦过程：投掷6次铜钱，得到6个爻
    返回6个爻的值列表（从初爻到上爻）
    """
    lines = [coin_toss() for _ in range(6)]
    return lines


def lines_to_binary(lines: list[int]) -> tuple[int, ...]:
    """
    将爻值列表转换为二进制表示
    阳爻(7,9) -> 1, 阴爻(6,8) -> 0
    """
    return tuple(1 if line in (7, 9) else 0 for line in lines)


def binary_to_trigram_name(binary: tuple[int, ...]) -> str | None:
    """
    将三位二进制转换为卦名
    """
    for name, data in TRIGRAMS.items():
        if data["binary"] == binary:
            return name
    return None


def get_trigrams_from_lines(lines: list[int]) -> tuple[str, str]:
    """
    从6个爻值中提取上下卦
    下卦：初爻到三爻（lines[0:3]）
    上卦：四爻到上爻（lines[3:6]）
    """
    binary = lines_to_binary(lines)

    # 下卦：初爻(0)、二爻(1)、三爻(2)
    lower_binary = binary[0:3]
    # 上卦：四爻(3)、五爻(4)、上爻(5)
    upper_binary = binary[3:6]

    lower_name = binary_to_trigram_name(lower_binary)
    upper_name = binary_to_trigram_name(upper_binary)

    return upper_name, lower_name


def get_changing_lines(lines: list[int]) -> list[int]:
    """
    获取动爻位置列表（1-indexed）
    老阴(6)和老阳(9)为动爻
    """
    changing = []
    for i, line in enumerate(lines):
        if line in (6, 9):
            changing.append(i + 1)  # 1-indexed: 1=初爻, 6=上爻
    return changing


def get_changed_lines(lines: list[int]) -> list[int]:
    """
    根据动爻计算变卦后的爻值
    老阳(9) -> 少阴(8)：阳变阴
    老阴(6) -> 少阳(7)：阴变阳
    其余不变
    """
    changed = []
    for line in lines:
        if line == 9:
            changed.append(8)  # 老阳变阴
        elif line == 6:
            changed.append(7)  # 老阴变阳
        else:
            changed.append(line)
    return changed


def get_changing_hexagram(lines: list[int]) -> dict | None:
    """
    根据动爻计算变卦
    如果没有动爻则返回None
    """
    changing_lines = get_changing_lines(lines)
    if not changing_lines:
        return None

    # 计算变卦的爻值
    changed = get_changed_lines(lines)
    # 获取变卦的上下卦
    upper_name, lower_name = get_trigrams_from_lines(changed)
    if not upper_name or not lower_name:
        return None

    # 查找变卦
    number = lookup_hexagram_number(upper_name, lower_name)
    if number is None:
        return None

    return get_hexagram_by_number(number)


def lookup_hexagram(upper: str, lower: str) -> dict | None:
    """
    根据上下卦名查找64卦
    """
    number = lookup_hexagram_number(upper, lower)
    if number is None:
        return None
    return get_hexagram_by_number(number)


def perform_divination(question: str = "") -> dict:
    """
    执行完整的算卦流程
    返回包含本卦、变卦、动爻等完整信息的结果字典
    """
    # 1. 摇卦得到6个爻值
    lines = divine()

    # 2. 获取上下卦名
    upper_name, lower_name = get_trigrams_from_lines(lines)

    # 3. 查找本卦
    hexagram_number = lookup_hexagram_number(upper_name, lower_name)
    hexagram_data = get_hexagram_by_number(hexagram_number)

    # 4. 获取动爻
    changing_lines = get_changing_lines(lines)

    # 5. 获取变卦
    changed_hexagram_data = get_changing_hexagram(lines)

    # 6. 构建上下卦符号
    upper_symbol = TRIGRAMS[upper_name]["symbol"]
    lower_symbol = TRIGRAMS[lower_name]["symbol"]

    # 7. 构建返回结果
    result = {
        "hexagram": {
            "number": hexagram_data["number"],
            "name": hexagram_data["name"],
            "symbol": f"{upper_symbol}{lower_symbol}",
            "lines": lines,
            "upper_trigram": upper_name,
            "lower_trigram": lower_name,
        },
        "judgment": hexagram_data["judgment"],
        "interpretation": hexagram_data["image"],
        "changing_lines": changing_lines,
        "changed_hexagram": None,
        "lines_text": hexagram_data["lines"],
        "question": question,
    }

    # 8. 如果有变卦，添加变卦信息
    if changed_hexagram_data:
        changed_upper = changed_hexagram_data["upper_trigram"]
        changed_lower = changed_hexagram_data["lower_trigram"]
        changed_upper_symbol = TRIGRAMS[changed_upper]["symbol"]
        changed_lower_symbol = TRIGRAMS[changed_lower]["symbol"]
        result["changed_hexagram"] = {
            "number": changed_hexagram_data["number"],
            "name": changed_hexagram_data["name"],
            "symbol": f"{changed_upper_symbol}{changed_lower_symbol}",
        }

    return result
