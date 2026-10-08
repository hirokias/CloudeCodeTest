"""交通費精算シミュレーターの計算ロジックに対する単体テスト"""

import csv
import io
import sys
from pathlib import Path

import pytest

# src/app.py を import できるようにパスを追加する
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app  # noqa: E402


# ---------- 機能A：交通費の計算 ----------
class TestCalculateFare:
    def test_自家用車は1kmあたり20円(self):
        assert app.calculate_fare("自家用車", distance_km=10) == 200

    def test_自家用車の小数距離は1円未満切り捨て(self):
        # 12.34km × 20円 = 246.8円 → 246円
        assert app.calculate_fare("自家用車", distance_km=12.34) == 246

    def test_タクシーは1kmあたり400円(self):
        assert app.calculate_fare("タクシー", distance_km=5) == 2000

    def test_電車は入力した運賃をそのまま採用(self):
        assert app.calculate_fare("電車", train_fare=560) == 560

    def test_距離0kmは0円(self):
        assert app.calculate_fare("自家用車", distance_km=0) == 0

    def test_負の距離はエラー(self):
        with pytest.raises(ValueError):
            app.calculate_fare("タクシー", distance_km=-1)

    def test_未対応の交通手段はエラー(self):
        with pytest.raises(ValueError):
            app.calculate_fare("飛行機", distance_km=100)


# ---------- 機能B：10,000円の承認判定 ----------
class TestApproval:
    def test_9999円は自動承認(self):
        assert app.needs_approval(9_999) is False
        assert app.approval_status(9_999) == "自動承認"

    def test_ちょうど10000円は自動承認(self):
        # 要件は「10,000円を超える場合」なので、ちょうどは対象外
        assert app.needs_approval(10_000) is False
        assert app.approval_status(10_000) == "自動承認"

    def test_10001円は要上長承認(self):
        assert app.needs_approval(10_001) is True
        assert app.approval_status(10_001) == "要上長承認"

    def test_複数明細の合計で判定する(self):
        # タクシー20km(8,000円) + 自家用車150km(3,000円) = 11,000円
        items = [
            app.make_item("本社", "A社", "タクシー", distance_km=20),
            app.make_item("A社", "B社", "自家用車", distance_km=150),
        ]
        total = app.calculate_total(items)
        assert total == 11_000
        assert app.approval_status(total) == "要上長承認"

    def test_自家用車500kmはちょうど10000円で自動承認(self):
        # 新単価20円/km × 500km = 10,000円（基準額ちょうど）
        items = [app.make_item("本社", "C社", "自家用車", distance_km=500)]
        total = app.calculate_total(items)
        assert total == 10_000
        assert app.approval_status(total) == "自動承認"

    def test_明細なしは0円で自動承認(self):
        assert app.calculate_total([]) == 0
        assert app.approval_status(0) == "自動承認"


# ---------- 機能C：一覧表示とCSV出力 ----------
class TestOutput:
    def test_明細の内容(self):
        item = app.make_item("高松駅", "香川大学", "タクシー", distance_km=2.5)
        assert item == {
            "出発地": "高松駅",
            "到着地": "香川大学",
            "交通手段": "タクシー",
            "走行距離(km)": 2.5,
            "金額(円)": 1000,
        }

    def test_一覧表の行数と列(self):
        items = [
            app.make_item("A", "B", "電車", train_fare=300),
            app.make_item("B", "C", "自家用車", distance_km=20),
        ]
        df = app.items_to_dataframe(items)
        assert len(df) == 2
        assert list(df.columns) == app.COLUMNS

    def test_CSVに明細が正しく出力される(self):
        items = [app.make_item("高松", "丸亀", "自家用車", distance_km=30)]
        data = app.items_to_csv(items)
        # Excelで文字化けしないようBOM付きUTF-8であること
        assert data.startswith(b"\xef\xbb\xbf")
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        assert rows[0] == app.COLUMNS
        assert rows[1] == ["高松", "丸亀", "自家用車", "30", "600"]

    def test_明細なしでもCSVはヘッダーのみ出力(self):
        rows = list(csv.reader(io.StringIO(app.items_to_csv([]).decode("utf-8-sig"))))
        assert rows == [app.COLUMNS]
