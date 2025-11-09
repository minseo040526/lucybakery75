# app.py
import streamlit as st
import pandas as pd
import itertools, re, os, smtplib, ssl
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime
from PIL import Image

# =========================
# 기본 설정
# =========================
st.set_page_config(page_title="AI 베이커리 메뉴 추천 시스템", layout="wide")

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

# =========================
# 유틸
# =========================
def now_ts(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_csv_safe(path, columns=None):
    if os.path.exists(path): return pd.read_csv(path)
    return pd.DataFrame(columns=columns or [])

def save_csv(df, path): df.to_csv(path, index=False)

def normalize_str(x):
    if pd.isna(x): return ""
    return re.sub(r"\s+", " ", str(x).strip())

def money(x): return f"{int(x):,}원"

def preprocess_tags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["tags_list"] = (
        df["tags"].fillna("").astype(str)
        .str.replace("#","",regex=False).str.replace(";",
        ",",regex=False).str.split(r"\s*,\s*", regex=True)
        .apply(lambda xs: [t for t in xs if t])
    )
    return df

def normalize_columns(df: pd.DataFrame, is_drink: bool=False) -> pd.DataFrame:
    menu_type = "음료" if is_drink else "베이커리"
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    required = ["name","price","sweetness","tags"]
    if is_drink: required.append("category")
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"🚨 {menu_type} 파일에 필수 컬럼({', '.join(missing)})이 없습니다.")
        st.stop()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["sweetness"] = pd.to_numeric(df["sweetness"], errors="coerce")
    if df["price"].isnull().any() or df["sweetness"].isnull().any():
        st.error(f"🚨 {menu_type} 파일의 price/sweetness에 잘못된 값이 있습니다.")
        st.stop()
    if is_drink:
        df["category"] = df["category"].astype(str).str.strip().str.replace("  "," ",regex=False)
    return df

