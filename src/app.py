"""交通費精算シミュレーター

docs/01_requirements.md の要件に基づき、交通費の計算・社内規定チェック・
CSV出力を行う Streamlit アプリ。
起動方法: streamlit run src/app.py --server.port 8501
"""
import csv
import datetime
import io
import math
from decimal import Decimal

# ===== 社内規定の値（docs/01_requirements.md より） =====
# 自家用車は 1km あたり 15円（旧仕様の20円は使わない）
CAR_RATE_PER_KM = 15
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

# 選択できる所属部署（要件定義書 機能A）
DEPARTMENTS = ["営業部", "総務部", "経理部", "企画部"]

# 画面の明細一覧に表示する列（明細1件ごとに異なる値を持つ項目）
RECORD_COLUMNS = ["利用日", "出発地", "到着地", "交通手段", "距離(km)", "金額(円)"]

# CSVファイルの列（要件定義書 5章の順番どおり）
# 申請者名・部署・承認ステータスは申請全体で共通の値を各行に付ける
CSV_COLUMNS = [
    "利用日",
    "申請者名",
    "部署",
    "出発地",
    "到着地",
    "交通手段",
    "距離(km)",
    "金額(円)",
    "承認ステータス",
]

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
    """明細の「金額(円)」を合計した申請総額（円）を返す。"""
    return sum(record["金額(円)"] for record in records)


def needs_approval(total):
    """申請総額が基準額を「超える」場合に True を返す。

    ちょうど基準額（10,000円）の場合は超えていないので False。
    """
    return total > APPROVAL_THRESHOLD


def approval_status(total):
    """申請総額から承認ステータスの文字列を返す。"""
    return STATUS_NEEDS_APPROVAL if needs_approval(total) else STATUS_AUTO


def make_record(use_date, departure, arrival, transport, distance_km=0, train_fare=0):
    """入力値から明細1件分（辞書）を作る。金額はここで計算する。

    - 利用日は date 型・"年-月-日" の文字列のどちらでも受け付け、
      "年-月-日" の文字列にそろえて保存する。
    - 電車は距離を使わないため、距離は None（CSVでは空欄）とする。
    - 距離が整数（例: 30.0）の場合は小数点を付けずに 30 として保存する。
    """
    # 金額を先に計算する（不正な交通手段や負の値はここでエラーになる）
    amount = calc_fare(transport, distance_km, train_fare)

    # 利用日を "年-月-日" の文字列にそろえる
    if isinstance(use_date, datetime.date):
        use_date = use_date.isoformat()

    # 距離の表示形式を整える
    if transport == TRAIN:
        distance = None
    elif float(distance_km).is_integer():
        distance = int(distance_km)
    else:
        distance = distance_km

    return {
        "利用日": use_date,
        "出発地": departure,
        "到着地": arrival,
        "交通手段": transport,
        "距離(km)": distance,
        "金額(円)": amount,
    }


def records_to_csv(records, applicant_name, department):
    """明細をCSVのバイト列に変換する。

    - 列は要件定義書 5章の順番（CSV_COLUMNS）とする。
    - 申請者名・部署・承認ステータスは、すべての行に同じ値を出力する。
      承認ステータスは明細全体の合計金額から判定する。
    - Excel で開いても文字化けしないよう、UTF-8（BOM付き）で出力する。
    - 明細が空でもヘッダ行は出力する。
    - 選択肢にない部署は ValueError とする。
    """
    if department not in DEPARTMENTS:
        raise ValueError(f"選択肢にない部署です: {department}")

    # 申請全体で共通の値（承認ステータスは合計金額から判定）
    common = {
        "申請者名": applicant_name,
        "部署": department,
        "承認ステータス": approval_status(calc_total(records)),
    }

    buffer = io.StringIO()
    # 距離が None の場合、DictWriter は空欄として書き出す
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        # 明細の値に共通の値を加えて1行にする
        writer.writerow({**record, **common})
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

    # ----- 機能A：申請者情報の入力（申請全体で1回だけ入力） -----
    st.subheader("申請者情報")
    col_name, col_dept = st.columns(2)
    applicant_name = col_name.text_input("申請者名", placeholder="例：香川 太郎")
    department = col_dept.selectbox("所属部署", DEPARTMENTS)

    # ----- 機能A：移動明細の入力 -----
    st.subheader("移動明細の入力")
    # 交通手段によって入力項目（距離 / 運賃）が変わるため、フォームの外で選ばせる
    transport = st.radio("交通手段", TRANSPORT_TYPES, horizontal=True)

    with st.form("input_form", clear_on_submit=True):
        # 利用日の初期値は当日とする
        use_date = st.date_input("利用日", value=datetime.date.today())
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
                make_record(
                    use_date, departure, arrival, transport, distance_km, train_fare
                )
            )
            # 合計金額の表示を更新するため、画面を再描画する
            st.rerun()

    # ----- 機能C：明細一覧とCSV出力 -----
    st.subheader("明細一覧")
    if records:
        # 電車の距離（None）は「None」と表示されないよう空欄にする
        st.dataframe(
            pd.DataFrame(records, columns=RECORD_COLUMNS).fillna(""),
            hide_index=True,
            use_container_width=True,
        )
        # 申請者名が空のままCSVを出力しないよう、未入力時はボタンを押せなくする
        if not applicant_name:
            st.warning("CSVをダウンロードするには、申請者名を入力してください。")
        st.download_button(
            "CSVダウンロード",
            data=records_to_csv(records, applicant_name, department),
            file_name="交通費精算.csv",
            mime="text/csv",
            disabled=not applicant_name,
        )
        if st.button("明細をクリア"):
            st.session_state.records = []
            st.rerun()
    else:
        st.info("明細はまだありません。上のフォームから追加してください。")


if __name__ == "__main__":
    main()
