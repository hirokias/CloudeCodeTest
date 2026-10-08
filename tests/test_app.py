"""交通費精算シミュレーターの単体テスト（docs/02_design.md 5章に対応）"""
import codecs
import os
import sys

import pytest

# src/app.py を読み込めるようにする
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import app  # noqa: E402


# ---------- 5.1 calc_fare ----------
class TestCalcFare:
    def test_自家用車は1kmあたり20円(self):
        assert app.calc_fare("自家用車", distance_km=10) == 200

    def test_自家用車_距離0kmは0円(self):
        assert app.calc_fare("自家用車", distance_km=0) == 0

    def test_自家用車_小数距離(self):
        assert app.calc_fare("自家用車", distance_km=12.5) == 250

    def test_自家用車_1円未満は切り捨て(self):
        assert app.calc_fare("自家用車", distance_km=0.33) == 6

    def test_タクシーは1kmあたり400円(self):
        assert app.calc_fare("タクシー", distance_km=10) == 4000

    def test_タクシー_小数距離(self):
        assert app.calc_fare("タクシー", distance_km=2.5) == 1000

    def test_電車は入力した運賃(self):
        assert app.calc_fare("電車", train_fare=580) == 580

    def test_電車は距離を使わない(self):
        assert app.calc_fare("電車", distance_km=100, train_fare=300) == 300

    def test_負の距離はエラー(self):
        with pytest.raises(ValueError):
            app.calc_fare("自家用車", distance_km=-1)

    def test_負の運賃はエラー(self):
        with pytest.raises(ValueError):
            app.calc_fare("電車", train_fare=-1)

    def test_未定義の交通手段はエラー(self):
        with pytest.raises(ValueError):
            app.calc_fare("飛行機", distance_km=10)


# ---------- 5.2 calc_total ----------
class TestCalcTotal:
    def test_明細なしは0円(self):
        assert app.calc_total([]) == 0

    def test_複数明細の合計(self):
        records = [{"金額": 200}, {"金額": 4000}, {"金額": 580}]
        assert app.calc_total(records) == 4780


# ---------- 5.3 needs_approval / approval_status（境界値） ----------
@pytest.mark.parametrize(
    "total, expected_flag, expected_status",
    [
        (0, False, "自動承認"),
        (9999, False, "自動承認"),
        (10000, False, "自動承認"),
        (10001, True, "要上長承認"),
    ],
)
def test_承認判定の境界値(total, expected_flag, expected_status):
    assert app.needs_approval(total) is expected_flag
    assert app.approval_status(total) == expected_status


# ---------- 5.4 make_record ----------
def test_明細の作成():
    record = app.make_record("高松駅", "丸亀駅", "自家用車", distance_km=30)
    assert record == {
        "出発地": "高松駅",
        "到着地": "丸亀駅",
        "交通手段": "自家用車",
        "距離(km)": 30,
        "金額": 600,
    }


# ---------- 5.5 records_to_csv ----------
class TestRecordsToCsv:
    def test_先頭にBOMが付く(self):
        data = app.records_to_csv([])
        assert data.startswith(codecs.BOM_UTF8)

    def test_明細なしでもヘッダ行が出力される(self):
        text = app.records_to_csv([]).decode("utf-8-sig")
        assert text.splitlines()[0] == "出発地,到着地,交通手段,距離(km),金額"

    def test_明細が行として出力される(self):
        record = app.make_record("高松駅", "丸亀駅", "自家用車", distance_km=30)
        lines = app.records_to_csv([record]).decode("utf-8-sig").splitlines()
        assert lines[0] == "出発地,到着地,交通手段,距離(km),金額"
        assert lines[1] == "高松駅,丸亀駅,自家用車,30,600"