def assign_popularity_score(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "popularity_score" not in df.columns:
        df["popularity_score"] = df["tags_list"].apply(lambda ts: 10 if "인기" in ts else 5)
    return df

def uniq_tags(df: pd.DataFrame) -> set:
    return set(t for arr in df["tags_list"] for t in arr if t)

def load_image(path: str):
    try: return Image.open(path)
    except: return None

# =========================
# 영속 테이블
# =========================
users = load_csv_safe(USERS_CSV, ["user_id","phone_last4","pw6","name","joined_at","last_login"])
coupons = load_csv_safe(COUPONS_CSV, ["coupon_id","user_id","amount","issued_at","used","used_at"])
orders = load_csv_safe(ORDERS_CSV, ["order_id","user_id","total_price","coupon_used","note","status","created_at","notified_email","notified_at","notify_error"])
order_items = load_csv_safe(ORDER_ITEMS_CSV, ["order_id","item_id","name","type","category","qty","unit_price"])

# =========================
# 세션
# =========================
if "user" not in st.session_state: st.session_state.user = None
if "cart" not in st.session_state: st.session_state.cart = []  # {item_id,name,type,category,qty,unit_price}

# =========================
# 이메일
# =========================
def send_order_email(to_emails, shop_name, order_id, items, total, note, coupon_used):
    if not SMTP_USER or not SMTP_PASS or not to_emails:
        return False, "SMTP 설정 누락"
    body = [f"[{shop_name}] 새 주문 도착", f"주문번호: {order_id}", "---- 품목 ----"]
    for it in items:
        body.append(f"- {it['name']} x{it['qty']} ({money(it['unit_price'])})")
    body += [
        "--------------",
        f"쿠폰사용: {'예(2000원)' if coupon_used else '아니오'}",
        f"총액: {money(total)}",
        f"요청메모: {note or '-'}",
        f"시간: {now_ts()}",
    ]
    msg = MIMEText("\n".join(body), _charset="utf-8")
    msg["Subject"] = f"[{shop_name}] 주문 알림 #{order_id}"
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(to_emails)
    if OWNER_EMAIL_CC:
        msg["Cc"] = OWNER_EMAIL_CC
        to_emails = to_emails + [OWNER_EMAIL_CC]
    msg["Date"] = formatdate(localtime=True)

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(msg["From"], to_emails, msg.as_string())
        return True, ""
    except Exception as e:
        return False, str(e)

# =========================
# 메뉴 CSV 업로드
# =========================
st.sidebar.header("메뉴 CSV 업로드")
up_bakery = st.sidebar.file_uploader("Bakery CSV (영문: name, price, sweetness, tags)", type=["csv"])
up_drink  = st.sidebar.file_uploader("Drink CSV (영문: name, price, sweetness, tags, category)", type=["csv"])

def load_or_default(up, default_name, is_drink):
    if up is not None:
        df = pd.read_csv(up)
    else:
        for cand in [default_name, default_name.replace(".csv"," (2).csv")]:
            if os.path.exists(cand):
                df = pd.read_csv(cand); break
        else:
            st.error(f"{default_name} 업로드 또는 파일 준비 필요")
            st.stop()
    df = normalize_columns(df, is_drink=is_drink)
    df = assign_popularity_score(preprocess_tags(df))
    df = df.reset_index(drop=True)
    df["type"] = "drink" if is_drink else "bakery"
    prefix = "D" if is_drink else "B"
    df["item_id"] = [f"{prefix}{i+1:04d}" for i in range(len(df))]
    return df

bakery_df = load_or_default(up_bakery, "Bakery_menu.csv", is_drink=False)
drink_df  = load_or_default(up_drink,  "Drink_menu.csv",  is_drink=True)

all_drink_categories = sorted(drink_df["category"].astype(str).str.strip().unique())
FLAVOR_TAGS = {'달콤한','고소한','짭짤한','단백한','부드러운','깔끔한','쌉싸름한','상큼한','씁쓸한','초코','치즈'}
BAKERY_TAGS = uniq_tags(bakery_df)
DRINK_TAGS  = uniq_tags(drink_df)
ui_bakery_utility_tags = sorted(BAKERY_TAGS - FLAVOR_TAGS)
ui_drink_flavor_tags   = sorted(DRINK_TAGS & FLAVOR_TAGS)

# =========================
# 추천 로직
# =========================
def filter_base(df, min_s, max_s, tags, max_price=None, categories=None, require_all=True):
    f = df.copy()
    if "category" in f.columns:
        if categories and len(categories)>0:
            cats = [str(c).strip() for c in categories]
            f = f[f["category"].astype(str).str.strip().isin(cats)]
        else:
            return pd.DataFrame(columns=f.columns)  # 카테고리 미선택 시 음료 추천 차단
    f = f[(f["sweetness"] >= min_s) & (f["sweetness"] <= max_s)]
    if tags:
        if require_all:
            f = f[f["tags_list"].apply(lambda x: set(tags).issubset(set(x)))]
        else:
            f = f[f["tags_list"].apply(lambda x: not set(x).isdisjoint(set(tags)))]
    if max_price is not None:
        f = f[f["price"] <= max_price]
    return f

def make_recs(f, n_items, max_price=None):
    recs = []
    if f.empty: return recs
    if n_items == 1:
        for _, r in f.sort_values(["popularity_score","price"], ascending=[False,True]).iterrows():
            recs.append([r.to_dict()])
            if len(recs) >= 200: break
        return recs
    pool = f.sort_values("popularity_score", ascending=False).head(30)
    if len(pool) < n_items:
        recs.append([r.to_dict() for _, r in pool.iterrows()])
        return recs
    for combo in itertools.combinations(pool.itertuples(index=False), n_items):
        total_price = sum(c.price for c in combo)
        if (max_price is None) or (total_price <= max_price):
            recs.append([{col: getattr(c, col) for col in f.columns} for c in combo])
            if len(recs) >= 200: break
    return recs

def recommend_strict(df, min_s, max_s, tags, n_items, max_price=None, categories=None):
    f = filter_base(df, min_s, max_s, tags, max_price, categories, require_all=True)
    return make_recs(f, n_items, max_price)

def recommend_relaxed(df, min_s, max_s, tags, n_items, max_price=None, categories=None):
    f = filter_base(df, min_s, max_s, tags, max_price, categories, require_all=False)
    if not f.empty: return make_recs(f, n_items, max_price)
    f = filter_base(df, min_s, max_s, [], max_price, categories, require_all=True)
    if not f.empty: return make_recs(f, n_items, max_price)
    f = filter_base(df, max(1, min_s-1), min(5, max_s+1), [], max_price, categories, require_all=True)
    if not f.empty: return make_recs(f, n_items, max_price)
    f = df.copy()
    if "category" in f.columns and categories:
        cats = [str(c).strip() for c in categories]
        f = f[f["category"].astype(str).str.strip().isin(cats)]
    if max_price is not None:
        f = f[f["price"] <= max_price]
    return make_recs(f.sort_values("popularity_score", ascending=False), n_items, max_price)

def calc_score(items, selected_tags):
    if not selected_tags:
        tag_score = 100.0
    else:
        total = len(items)
        match = sum(1 for it in items if not set(it["tags_list"]).isdisjoint(selected_tags))
        tag_score = (match/total)*100.0 if total else 0.0
    avg_pop = sum(it["popularity_score"] for it in items)/len(items) if items else 0.0
    return round(tag_score*0.7 + (avg_pop*10)*0.3, 1)

# =========================
# 로그인/가입
# =========================
st.header("🥐 베이커리 추천·주문")
if st.session_state.user is None:
    st.subheader("로그인")
    phone_last4 = st.text_input("휴대폰번호 뒷 4자리", max_chars=4)
    pw6 = st.text_input("비밀번호(6자리)", max_chars=6, type="password")
    name_opt = st.text_input("이름(처음이면 입력)")
    c1, c2 = st.columns(2)
    if c1.button("로그인"):
        m = users[(users["phone_last4"] == phone_last4) & (users["pw6"] == pw6)]
        if len(m)==1:
            users.loc[m.index[0], "last_login"] = now_ts(); save_csv(users, USERS_CSV)
            st.session_state.user = m.iloc[0].to_dict()
            st.success("로그인 완료")
        else:
            st.error("일치하는 계정 없음. 최초가입을 눌러 주세요.")
    if c2.button("최초가입"):
        if not phone_last4 or not pw6:
            st.error("뒷자리/비번 입력해 주세요.")
        else:
            dupe = users[(users["phone_last4"] == phone_last4) & (users["pw6"] == pw6)]
            if len(dupe)>0:
                st.warning("이미 가입되어 있습니다. 로그인해 주세요.")
            else:
                uid = f"U{len(users)+1:04d}"
                users = pd.concat([users, pd.DataFrame([{
                    "user_id": uid, "phone_last4": phone_last4, "pw6": pw6,
                    "name": name_opt or "", "joined_at": now_ts(), "last_login": now_ts()
                }])], ignore_index=True); save_csv(users, USERS_CSV)
                cid = f"C{len(coupons)+1:04d}"
                coupons = pd.concat([coupons, pd.DataFrame([{
                    "coupon_id": cid, "user_id": uid, "amount": WELCOME_COUPON_AMOUNT,
                    "issued_at": now_ts(), "used": 0, "used_at": ""
                }])], ignore_index=True); save_csv(coupons, COUPONS_CSV)
                st.session_state.user = users.iloc[-1].to_dict()
                st.success(f"가입 완료! {WELCOME_COUPON_AMOUNT}원 쿠폰 1장 지급")
    st.stop()

user = st.session_state.user
st.success(f"{user.get('name') or '고객'}님 환영합니다!")

# =========================
# 탭
# =========================
tab_reco, tab_board, tab_cart = st.tabs(["AI 메뉴 추천", "메뉴판", "장바구니"])

with tab_reco:
    st.title("🤖AI 메뉴 추천 시스템")
    st.caption("취향+인기 기반 추천. 음료 카테고리는 정확 일치.")

    c1, c2, c3 = st.columns(3)
    with c1:
        n_people = st.number_input("인원 수", 1, 10, 2)
        unlimited = st.checkbox("예산 무제한", value=True)
        if unlimited:
            max_budget = None
            st.slider("최대 예산(1인)", 5000, 50000, 50000, 1000, disabled=True)
        else:
            max_budget = st.slider("최대 예산(1인)", 5000, 50000, 15000, 1000)
    with c2:
        n_bakery = st.slider("베이커리 개수", 1, 5, 2)
        min_bak, max_bak = st.slider("베이커리 당도", 1, 5, (1,5))
        sel_bak_tags = st.multiselect("베이커리 태그", sorted(uniq_tags(bakery_df)))
    with c3:
        sel_cats = st.multiselect("음료 카테고리", all_drink_categories, default=all_drink_categories)
        min_drk, max_drk = st.slider("음료 당도", 1, 5, (1,5))
        sel_drk_tags = st.multiselect("음료 맛 태그", sorted(uniq_tags(drink_df)))

    st.markdown("---")

    if st.button("AI 추천 메뉴 보기👇", type="primary", use_container_width=True):
        drink_recs  = recommend_strict(drink_df,  min_drk, max_drk, sel_drk_tags, 1,        max_budget, sel_cats)
        bakery_recs = recommend_strict(bakery_df, min_bak, max_bak, sel_bak_tags, n_bakery, max_budget)
        relaxed_used = False
        if not drink_recs:
            drink_recs = recommend_relaxed(drink_df,  min_drk, max_drk, sel_drk_tags, 1,        max_budget, sel_cats); relaxed_used=True
        if not bakery_recs:
            bakery_recs = recommend_relaxed(bakery_df, min_bak, max_bak, sel_bak_tags, n_bakery, max_budget); relaxed_used=True
        if not drink_recs and not bakery_recs:
            st.warning("조건에 맞는 메뉴가 없습니다. 태그/당도를 완화해 주세요."); st.stop()

        results = []
        for d_combo, b_combo in itertools.product(drink_recs or [[]], bakery_recs or [[]]):
            per_price = (d_combo[0]['price'] if d_combo else 0) + sum(x['price'] for x in b_combo)
            if (max_budget is None) or (per_price <= max_budget):
                items = (d_combo or []) + b_combo
                score = calc_score(items, sel_drk_tags + sel_bak_tags)
                results.append({"score":score,"drink":d_combo[0] if d_combo else None,"bakery":b_combo,"per_price":per_price})
            if len(results) >= 200: break
        if not results:
            st.warning("예산에 맞는 메뉴가 없습니다. 조건을 완화해 주세요."); st.stop()

        st.markdown("""
<style>
.card{padding:14px 16px;margin-bottom:12px;border-radius:12px;border:1px solid #eee;background:#fff}
.card h4{margin:0 0 6px 0;font-size:1.05rem}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid #ff5a5f;margin-right:6px;font-size:0.85rem}
.kv{background:#fafafa;border:1px solid #eee;border-radius:8px;padding:8px 10px;margin-top:6px}
.small{color:#666;font-size:0.9rem}
.tag{display:inline-block;background:#fff4f4;color:#c44;border:1px solid #fbb;padding:2px 6px;border-radius:6px;margin:2px;font-size:0.85rem}
</style>
        """, unsafe_allow_html=True)

        results.sort(key=lambda x: x['score'], reverse=True)
        if relaxed_used: st.info("정확 매칭이 부족하여 유사 메뉴를 포함해 추천했습니다.")

        # 🔥 상위 3개 세트만 노출
        for rank, r in enumerate(results[:3], start=1):
            base_drink = r['drink']
            bakery_list = r['bakery']
            per_price   = r['per_price']
            total_price = per_price * n_people

            # 인원수만큼 음료 후보(표시용)
            drink_list = []
            if base_drink: drink_list.append(base_drink)

            def tags_html(tags):
                t = [f"<span class='tag'>#{x}</span>" for x in tags if x != '인기']
                return "".join(t) if t else "<span class='small'>태그 없음</span>"

            drink_html  = "<br>".join([f"- {d['name']} ({d['price']:,}원)<br>{tags_html(d['tags_list'])}" for d in drink_list]) if drink_list else "<span class='small'>—</span>"
            bakery_html = "<br>".join([f"- {b['name']} ({b['price']:,}원)<br>{tags_html(b['tags_list'])}" for b in bakery_list])

            st.markdown(f"""
<div class="card">
  <h4>추천 세트 {rank} · 점수 {r['score']}점</h4>
  <span class="badge">1인 {per_price:,}원</span>
  <span class="badge">{n_people}명 총 {total_price:,}원</span>
  <div class="kv"><b>음료(대표)</b><br>{drink_html}</div>
  <div class="kv"><b>베이커리</b><br>{bakery_html}</div>
  <div class="small">※ 항목별로 개별 담기가 가능합니다.</div>
</div>
            """, unsafe_allow_html=True)

            # ✅ 개별 담기 버튼들
            # 음료(대표 1개만 노출되므로 그 한 항목만 개별담기)
            if base_drink:
                if st.button(f"음료 담기: {base_drink['name']} (세트{rank})", key=f"add_d_{rank}"):
                    st.session_state.cart.append({
                        "item_id": base_drink["item_id"], "name": base_drink["name"], "type": base_drink["type"],
                        "category": base_drink.get("category",""), "qty": 1, "unit_price": int(base_drink["price"])
                    })
                    st.success("장바구니에 담았습니다.")

            # 베이커리 각 항목별 담기
            for j, b in enumerate(bakery_list):
                if st.button(f"베이커리 담기: {b['name']} (세트{rank}-{j+1})", key=f"add_b_{rank}_{j}"):
                    st.session_state.cart.append({
                        "item_id": b["item_id"], "name": b["name"], "type": b["type"],
                        "category": b.get("category",""), "qty": 1, "unit_price": int(b["price"])
                    })
                    st.success("장바구니에 담았습니다.")

with tab_board:
    st.title("메뉴판")
    img1, img2 = load_image("menu_board_1.png"), load_image("menu_board_2.png")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("베이커리 메뉴")
        if img1: st.image(img1, caption="Bakery 메뉴판", use_column_width=True)
        else: st.dataframe(bakery_df)
    with c2:
        st.subheader("음료 메뉴")
        if img2: st.image(img2, caption="Drink 메뉴판", use_column_width=True)
        else: st.dataframe(drink_df)

with tab_cart:
    st.title("장바구니")
    if len(st.session_state.cart)==0:
        st.write("- 비어 있습니다.")
    else:
        df_cart = pd.DataFrame(st.session_state.cart)

        for i in range(len(df_cart)):
            c1, c2, c3, c4 = st.columns([4,2,2,2])
            with c1: st.write(f"{df_cart.iloc[i]['name']} ({df_cart.iloc[i]['type']})")
            with c2:
                new_qty = st.number_input("수량", min_value=1, value=int(df_cart.iloc[i]['qty']), key=f"qty_{i}")
                df_cart.at[i, "qty"] = new_qty
            with c3: st.write(money(df_cart.iloc[i]['unit_price']))
            with c4:
                if st.button("삭제", key=f"rm_{i}"):
                    st.session_state.cart.pop(i); st.rerun()

        subtotal = int((df_cart["qty"] * df_cart["unit_price"]).sum())
        my_coupons = coupons[(coupons["user_id"]==user["user_id"]) & (coupons["used"]==0)]
        use_coupon = False; coupon_id=None
        if len(my_coupons)>0:
            use_coupon = st.checkbox(f"쿠폰 사용 (-{WELCOME_COUPON_AMOUNT}원)")
            if use_coupon: coupon_id = my_coupons.iloc[0]["coupon_id"]

        note = st.text_input("요청 메모", "")
        total = max(0, subtotal - (WELCOME_COUPON_AMOUNT if use_coupon else 0))
        st.write(f"**총액: {money(total)}**")

        ca, cb = st.columns(2)
        if ca.button("장바구니 비우기"):
            st.session_state.cart = []; st.rerun()

        if cb.button("주문 완료(매장 이메일 알림)"):
            new_id = f"O{len(orders)+1:06d}"
            new_order = {
                "order_id": new_id, "user_id": user["user_id"], "total_price": total,
                "coupon_used": 1 if use_coupon else 0, "note": note, "status": "접수",
                "created_at": now_ts(), "notified_email": 0, "notified_at": "", "notify_error": ""
            }
            orders = pd.concat([orders, pd.DataFrame([new_order])], ignore_index=True)

            rows = []
            for _, r in df_cart.iterrows():
                rows.append({
                    "order_id": new_id, "item_id": r["item_id"], "name": r["name"],
                    "type": r["type"], "category": r.get("category",""),
                    "qty": int(r["qty"]), "unit_price": int(r["unit_price"])
                })
            order_items = pd.concat([order_items, pd.DataFrame(rows)], ignore_index=True)

            if use_coupon and coupon_id:
                idx = coupons[coupons["coupon_id"]==coupon_id].index
                if len(idx)==1:
                    coupons.loc[idx[0], "used"] = 1
                    coupons.loc[idx[0], "used_at"] = now_ts()

            save_csv(orders, ORDERS_CSV); save_csv(order_items, ORDER_ITEMS_CSV); save_csv(coupons, COUPONS_CSV)

            ok, err = send_order_email(
                to_emails=[OWNER_EMAIL_PRIMARY] if OWNER_EMAIL_PRIMARY else [],
                shop_name=SHOP_NAME, order_id=new_id,
                items=df_cart.to_dict("records"), total=total, note=note, coupon_used=bool(use_coupon)
            )
            if ok:
                idx2 = orders[orders["order_id"]==new_id].index
                if len(idx2)==1:
                    orders.loc[idx2[0], "notified_email"] = 1
                    orders.loc[idx2[0], "notified_at"] = now_ts()
                    save_csv(orders, ORDERS_CSV)
                st.success(f"주문 접수되었습니다! #{new_id} / 매장 이메일 발송 완료")
                st.session_state.cart = []
            else:
                idx2 = orders[orders["order_id"]==new_id].index
                if len(idx2)==1:
                    orders.loc[idx2[0], "notify_error"] = err; save_csv(orders, ORDERS_CSV)
                st.warning(f"주문 저장 완료, 이메일 실패: {err}")

