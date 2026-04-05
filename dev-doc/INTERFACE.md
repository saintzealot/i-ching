# I-Ching — 接口契约

## 技术栈
- Backend: Python FastAPI
- Frontend: HTML + CSS + Vanilla JS (单页应用)
- Test: pytest

## API 接口

### POST /api/divine
发起一次算卦

**Request Body:**
```json
{
  "question": "string (可选，用户的问题)"
}
```

**Response:**
```json
{
  "hexagram": {
    "number": 1,
    "name": "乾",
    "symbol": "☰☰",
    "lines": [9, 9, 9, 9, 9, 9],
    "upper_trigram": "乾",
    "lower_trigram": "乾"
  },
  "judgment": "元亨利贞。",
  "interpretation": "乾卦象征天...",
  "changing_lines": [1, 3],
  "changed_hexagram": {
    "number": 44,
    "name": "姤",
    "symbol": "☰☴"
  },
  "lines_text": ["初九：潜龙勿用。", ...],
  "question": "string"
}
```

### GET /api/hexagrams
获取64卦列表

**Response:**
```json
[
  {"number": 1, "name": "乾", "symbol": "䷀", "judgment": "元亨利贞。"},
  ...
]
```

### GET /api/hexagrams/{number}
获取单个卦的详细信息

## 数据模型

```python
@dataclass
class Trigram:
    name: str       # 乾/坤/震/巽/坎/离/艮/兑
    symbol: str     # ☰☷☳☴☵☲☶☱
    nature: str     # 天/地/雷/风/水/火/山/泽

@dataclass
class Hexagram:
    number: int          # 1-64
    name: str            # 卦名
    symbol: str          # Unicode 卦符
    upper_trigram: str   # 上卦
    lower_trigram: str   # 下卦
    judgment: str        # 卦辞
    image: str           # 象辞
    lines: list[str]     # 六爻爻辞

@dataclass
class DivinationResult:
    hexagram: Hexagram
    lines: list[int]           # 每爻的值 6/7/8/9
    changing_lines: list[int]  # 动爻位置
    changed_hexagram: Hexagram | None  # 变卦
    question: str
```

## 铜钱摇卦算法
- 模拟投掷三枚铜钱，6次
- 正面(字)=3，反面(花)=2
- 三枚之和: 6=老阴(变), 7=少阳, 8=少阴, 9=老阳(变)
- 从初爻(底)到上爻(顶)依次排列
- 老阴(6)和老阳(9)为动爻，会产生变卦
