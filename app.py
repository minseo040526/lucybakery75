# app.py
import streamlit as st
import pandas as pd
import numpy as np
import re, os, math, smtplib, ssl
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime
from io import StringIO

st.set_page_config(page_title="Bakery Recommender", page_icon="🥐", layout="centered")

# -----------------------
# 기본 설정(사장 이메일 등)
# -----------------------
SHOP_NAME = st.secrets.get("SHOP_NAME", "Lucy Bakery")
OWNER_EMAIL_PRIMARY = st.secrets.get("OWNER_EMAIL_PRIMARY", "")  # 예: owner@example.com
OWNER_EMAIL_CC = st.secrets.get("OWNER_EMAIL_CC", "")
WELCOME_COUPON_AMOUNT = int(st.secrets.get("WELCOME_COUPON_AMOUNT", "2000"))

# 이메일(SMTP) 설정(지메일 권장: 앱 비밀번호 사용)
SMTP_HOST = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(st.secrets.get("SMTP_PORT", "465"))
SMTP_USER = st.secrets.get("SMTP_USER", "")  # 예: yourshop.notify@gmail.com
SMTP_PASS = st.secrets.get("SMTP_PASS", "")  # 앱 비밀번호

DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)

USERS_CSV = os.path.join(DATA_DIR, "users.csv")
COUPONS_CSV = os.path.join(DATA_DIR, "coupons.csv")
ORDERS_CSV = os.path.join(DATA_DIR, "orders.csv")
ORDER_ITEMS_CSV = os.path.join(DATA_DIR, "order_items.csv")

# -----------------------
# 유틸
# -----------------------
def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_csv_safe(path, columns=None):
    if os.path.exists(path):
        df = pd.read_csv(path)
    else:
        df = pd.DataFrame(columns=columns or [])
    return df

def save_csv(df, path):
    df.to_csv(path, index=False)

def normalize_str(x):
    if pd.isna(x):
        return ""
    return re.sub(r"\s+", " ", str(x).strip())

def parse_tags(s):
    s = normalize_str(s).lower()
    # 허용 구분자: 공백/콤마/세미콜론/해시
    s = s.replace(",", " ").replace(";", " ")
    parts = [p.strip("#").strip() for p in s.split() if p.strip("#").strip()]
    return list(dict.fromkeys(parts))  # 중복 제거, 순서 보존

def money(x):
    return f"{int(x):,}원"

# -----------------------
# 영속 테이블 로드/초기화
# -----------------------
users = load_csv_safe(USERS_CSV, ["user_id","phone_last4","pw6","name","joined_at","last_login"])
coupons = load_csv_safe(COUPONS_CSV, ["coupon_id","user_id","amount","issued_at","used","used_at"])
orders = load_csv_safe(ORDERS_CSV, ["order_id","user_id","total_price","coupon_used","note","status","created_at","notified_email","notified_at","notify_error"])
order_items = load_csv_safe(ORDER_ITEMS_CSV, ["order_id","item_id","name","type","category","qty","unit_price"])

# -----------------------
# 세션상태
# -----------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "cart" not in st.session_state:
    st.session_state.cart = []  # list of dict: {item_id,name,type,category,qty,unit_price}
if "drinks" not in st.session_state:
    st.session_state.drinks = None
if "bakery" not in st.session_state:
    st.session_state.bakery = None

# -----------------------
# 이메일 발송
# -----------------------
def send_order_email(to_emails, shop_name, order_id, items, total, note, coupon_used):
    if not SMTP_USER or not SMTP_PASS or not to_emails:
        return False, "SMTP 설정 누락"

    body_lines = [f"[{shop_name}] 새 주문 도착",
                  f"주문번호: {order_id}",
                  "---- 품목 ----"]
    for it in items:
        body_lines.append(f"- {it['name']} x{it['qty']} ({money(it['unit_price'])})")
    body_lines += [
        "--------------",
        f"쿠폰사용: {'예(2000원)' if coupon_used else '아니오'}",
        f"총액: {money(total)}",
        f"요청메모: {note or '-'}",
        f"시간: {now_ts()}",
    ]
    msg = MIMEText("\n".join(body_lines), _charset="utf-8")
    msg["Subject"] = f"[{shop_name}] 주문 알림 #{order_id}"
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(to_emails)
    if OWNER_EMAIL_CC:
        msg["Cc"] = OWNER_EMAIL_CC
        to_emails = to_emails + [OWNER_EMAIL_CC]
    msg["Date"] = formatdate(localtime=True)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(msg["From"], to_emails, msg.as_string())
        return True, ""
    except Exception as e:
        return False, str(e)

