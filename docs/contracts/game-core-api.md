# 契約: ゲームコアAPI(game-core-api)

判定エンジン(実装: `server/app/core/`、S1)の関数シグネチャと事前計算テーブルのスキーマ。
ルールの正: [../game/hanoi_arrange_rules.md](../game/hanoi_arrange_rules.md)。盤面表現: [board.md](board.md)。

## 1. 盤面ユーティリティ(`app/core/board.py`、S0で作成済み)

```python
Size = Literal["L", "M", "S"]
Tower = Literal["A", "B", "C"]

TOWER_STATES: tuple[str, ...]        # ("", "S", "M", "L", "MS", "LS", "LM", "LMS")

def is_legal_tower(tower: str) -> bool          # 塔文字列が8状態のいずれか
def parse_board(board: str) -> tuple[str, str, str]   # "LMS//L" -> ("LMS", "", "L")。不正形式は ValueError
def format_board(towers: Sequence[str]) -> str
def is_legal_board(board: str) -> bool
def mirror_board(board: str) -> str             # A塔とC塔を入れ替え
def canonical_key(board: str) -> str            # min(board, mirror_board(board)) 辞書順
def board_index(board: str) -> int              # 0..511(board.md §4)。不正盤面は ValueError
def board_from_index(index: int) -> str
def box_count(board: str) -> int                # 盤面上の箱の総数(得点の係数)
```

## 2. 判定エンジン(S1で実装)

```python
class Judgement(BaseModel):
    result: Literal["scored", "unclearable", "duplicate_same", "duplicate_mirror"]
    points: int                 # 獲得点。scored 以外は 0
    min_moves: int | None       # クリア可能時の最短手数(unclearable は None)
    canonical_key: str          # 重複照合に使った正準キー

def judge(board: str, judged_keys: AbstractSet[str], table: PrecomputeTable) -> Judgement
    # board: 合法盤面文字列(呼び出し側が legal を保証する)
    # judged_keys: このプレイで既に判定済みの canonical_key の集合(scored/duplicate は呼び出し側が追加)
    # 規則(ルールブック§6):
    #   - クリア不可 -> unclearable(失敗カウント+1は呼び出し側)
    #   - canonical_key が judged_keys にあり、盤面文字列も完全一致で判定済み -> duplicate_same
    #     鏡像のみ一致 -> duplicate_mirror(いずれも0点)
    #   - それ以外でクリア可能 -> scored, points = box_count(board) * min_moves

def score(board: str, table: PrecomputeTable) -> int   # box_count * min_moves。クリア不可は 0
def min_path(board: str, table: PrecomputeTable) -> list[Move] | None
```

`duplicate_same` / `duplicate_mirror` の区別のため、呼び出し側(状態機械)は判定済み盤面の
**生の盤面文字列の集合**も保持する(canonical_key 集合と併用)。

## 3. 事前計算テーブル(S1で生成)

- 生成: `server/app/core/precompute.py`(BFSで全512盤面を探索)→ JSON 出力。
- 配置: `server/app/core/data/precompute.json`(ビルド時生成の静的アセット。リポジトリにコミットし、
  ローカル/クラウド(記録画面のシミュレーション再生)で共用する)。
- 検証: 独立実装の総当たりBFSとの照合テストで512盤面全一致(S1のDoD)。

### JSONスキーマ

```jsonc
{
  "version": 1,
  "boards": [                    // 512要素、board_index 順
    {
      "board": "LMS//L",         // 盤面文字列(正準形)
      "index": 451,              // board_index(board) と一致(7*64 + 0*8 + 3)
      "clearable": true,
      "min_moves": 3,            // clearable=false なら null
      "min_path": [              // 最短手順。clearable=false なら null。0手クリアは存在しない
        { "size": "S", "from": "A", "to": "B" },
        { "size": "M", "from": "A", "to": "C" },
        { "size": "S", "from": "B", "to": "C" }
      ],
      "mirror": "L//LMS",        // 鏡像の盤面文字列
      "canonical_key": "L//LMS"
    }
  ]
}
```

### Move 型

```python
class Move(BaseModel):
    size: Size            # 動かす箱のサイズ(一番上の箱なのでサイズで一意)
    from_: Tower          # JSON キーは "from"(pydantic alias)
    to: Tower
```

## 4. クリア条件(実装の正はルールブック§5)

- 枚数配置 (a,b,c) が反転 (c,b,a) になり、かつ最終盤面 ≠ 初期盤面。
- 参考検算値: クリア可能 231/512、鏡像同一視で119クラス、最短手数の最大は7手(`LMS//`)、
  総得点プール839点。S1のテストでこの値と一致することを確認する。
