# hanoi_markers — H/A/N/O/I カスタムマーカー

人間には **H / A / N / O / I の文字として読め**、OpenCV には **5種類の異なるIDとして
安定認識できる** 7×7カスタムマーカー。`cv2.aruco` のカスタムDictionaryとして実装
(本家AprilTagライブラリは変更しない)。

> **注意**: hanoi-cube 本番CV(`server/app/cv/`)は契約
> [cv-interface](../docs/contracts/cv-interface.md) どおり tag36h11 +
> `output/tag_master.json` を使う。本ディレクトリは独立した自己完結PoCであり、
> 契約・本番CVには一切手を入れていない。

## ビット規約

**`1 = 白(文字ストローク) / 0 = 黒(背景)`**。OpenCV aruco の内部規約と同一
(`generateImageMarker` で bit=1 のセルが白く描かれることを実験で確認済み)。

## ID対応

| ID | 文字 |
|----|------|
| 0  | H |
| 1  | A |
| 2  | N |
| 3  | O |
| 4  | I |

```python
LABELS = {0: "H", 1: "A", 2: "N", 3: "O", 4: "I"}
```

## 使い方

依存: `opencv-python>=4.7`(aruco同梱)+ `numpy`。hanoi-cube の server venv に
既に入っているため、リポジトリルートから `cd server && uv run ...` で動く。
単体利用は `pip install -r requirements.txt`。

```bash
cd server
uv run python ../hanoi_markers/scripts/optimize_markers.py   # パターン探索(seed=42、再現可)
uv run python ../hanoi_markers/scripts/generate_markers.py   # markers/*.png 生成
uv run python ../hanoi_markers/scripts/detect.py sample.jpg  # 検出+枠・ラベル描画
uv run pytest ../hanoi_markers/tests -q                      # 自己テスト
```

```python
from src.dictionary import create_hanoi_dictionary, LABELS
from src.detector import detect_letters

dictionary = create_hanoi_dictionary()
for det in detect_letters(image):
    print(f"Detected: {det.label}")
```

## 設計

### ベース形 → 最適化

各文字を「固定bit(文字ストローク。最適化後も**1bitも欠けない**ことをテストで保証)」と
「変更可能bit(ストロークに上下左右で隣接する背景セルのみ。白を足すとセリフ/ヒゲに
見えるため可読性を保つ。1文字あたり最大6bit)」に分け、変更可能bitだけを探索した。

なお I のベース形は上下バーを短くしてある。フルバー(`■■■■■■■`)だと
**I(90°) が H(0°) と完全一致**する(H=左右縦棒+中央横棒、I(90°)=上下横棒+中央縦棒が
回転で同型)ため、ベース形の段階で距離を確保した。

### 探索アルゴリズム

ランダム再スタート付き **simulated annealing**(`src/optimizer.py`、seed=42 で決定的)。
変更可能bit全体の全探索は 2^60 超で不可能なため、SA(6再スタート×20,000反復、約13秒)を
採用。目的は辞書式に:

1. H/A/N/O/I として人間が読める(固定bit+隣接制約+6bit上限で構造的に保証)
2. 回転方向を区別できる(同一文字の回転間距離も目的関数に含む)
3. 20パターン(5文字×4回転)間の最小Hamming距離を最大化
4. タイブレーク: 最小距離を取るペア数を最小化 → 元の文字からの変更bit数を最小化

### 採用パターン(original / optimized / difference)

```
H (変更6bit)                A (変更2bit)                N (変更6bit)
original   optimized        original   optimized        original   optimized
■□□□□□■  ■□□□□□■   □□■■■□□  □□■■■□□   ■□□□□□■  ■□□□□□■
■□□□□□■  ■□□□□■■   □■□□□■□  □■□□□■□   ■■□□□□■  ■■□□□□■
■□□□□□■  ■□□□□■■   ■□□□□□■  ■□■□■□■   ■□■□□□■  ■■■□□■■
■■■■■■■  ■■■■■■■   ■■■■■■■  ■■■■■■■   ■□□■□□■  ■■□■□□■
■□□□□□■  ■□■□□■■   ■□□□□□■  ■□□□□□■   ■□□□■□■  ■□□□■□■
■□□□□□■  ■□□□□□■   ■□□□□□■  ■□□□□□■   ■□□□□■■  ■■□□■■■
■□□□□□■  ■■□□□■■   ■□□□□□■  ■□□□□□■   ■□□□□□■  ■□□□□■■

O (変更6bit)                I (変更6bit)
original   optimized        original   optimized
□■■■■■□  ■■■■■■□   □■■■■■□  □■■■■■■
■□□□□□■  ■■□□□□■   □□□■□□□  □□■■□■□
■□□□□□■  ■□□□□■■   □□□■□□□  □□□■□□□
■□□□□□■  ■□□□□■■   □□□■□□□  □□□■■□□
■□□□□□■  ■□□□□■■   □□□■□□□  □□■■□□□
■□□□□□■  ■■□□□□■   □□□■□□□  □□□■□■□
□■■■■■□  □■■■■■□   □■■■■■□  □■■■■■□
```