# -----------------------
# 메뉴 CSV 업로드 UI
# -----------------------
st.sidebar.header("1) 메뉴 CSV 업로드")
up_drink = st.sidebar.file_uploader("Drink CSV (영문 컬럼: name, category, price, tags, image_url?, is_active?)", type=["csv"])
up_bakery = st.sidebar.file_uploader("Bakery CSV (영문 컬럼: name, category, price, tags, image_url?, is_active?)", type=["csv"])

def normalize_menu(df, item_type):
    # 기대 컬럼: name, category, price, tags, image_url?, is_active?
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    needed = ["name","category","price","tags"]
    for c in needed:
        if c not in df.columns:
            df[c] = ""
    if "is_active" not in df.columns:
        df["is_active"] = 1
    if "image_url" not in df.columns:
        df["image_url"] = ""
    df["name"] = df["name"].apply(normalize_str)
    df["category"] = df["category"].apply(normalize_str)
    # price 숫자화
    def to_int(x):
        try:
            return int(float(str(x).replace(",","").strip()))
        except:
            return 0
    df["price"] = df["price"].apply(to_int)
    df["tags_list"] = df["tags"].apply(parse_tags)
    df["type"] = item_type
    # item_id 부여
    base = "D" if item_type == "drink" else "B"
    df = df.reset_index(drop=True)
    df["item_id"] = [f"{base}{i+1:04d}" for i in range(len(df))]
    # active 필터
    def to_active(v):
        try:
            return 1 if int(v) == 1 else 0
        except:
            s = str(v).strip().lower()
            return 1 if s in ("1","true","yes","y") else 0
    df["is_active"] = df["is_active"].apply(to_active)
    # 최종 컬럼 순서
    cols = ["item_id","name","type","category","price","tags","tags_list","is_active","image_url"]
    return df[cols]

if up_drink is not None:
    df_d = pd.read_csv(up_drink)
    st.session_state.drinks = normalize_menu(df_d, "drink")
if up_bakery is not None:
    df_b = pd.read_csv(up_bakery)
    st.session_state.bakery = normalize_menu(df_b, "bakery")

if st.session_state.drinks is not None:
    st.sidebar.success(f"음료 {len(st.session_state.drinks)}개 로드됨")
if st.session_state.bakery is not None:
    st.sidebar.success(f"빵 {len(st.session_state.bakery)}개 로드됨")

# -----------------------
# 로그인/가입
# -----------------------
st.header("🥐 베이커리 추천·주문")

if st.session_state.user is None:
    st.subheader("로그인")
    phone_last4 = st.text_input("휴대폰번호 뒷 4자리", max_chars=4)
    pw6 = st.text_input("비밀번호(6자리)", max_chars=6, type="password")
    name_opt = st.text_input("이름(처음이면 입력)")
    colL, colR = st.columns(2)
    login_btn = colL.button("로그인")
    signup_btn = colR.button("최초가입")

    if login_btn:
        m = users[(users["phone_last4"] == phone_last4) & (users["pw6"] == pw6)]
        if len(m) == 1:
            users.loc[m.index[0], "last_login"] = now_ts()
            save_csv(users, USERS_CSV)
            st.session_state.user = m.iloc[0].to_dict()
            st.success("로그인 완료")
        else:
            st.error("일치하는 계정 없음. 최초가입 눌러줘")

    if signup_btn:
        if not phone_last4 or not pw6:
            st.error("뒷4자리/비번6자리 입력")
        else:
            dupe = users[(users["phone_last4"] == phone_last4) & (users["pw6"] == pw6)]
            if len(dupe) > 0:
                st.warning("이미 가입되어 있음. 로그인 사용")
            else:
                uid = f"U{len(users)+1:04d}"
                users = pd.concat([users, pd.DataFrame([{
                    "user_id": uid,
                    "phone_last4": phone_last4,
                    "pw6": pw6,
                    "name": name_opt or "",
                    "joined_at": now_ts(),
                    "last_login": now_ts()
                }])], ignore_index=True)
                save_csv(users, USERS_CSV)
                # 쿠폰 발급(2000원)
                cid = f"C{len(coupons)+1:04d}"
                coupons = pd.concat([coupons, pd.DataFrame([{
                    "coupon_id": cid, "user_id": uid, "amount": WELCOME_COUPON_AMOUNT,
                    "issued_at": now_ts(), "used": 0, "used_at": ""
                }])], ignore_index=True)
                save_csv(coupons, COUPONS_CSV)
                st.session_state.user = users.iloc[-1].to_dict()
                st.success(f"가입완료! {WELCOME_COUPON_AMOUNT}원 쿠폰 1장 지급")
    st.stop()

