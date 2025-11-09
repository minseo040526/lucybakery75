# app.py
import streamlit as st
import pandas as pd
import itertools, os, re, smtplib, ssl, uuid
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime
from PIL import Image

# ---------------- 기본 설정 ----------------
st.set_page_config(page_title="AI 베이커리 추천·주문", layout="wide")

SHOP_NAME = st.secrets.get("SHOP_NAME", "Lucy Bakery")
OWNER_EMAIL_PRIMARY = st.secrets.get("OWNER_EMAIL_PRIMARY", "")
WELCOME_COUPON_AMOUNT = int(st.secrets.get("WELCOME_COUPON_AMOUNT", "2000"))
SMTP_HOST = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(st.secrets.get("SMTP_PORT", "465"))
SMTP_USER = st.secrets.get("SMTP_USER", "")
SMTP_PASS = st.secrets.get("SMTP_PASS", "")

# ---------------- 유틸 ----------------
def money(x): return f"{int(x):,}원"
def now_ts(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def normalize_str(s): return re.sub(r"\s+"," ",str(s).strip()) if pd.notna(s) else ""

# ---------------- 이메일 ----------------
def send_order_email(to_emails, shop_name, order_id, items, total, note):
    if not to_emails: return False, "이메일 설정이 없습니다."
    msg_lines = [
        f"[{shop_name}] 주문이 접수되었습니다.",
        f"주문번호: {order_id}",
        "---------------------------",
    ]
    for it in items:
        msg_lines.append(f"- {it['name']} x{it['qty']} ({money(it['unit_price'])})")
    msg_lines += [
        "---------------------------",
        f"총액: {money(total)}",
        f"요청사항: {note or '없음'}",
        f"시간: {now_ts()}"
    ]
    msg = MIMEText("\n".join(msg_lines), _charset="utf-8")
    msg["Subject"] = f"[{shop_name}] 주문 알림 #{order_id}"
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(to_emails)
    msg["Date"] = formatdate(localtime=True)
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(msg["From"], to_emails, msg.as_string())
        return True, ""
    except Exception as e:
        return False, str(e)

# ---------------- 메뉴 로드 ----------------
def normalize_columns(df, is_drink=False):
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    if is_drink:
        required = ["name","price","category"]
    else:
        if "tags" not in df.columns: df["tags"] = ""
        required = ["name","price","tags"]
    for c in required:
        if c not in df.columns: st.error(f"{c} 컬럼이 없습니다."); st.stop()

    df["name"] = df["name"].apply(normalize_str)
    if "category" in df.columns:
        df["category"] = df["category"].apply(normalize_str)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    if df["price"].isnull().any():
        st.error("가격 정보가 잘못된 항목이 있습니다."); st.stop()

    if "tags" in df.columns:
        df["tags_list"] = (
            df["tags"].fillna("").astype(str)
            .str.replace("#","").str.replace(";",",")
            .str.split(r"\s*,\s*", regex=True)
            .apply(lambda xs: [t for t in xs if t])
        )
    else:
        df["tags_list"] = [[] for _ in range(len(df))]

    df["type"] = "drink" if is_drink else "bakery"
    prefix = "D" if is_drink else "B"
    df["item_id"] = [f"{prefix}{i+1:04d}" for i in range(len(df))]
    return df

bakery_df = normalize_columns(pd.read_csv("Bakery_menu.csv"), is_drink=False)
drink_df  = normalize_columns(pd.read_csv("Drink_menu.csv"), is_drink=True)
drink_categories = sorted(drink_df["category"].dropna().unique())
bakery_tags = sorted({t for arr in bakery_df["tags_list"] for t in arr})

# ---------------- 세션 ----------------
if "user" not in st.session_state: st.session_state.user = {"name":"고객"}
if "cart" not in st.session_state: st.session_state.cart = []

# ---------------- 로그인 ----------------
st.header("🥐 베이커리 추천·주문")
st.success(f"{st.session_state.user['name']}님, 환영합니다!")

# ---------------- 탭 ----------------
tab_reco, tab_menu, tab_cart = st.tabs(["AI 추천", "메뉴판", "장바구니"])

# ===== 추천 =====
with tab_reco:
    st.title("🤖 AI 추천 메뉴")

    c1, c2, c3 = st.columns(3)
    with c1:
        n_people = st.number_input("인원 수(음료 잔 수)", 1, 20, 2)
        budget_type = st.selectbox("예산 기준", ["총예산", "1인예산"])
        budget_val = st.number_input("금액(원)", min_value=0, value=15000, step=500)

    with c2:
        n_bakery = st.slider("베이커리 개수", 0, 5, 2)
        sel_cats = st.multiselect("음료 카테고리", drink_categories, default=drink_categories)

    with c3:
        sel_tags = st.multiselect("베이커리 태그(최대 3개)", bakery_tags, max_selections=3)

    st.markdown("---")

    if st.button("AI 추천 보기", type="primary", use_container_width=True):
        drinks = drink_df[drink_df["category"].isin(sel_cats)] if sel_cats else drink_df
        bakery = bakery_df.copy()
        if sel_tags:
            tagset = set(sel_tags)
            bakery = bakery[bakery["tags_list"].apply(lambda xs: not tagset.isdisjoint(set(xs)))]

        results = []
        for d in drinks.head(10).to_dict("records"):
            for b_combo in itertools.combinations(bakery.head(10).to_dict("records"), n_bakery if n_bakery > 0 else 0):
                total_price = d["price"] * n_people + sum(b["price"] for b in b_combo)
                results.append({"drink": d, "bakery": b_combo, "total": total_price})

        if not results:
            st.warning("조건에 맞는 메뉴가 없습니다.")
            st.stop()

        for i, r in enumerate(results[:3], start=1):
            st.markdown(f"### 추천 세트 {i}")
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**음료:** {r['drink']['name']} ({money(r['drink']['price'])})")
                if st.button(f"🛒 담기 (음료) {r['drink']['name']}", key=f"d_{uuid.uuid4().hex[:6]}"):
                    st.session_state.cart.append({
                        "item_id": r["drink"]["item_id"], "name": r["drink"]["name"],
                        "type": "drink", "category": r["drink"]["category"],
                        "qty": 1, "unit_price": int(r["drink"]["price"])
                    })
                    st.toast("음료를 장바구니에 담았습니다.")
                    st.session_state.modified_cart = True
                    st.rerun()
            with col2:
                st.write("**베이커리**")
                for b in r["bakery"]:
                    st.write(f"- {b['name']} ({money(b['price'])})")
                    if st.button(f"🛒 담기 (베이커리) {b['name']}", key=f"b_{uuid.uuid4().hex[:6]}"):
                        st.session_state.cart.append({
                            "item_id": b["item_id"], "name": b["name"], "type": "bakery",
                            "category": "", "qty": 1, "unit_price": int(b["price"])
                        })
                        st.toast("베이커리를 장바구니에 담았습니다.")
                        st.session_state.modified_cart = True
                        st.rerun()

# ===== 메뉴판 =====
with tab_menu:
    st.title("📋 메뉴판")
    c1, c2 = st.columns(2)
    with c1: st.dataframe(bakery_df[["name","price","tags"]])
    with c2: st.dataframe(drink_df[["name","price","category"]])

# ===== 장바구니 =====
with tab_cart:
    st.title("🛍️ 장바구니")
    if not st.session_state.cart:
        st.write("장바구니가 비어 있습니다.")
    else:
        df_cart = pd.DataFrame(st.session_state.cart)
        for i in range(len(df_cart)):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
            with c1: st.write(df_cart.iloc[i]["name"])
            with c2:
                qty = st.number_input("수량", 1, 99, int(df_cart.iloc[i]["qty"]), key=f"qty_{i}")
                df_cart.at[i, "qty"] = qty
            with c3: st.write(money(df_cart.iloc[i]["unit_price"]))
            with c4:
                if st.button("삭제", key=f"rm_{uuid.uuid4().hex[:6]}"):
                    st.session_state.cart.pop(i)
                    st.session_state.modified_cart = True
                    st.rerun()

        st.session_state.cart = df_cart.to_dict("records")
        total = int((df_cart["qty"] * df_cart["unit_price"]).sum())
        note = st.text_input("요청사항", "")
        st.write(f"**총액: {money(total)}**")

        if st.button("주문 완료 (매장 이메일 발송)", type="primary"):
            oid = f"O{datetime.now().strftime('%H%M%S')}"
            ok, err = send_order_email([OWNER_EMAIL_PRIMARY], SHOP_NAME, oid, df_cart.to_dict("records"), total, note)
            if ok:
                st.success("주문이 접수되었습니다. 매장으로 이메일이 발송되었습니다.")
                st.session_state.cart = []
                st.session_state.modified_cart = False
                st.rerun()
            else:
                st.error(f"이메일 전송에 실패했습니다: {err}")
