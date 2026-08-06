# 契約: CVワーカー → サーバー インターフェース(cv-interface)

CVワーカー(実装: `server/app/cv/`)がサーバー(状態機械)へ渡す検出結果の型。
**モックCV(`server/app/cv/mock.py`)は本契約と同一の型を出す**。サーバー側はモックと実CVを区別しない。
仕様の正: specification.md §4(箱認識サブシステム)。

## 1. ソースのPythonプロトコル

```python
class CvSource(Protocol):
    def poll(self) -> list[CvMessage]:
        """未配信のメッセージを取り出す(なければ空リスト)。サーバーが約30fpsで呼ぶ。"""
```

`CvMessage = CvFrame | CvBoardUpdate`(pydanticモデル、`server/app/cv/interface.py`)。
実CVは別プロセス→キュー経由で受けた結果を `poll()` で返す。モックはキーボード操作の結果を返す。

## 2. CvFrame(連続ストリーム、約30fps、3D表示用)

```jsonc
{
  "kind": "frame",
  "t_ms": 123456,                  // 単調増加のタイムスタンプ(ms)
  "mat_corners_detected": 4,       // マット四隅タグ(ID 200-203)の検出数。セルフチェック用
  "boxes": [                        // 常に9箱すべて(ロスト中も保持位置で含める。§4.2)
    {
      "box_id": "large-1",         // tag_master.json の box(large|medium|small - 1..3)
      "size": "large",             // "large" | "medium" | "small"
      "pos_mm": [150.0, 300.0, 0.0],  // マット座標系での箱の底面中心 [x, y, z]
      "quat": [0.0, 0.0, 0.0, 1.0],   // 姿勢クォータニオン [x, y, z, w]。単位=無回転(面1が上)
      "area": "A",                 // "A" | "B" | "C" | "staging" | null(移動中・掴まれ中)
      "level": 0,                  // 塔内の段(下から0)。area が塔以外なら null
      "visible": true,             // false = タグロスト中(最後の確定位置を保持して送る)
      "seen_tag_ids": [0, 2]       // このフレームで検出できたタグID(visible=false なら空)
    }
  ]
}
```

- マット座標系: マット左手前隅が原点、x=右方向、y=奥(塔)方向、z=上方向、単位mm。
  実CVはホモグラフィでこの座標系に変換する。モックは固定レイアウト(mock.py 冒頭の定数)で座標を合成する。
- タグロスト時は最後の確定位置を目安2秒保持し `visible: false` で送り続ける(仕様§4.2)。

## 3. CvBoardUpdate(イベント、確定盤面の変化時のみ)

論理盤面が **Nフレーム(目安0.3秒)連続で同一** になり確定盤面が変化したときに送る(仕様§4.1-6)。
起動後の**最初の確定盤面も1回送る**(サーバーはこれを最新盤面の初期値にする。モックは初期状態
=全箱待機を初回 `poll()` で返す)。同一 `poll()` バッチ内のメッセージは時系列順(t_ms 非減少)。

```jsonc
{
  "kind": "board",
  "t_ms": 123456,
  "towers": ["LMS", "", "L"],      // A/B/C の生スタック(下から上)。違反時は "SL" 等もあり得る
  "board": "LMS//L",               // "/".join(towers)。legal=true のとき board.md の正準形
  "legal": true,                   // 配置ルール(ルールブック§3)を満たすか
  "violations": [],                // legal=false のときの違反リスト(下表)
  "staging_box_ids": ["small-3"],  // 待機エリアにある箱(盤面には含まれない)
  "tower_box_ids": [               // 塔ごとの箱の個体(下から上)。towers と同じ並び
    ["large-1", "medium-1", "small-1"], [], ["large-2"]
  ]
}
```

- 掴まれ中・移動中の箱はどの塔にも属さない(towers にも staging にも含めない)。
- `tower_box_ids` のサイズ列は `towers` と一致する(モデルのバリデータで保証)。
- **「確定盤面が変化した」の判定には `tower_box_ids` まで含める。** 同サイズの箱を塔間で
  入れ替えただけだと `towers` は変わらないが、クリア条件2は箱の個体で判定する
  (ルールブック§5)ため、送らないとサーバーが入れ替え前の箱構成のまま判定してしまう。
- サーバーは `tower_box_ids` を**判定にも重複判定にも使わない**(判定は `board` のみ)。
  用途は判定履歴への記録と記録画面での表示(firestore.md §1)。
- 判定エンジンに渡せるのは `legal: true` の board のみ。`legal: false` の間、サーバーは
  警告表示+判定ボタン無効化を行う(仕様§4.2)。

### violation の型

```jsonc
{ "tower": "B", "type": "size_order" }
```

| type | 意味 |
|---|---|
| `size_order` | 小さい箱の上に大きい箱が乗っている |
| `duplicate_size` | 同じ塔に同サイズが2個以上 |
| `overflow` | 1塔に4個以上 |

## 4. モックCVの操作(make mock)

`server/app/cv/mock_cli.py`。標準入力のコマンドで論理盤面を操作し、emit される CvMessage をJSONで表示する。

| コマンド | 動作 |
|---|---|
| `grab <box>` | 箱を掴む(例 `grab L1` = large-1)。掴んだ箱は area=null になる |
| `place <A\|B\|C\|W>` | 掴んでいる箱を塔A/B/C または待機エリア(W)に置く。違反配置も許す(違反検出のテスト用) |
| `board <盤面文字列>` | 論理盤面を一括セット(例 `board LMS//L`)。残りの箱は待機エリアへ |
| `show` | 現在の状態を表示 |
| `quit` | 終了 |

置く・一括セットの操作後に確定盤面(CvBoardUpdate)を emit する(モックは安定待ち0.3秒を即時とみなす)。
