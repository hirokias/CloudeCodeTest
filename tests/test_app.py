"""交通費精算シミュレーターの単体テスト（docs/02_design.md 5章に対応）"""
import codecs
import datetime
import os
import sys

import pytest

# src/app.py を読み込めるようにする
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import app  # noqa: E402


# ---------- 5.1 calc_fare ----------
class TestCalcFare:
    def test_自家用車は1kmあたり15円(self):
        assert app.calc_fare("自家用車", distance_km=10) == 150

    def test_自家用車_距離0kmは0円(self):
        assert app.calc_fare("自家用車", distance_km=0) == 0

    def test_自家用車_小数距離(self):
        assert app.calc_fare("自家用車", distance_km=12.5) == 187

    def test_自家用車_1円未満は切り捨て(self):
        assert app.calc_fare("自家用車", distance_km=0.33) == 4

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
        records = [{"金額(円)": 150}, {"金額(円)": 4000}, {"金額(円)": 580}]
        assert app.calc_total(records) == 4730


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
class TestMakeRecord:
    def test_明細の作成(self):
        record = app.make_record(
            datetime.date(2026, 10, 8), "高松", "丸亀", "自家用車", distance_km=30
        )
        assert record == {
            "利用日": "2026-10-08",
            "出発地": "高松",
            "到着地": "丸亀",
            "交通手段": "自家用車",
            "距離(km)": 30,
            "金額(円)": 450,
        }

    def test_利用日は文字列でも指定できる(self):
        record = app.make_record("2026-10-08", "高松", "丸亀", "自家用車", distance_km=30)
        assert record["利用日"] == "2026-10-08"

    def test_整数の距離は小数点を付けない(self):
        record = app.make_record("2026-10-08", "高松", "丸亀", "自家用車", distance_km=30.0)
        assert record["距離(km)"] == 30
        assert isinstance(record["距離(km)"], int)

    def test_電車は距離が空(self):
        record = app.make_record("2026-10-08", "高松", "丸亀", "電車", train_fare=580)
        assert record["距離(km)"] is None
        assert record["金額(円)"] == 580


# ---------- 5.5 records_to_csv ----------
CSV_HEADER = "利用日,申請者名,部署,出発地,到着地,交通手段,距離(km),金額(円),承認ステータス"


def _csv_lines(records, name="香川 太郎", department="営業部"):
    """CSVを作り、BOMを除いた文字列を行ごとのリストで返す"""
    return app.records_to_csv(records, name, department).decode("utf-8-sig").splitlines()


class TestRecordsToCsv:
    def test_先頭にBOMが付く(self):
        data = app.records_to_csv([], "香川 太郎", "営業部")
        assert data.startswith(codecs.BOM_UTF8)

    def test_明細なしでもヘッダ行が出力される(self):
        assert _csv_lines([]) == [CSV_HEADER]

    def test_要件の例どおりに出力される(self):
        record = app.make_record("2026-10-08", "高松", "丸亀", "自家用車", distance_km=30)
        lines = _csv_lines([record])
        assert lines[0] == CSV_HEADER
        assert lines[1] == "2026-10-08,香川 太郎,営業部,高松,丸亀,自家用車,30,450,自動承認"

    def test_電車の距離は空欄(self):
        record = app.make_record("2026-10-08", "高松", "丸亀", "電車", train_fare=580)
        lines = _csv_lines([record], department="総務部")
        assert lines[1] == "2026-10-08,香川 太郎,総務部,高松,丸亀,電車,,580,自動承認"

    def test_基準額を超える申請はすべての行が要上長承認(self):
        records = [
            app.make_record("2026-10-08", "高松", "丸亀", "自家用車", distance_km=30),
            app.make_record("2026-10-09", "丸亀", "坂出", "電車", train_fare=580),
            app.make_record("2026-10-10", "坂出", "高松空港", "タクシー", distance_km=25),
        ]
        lines = _csv_lines(records, department="経理部")
        assert len(lines) == 4
        for line in lines[1:]:
            cols = line.split(",")
            assert cols[1] == "香川 太郎"
            assert cols[2] == "経理部"
            assert cols[8] == "要上長承認"

    def test_選択肢にない部署はエラー(self):
        with pytest.raises(ValueError):
            app.records_to_csv([], "香川 太郎", "人事部")