# -----------------------
# 홈(추천/지난주문)
# -----------------------
user = st.session_state.user
st.success(f"{user.get('name') or '고객'}님 환영!")
st.caption("홈 → 내 취향 메뉴 찾기에서 추천받고 장바구니 담아 주문완료 누르면 이메일로 매장에 알림")

col1, col2 = st.columns(2)
with col1:
    st.markdown("### 오늘의 추천")
    # 단순히 활성화된 상위 4개 샘플
    recs = []
    if st.session_state.drinks is not None:
        recs += st.session_state.drinks[st.session_state.drinks["is_active"]==1].head(2).to_dict("records")
    if st.session_state.bakery is not None:
        recs += st.session_state.bakery[st.session_state.bakery["is_active"]==1].head(2).to_dict("records")
    if recs:
        for r in recs:
            st.write(f"- {r['name']} ({money(r['price'])})")
    else:
        st.write("- 메뉴 CSV 업로드 필요")

with col2:
    st.markdown("### 지난 주문")
    my_orders = orders[orders["user_id"] == user["user_id"]].sort_values("created_at", ascending=False).head(3)
    if len(my_orders)==0:
        st.write("- 아직 없음")
    else:
        for _, row in my_orders.iterrows():
            st.write(f"- #{row['order_id']} / {row['created_at']} / {money(row['total_price'])}")

st.divider()

# -----------------------
# 내 취향 메뉴 찾기(추천)
# -----------------------
st.subheader("내 취향 메뉴 찾기")

# 카테고리 목록(음료만)
drink_df = st.session_state.drinks if st.session_state.drinks is not None else pd.DataFrame()
bakery_df = st.session_state.bakery if st.session_state.bakery is not None else pd.DataFrame()

drink_categories = sorted([c for c in drink_df["category"].dropna().unique()]) if not drink_df.empty else []
sel_category = st.selectbox("음료 카테고리(정확일치)", options=drink_categories) if drink_categories else st.text_input("음료 카테고리(정확일치 텍스트)")

colL, colR = st.columns(2)
people = colL.number_input("인원 수(음료 추천 개수)", min_value=1, value=2, step=1)
bakery_cnt = colR.number_input("빵 추천 개수", min_value=0, value=1, step=1)

colB1, colB2 = st.columns(2)
budget_mode = colB1.selectbox("예산 입력 방식", ["총예산", "1인예산"])
budget_val = colB2.number_input("금액(원)", min_value=0, value=10000, step=500)

pref_tags = st.text_input("취향 태그(예: sweet nutty light)", help="공백/콤마/해시 모두 가능")
pref_list = parse_tags(pref_tags)

def score_items(df, pref):
    if df is None or df.empty:
        return pd.DataFrame(columns=list(df.columns) if df is not None else [])
    df = df[df["is_active"]==1].copy()
    # 태그 매칭 점수
    df["tag_score"] = df["tags_list"].apply(lambda L: len(set([t.lower() for t in pref]) & set([t.lower() for t in L])))
    # 간단 인기점수(없음): 0
    df["pop_score"] = 0.0
    df["score"] = df["tag_score"] + df["pop_score"]
    return df.sort_values(["score","price"], ascending=[False, True])

