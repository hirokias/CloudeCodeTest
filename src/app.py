"""交通費精算シミュレーター

docs/01_requirements.md の要件に基づき、交通費の計算・社内規定チェック・
CSV出力を行う Streamlit アプリ。
起動方法: streamlit run src/app.py --server.port 8501
"""
import csv
import io
import math
from decimal import Decimal

# ===== 社内規定の値（docs/01_requirements.md より） =====
# 自家用車は 1km あたり 20円（旧仕様の15円は使わない）
CAR_RATE_PER_KM = 20
# タクシーは一律 1km あたり 400円
TAXI_RATE_PER_KM = 400
# 1回の申請総額がこの金額を「超える」と上長承認が必要
APPROVAL_THRESHOLD = 10000

# 交通手段の名称（画面・CSV・計算で共通に使う）
TRAIN = "電車"
TAXI = "タクシー"
CAR = "自家用車"
# 選択できる交通手段（画面の並び順）
TRANSPORT_TYPES = [TRAIN, TAXI, CAR]

# 承認ステータスの表示文字列
STATUS_AUTO = "自動承認"
STATUS_NEEDS_APPROVAL = "要上長承認"

# 明細（CSV・一覧表）の列名。この順番で出力する
COLUMNS = ["出発地", "到着地", "交通手段", "距離(km)", "金額"]

# 距離で計算する交通手段と、その1kmあたり単価の対応表
RATE_PER_KM = {
    CAR: CAR_RATE_PER_KM,
    TAXI: TAXI_RATE_PER_KM,
}


def calc_fare(transport, distance_km=0, train_fare=0):
    """交通手段ごとに金額（円）を計算する。

    - 自家用車・タクシー: 距離(km) × 1kmあたり単価。1円未満は切り捨て。
    - 電車: 利用者が入力した運賃をそのまま使う（距離は使わない）。
    - 負の値や未定義の交通手段は ValueError とする。
    """
    if transport == TRAIN:
        # 電車は運賃をそのまま採用する
        if train_fare < 0:
            raise ValueError("運賃は0円以上で入力してください。")
        return int(train_fare)

    if transport not in RATE_PER_KM:
        # 定義されていない交通手段は受け付けない
        raise ValueError(f"未対応の交通手段です: {transport}")

    if distance_km < 0:
        raise ValueError("距離は0km以上で入力してください。")

    # 小数の誤差（例: 0.29 × 100 = 28.999...）を避けるため、
    # Decimal（10進数の正確な計算）で掛け算してから切り捨てる
    amount = Decimal(str(distance_km)) * RATE_PER_KM[transport]
    return math.floor(amount)


def calc_total(records):
    """明細の「金額」を合計した申請総額（円）を返す。"""
    return sum(record["金額"] for record in records)


def needs_approval(total):
    """申請総額が基準額を「超える」場合に True を返す。

    ちょうど基準額（10,000円）の場合は超えていないので False。
    """
    return total > APPROVAL_THRESHOLD


def approval_status(total):
    """申請総額から承認ステータスの文字列を返す。"""
    return STATUS_NEEDS_APPROVAL if needs_approval(total) else STATUS_AUTO


def make_record(departure, arrival, transport, distance_km=0, train_fare=0):
    """入力値から明細1件分（辞書）を作る。金額はここで計算する。"""
    return {
        "出発地": departure,
        "到着地": arrival,
        "交通手段": transport,
        "距離(km)": distance_km,
        "金額": calc_fare(transport, distance_km, train_fare),
    }


def records_to_csv(records):
    """明細をCSVのバイト列に変換する。

    Excel で開いても文字化けしないよう、UTF-8（BOM付き）で出力する。
    明細が空でもヘッダ行は出力する。
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    return buffer.getvalue().encode("utf-8-sig")


def main():
    """Streamlit の画面を描画する。"""
    # Streamlit と pandas は画面表示でのみ使うため、ここで読み込む
    # （単体テストではこれらを読み込まずに計算部分だけを確認できる）
    import pandas as pd
    import streamlit as st

    st.set_page_config(page_title="交通費精算シミュレーター", page_icon="🚃")

    # 入力した明細は画面を操作しても消えないようにセッションに保持する
    if "records" not in st.session_state:
        st.session_state.records = []
    records = st.session_state.records

    st.title("交通費精算シミュレーター")

    # ----- 最上部：合計金額と承認ステータスを大きく表示 -----
    total = calc_total(records)
    col_total, col_status = st.columns(2)
    col_total.metric("合計金額", f"{total:,} 円")
    col_status.metric("承認ステータス", approval_status(total))
    if needs_approval(total):
        # 基準額を超えたら赤字で警告する（機能B）
        st.markdown(
            f"<p style='color:red; font-size:1.5rem; font-weight:bold;'>"
            f"※要上長承認（申請総額が {APPROVAL_THRESHOLD:,} 円を超えています）</p>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ----- 機能A：移動明細の入力 -----
    st.subheader("移動明細の入力")
    # 交通手段によって入力項目（距離 / 運賃）が変わるため、フォームの外で選ばせる
    transport = st.radio("交通手段", TRANSPORT_TYPES, horizontal=True)

    with st.form("input_form", clear_on_submit=True):
        departure = st.text_input("出発地")
        arrival = st.text_input("到着地")
        distance_km = 0.0
        train_fare = 0
        if transport == TRAIN:
            train_fare = st.number_input("運賃（円）", min_value=0, step=10)
        else:
            rate = RATE_PER_KM[transport]
            distance_km = st.number_input(
                f"走行距離（km）※1kmあたり {rate} 円",
                min_value=0.0,
                step=0.1,
                format="%.1f",
            )
        submitted = st.form_submit_button("明細を追加")

    if submitted:
        if not departure or not arrival:
            st.error("出発地と到着地を入力してください。")
        else:
            records.append(
                make_record(departure, arrival, transport, distance_km, train_fare)
            )
            # 合計金額の表示を更新するため、画面を再描画する
            st.rerun()

    # ----- 機能C：明細一覧とCSV出力 -----
    st.subheader("明細一覧")
    if records:
        st.dataframe(
            pd.DataFrame(records, columns=COLUMNS),
            hide_index=True,
            use_container_width=True,
        )
        st.download_button(
            "CSVダウンロード",
            data=records_to_csv(records),
            file_name="交通費精算.csv",
            mime="text/csv",
        )
        if st.button("明細をクリア"):
            st.session_state.records = []
            st.rerun()
    else:
        st.info("明細はまだありません。上のフォームから追加してください。")


if __name__ == "__main__":
    main()
