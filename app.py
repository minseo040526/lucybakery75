import streamlit as st
import pandas as pd
import itertools, os, re, smtplib, ssl, uuid
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime
from PIL import Image

# ---------------- 기본 설정 ----------------
st.set_page_config(page_title="AI 베이커리 추천·주문", layout="wide")

# Secret variables for configuration (replace with actual values in st.secrets)
SHOP_NAME = st.secrets.get("SHOP_NAME", "Lucy Bakery")
OWNER_EMAIL_PRIMARY = st.secrets.get("OWNER_EMAIL_PRIMARY", "owner@example.com") # 사장님 이메일 (주문 알림용)
WELCOME_COUPON_AMOUNT = int(st.secrets.get("WELCOME_COUPON_AMOUNT", "2000"))
SMTP_HOST = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(st.secrets.get("SMTP_PORT", "465"))
SMTP_USER = st.secrets.get("SMTP_USER", "noreply@example.com") # 발신 이메일
SMTP_PASS = st.secrets.get("SMTP_PASS", "your_smtp_password") # 발신 이메일 비밀번호
POPULAR_BONUS_SCORE = 1 # 인기 메뉴에 부여할 가산점

# ---------------- 디자인 테마 적용 ----------------
def set_custom_style():
    """베이지/브라운 톤의 고급스러운 디자인을 Streamlit에 적용합니다."""
    # Warm Beige/Brown Palette
    BG_COLOR = "#FAF8F1"     # Light Creamy Beige (Main Background)
    CARD_COLOR = "#F8F6F4"   # Slightly darker cream (Input/Container Background)
    TEXT_COLOR = "#3E2723"   # Dark Espresso Brown
    PRIMARY_COLOR = "#A1887F" # Muted Brown / Taupe (Secondary Buttons, Borders)
    ACCENT_COLOR = "#795548"  # Medium Brown (Primary Buttons, Highlights)
    
    css = f"""
    <style>
    /* 1. Main Background and Text */
    .stApp {{
        background-color: {BG_COLOR};
        color: {TEXT_COLOR};
        font-family: 'Malgun Gothic', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }}
    
    /* 2. Headers and Titles */
    h1, h2, h3, h4, h5, h6, .stMarkdown, .stText, .stLabel {{
        color: {TEXT_COLOR} !important;
        font-family: inherit;
    }}
    
    /* 3. Main Streamlit Containers & Cards */
    .block-container {{
        background-color: {BG_COLOR};
        padding-top: 2rem;
    }}
    
    /* 4. Input Fields, Select Boxes, Radio, Slider */
    div[data-testid="stTextInput"] > div:first-child, 
    div[data-testid="stNumberInput"] > div:first-child, 
    div[data-testid="stSelectbox"] > div:first-child, 
    div[data-testid="stMultiSelect"] > div:first-child,
    div[data-testid="stRadio"], div[data-testid="stSlider"] {{
        background-color: {CARD_COLOR}; 
        border-radius: 12px;
        padding: 10px;
        border: 1px solid {PRIMARY_COLOR}30; /* Light border */
        box-shadow: 1px 1px 3px rgba(0, 0, 0, 0.05);
    }}
    div[data-testid="stRadio"] label {{ padding: 5px 0; }} /* Radio vertical padding */

    /* 5. Buttons - Premium Look */
    .stButton > button {{
        background-color: {PRIMARY_COLOR};
        color: white;
        border-radius: 12px;
        padding: 8px 16px;
        font-weight: bold;
        transition: all 0.2s ease-in-out;
        border: none;
        box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.15);
    }}
    .stButton > button:hover {{
        background-color: {ACCENT_COLOR};
        box-shadow: 3px 3px 8px rgba(0, 0, 0, 0.25);
        transform: translateY(-1px);
    }}

    /* Primary Buttons (AI 추천, 로그인/가입, 주문 완료) - Darker Brown */
    .stButton button[data-testid*="primary"] {{
        background-color: {ACCENT_COLOR};
    }}
    .stButton button[data-testid*="primary"]:hover {{
        background-color: #BCAAA4; /* Lighter brown for hover */
    }}

    /* 6. Info/Success/Warning Boxes for better integration */
    div[data-testid="stAlert"] {{
        border-left: 5px solid {ACCENT_COLOR};
        background-color: {CARD_COLOR};
        color: {TEXT_COLOR};
        border-radius: 12px;
        box-shadow: 1px 1px 5px rgba(0, 0, 0, 0.1);
    }}
    
    /* 7. Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 15px; /* Spacing between tabs */
        border-bottom: 2px solid {PRIMARY_COLOR}50;
    }}
    .stTabs [data-baseweb="tab"] {{
        background-color: {BG_COLOR};
        border-radius: 10px 10px 0 0;
        border-bottom: 3px solid transparent !important;
        padding: 10px 20px;
        font-weight: 600;
        color: {PRIMARY_COLOR};
        transition: all 0.2s ease;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {CARD_COLOR}; /* Active tab background */
        color: {TEXT_COLOR} !important;
        border-bottom: 3px solid {ACCENT_COLOR} !important;
        box-shadow: 0 -2px 5px rgba(0, 0, 0, 0.05);
    }}
    
    /* 8. Item Caption (Tags) Color */
    .stMarkdown caption {{
        color: {PRIMARY_COLOR} !important;
    }}
    
    /* 9. Divider */
    hr {{
        border-top: 1px solid {PRIMARY_COLOR}50;
    }}
    
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# ---------------- 유틸 ----------------
def money(x): return f"{int(x):,}원"
def now_ts(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def normalize_str(s): return re.sub(r"\s+"," ",str(s).strip()) if pd.notna(s) else ""

# ---------------- 이메일 ----------------
def send_order_email(to_emails, shop_name, order_id, items, total, note):
    """주문 완료 시 사장님에게 알림 이메일을 전송합니다."""
    if not SMTP_USER or not SMTP_PASS:
        return False, "SMTP 계정 정보가 설정되지 않아 이메일을 보낼 수 없습니다."
        
    msg_lines = [
        f"[{shop_name}] 신규 주문이 접수되었습니다.",
        f"주문번호: {order_id}",
        "---------------------------",
    ]
    for it in items:
        msg_lines.append(f"- {it['name']} x{it['qty']} ({money(it['unit_price'])})")
    msg_lines += [
        "---------------------------",
        f"총액: {money(total)} (결제는 현장에서 진행)",
        f"요청사항: {note or '없음'}",
        f"접수 시간: {now_ts()}"
    ]
    msg = MIMEText("\n".join(msg_lines), _charset="utf-8")
    msg["Subject"] = f"[{shop_name}] 신규 주문 알림 #{order_id}"
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
        st.error(f"이메일 전송 오류: {e}")
        return False, str(e)

# ---------------- 메뉴 로드 ----------------
@st.cache_data
def load_menu_data():
    """CSV 파일을 읽고 데이터프레임을 전처리하고 스코어를 부여합니다."""
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

        # 태그 리스트 생성
        if "tags" in df.columns:
            df["tags_list"] = (
                df["tags"].fillna("").astype(str)
                .str.replace("#","").str.replace(";",",")
                .str.split(r"\s*,\s*", regex=True)
                .apply(lambda xs: [t for t in xs if t])
            )
        else:
            df["tags_list"] = [[] for _ in range(len(df))]
        
        # 스코어 부여 (AI 추천에 사용)
        df["score"] = 1 # 기본 점수
        if not is_drink:
            # 베이커리 메뉴에만 '인기' 태그 가산점 부여
            POPULAR_TAG = "인기"
            df["score"] = df.apply(lambda row: row["score"] + POPULAR_BONUS_SCORE if POPULAR_TAG in row["tags_list"] else row["score"], axis=1)

        df["type"] = "drink" if is_drink else "bakery"
        prefix = "D" if is_drink else "B"
        df["item_id"] = [f"{prefix}{i+1:04d}" for i in range(len(df))]
        return df

    # NOTE: These files are assumed to be accessible in the environment.
    bakery_df = normalize_columns(pd.read_csv("Bakery_menu.csv"), is_drink=False)
    drink_df  = normalize_columns(pd.read_csv("Drink_menu.csv"), is_drink=True)
    drink_categories = sorted(drink_df["category"].dropna().unique())
    bakery_tags = sorted({t for arr in bakery_df["tags_list"] for t in arr if t})
    
    return bakery_df, drink_df, drink_categories, bakery_tags

bakery_df, drink_df, drink_categories, bakery_tags = load_menu_data()

# ---------------- 세션 및 로그인 데이터 ----------------
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user" not in st.session_state: st.session_state.user = {}
if "cart" not in st.session_state: st.session_state.cart = []
if "reco_results" not in st.session_state: st.session_state.reco_results = []
if "is_reco_fallback" not in st.session_state: st.session_state.is_reco_fallback = False
# 임시 사용자 데이터베이스: key는 '폰뒷4자리', value는 {pass:비밀번호, coupon:쿠폰액}
if "users_db" not in st.session_state: st.session_state.users_db = {} 

# ---------------- 로그인 페이지 ----------------
def show_login_page():
    set_custom_style()
    st.title(f"🥐 {SHOP_NAME}")
    st.header("휴대폰 번호 뒷자리로 로그인/회원가입")

    with st.form("login_form"):
        phone_suffix = st.text_input("휴대폰 번호 뒷 4자리", max_chars=4, placeholder="0000")
        password = st.text_input("비밀번호 (6자리)", type="password", max_chars=6, placeholder="******")
        
        submitted = st.form_submit_button("로그인 / 가입", type="primary")

        if submitted:
            phone_suffix = phone_suffix.strip()
            password = password.strip()
            
            if not (re.fullmatch(r'\d{4}', phone_suffix) and re.fullmatch(r'\d{6}', password)):
                st.error("휴대폰 번호 뒷 4자리와 비밀번호 6자리를 정확히 입력해주세요.")
                return

            if phone_suffix in st.session_state.users_db:
                # 기존 사용자 로그인
                if st.session_state.users_db[phone_suffix]["pass"] == password:
                    st.session_state.logged_in = True
                    st.session_state.user = {
                        "name": f"고객({phone_suffix})",
                        "phone": phone_suffix,
                        "coupon": st.session_state.users_db[phone_suffix]["coupon"]
                    }
                    st.success(f"{st.session_state.user['name']}님, 로그인되었습니다.")
                    st.rerun()
                else:
                    st.error("비밀번호가 일치하지 않습니다.")
            else:
                # 신규 가입
                st.session_state.users_db[phone_suffix] = {
                    "pass": password,
                    "coupon": WELCOME_COUPON_AMOUNT
                }
                st.session_state.logged_in = True
                st.session_state.user = {
                    "name": f"고객({phone_suffix})",
                    "phone": phone_suffix,
                    "coupon": WELCOME_COUPON_AMOUNT
                }
                st.success(f"회원가입이 완료되었으며, {money(WELCOME_COUPON_AMOUNT)} 쿠폰이 지급되었습니다!")
                st.balloons()
                st.rerun()

# ---------------- 장바구니 추가 헬퍼 ----------------
def add_item_to_cart(item, qty=1):
    """장바구니에 아이템을 추가하고 토스트 메시지를 표시합니다."""
    st.session_state.cart.append({
        "item_id": item["item_id"], "name": item["name"], 
        "type": item["type"], "category": item.get("category", ""), 
        "qty": qty, "unit_price": int(item["price"])
    })
    st.toast(f"**{item['name']}** {qty}개를 장바구니에 담았습니다. 🛒")

# ---------------- 조합 및 스코어링 헬퍼 ----------------
def find_combinations(drinks_df, bakery_df, n_people, n_bakery, max_budget):
    """음료와 베이커리를 조합하고 예산 및 스코어를 계산하여 반환합니다."""
    found_results = []
    
    # 성능 최적화를 위해 상위 항목만 사용
    drinks_to_use = drinks_df.head(10).to_dict("records")
    # 베이커리는 인기 메뉴 우선순위를 위해 스코어 기준으로 상위 15개 사용
    bakery_to_use = bakery_df.sort_values(by="score", ascending=False).head(15).to_dict("records")
    
    for d in drinks_to_use:
        # 음료 스코어는 기본 1
        d_score = d.get("score", 1) 
        
        combos = itertools.combinations(bakery_to_use, n_bakery) if n_bakery > 0 else [[]]

        for b_combo in combos:
            total_price = d["price"] * n_people + sum(b["price"] for b in b_combo)
            
            if total_price <= max_budget:
                # 총 스코어 계산 (음료 스코어 + 베이커리 스코어 합산)
                total_score = d_score + sum(b["score"] for b in b_combo)
                
                found_results.append({
                    "drink": d, 
                    "bakery": b_combo, 
                    "total": total_price, 
                    "score": total_score
                })
    return found_results

# ---------------- 메인 앱 페이지 ----------------
def show_main_app():
    set_custom_style()
    st.title("🥐 AI 베이커리 추천·주문")
    
    c_user, c_coupon, c_logout = st.columns([4, 4, 2])
    with c_user:
        st.success(f"**{st.session_state.user.get('name', '고객')}**님, 환영합니다!")
    with c_coupon:
        st.info(f"사용 가능 쿠폰: **{money(st.session_state.user.get('coupon', 0))}**")
    with c_logout:
        if st.button("로그아웃", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user = {}
            st.session_state.cart = []
            st.session_state.reco_results = []
            st.session_state.is_reco_fallback = False
            st.success("로그아웃되었습니다.")
            st.rerun()

    st.markdown("---")

    # ---------------- 탭 ----------------
    tab_reco, tab_menu, tab_cart = st.tabs(["🤖 AI 메뉴 추천", "📋 메뉴판", "🛍️ 장바구니"])

    # ===== 추천 로직 =====
    with tab_reco:
        st.header("AI 맞춤형 메뉴 추천")

        st.subheader("1. 추천 조건 설정")
        c1, c2, c3 = st.columns(3)
        with c1:
            # 인원수/음료 수량
            n_people = st.number_input("인원 수 (음료 잔 수)", 1, 20, 2, key="n_people")
            
            # 예산 설정 통합 및 무제한 옵션 추가
            budget_choice = st.radio("1인 예산 기준", ["무제한", "금액 직접 입력"], index=1, key="budget_choice")
            
            # 금액 직접 입력 시 값
            input_budget_val = 0
            if budget_choice == "금액 직접 입력":
                input_budget_val = st.number_input("1인 예산 금액 (원)", min_value=1, value=7500, step=500, key="input_budget_val")
            
        with c2:
            # 베이커리 개수
            n_bakery = st.slider("베이커리 개수", 0, 5, 2, key="n_bakery")
            # 음료 카테고리 필터
            sel_cats = st.multiselect("원하는 음료 카테고리", drink_categories, default=drink_categories, key="sel_cats")

        with c3:
            # 베이커리 태그 필터 (취향)
            sel_tags = st.multiselect("원하는 베이커리 태그 (최대 3개)", bakery_tags, max_selections=3, key="sel_tags")

        st.markdown("---")

        # 'AI 추천 보기' 버튼을 눌렀을 때만 추천 결과를 계산하여 세션에 저장
        if st.button("AI 추천 보기", type="primary", use_container_width=True):
            with st.spinner("최적의 메뉴를 조합하고 있습니다..."):
                
                # --- 공통 필터링: 음료 및 예산 설정 ---
                drinks = drink_df[drink_df["category"].isin(st.session_state.sel_cats)] if st.session_state.sel_cats else drink_df
                bakery_base = bakery_df.copy()

                n_people_val = st.session_state.n_people
                
                # 최대 예산 계산
                if st.session_state.budget_choice == "금액 직접 입력":
                    budget_per_person = st.session_state.get('input_budget_val', 0)
                    max_budget = budget_per_person * n_people_val
                    if max_budget == 0:
                        st.error("1인 예산이 0원으로 설정되었습니다. 예산을 높이거나 '무제한'을 선택해주세요.")
                        st.session_state.reco_results = []
                        st.session_state.is_reco_fallback = False
                        return
                else:
                    max_budget = float('inf') # 무제한

                # --- Phase 1: 엄격한 조건 (태그 필터링 적용) ---
                bakery_strict = bakery_base.copy()
                if st.session_state.sel_tags:
                    tagset = set(st.session_state.sel_tags)
                    # Strict filter: must contain at least one of the selected tags
                    bakery_strict = bakery_strict[bakery_strict["tags_list"].apply(lambda xs: not tagset.isdisjoint(set(xs)))]
                
                results = find_combinations(drinks, bakery_strict, n_people_val, st.session_state.n_bakery, max_budget)
                is_fallback = False

                # --- Phase 2: 폴백 (유사 메뉴 추천) ---
                if not results and st.session_state.sel_tags:
                    is_fallback = True
                    # 태그 필터링을 풀고 전체 베이커리 목록으로 다시 시도
                    results = find_combinations(drinks, bakery_base, n_people_val, st.session_state.n_bakery, max_budget)

                if not results:
                    st.warning("조건에 맞는 메뉴 조합을 찾지 못했습니다. 조건을 완화하거나 변경해보세요.")
                    st.session_state.reco_results = []
                    st.session_state.is_reco_fallback = False
                else:
                    # 최종 정렬: 스코어 내림차순, 총액 오름차순 (인기 메뉴 우선)
                    sorted_results = sorted(results, key=lambda x: (-x["score"], x["total"]))[:3]
                    st.session_state.reco_results = sorted_results
                    st.session_state.is_reco_fallback = is_fallback
                    st.toast("추천 메뉴 조합이 성공적으로 생성되었습니다!")
                    
        # 세션에 저장된 추천 결과를 출력합니다.
        if st.session_state.reco_results:
            st.subheader("2. AI 추천 세트")
            
            if st.session_state.is_reco_fallback:
                 st.info("⚠️ **선택하신 태그를 모두 만족하는 조합이 없어** 인기 메뉴 및 유사 메뉴를 포함하여 추천되었습니다.")
            
            # n_people은 현재 n_people 위젯의 값으로 사용
            current_n_people = st.session_state.n_people
            
            for i, r in enumerate(st.session_state.reco_results, start=1):
                st.markdown(f"**--- 추천 세트 {i} (스코어: {r['score']}, 금액: {money(r['total'])}) ---**")
                
                col1, col2 = st.columns(2)
                
                # --- 음료 ---
                with col1:
                    st.markdown("##### ☕ 음료")
                    st.write(f"**{r['drink']['name']}** ({money(r['drink']['price'])} x {current_n_people}잔)")
                    st.caption(f"카테고리: {r['drink']['category']}")
                    
                    # 장바구니에 담기
                    if st.button(f"🛒 음료 {current_n_people}잔 담기", key=f"d_reco_{i}", use_container_width=True, type="secondary"):
                        add_item_to_cart(r["drink"], qty=current_n_people)

                # --- 베이커리 ---
                with col2:
                    st.markdown(f"##### 🥐 베이커리 ({len(r['bakery'])}개)")
                    
                    if r["bakery"]:
                        for j, b in enumerate(r["bakery"]):
                            pop_icon = "⭐ " if "인기" in b["tags_list"] else ""
                            st.write(f"- {pop_icon}{b['name']} ({money(b['price'])})")
                            st.caption(f"태그: {', '.join(b['tags_list'])}")
                            
                            # 장바구니에 담기
                            if st.button(f"🛒 {b['name']} 담기", key=f"b_reco_{i}_{j}", use_container_width=True, type="secondary"):
                                add_item_to_cart(b, qty=1)
                    else:
                         st.write("- 베이커리 선택 안 함")
                
                st.markdown(f"#### 💰 최종 합계: **{money(r['total'])}**")
                st.markdown("---")


    # ===== 메뉴판 (주문 가능) =====
    with tab_menu:
        st.header("📋 전체 메뉴판")
        
        st.subheader("🍞 베이커리 메뉴")
        st.caption(f"총 {len(bakery_df)}개 품목")
        
        # 베이커리 메뉴 반복 출력 및 '담기' 버튼 추가
        for i, item in bakery_df.iterrows():
            pop_icon = "⭐ " if "인기" in item["tags_list"] else ""
            
            c1, c2, c3, c4 = st.columns([3, 2, 4, 2])
            with c1: st.write(f"**{pop_icon}{item['name']}**")
            with c2: st.write(money(item['price']))
            with c3: st.caption(f"태그: {', '.join(item['tags_list'])}")
            with c4:
                # 고유 키: menu_b_아이템ID
                if c4.button("🛒 담기", key=f"menu_b_{item['item_id']}", use_container_width=True, type="secondary"):
                    add_item_to_cart(item, qty=1)

        st.markdown("---")
        
        st.subheader("☕ 음료 메뉴")
        st.caption(f"총 {len(drink_df)}개 품목")
        
        # 음료 메뉴 반복 출력 및 '담기' 버튼 추가
        for i, item in drink_df.iterrows():
            c1, c2, c3, c4 = st.columns([3, 2, 4, 2])
            with c1: st.write(f"**{item['name']}**")
            with c2: st.write(money(item['price']))
            with c3: st.caption(f"카테고리: {item['category']}")
            with c4:
                # 고유 키: menu_d_아이템ID
                if c4.button("🛒 담기", key=f"menu_d_{item['item_id']}", use_container_width=True, type="secondary"):
                    add_item_to_cart(item, qty=1)

    # ===== 장바구니 =====
    with tab_cart:
        st.header("🛍️ 장바구니")
        
        if not st.session_state.cart:
            st.info("장바구니가 비어 있습니다. AI 추천 탭이나 메뉴판 탭에서 상품을 담아주세요.")
        else:
            # 장바구니 리스트를 데이터프레임으로 변환 (수량 변경 및 삭제 시 세션 상태를 직접 수정)
            df_cart = pd.DataFrame(st.session_state.cart)
            df_cart["total_price"] = df_cart["qty"] * df_cart["unit_price"]

            st.markdown("##### 현재 장바구니 목록")
            
            # 장바구니 디스플레이 및 수량 변경/삭제 로직
            for i in range(len(df_cart)):
                item = df_cart.iloc[i]
                
                # 수량 변경 시 key가 변경되어야 하므로 unique key를 사용합니다.
                qty_key = f"qty_{item['item_id']}_{i}"
                remove_key = f"rm_{item['item_id']}_{i}"
                
                c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 2, 1])
                
                with c1: st.write(f"**{item['name']}**")
                with c2: st.write(money(item['unit_price']))
                with c3:
                    # 항목 ID와 루프 인덱스를 결합하여 고유한 키 생성
                    qty = st.number_input("수량", 1, 99, int(item["qty"]), key=qty_key, label_visibility="collapsed")
                    # 수량 변경 시 세션 상태에 반영
                    if qty != item["qty"]:
                        st.session_state.cart[i]["qty"] = int(qty)
                        st.rerun() # 수량이 변경되면 바로 화면을 업데이트

                with c4: st.write(f"**{money(item['total_price'])}**")
                with c5:
                    if st.button("X", key=remove_key, type="secondary"):
                        st.session_state.cart.pop(i)
                        st.toast(f"{item['name']}을 삭제했습니다.")
                        st.rerun()

            st.markdown("---")
            total = int(df_cart["total_price"].sum())
            
            # 쿠폰 적용 (사용 시 사용자 DB에서 쿠폰 차감 필요)
            coupon_amount = st.session_state.user.get('coupon', 0)
            use_coupon = st.checkbox(f"쿠폰 사용 ({money(coupon_amount)} 보유)", value=coupon_amount > 0)
            
            discount = coupon_amount if use_coupon else 0
            final_total = max(0, total - discount)
            
            st.subheader(f"총 주문 금액: {money(total)}")
            st.write(f"적용 할인 (쿠폰): - **{money(discount)}**")
            st.markdown(f"## 최종 결제 금액: **{money(final_total)}**")

            note = st.text_area("요청사항", height=50)

            if st.button("주문 완료 및 매장 알림", type="primary", use_container_width=True):
                # NOTE: 이메일 전송 기능은 SMTP 설정이 필요합니다.
                if OWNER_EMAIL_PRIMARY == "owner@example.com" or not SMTP_PASS:
                    st.error("⚠️ 사장님 이메일 또는 SMTP 설정이 올바르지 않아 주문 알림을 보낼 수 없습니다. 설정을 확인해 주세요.")
                    # 시뮬레이션
                    st.warning("이메일 전송 없이 주문이 접수된 것으로 처리합니다. (결제는 카운터에서)")
                    st.session_state.cart = []
                    if use_coupon:
                        st.session_state.user['coupon'] = 0
                        st.session_state.users_db[st.session_state.user['phone']]['coupon'] = 0
                    st.success(f"주문이 성공적으로 접수되었습니다! 최종 결제 금액: {money(final_total)} (카운터 결제)")
                    st.rerun()

                else:
                    oid = f"O{datetime.now().strftime('%m%d%H%M%S')}"
                    ok, err = send_order_email(
                        [OWNER_EMAIL_PRIMARY], SHOP_NAME, oid, 
                        df_cart.to_dict("records"), final_total, note
                    )
                    
                    if ok:
                        st.success(f"주문번호 **#{oid}** 접수 완료. 매장으로 알림 이메일이 발송되었습니다. 최종 금액: {money(final_total)} (카운터 결제)")
                        # 주문 후 장바구니 비우기
                        st.session_state.cart = []
                        if use_coupon:
                            st.session_state.user['coupon'] = 0
                            st.session_state.users_db[st.session_state.user['phone']]['coupon'] = 0
                        st.rerun()
                    else:
                        st.error(f"주문 알림 이메일 전송에 실패했습니다: {err}")


# ---------------- 메인 실행 ----------------
if __name__ == "__main__":
    if st.session_state.logged_in:
        show_main_app()
    else:
        show_login_pag
