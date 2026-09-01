"""接地自動校正: マット上で静止している箱の底面zから高さの系統誤差を推定・補正する。

マット四隅タグは全て高さ0の同一平面にあるため、キャリブレーションは高さ方向の
スケール(焦点距離)を自己検証できず、箱の高さ推定に数十mmの系統誤差が残ることが
ある(S24〜S26 で実測: 接地箱が一様に -31〜+13mm ずれ、判定抜け・表示の埋まりの
原因になった)。「底面zが0近傍の箱はマット面に静止している」という物理的事実を
参照高さとして使い、ずれを推定して観測zから一様に引く。相対値(積みギャップ)は
変えないため積み判定の精度には影響せず、接地判定のマージンだけが回復する。

推定は補正前の生の観測zに対して行う(補正後の残誤差を追う方式だと、補正量が
古いまま誤差の符号が反転した場合に参照棄却と噛み合って更新不能に陥りうるため)。

推定は常時ではなく「調整ウィンドウ」中だけ行い、収束したら固定する(S29で
ユーザー決定: プレイ中の観測で補正が動き続けるより、起動時・明示的な再調整
コマンド時の「箱がきちんと置かれた状態」から確定する方が予測可能で安全)。
ウィンドウはワーカー起動時に自動で開き、接地箱が見えた更新が
GROUND_CAL_SETTLE_STEPS 回に達したら確定する。再調整は `make ground-cal`
(トリガーファイル)でいつでも開き直せる。運用は「マット上に箱を1つ以上置いて make ground-cal」。

積まれた箱(底面は最低でも小箱の上=+37.5mm)を地面と誤認しないよう、
(1) トラッカーが段1以上と保持している箱は候補から除外し(遮蔽中も盤面は保持される)、
(2) 残った候補の最下クラスタの中央値が上限を超える場合は参照しない。
それでも「土台の箱が一度も観測されないまま上の箱だけ見え、かつ負の系統誤差が
大きい」場合は誤差±数十mmで誤学習しうるが、接地箱が1つでも見えれば
最下クラスタ側が勝って回復する。持ち上げ中の箱をマット面近くで静止保持した場合も
同様に一時的に引きずられ、置き直せば数秒で再収束する(ゲインを小さくして緩和)。
HANOI_CV_GROUND_AUTOCAL=0 で無効化できる(縮退経路)。
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import median
from typing import Protocol

from app.cv.layout import MAT_SIZE_MM

# 参照候補の窓(mm): 補正前の底面zがこの範囲ならマット面に静止しているとみなす。
# 実測された系統誤差(±31mm)を覆いつつ、積まれた箱(最低でも小箱の上=+37.5mm)を
# なるべく含めない値
GROUND_CAL_WINDOW_MM = 45.0
# 最下クラスタの幅(mm): 候補のうち最小zからこの範囲だけを参照に使う。
# 接地箱と積まれた箱(+37.5mm以上)が窓内に混在しても、より低い接地箱側だけが残る
GROUND_CAL_CLUSTER_MM = 20.0
# 補正量の上限(mm): これを超える誤差は接地判定(許容25mm)が先に破綻する領域で、
# 参照の取り違え(全箱が積まれている等)の可能性が高いため更新しない
GROUND_CAL_MAX_MM = 30.0
# 1フレームあたりの追従率(約30fpsで2〜4秒で収束)。持ち上げ中の箱が一瞬
# 窓に入っても影響が残らないよう小さめにする
GROUND_CAL_GAIN = 0.02
# 調整ウィンドウ: 参照(接地箱)が得られた更新がこの回数に達したら補正量を確定・固定
# する(約30fpsで接地箱が見えている約5秒分)。壁時計でなく更新回数で数えるのは、
# 参照が途切れた時間を収束に数えて未収束のまま確定しないため。
# ゲイン0.02でこの回数なら目標値の95%超まで収束する
GROUND_CAL_SETTLE_STEPS = 150


class _HasPos(Protocol):
    @property
    def box_id(self) -> str: ...

    @property
    def pos_mm(self) -> tuple[float, float, float]: ...


def resting_reference_error_mm(
    sightings: Sequence[_HasPos], elevated_box_ids: frozenset[str] = frozenset()
) -> float | None:
    """接地しているとみなせる箱の(補正前)底面zの代表値=高さの系統誤差を返す。

    マット内(x,y)かつ |z| が窓内の箱を候補とし、最下クラスタの中央値を採る。
    elevated_box_ids(トラッカーが段1以上と保持している箱)は積まれているため除外。
    候補がない・代表値が上限超のときは None(更新材料なし)。
    """
    w, h = MAT_SIZE_MM
    candidates = [
        s.pos_mm[2]
        for s in sightings
        if s.box_id not in elevated_box_ids
        and 0.0 <= s.pos_mm[0] <= w
        and 0.0 <= s.pos_mm[1] <= h
        and abs(s.pos_mm[2]) <= GROUND_CAL_WINDOW_MM
    ]
    if not candidates:
        return None
    lowest = min(candidates)
    cluster = [z for z in candidates if z - lowest <= GROUND_CAL_CLUSTER_MM]
    value = median(cluster)
    if abs(value) > GROUND_CAL_MAX_MM:
        return None
    return value


def next_ground_offset_mm(current_mm: float, error_mm: float | None) -> float:
    """補正量を1ステップ更新する(生観測から推定した誤差 error_mm へ指数追従)。

    error_mm は補正前の値なので、現在の補正量によらず目標値そのもの。
    誤差の符号が後から反転しても(再キャリブレーション等)必ず再収束する。
    """
    if error_mm is None:
        return current_mm
    updated = current_mm + (error_mm - current_mm) * GROUND_CAL_GAIN
    return max(-GROUND_CAL_MAX_MM, min(GROUND_CAL_MAX_MM, updated))
