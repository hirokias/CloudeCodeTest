"""交通費精算シミュレーター（Streamlitアプリ）

要件定義書 docs/01_requirements.md に基づく実装。
- 機能A：移動明細の入力と計算（電車 / タクシー / 自家用車）
- 機能B：社内規定のチェック（申請総額が10,000円を超える場合は要上長承認）
- 機能C：申請データの出力（明細の一覧表示とCSVダウンロード）

計算ロジックは画面処理から切り離した関数として定義し、
tests/test_app.py から単体テストできるようにしている。
"""

import pandas as pd

# ------------------------------------------------------------
# 社内規定の定数
# ------------------------------------------------------------
# 自家用車：1kmあたりのガソリン代換算単価（円）
CAR_RATE_PER_KM = 20
# タクシー：1kmあたりの一律単価（円）
TAXI_RATE_PER_KM = 400
# 上長承認が必要になる基準額（円）。この金額を「超える」場合に要承認となる
APPROVAL_THRESHOLD = 10_000

# 交通手段の選択肢
TRANSPORT_TRAIN = "電車"
TRANSPORT_TAXI = "タクシー"
TRANSPORT_CAR = "自家用車"
TRANSPORT_OPTIONS = [TRANSPORT_TRAIN, TRANSPORT_TAXI, TRANSPORT_CAR]

# 承認ステータスの表示文言
STATUS_AUTO = "自動承認"
STATUS_NEEDS_APPROVAL = "要上長承認"

# CSV・一覧表示に用いる列名
COLUMNS = ["出発地", "到着地", "交通手段", "走行距離(km)", "金額(円)"]


# ------------------------------------------------------------
# 計算ロジック（画面に依存しない関数群）
# ------------------------------------------------------------
def calculate_fare(transport: str, distance_km: float = 0, train_fare: int = 0) -> int:
    """交通手段に応じて1件分の交通費（円）を計算する。

    - 自家用車：走行距離 × 20円
    - タクシー：走行距離 × 400円
    - 電車　　：入力された運賃をそのまま採用（要件に計算式の定めがないため）
    1円未満は切り捨てる。
    """
    # マイナスの入力は誤りとして扱う
    if distance_km < 0 or train_fare < 0:
        raise ValueError("距離・運賃に負の値は入力できません")

    if transport == TRANSPORT_CAR:
        return int(distance_km * CAR_RATE_PER_KM)
    if transport == TRANSPORT_TAXI:
        return int(distance_km * TAXI_RATE_PER_KM)
    if transport == TRANSPORT_TRAIN:
        return int(train_fare)
    # 想定外の交通手段はエラーにする
    raise ValueError(f"未対応の交通手段です: {transport}")


def calculate_total(items: list[dict]) -> int:
    """明細リストの金額を合計する。"""
    return sum(item["金額(円)"] for item in items)


def needs_approval(total: int) -> bool:
    """申請総額が基準額（10,000円）を超えるかどうかを判定する。

    要件「10,000円を超える場合」に従い、ちょうど10,000円は自動承認とする。
    """
    return total > APPROVAL_THRESHOLD


def approval_status(total: int) -> str:
    """申請総額から承認ステータスの文言を返す。"""
    return STATUS_NEEDS_APPROVAL if needs_approval(total) else STATUS_AUTO


def make_item(departure: str, arrival: str, transport: str,
              distance_km: float = 0, train_fare: int = 0) -> dict:
    """入力値から明細1件分のデータ（辞書）を作成する。"""
    fare = calculate_fare(transport, distance_km, train_fare)
    return {
        "出発地": departure,
        "到着地": arrival,
        "交通手段": transport,
        # 電車は距離を使わないため空欄にする
        "走行距離(km)": distance_km if transport != TRANSPORT_TRAIN else None,
        "金額(円)": fare,
    }


def items_to_dataframe(items: list[dict]) -> pd.DataFrame:
    """明細リストを一覧表示用の表（DataFrame）に変換する。"""
    return pd.DataFrame(items, columns=COLUMNS)


def items_to_csv(items: list[dict]) -> bytes:
    """明細リストをCSV（Excelで文字化けしないBOM付きUTF-8）に変換する。"""
    return items_to_dataframe(items).to_csv(index=False).encode("utf-8-sig")


# ------------------------------------------------------------
# 画面（Streamlit）
# ------------------------------------------------------------
def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="交通費精算シミュレーター", page_icon="🚃")

    # 明細はセッション内に保持する（ブラウザを閉じると消える）
    if "items" not in st.session_state:
        st.session_state["items"] = []
    items = st.session_state["items"]

    st.title("🚃 交通費精算シミュレーター")

    # --- 要件4：合計金額と承認ステータスを一番上に大きく表示 ---
    total = calculate_total(items)
    col_total, col_status = st.columns(2)
    col_total.metric("申請合計金額", f"{total:,} 円")
    col_status.metric("承認ステータス", approval_status(total))

    # --- 機能B：10,000円を超えたら赤字で警告 ---
    if needs_approval(total):
        st.markdown(
            "<p style='color:red; font-size:1.4em; font-weight:bold;'>※要上長承認</p>",
            unsafe_allow_html=True,
        )

    st.divider()

    # --- 機能A：移動明細の入力 ---
    st.subheader("移動明細の入力")
    # 交通手段によって入力欄が変わるため、フォームの外で選択させる
    transport = st.radio("交通手段", TRANSPORT_OPTIONS, horizontal=True)

    with st.form("entry_form", clear_on_submit=True):
        departure = st.text_input("出発地")
        arrival = st.text_input("到着地")
        distance_km = 0.0
        train_fare = 0
        if transport == TRANSPORT_TRAIN:
            train_fare = st.number_input("運賃（円）", min_value=0, step=10)
        else:
            rate = CAR_RATE_PER_KM if transport == TRANSPORT_CAR else TAXI_RATE_PER_KM
            distance_km = st.number_input(
                f"走行距離（km）※1kmあたり{rate}円で計算",
                min_value=0.0, step=0.1, format="%.1f",
            )
        submitted = st.form_submit_button("明細に追加", type="primary")

    if submitted:
        if not departure or not arrival:
            st.error("出発地と到着地を入力してください。")
        else:
            items.append(make_item(departure, arrival, transport, distance_km, train_fare))
            # 合計表示を更新するため再描画する
            st.rerun()

    st.divider()

    # --- 機能C：明細一覧とCSVダウンロード ---
    st.subheader("明細一覧")
    if items:
        st.dataframe(items_to_dataframe(items), width="stretch", hide_index=True)
        col_dl, col_clear = st.columns(2)
        col_dl.download_button(
            "CSVをダウンロード",
            data=items_to_csv(items),
            file_name="交通費精算.csv",
            mime="text/csv",
        )
        if col_clear.button("明細をすべて削除"):
            st.session_state["items"] = []
            st.rerun()
    else:
        st.info("まだ明細がありません。上のフォームから追加してください。")


# `streamlit run src/app.py` で実行された場合のみ画面を描画する
# （テストから import したときは画面処理を動かさない）
if __name__ == "__main__":
    main()