変更bitはすべて「白の追加」(＋)で、内訳は H=6, A=2, N=6, O=6, I=6(合計26bit)。
差分の正確な位置は `scripts/optimize_markers.py` の出力、または
`src/optimized_patterns.json` を参照。

### Hamming距離(seed=42 の探索結果)

- **Minimum Hamming Distance: 10**
- 最小ペア: `O(0°) vs O(90°)`, `O(0°) vs O(270°)`, `O(90°) vs O(180°)`,
  `O(180°) vs O(270°)`(いずれも距離10)
- 同一文字の回転間の最小: **10** / 異なる文字間の最小: **12**

全190ペアの距離表は `scripts/optimize_markers.py` が出力する。

### 誤り訂正と maxCorrectionBits

| 項目 | 値 |
|---|---|
| 最小Hamming距離 d | 10 |
| 理論上の訂正可能bit数 floor((d-1)/2) | 4 |
| **採用した maxCorrectionBits** | **3** |

理論上は4bitまで訂正できるが、訂正を上限まで許すと背景の四角形パターンを
マーカーと誤認するリスクが上がるため、安全側の3(距離の30%)を採用
(`src/dictionary.py` の `MAX_CORRECTION_BITS_CAP`)。ID誤認(文字間)については
文字間最小距離が12なので、3bit訂正でもマージンは十分。
なお `maxCorrectionBits` は辞書側の上限で、実行時の受理閾値はさらに
`DetectorParameters.errorCorrectionRate`(OpenCV既定 0.6)で縮む:
**実効閾値 = floor(0.6 × 3) = 1bit**(テストで実測確認)。ノイズ耐性を
優先する場合は `errorCorrectionRate = 1.0` にすると3bitまで受理する
(こちらもテストで実測確認済み)。本PoCの既定は誤検出最小の 0.6 のまま。

## PNG生成

`markers/H.png` 〜 `I.png`。黒枠(border 1セル)+ 7×7データ領域 + 白quiet zone
(1セル)。セル寸法などは指定可能:

```python
generate_marker_image(marker, cell_size=100, border_bits=1, quiet_zone_bits=1)
```

## 自己テスト(69件、全パス)

`tests/test_markers.py`:

1. **再認識**: コミット済み `markers/*.png` とメモリ上レンダの両方で、期待IDが
   ちょうど1つ検出される(5文字×2)
2. **回転**: 各文字の0°/90°/180°/270°がすべて同一IDになる(20件)
3. **劣化**: 縮小(0.15倍)・Gaussian blur・射影変換・ガウスノイズでも検出(20件)
4. **偽陽性**: 無地・乱数ノイズ・市松模様の未知マーカーを検出しない
5. **誤り訂正の実測**: 1bit誤りは既定で訂正、2bitは既定で棄却、
   3bitは `errorCorrectionRate=1.0` で訂正
6. **設計制約**: 最小Hamming距離≥8、maxCorrectionBitsが理論上界以下、
   文字ストロークの完全保存、変更bitがマスク内かつ6bit以下、LABELS対応
7. **成果物の一致**: JSONのstatsと実パターンの再評価が一致、設計値
   (最小距離10・変更bit内訳・訂正bit3)の固定、`markers/*.png` が
   パターンからの再生成と一致

## 構成

```
hanoi_markers/
├── README.md
├── requirements.txt
├── src/
│   ├── marker_patterns.py        ベース形・変更可能マスク・ASCII表示
│   ├── optimizer.py              SA探索・Hamming距離・評価
│   ├── optimized_patterns.json   探索結果(seed=42。コミット済み=正)
│   ├── dictionary.py             カスタムDictionary構築(ID 0-4)
│   ├── generator.py              PNG生成
│   └── detector.py               ArucoDetector検出・描画
├── scripts/
│   ├── optimize_markers.py
│   ├── generate_markers.py
│   └── detect.py
├── tests/
│   └── test_markers.py
└── markers/
    ├── H.png  A.png  N.png  O.png  I.png
```
