# app.py
import streamlit as st
import pandas as pd
import itertools, os, re, smtplib, ssl
from email.mime.text import MIMEText  # ✅ fixed
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

DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)
USERS_CSV = os.path.join(DATA_DIR, "users.csv")
COUPONS_CSV = os.path.join(DATA_DIR, "coupons.csv")
ORDERS_CSV = os.path.join(DATA_DIR, "orders.csv")
ORDER_ITEMS_CSV = os.path.join(DATA_DIR, "order_items.csv")

# ---------------- 유틸 ----------------
def now_ts(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def load_csv(path, cols):
    if os.path.exists(path): return pd.read_csv(path)
    return pd.DataFrame(columns=cols)
def save_csv(df, path): df.to_csv(path, index=False)
def normalize_str(s): return re.sub(r"\s+"," ",str(s).strip()) if pd.notna(s) else ""
def money(x): 
    try: return f"{int(x):,}원"
    except: return f"{x}"
def load_image(path):
    try: return Image.open(path)
    except: return None

# ---------------- 영속 테이블 ----------------
users = load_csv(USERS_CSV, ["user_id","phone_last4","pw6","name","joined_at","last_login"])
coupons = load_csv(COUPONS_CSV, ["coupon_id","user_id","amount","issued_at","used","used_at"])
orders = load_csv(ORDERS_CSV, ["order_id","user_id","total_price","coupon_used","note","status","created_at","notified_email","notified_at","notify_error"])
order_items = load_csv(ORDER_ITEMS_CSV, ["order_id","item_id","name","type","category","qty","unit_price"])

# ---------------- 세션 ----------------
if "user" not in st.session_state: st.session_state.user = None
if "cart" not in st.session_state: st.session_state.cart = []  # {item_id,name,type,category,qty,unit_price}

# ---------------- 이메일 ----------------
def send_order_email(to_emails, shop_name, order_id, items, total, note, coupon_used):
    if not SMTP_USER or not SMTP_PASS or not to_emails: 
        return False, "SMTP 설정 누락"
    lines = [f"[{shop_name}] 새 주문 도착", f"주문번호: {order_id}", "---- 품목 ----"]
    for it in items:
        lines.append(f"- {it['name']} x{it['qty']} ({money(it['unit_price'])})")
    lines += ["--------------", f"쿠폰사용: {'예(2000원)' if coupon_used else '아니오'}",
              f"총액: {money(total)}", f"요청메모: {note or '-'}", f"시간: {now_ts()}"]
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

# ---------------- 메뉴 CSV 업로드 ----------------
st.sidebar.header("메뉴 CSV 업로드")
up_bakery = st.sidebar.file_uploader("Bakery CSV (영문: name, price[, category])", type=["csv"])
up_drink  = st.sidebar.file_uploader("Drink CSV (영문: name, price, category)", type=["csv"])

def normalize_columns(df, is_drink=False):
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    required = ["name","price"] + (["category"] if is_drink else [])
    miss = [c for c in required if c not in df.columns]
    if miss:
        st.error(f"필수 컬럼 누락: {', '.join(miss)}")
        st.stop()
    df["name"] = df["name"].apply(normalize_str)
    if "category" in df.columns:
        df["category"] = df["category"].apply(normalize_str)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    if df["price"].isnull().any(): 
        st.error("price에 숫자가 아닌 값이 있습니다.")
        st.stop()
    df = df.reset_index(drop=True)
    df["type"] = "drink" if is_drink else "bakery"
    df["item_id"] = [("D" if is_drink else "B")+f"{i+1:04d}" for i in range(len(df))]
    cols = ["item_id","name","type","price"] + (["category"] if is_drink else (["category"] if "category" in df.columns else []))
    # 중복 제거(이름+타입 기준)
    df = df.drop_duplicates(subset=["name","type"])
    return df[cols]

def load_or_default(up, default_name, is_drink):
    if up is not None:
        df = pd.read_csv(up)
    else:
        candidates = [default_name, default_name.replace(".csv"," (2).csv")]
        for c in candidates:
            if os.path.exists(c):
                df = pd.read_csv(c); break
        else:
            st.error(f"{default_name} 업로드 또는 파일 배치 필요")
            st.stop()
    return normalize_columns(df, is_drink=is_drink)

bakery_df = load_or_default(up_bakery, "Bakery_menu.csv", is_drink=False)
drink_df  = load_or_default(up_drink,  "Drink_menu.csv",  is_drink=True)

drink_categories = sorted(drink_df["category"].dropna().unique().tolist())

# ---------------- 로그인/게스트 ----------------
st.header("🥐 베이커리 추천·주문")

with st.expander("로그인/가입(선택)"):
    colA,colB,colC = st.columns([1,1,1])
    with colA: phone_last4 = st.text_input("휴대폰 뒷 4자리", max_chars=4)
    with colB: pw6 = st.text_input("비밀번호(6자리)", max_chars=6, type="password")
    with colC: name_opt = st.text_input("이름(선택)")
    c1,c2,c3 = st.columns(3)
    if c1.button("로그인/자동가입"):
        m = users[(users["phone_last4"]==phone_last4) & (users["pw6"]==pw6)]
        if len(m)==1:
            users.loc[m.index[0],"last_login"]=now_ts(); save_csv(users,USERS_CSV)
            st.session_state.user = m.iloc[0].to_dict()
            st.success("로그인 완료")
        else:
            if not phone_last4 or not pw6:
                st.warning("뒷4자리/비번 입력 후 다시 눌러줘")
            else:
                uid = f"U{len(users)+1:04d}"
                newu = {"user_id":uid,"phone_last4":phone_last4,"pw6":pw6,"name":name_opt or "",
                        "joined_at":now_ts(),"last_login":now_ts()}
                users = pd.concat([users,pd.DataFrame([newu])], ignore_index=True); save_csv(users,USERS_CSV)
                cid = f"C{len(coupons)+1:04d}"
                coupons = pd.concat([coupons, pd.DataFrame([{
                    "coupon_id":cid,"user_id":uid,"amount":WELCOME_COUPON_AMOUNT,
                    "issued_at":now_ts(),"used":0,"used_at":""
                }])], ignore_index=True); save_csv(coupons, COUPONS_CSV)
                st.session_state.user = newu
                st.success("자동 가입 후 로그인됐어(쿠폰 지급).")
    if c2.button("게스트 주문"):
        st.session_state.user = {"user_id":"GUEST","name":"게스트","phone_last4":"","pw6":""}
        st.success("게스트로 주문할게(쿠폰 제외).")

user = st.session_state.user
if user is None:
    st.info("게스트 주문을 누르거나, 로그인/자동가입을 해줘.")
    st.stop()
st.success(f"{user.get('name') or '고객'}님 환영!")

# ---------------- 탭 ----------------
tab_reco, tab_board, tab_cart = st.tabs(["AI 메뉴 추천","메뉴판","장바구니"])

# ===== 추천(카테고리+예산/인원/빵개수만) =====
with tab_reco:
    st.title("🤖 AI 추천")
    c1,c2,c3 = st.columns(3)
    with c1:
        n_people = st.number_input("인원 수(음료 잔 수)", 1, 20, 2)
        mode = st.selectbox("예산 입력", ["총예산","1인예산"])
        budget_val = st.number_input("금액(원)", min_value=0, value=15000, step=500)
    with c2:
        n_bakery = st.slider("베이커리 개수", 0, 8, 2)
        sel_cat = st.selectbox("음료 카테고리", drink_categories if drink_categories else [""])
    with c3:
        st.write("")

    if st.button("추천 보기", type="primary", use_container_width=True):
        drinks = drink_df[drink_df["category"].astype(str).str.strip()==normalize_str(sel_cat)].copy()
        drinks = drinks.sort_values(["price","name"])
        bakery = bakery_df.sort_values(["price","name"])
        if drinks.empty:
            st.warning("해당 카테고리의 음료가 없어."); st.stop()

        if mode=="총예산":
            total_budget = int(budget_val); per_budget = None
        else:
            total_budget = None; per_budget = int(budget_val)

        bakery_pool = bakery.head(max(10, n_bakery))
        bakery_combos = [[]] if n_bakery==0 else []
        if n_bakery>0:
            pool_list = list(bakery_pool.itertuples(index=False))
            for combo in itertools.combinations(pool_list, n_bakery):
                items = [{col:getattr(c,col) for col in bakery.columns} for c in combo]
                bakery_combos.append(items)

        drink_candidates = drinks.head(6).to_dict("records")
        results = []
        for d in drink_candidates:
            drink_cost_per = d["price"]
            for bset in bakery_combos:
                per_price = drink_cost_per
                set_total = drink_cost_per*n_people + sum(x["price"] for x in bset)
                ok = True
                if per_budget is not None and per_price > per_budget: ok = False
                if total_budget is not None and set_total > total_budget: ok = False
                if ok:
                    results.append({"drink": d,"bakery": bset,"per_price": per_price,"total_price": set_total})
            if len(results) > 400: break

        if not results:
            st.warning("예산 조건에 맞는 조합이 없어. 금액을 조정해줘."); st.stop()

        results.sort(key=lambda r: (r["total_price"], r["per_price"]))

        # 상위 3개 + 개별 담기
        for i, r in enumerate(results[:3], start=1):
            st.markdown(f"### 추천 세트 {i}")
            colL, colR = st.columns([1,1])

            with colL:
                d = r["drink"]
                st.write(f"**음료(대표)**: {d['name']} · {money(d['price'])}")
                if st.button(f"담기(음료): {d['name']}", key=f"add_d_{i}_{d['item_id']}"):
                    st.session_state.cart.append({
                        "item_id": d["item_id"], "name": d["name"], "type": d["type"],
                        "category": d.get("category",""), "qty": 1, "unit_price": int(d["price"])
                    })
                    st.toast("장바구니에 담았어.")
                    st.rerun()

            with colR:
                st.write("**베이커리**")
                if len(r["bakery"])==0:
                    st.caption("선택한 베이커리 없음")
                for j, b in enumerate(r["bakery"], start=1):
                    st.write(f"- {b['name']} · {money(b['price'])}")
                    if st.button(f"담기(베이커리): {b['name']}", key=f"add_b_{i}_{j}_{b['item_id']}"):
                        st.session_state.cart.append({
                            "item_id": b["item_id"], "name": b["name"], "type": b["type"],
                            "category": b.get("category",""), "qty": 1, "unit_price": int(b["price"])
                        })
                        st.toast("장바구니에 담았어.")
                        st.rerun()

            st.info(f"1인 {money(r['per_price'])} · 총 {n_people}명 {money(r['total_price'])}")

# ===== 메뉴판 =====
with tab_board:
    st.title("메뉴판")
    img1, img2 = load_image("menu_board_1.png"), load_image("menu_board_2.png")
    c1,c2 = st.columns(2)
    with c1:
        st.subheader("베이커리")
        if img1: st.image(img1, use_column_width=True)
        else: st.dataframe(bakery_df)
    with c2:
        st.subheader("음료")
        if img2: st.image(img2, use_column_width=True)
        else: st.dataframe(drink_df)

# ===== 장바구니 =====
with tab_cart:
    st.title("장바구니")
    if len(st.session_state.cart)==0:
        st.write("- 비어 있어.")
    else:
        df_cart = pd.DataFrame(st.session_state.cart)
        for i in range(len(df_cart)):
            c1,c2,c3,c4 = st.columns([4,2,2,2])
            with c1: st.write(f"{df_cart.iloc[i]['name']} ({df_cart.iloc[i]['type']})")
            with c2:
                qty = st.number_input("수량", 1, 99, int(df_cart.iloc[i]['qty']), key=f"qty_{i}")
                df_cart.at[i,"qty"] = qty
            with c3: st.write(money(df_cart.iloc[i]["unit_price"]))
            with c4:
                if st.button("삭제", key=f"rm_{i}"):
                    st.session_state.cart.pop(i); st.rerun()

        subtotal = int((df_cart["qty"] * df_cart["unit_price"]).sum())

        can_coupon = (st.session_state.user.get("user_id")!="GUEST")
        coupon_used = False; coupon_id = None
        if can_coupon:
            my_coupons = coupons[(coupons["user_id"]==st.session_state.user["user_id"]) & (coupons["used"]==0)]
            if len(my_coupons)>0:
                coupon_used = st.checkbox(f"쿠폰 사용 (-{WELCOME_COUPON_AMOUNT}원)")
                if coupon_used: coupon_id = my_coupons.iloc[0]["coupon_id"]

        note = st.text_input("요청 메모","")
        total = max(0, subtotal - (WELCOME_COUPON_AMOUNT if coupon_used else 0))
        st.write(f"**총액: {money(total)}**")

        cA,cB = st.columns(2)
        if cA.button("장바구니 비우기"):
            st.session_state.cart = []; st.rerun()

        if cB.button("주문 완료(이메일 알림)"):
            oid = f"O{len(orders)+1:06d}"
            new_order = {"order_id":oid,"user_id":st.session_state.user["user_id"],"total_price":total,
                         "coupon_used":1 if coupon_used else 0,"note":note,"status":"접수",
                         "created_at":now_ts(),"notified_email":0,"notified_at":"","notify_error":""}
            orders = pd.concat([orders,pd.DataFrame([new_order])], ignore_index=True)

            rows = []
            for _, r in df_cart.iterrows():
                rows.append({"order_id":oid,"item_id":r["item_id"],"name":r["name"],"type":r["type"],
                             "category":r.get("category",""),"qty":int(r["qty"]),"unit_price":int(r["unit_price"])})
            order_items = pd.concat([order_items,pd.DataFrame(rows)], ignore_index=True)

            if coupon_used and coupon_id:
                idx = coupons[coupons["coupon_id"]==coupon_id].index
                if len(idx)==1:
                    coupons.loc[idx[0],"used"]=1; coupons.loc[idx[0],"used_at"]=now_ts()

            save_csv(orders,ORDERS_CSV); save_csv(order_items,ORDER_ITEMS_CSV); save_csv(coupons,COUPONS_CSV)

            ok, err = send_order_email([OWNER_EMAIL_PRIMARY] if OWNER_EMAIL_PRIMARY else [],
                                       SHOP_NAME, oid, df_cart.to_dict("records"), total, note, coupon_used)
            if ok:
                idx2 = orders[orders["order_id"]==oid].index
                if len(idx2)==1:
                    orders.loc[idx2[0],"notified_email"]=1; orders.loc[idx2[0],"notified_at"]=now_ts()
                    save_csv(orders, ORDERS_CSV)
                st.success(f"주문 접수됐어! #{oid} 이메일 발송 완료")
                st.session_state.cart = []; st.rerun()
            else:
                idx2 = orders[orders["order_id"]==oid].index
                if len(idx2)==1:
                    orders.loc[idx2[0],"notify_error"]=err; save_csv(orders,ORDERS_CSV)
                st.warning(f"주문 저장됨, 이메일 실패: {err}")
