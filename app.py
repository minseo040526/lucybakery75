# app.py
import streamlit as st
import pandas as pd
import itertools, os, re, smtplib, ssl
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime
from PIL import Image

# ---------------- 기본 설정 ----------------
st.set_page_config(page_title="AI 베이커리 추천·주문", layout="wide")

SHOP_NAME = st.secrets.get("SHOP_NAME", "Lucy Bakery")
OWNER_EMAIL_PRIMARY = st.secrets.get("OWNER_EMAIL_PRIMARY", "")
OWNER_EMAIL_CC = st.secrets.get("OWNER_EMAIL_CC", "")
WELCOME_COUPON_AMOUNT = int(st.secrets.get("WELCOME_COUPON_AMOUNT", "2000"))
SMTP_HOST = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(st.secrets.get("SMTP_PORT", "465"))
SMTP_USER = st.secrets.get("SMTP_USER", "")
SMTP_PASS = st.secrets.get("SMTP_PASS", "")

DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)
USERS_CSV = os.path.join(DATA_DIR, "users.csv")
COUPONS_CSV = os.path.join(DATA_DIR, "coupons.csv")
ORDERS_CSV = os.path.join(DATA_DIR, "orders.csv")
ORDER_ITEMS_CSV = os.path.join(DATA_DIR, "order_items.csv")

# ---------------- 유틸 ----------------
def now_ts(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_csv(path, cols):
    if os.path.exists(path): 
        try: return pd.read_csv(path)
        except Exception: return pd.DataFrame(columns=cols)
    return pd.DataFrame(columns=cols)

def save_csv(df, path): df.to_csv(path, index=False)

def normalize_str(s): return re.sub(r"\s+"," ",str(s).strip()) if pd.notna(s) else ""

def money(x):
    try: return f"{int(x):,}원"
    except: return str(x)

def load_image(path):
    try: return Image.open(path)
    except: return None

# ---------------- 데이터 로드 ----------------
def normalize_columns(df, is_drink=False):
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]

    if is_drink:
        required = ["name","price","category"]
    else:
        if "tags" not in df.columns:
            df["tags"] = ""
        required = ["name","price","tags"]

    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"필수 컬럼이 없습니다: {', '.join(missing)}")
        st.stop()

    df["name"] = df["name"].apply(normalize_str)
    if "category" in df.columns:
        df["category"] = df["category"].apply(normalize_str)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    if df["price"].isnull().any():
        st.error("price 컬럼에 숫자가 아닌 값이 포함되어 있습니다.")
        st.stop()

    if "tags" in df.columns:
        df["tags"] = df["tags"].fillna("").astype(str)
        df["tags_list"] = (
            df["tags"].str.replace("#","",regex=False)
                      .str.replace(";", ",", regex=False)
                      .str.split(r"\s*,\s*", regex=True)
                      .apply(lambda xs: [t for t in xs if t])
        )
    else:
        df["tags_list"] = [[] for _ in range(len(df))]

    df = df.reset_index(drop=True)
    df["type"] = "drink" if is_drink else "bakery"
    prefix = "D" if is_drink else "B"
    df["item_id"] = [f"{prefix}{i+1:04d}" for i in range(len(df))]
    df = df.drop_duplicates(subset=["name","type"])
    return df

bakery_df = normalize_columns(pd.read_csv("Bakery_menu.csv"), is_drink=False)
drink_df  = normalize_columns(pd.read_csv("Drink_menu.csv"), is_drink=True)

drink_categories = sorted([c for c in drink_df["category"].dropna().unique().tolist() if c != ""])
bakery_all_tags = sorted({t for arr in bakery_df["tags_list"] for t in arr})

# ---------------- 세션 ----------------
if "user" not in st.session_state: st.session_state.user = None
if "cart" not in st.session_state: st.session_state.cart = []

# ---------------- 이메일 ----------------
def send_order_email(to_emails, shop_name, order_id, items, total, note, coupon_used):
    if not SMTP_USER or not SMTP_PASS or not to_emails:
        return False, "SMTP 설정이 완료되지 않았습니다."
    lines = [
        f"[{shop_name}] 새 주문이 접수되었습니다.",
        f"주문번호: {order_id}",
        "---- 주문 품목 ----"
    ]
    for it in items:
        lines.append(f"- {it['name']} x{it['qty']} ({money(it['unit_price'])})")
    lines += [
        "-------------------",
        f"쿠폰 사용: {'예(2000원)' if coupon_used else '아니오'}",
        f"총액: {money(total)}",
        f"요청 메모: {note or '-'}",
        f"시간: {now_ts()}",
    ]
    msg = MIMEText("\n".join(lines), _charset="utf-8")
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

# ---------------- 로그인 ----------------
st.header("🥐 베이커리 추천·주문")

with st.expander("로그인 또는 게스트 주문"):
    colA, colB = st.columns(2)
    with colA: phone_last4 = st.text_input("휴대폰번호 뒷 4자리", max_chars=4)
    with colB: pw6 = st.text_input("비밀번호(6자리)", max_chars=6, type="password")

    if st.button("로그인 또는 자동가입"):
        st.session_state.user = {"user_id":"GUEST","name":"고객","phone_last4":phone_last4,"pw6":pw6}
        st.success("로그인 없이 주문이 가능합니다. (쿠폰 사용은 비활성화됩니다.)")

