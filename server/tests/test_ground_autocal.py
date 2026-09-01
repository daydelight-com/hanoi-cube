"""接地自動校正(ground_autocal.py と FramePipeline への組み込み)のテスト。

四隅タグ(全て高さ0)だけではキャリブレーションが高さスケールを自己検証できず、
箱の底面zに数十mmの系統誤差が残る(S24〜S26 の実測)。接地箱を参照高さとして
誤差を推定・補正する仕組みを検証する。座標は conftest の 600x400 レイアウト前提。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.cv.ground_autocal import (
    GROUND_CAL_MAX_MM,
    next_ground_offset_mm,
    resting_reference_error_mm,
)

from tests.cv_scene import BoxPose, Scene
from tests.test_cv_pipeline import PipeDriver, frames


@dataclass(frozen=True)
class _Sight:
    pos_mm: tuple[float, float, float]
    box_id: str = "large-1"


def _s(x: float, y: float, z: float) -> _Sight:
    return _Sight(pos_mm=(x, y, z))


class TestRestingReferenceError:
    def test_接地箱の底面zの中央値を返す(self) -> None:
        assert resting_reference_error_mm([_s(150, 280, -12.0), _s(300, 280, -14.0)]) == -13.0

    def test_候補なしはNone(self) -> None:
        assert resting_reference_error_mm([]) is None
        # マット外(600x400 の外)
        assert resting_reference_error_mm([_s(-50, 280, -12.0)]) is None
        assert resting_reference_error_mm([_s(150, 450, -12.0)]) is None
        # 窓の外(積まれた箱: 大箱の上=+75mm)
        assert resting_reference_error_mm([_s(150, 280, 75.0)]) is None

    def test_段1以上と保持されている箱は候補から除外される(self) -> None:
        # 土台が遮蔽され、負の系統誤差で積み箱(真値+37.5)が窓内(+22.5)に入るケース。
        # トラッカーの保持盤面由来の除外がなければ誤学習する
        stacked = _Sight(pos_mm=(150, 280, 22.5))
        assert resting_reference_error_mm([stacked], frozenset({"large-1"})) is None
        # 除外指定がなければ(トラッカー未確定の起動直後など)候補にはなる
        assert resting_reference_error_mm([stacked]) == 22.5

    def test_接地箱と積まれた箱が混在しても最下クラスタだけを使う(self) -> None:
        # 系統誤差-10mmの下で、接地箱(-10)と小箱の上の箱(37.5-10=27.5)が窓内に混在
        error = resting_reference_error_mm(
            [_s(150, 280, -10.0), _s(300, 280, -9.0), _s(450, 280, 27.5)]
        )
        assert error == -9.5

    def test_全箱が積まれている場合は上限超で棄却(self) -> None:
        # 接地箱ゼロ・全て小箱の上(+37.5mm前後)なら参照にしない
        assert resting_reference_error_mm([_s(150, 280, 36.0), _s(300, 280, 38.0)]) is None


class TestNextGroundOffset:
    def test_誤差Noneは現状維持(self) -> None:
        assert next_ground_offset_mm(7.5, None) == 7.5

    def test_反復適用で系統誤差に収束する(self) -> None:
        offset = 0.0
        for _ in range(600):
            offset = next_ground_offset_mm(offset, -12.5)
        assert abs(offset - (-12.5)) < 0.5

    def test_誤差の符号が反転しても再収束する(self) -> None:
        # 再キャリブレーション等で系統誤差が -30 → +13 に変わった場合のデッドロック回帰
        offset = -GROUND_CAL_MAX_MM
        for _ in range(600):
            offset = next_ground_offset_mm(offset, 13.0)
        assert abs(offset - 13.0) < 0.5

    def test_補正量は上限でクランプされる(self) -> None:
        offset = 0.0
        for _ in range(3000):
            offset = next_ground_offset_mm(offset, -100.0)
        assert offset == -GROUND_CAL_MAX_MM


class TestPipelineIntegration:
    def _biased_driver(self, bias: float, *, autocal: bool = True) -> PipeDriver:
        """幾何解決の底面zに一様な系統誤差 bias を注入したパイプライン。"""
        d = PipeDriver()
        d.pipeline._ground_autocal = autocal
        original = d.pipeline._resolve_boxes

        def biased(detections, camera):  # type: ignore[no-untyped-def]
            return [
                replace(s, pos_mm=(s.pos_mm[0], s.pos_mm[1], s.pos_mm[2] + bias))
                for s in original(detections, camera)
            ]

        d.pipeline._resolve_boxes = biased  # type: ignore[method-assign]
        return d

    def _grounded_scene(self) -> Scene:
        return Scene(boxes=[BoxPose(box_id="large-1", pos=(150.0, 280.0, 0.0))])

    def test_系統誤差が数秒で補正され底面zが0近傍になる(self) -> None:
        d = self._biased_driver(-15.0)
        d.feed("g", self._grounded_scene(), repeat=300)  # 約10秒相当
        assert abs(d.pipeline._ground_offset_mm - (-15.0)) < 2.0
        last = frames(d.feed("g", self._grounded_scene(), repeat=1))[-1]
        z = next(b.pos_mm[2] for b in last.boxes if b.box_id == "large-1")
        assert abs(z) < 3.0

    def test_無効化時は補正されない(self) -> None:
        d = self._biased_driver(-15.0, autocal=False)
        d.feed("g", self._grounded_scene(), repeat=60)
        assert d.pipeline._ground_offset_mm == 0.0
        last = frames(d.feed("g", self._grounded_scene(), repeat=1))[-1]
        z = next(b.pos_mm[2] for b in last.boxes if b.box_id == "large-1")
        assert z < -10.0

    def test_補正量は保存され復元される(self) -> None:
        d = self._biased_driver(-15.0)
        d.feed("g", self._grounded_scene(), repeat=300)
        data = d.pipeline.export_calibration()
        assert data is not None
        saved = data["ground_offset_mm"]
        assert isinstance(saved, float) and abs(saved - (-15.0)) < 2.0
        d2 = PipeDriver()
        d2.pipeline.restore_calibration(data)
        assert d2.pipeline._ground_offset_mm == saved

    def test_旧形式の保存データはオフセット0で復元される(self) -> None:
        d = PipeDriver()
        d.feed("g", self._grounded_scene(), repeat=5)
        data = d.pipeline.export_calibration()
        assert data is not None
        data.pop("ground_offset_mm")
        d2 = PipeDriver()
        d2.pipeline.restore_calibration(data)
        assert d2.pipeline._ground_offset_mm == 0.0

    def test_復元時も補正量は上限でクランプされる(self) -> None:
        d = PipeDriver()
        d.feed("g", self._grounded_scene(), repeat=5)
        data = d.pipeline.export_calibration()
        assert data is not None
        data["ground_offset_mm"] = 1e9  # 壊れたファイルを想定
        d2 = PipeDriver()
        d2.pipeline.restore_calibration(data)
        assert d2.pipeline._ground_offset_mm == GROUND_CAL_MAX_MM


class TestWorkerResave:
    def test_再保存判定はドリフト量と間隔の両方を要求する(self) -> None:
        from app.cv.worker import should_resave_calibration

        # 初回保存(補正0)→ 収束(-15mm)・間隔経過 → 再保存
        assert should_resave_calibration(0.0, -15.0, last_save_ms=0, t_ms=10_000)
        # ドリフトが閾値以下なら保存しない
        assert not should_resave_calibration(-14.0, -15.0, last_save_ms=0, t_ms=10_000)
        # 間隔が空いていなければ保存しない(書き込み連発の防止)
        assert not should_resave_calibration(0.0, -15.0, last_save_ms=0, t_ms=9_999)

    def test_収束後の補正量が保存データ経由で次回起動に引き継がれる(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """初回保存時は補正量≈0でも、収束後の値がファイルに反映されること(S27)。"""
        import json

        from app.cv.pipeline import FramePipeline

        d = self._converged_driver()
        data = d.pipeline.export_calibration()
        assert data is not None
        path = tmp_path / "calib.json"
        path.write_text(json.dumps(data))
        restored = FramePipeline(d.pipeline._master)
        restored.restore_calibration(json.loads(path.read_text()))
        assert abs(restored.ground_offset_mm - d.pipeline.ground_offset_mm) < 0.01

    def _converged_driver(self) -> PipeDriver:
        d = PipeDriver()
        original = d.pipeline._resolve_boxes

        def biased(detections, camera):  # type: ignore[no-untyped-def]
            from dataclasses import replace as rep

            return [
                rep(s, pos_mm=(s.pos_mm[0], s.pos_mm[1], s.pos_mm[2] - 15.0))
                for s in original(detections, camera)
            ]

        d.pipeline._resolve_boxes = biased  # type: ignore[method-assign]
        d.feed("g", Scene(boxes=[BoxPose(box_id="large-1", pos=(150.0, 280.0, 0.0))]), repeat=300)
        return d


class TestCalibrationWindow:
    """調整ウィンドウ(起動時に収束→固定、make ground-cal で開き直し)の検証。"""

    def _biased_driver(self, bias: float) -> PipeDriver:
        d = PipeDriver()
        d._bias = bias  # type: ignore[attr-defined]
        original = d.pipeline._resolve_boxes

        def biased(detections, camera):  # type: ignore[no-untyped-def]
            return [
                replace(s, pos_mm=(s.pos_mm[0], s.pos_mm[1], s.pos_mm[2] + d._bias))  # type: ignore[attr-defined]
                for s in original(detections, camera)
            ]

        d.pipeline._resolve_boxes = biased  # type: ignore[method-assign]
        return d

    def _scene(self) -> Scene:
        return Scene(boxes=[BoxPose(box_id="large-1", pos=(150.0, 280.0, 0.0))])

    def test_参照が途切れた時間は収束に数えない(self) -> None:
        # 接地箱が50フレームだけ見え、その後長く見えなくても未収束のまま確定しない
        d = self._biased_driver(-15.0)
        d.feed("g", self._scene(), repeat=50)
        assert d.pipeline._ground_cal_active
        d.feed("empty", Scene(boxes=[]), repeat=400)  # 参照なしが長時間続く
        assert d.pipeline._ground_cal_active  # まだ確定しない
        d.feed("g", self._scene(), repeat=120)  # 合計170回の参照つき更新で確定
        assert not d.pipeline._ground_cal_active
        assert abs(d.pipeline.ground_offset_mm - (-15.0)) < 2.0

    def test_収束後は固定され以後の観測変化に追従しない(self) -> None:
        d = self._biased_driver(-15.0)
        d.feed("g", self._scene(), repeat=300)  # 約10秒 > 確定窓5秒
        assert not d.pipeline._ground_cal_active
        frozen = d.pipeline.ground_offset_mm
        assert abs(frozen - (-15.0)) < 2.0
        # 確定後にバイアスが変わっても(照明変化等)補正量は動かない
        d._bias = +10.0  # type: ignore[attr-defined]
        d.feed("g2", self._scene(), repeat=120)
        assert d.pipeline.ground_offset_mm == frozen

    def test_restart_ground_autocalで新しい状態に再収束する(self) -> None:
        d = self._biased_driver(-15.0)
        d.feed("g", self._scene(), repeat=300)
        d._bias = +10.0  # type: ignore[attr-defined]
        d.pipeline.restart_ground_autocal()
        d.feed("g2", self._scene(), repeat=300)
        assert not d.pipeline._ground_cal_active
        assert abs(d.pipeline.ground_offset_mm - 10.0) < 2.0


class TestGroundCalRequest:
    def test_トリガーファイルは消費されて一度だけ発火する(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from app.cv.worker import consume_ground_cal_request

        trigger = tmp_path / "ground_autocal.request"
        assert not consume_ground_cal_request(trigger)  # 無ければ何もしない
        assert not consume_ground_cal_request(None)  # 無効設定
        trigger.touch()
        assert consume_ground_cal_request(trigger)
        assert not trigger.exists()
        assert not consume_ground_cal_request(trigger)  # 2回目は発火しない