def pick_drinks(df, category, n, per_person_budget=None, total_budget=None, bakery_total=0):
    if df is None or df.empty:
        return []
    # 카테고리 정확 일치(공백정규화)
    norm_cat = normalize_str(category).lower()
    cand = df[df["category"].apply(lambda x: normalize_str(x).lower()==norm_cat)].copy()
    cand = score_items(cand, pref_list)
    if len(cand)==0:
        return []
    # 예산 고려: 음료 총예산 = total_budget - bakery_total
    drink_total_budget = None
    if total_budget is not None:
        drink_total_budget = max(0, total_budget - bakery_total)
    elif per_person_budget is not None:
        drink_total_budget = per_person_budget * n

    picked = []
    total = 0
    for _, row in cand.iterrows():
        if len(picked) >= n:
            break
        if drink_total_budget is not None and total + row["price"] > drink_total_budget:
            continue
        picked.append(row.to_dict())
        total += row["price"]
    # 예산 때문에 모자라면 그냥 상위에서 채움(있는 만큼)
    if len(picked) < n:
        for _, row in cand.iterrows():
            if len(picked) >= n:
                break
            if row.to_dict() not in picked:
                picked.append(row.to_dict())
    return picked

def pick_bakery(df, k, remaining_budget=None):
    if df is None or df.empty or k<=0:
        return []
    cand = score_items(df, pref_list)
    picked = []
    total = 0
    for _, row in cand.iterrows():
        if len(picked) >= k:
            break
        if remaining_budget is not None and total + row["price"] > remaining_budget:
            continue
        picked.append(row.to_dict())
        total += row["price"]
    # 예산 때문에 못 채우면 상위에서 채움
    if len(picked) < k:
        for _, row in cand.iterrows():
            if len(picked) >= k:
                break
            if row.to_dict() not in picked:
                picked.append(row.to_dict())
    return picked