user = st.session_state.user
if user is None:
    st.info("로그인 또는 게스트 주문을 진행해 주세요.")
    st.stop()
st.success(f"{user.get('name') or '고객'}님, 환영합니다!")

# ---------------- 탭 ----------------
tab_reco, tab_board, tab_cart = st.tabs(["AI 메뉴 추천","메뉴판","장바구니"])

# ===== AI 메뉴 추천 =====
with tab_reco:
    st.title("🤖 AI 추천")

    c1, c2, c3 = st.columns(3)
    with c1:
        n_people = st.number_input("인원 수(음료 잔 수)", 1, 20, 2)
        budget_mode = st.selectbox("예산 방식", ["총예산", "1인예산"])
        budget_val = st.number_input("금액(원)", min_value=0, value=15000, step=500)

    with c2:
        n_bakery = st.slider("베이커리 개수", 0, 8, 2)
        sel_cats = st.multiselect("음료 카테고리(복수 선택 가능)", drink_categories, default=drink_categories)

    with c3:
        sel_tags = st.multiselect("베이커리 태그 선택(최대 3개)", bakery_all_tags, max_selections=3)

    st.markdown("---")

    if st.button("AI 추천 보기", type="primary", use_container_width=True):
        drinks = drink_df.copy()
        if sel_cats:
            sel_cats_norm = [normalize_str(c) for c in sel_cats]
            drinks = drinks[drinks["category"].astype(str).str.strip().isin(sel_cats_norm)]
        bakery = bakery_df.copy()
        if sel_tags:
            tagset = set(sel_tags)
            bakery = bakery[bakery["tags_list"].apply(lambda xs: not tagset.isdisjoint(set(xs)))]

        results = []
        for d in drinks.head(10).to_dict("records"):
            for combo in itertools.combinations(bakery.head(10).to_dict("records"), n_bakery if n_bakery > 0 else 0):
                total_price = d["price"] * n_people + sum(x["price"] for x in combo)
                results.append({"drink": d, "bakery": combo, "total": total_price})
        if not results:
            st.warning("조건에 맞는 추천이 없습니다. 조건을 변경해 주세요.")
            st.stop()

        for i, r in enumerate(results[:3], start=1):
            st.markdown(f"### 추천 세트 {i}")
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**음료:** {r['drink']['name']} ({money(r['drink']['price'])})")
                if st.button(f"🛒 담기 (음료) {r['drink']['name']}", key=f"d_{i}"):
                    st.session_state.cart.append({
                        "item_id": r["drink"]["item_id"], "name": r["drink"]["name"], "type": "drink",
                        "category": r["drink"]["category"], "qty": 1, "unit_price": r["drink"]["price"]
                    })
                    st.toast("음료를 장바구니에 담았습니다.")
                    st.rerun()
            with c2:
                st.write("**베이커리**")
                for b in r["bakery"]:
                    st.write(f"- {b['name']} ({money(b['price'])})")
                    if st.button(f"🛒 담기 (베이커리) {b['name']}", key=f"b_{i}_{b['item_id']}"):
                        st.session_state.cart.append({
                            "item_id": b["item_id"], "name": b["name"], "type": "bakery",
                            "category": "", "qty": 1, "unit_price": b["price"]
                        })
                        st.toast("베이커리를 장바구니에 담았습니다.")
                        st.rerun()

# ===== 메뉴판 =====
with tab_board:
    st.title("메뉴판")
    c1, c2 = st.columns(2)
    with c1: st.dataframe(bakery_df[["name","price","tags"]])
    with c2: st.dataframe(drink_df[["name","price","category"]])

# ===== 장바구니 =====
with tab_cart:
    st.title("장바구니")
    if len(st.session_state.cart)==0:
        st.write("- 장바구니가 비어 있습니다.")
    else:
        df_cart = pd.DataFrame(st.session_state.cart)
        for i in range(len(df_cart)):
            c1, c2, c3, c4 = st.columns([4,2,2,2])
            with c1: st.write(df_cart.iloc[i]["name"])
            with c2:
                new_qty = st.number_input("수량", 1, 99, int(df_cart.iloc[i]["qty"]), key=f"qty_{i}")
                df_cart.at[i, "qty"] = new_qty
            with c3: st.write(money(df_cart.iloc[i]["unit_price"]))
            with c4:
                if st.button("삭제", key=f"rm_{i}"):
                    st.session_state.cart.pop(i)
                    st.rerun()

        st.session_state.cart = df_cart.to_dict("records")
        total = int((df_cart["qty"] * df_cart["unit_price"]).sum())
        note = st.text_input("요청 메모", "")
        st.write(f"**총액: {money(total)}**")

        if st.button("주문 완료(매장 이메일 알림)"):
            ok, err = send_order_email([OWNER_EMAIL_PRIMARY], SHOP_NAME, f"O{datetime.now().strftime('%H%M%S')}",
                                       df_cart.to_dict("records"), total, note, False)
            if ok:
                st.success("주문이 접수되었습니다. 매장으로 이메일이 발송되었습니다.")
                st.session_state.cart = []
                st.rerun()
            else:
                st.error(f"이메일 발송에 실패했습니다: {err}")