# 추천 실행 버튼
if st.button("추천 받기"):
    total_budget = None
    per_person_budget = None
    if budget_mode == "총예산":
        total_budget = int(budget_val)
    else:
        per_person_budget = int(budget_val)

    # 빵 먼저 대충 픽(예산 없으면 상위)
    bakery_pick = pick_bakery(bakery_df, bakery_cnt, None if total_budget is None else total_budget//2)
    bakery_sum = sum([b["price"] for b in bakery_pick])

    drinks_pick = pick_drinks(drink_df, sel_category, people,
                              per_person_budget=per_person_budget,
                              total_budget=total_budget,
                              bakery_total=bakery_sum)
    st.write("**음료 추천**")
    if drinks_pick:
        for it in drinks_pick:
            st.write(f"- {it['name']} / {it['category']} / {money(it['price'])} / tags: {', '.join(it['tags_list'])}")
    else:
        st.info("해당 카테고리에서 추천할 음료 없음")

    st.write("**빵 추천**")
    if bakery_pick:
        for it in bakery_pick:
            st.write(f"- {it['name']} / {money(it['price'])} / tags: {', '.join(it['tags_list'])}")
    else:
        st.info("빵 추천 없음")

    # 장바구니 담기
    add_to_cart = st.checkbox("위 추천을 장바구니에 담기")
    if add_to_cart:
        for it in drinks_pick + bakery_pick:
            st.session_state.cart.append({
                "item_id": it["item_id"],
                "name": it["name"],
                "type": it["type"],
                "category": it["category"],
                "qty": 1,
                "unit_price": int(it["price"])
            })
        st.success("장바구니에 담았음")

st.divider()

# -----------------------
# 장바구니 & 주문
# -----------------------
st.subheader("장바구니")
if len(st.session_state.cart)==0:
    st.write("- 비어있음")
else:
    df_cart = pd.DataFrame(st.session_state.cart)
    # 수량 수정
    for i in range(len(df_cart)):
        c1, c2, c3, c4 = st.columns([4,2,2,2])
        with c1:
            st.write(f"{df_cart.iloc[i]['name']} ({df_cart.iloc[i]['type']})")
        with c2:
            new_qty = st.number_input("수량", min_value=1, value=int(df_cart.iloc[i]['qty']), key=f"qty_{i}")
            df_cart.at[i, "qty"] = new_qty
        with c3:
            st.write(money(df_cart.iloc[i]['unit_price']))
        with c4:
            rm = st.button("삭제", key=f"rm_{i}")
            if rm:
                st.session_state.cart.pop(i)
                st.experimental_rerun()
    # 총액
    subtotal = int((df_cart["qty"] * df_cart["unit_price"]).sum())

    # 쿠폰 사용 가능 여부
    my_coupons = coupons[(coupons["user_id"]==user["user_id"]) & (coupons["used"]==0)]
    use_coupon = False
    if len(my_coupons)>0:
        use_coupon = st.checkbox(f"쿠폰 사용 (-{WELCOME_COUPON_AMOUNT}원)")

    note = st.text_input("요청 메모", "")

    total = subtotal
    coupon_id = None
    if use_coupon:
        total = max(0, subtotal - WELCOME_COUPON_AMOUNT)
        coupon_id = my_coupons.iloc[0]["coupon_id"]

    st.write(f"**총액: {money(total)}**")

    colA,colB = st.columns(2)
    if colA.button("장바구니 비우기"):
        st.session_state.cart = []
        st.experimental_rerun()

    order_btn = colB.button("주문 완료(매장 이메일 알림)")
    if order_btn:
        # 주문 저장
        new_id = f"O{len(orders)+1:06d}"
        new_order = {
            "order_id": new_id,
            "user_id": user["user_id"],
            "total_price": total,
            "coupon_used": 1 if use_coupon else 0,
            "note": note,
            "status": "접수",
            "created_at": now_ts(),
            "notified_email": 0,
            "notified_at": "",
            "notify_error": ""
        }
        orders = pd.concat([orders, pd.DataFrame([new_order])], ignore_index=True)
        # 아이템 저장
        to_save_items = []
        for _, r in df_cart.iterrows():
            to_save_items.append({
                "order_id": new_id,
                "item_id": r["item_id"],
                "name": r["name"],
                "type": r["type"],
                "category": r["category"],
                "qty": int(r["qty"]),
                "unit_price": int(r["unit_price"])
            })
        order_items = pd.concat([order_items, pd.DataFrame(to_save_items)], ignore_index=True)

        # 쿠폰 소모
        if use_coupon and coupon_id:
            idx = coupons[coupons["coupon_id"]==coupon_id].index
            if len(idx)==1:
                coupons.loc[idx[0], "used"] = 1
                coupons.loc[idx[0], "used_at"] = now_ts()

        # 저장
        save_csv(orders, ORDERS_CSV)
        save_csv(order_items, ORDER_ITEMS_CSV)
        save_csv(coupons, COUPONS_CSV)

        # 이메일 발송
        cart_items = df_cart.to_dict("records")
        ok, err = send_order_email(
            to_emails=[OWNER_EMAIL_PRIMARY] if OWNER_EMAIL_PRIMARY else [],
            shop_name=SHOP_NAME,
            order_id=new_id,
            items=cart_items,
            total=total,
            note=note,
            coupon_used=bool(use_coupon)
        )
        if ok:
            # 주문 상태 업데이트
            idx2 = orders[orders["order_id"]==new_id].index
            if len(idx2)==1:
                orders.loc[idx2[0], "notified_email"] = 1
                orders.loc[idx2[0], "notified_at"] = now_ts()
                save_csv(orders, ORDERS_CSV)

            st.success(f"주문 접수됨! 주문번호 #{new_id} / 매장 이메일 발송 완료")
            st.session_state.cart = []
        else:
            idx2 = orders[orders["order_id"]==new_id].index
            if len(idx2)==1:
                orders.loc[idx2[0], "notify_error"] = err
                save_csv(orders, ORDERS_CSV)
            st.warning(f"주문 저장 완료, **이메일 실패**: {err}. 관리자에게 확인 바람.")

st.divider()
st.caption("관리 팁: .streamlit/secrets.toml에 SHOP_NAME/OWNER_EMAIL_PRIMARY/SMTP_USER/SMTP_PASS 설정하면 바로 실사용.")
