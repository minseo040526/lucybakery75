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
# 요청에 따라 1000원으로 수정
WELCOME_COUPON_AMOUNT = int(st.secrets.get("WELCOME_COUPON_AMOUNT", "1000")) 
SMTP_HOST = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(st.secrets.get("SMTP_PORT", "465"))
SMTP_USER = st.secrets.get("SMTP_USER", "noreply@example.com") # 발신 이메일
SMTP_PASS = st.secrets.get("SMTP_PASS", "your_smtp_password") # 발신 이메일 비밀번호
POPULAR_BONUS_SCORE = 1 # 인기 메뉴에 부여할 가산점
TAG_BONUS_SCORE = 5 # 선택 태그 일치 메뉴에 부여할 가산점

# 스탬프/리워드 시스템 설정
AMERICANO_PRICE = 4000 # 아메리카노 기준 가격
STAMP_REWARD_AMOUNT = AMERICANO_PRICE # 스탬프 10개 달성 시 지급할 쿠폰 금액
STAMP_GOAL = 10 # 아메리카노 리워드 목표 스탬프 수

# ---------------- 디자인 테마 적용 ----------------
def set_custom_style():
    """베이지/브라운 톤의 고급스러운 디자인을 Streamlit에 적용합니다."""
    # Warm Beige/Brown Palette
    BG_COLOR = "#FAF8F1"      # Light Creamy Beige (Main Background)
    CARD_COLOR = "#F8F6F4"    # Slightly darker cream (Input/Container Background)
    TEXT_COLOR = "#3E2723"    # Dark Espresso Brown
    PRIMARY_COLOR = "#A1887F" # Muted Brown / Taupe (Secondary Buttons, Borders)
    ACCENT_COLOR = "#795548"  # Medium Brown (Primary Buttons, Highlights)

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
    if not SMTP_USER or not SMTP_PASS or OWNER_EMAIL_PRIMARY == "owner@example.com":
        # 이메일 전송 기능이 비활성화되었더라도 주문 처리는 계속 진행해야 함
        return False, "SMTP 계정 정보가 설정되지 않아 이메일을 보낼 수 없습니다. (개발 환경)"

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
        # st.error(f"이메일 전송 오류: {e}") # 사용자에게 에러 메시지 노출 방지
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
    # 파일이 없으면 더미 데이터 사용 (Streamlit Cloud에서 실행 시 파일 경로 문제 대비)
    try:
        bakery_df = normalize_columns(pd.read_csv("Bakery_menu.csv"), is_drink=False)
    except FileNotFoundError:
        st.warning("Bakery_menu.csv 파일을 찾을 수 없습니다. 더미 데이터를 사용합니다.")
        dummy_bakery = {
            "name": ["크루아상", "소금빵", "에그타르트", "모카번", "인절미빵"],
            "price": [3500, 3000, 4500, 4000, 5000],
            "tags": ["바삭,인기", "짭짤", "달콤", "커피,달콤", "고소"]
        }
        bakery_df = normalize_columns(pd.DataFrame(dummy_bakery), is_drink=False)
    
    try:
        drink_df  = normalize_columns(pd.read_csv("Drink_menu.csv"), is_drink=True)
    except FileNotFoundError:
        st.warning("Drink_menu.csv 파일을 찾을 수 없습니다. 더미 데이터를 사용합니다.")
        dummy_drink = {
            "name": ["아메리카노", "카페라떼", "바닐라라떼", "딸기 에이드", "밀크티"],
            "price": [4000, 4500, 5000, 6000, 5500],
            "category": ["커피", "커피", "커피", "에이드", "티"]
        }
        drink_df = normalize_columns(pd.DataFrame(dummy_drink), is_drink=True)


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
# 임시 사용자 데이터베이스: key는 '폰뒷4자리', value는 {pass:비밀번호, coupon:쿠폰액, stamps:스탬프 수, orders:주문내역}
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
                # 기존 사용자 로그인 및 데이터 로드 (스탬프/쿠폰 유지)
                user_data = st.session_state.users_db[phone_suffix]
                
                if user_data["pass"] == password:
                    # 데이터 누락 방지를 위해 setdefault 사용
                    user_data.setdefault("stamps", 0)
                    user_data.setdefault("coupon", 0) # 쿠폰 필드 추가/초기화 보장
                    user_data.setdefault("orders", [])

                    st.session_state.logged_in = True
                    st.session_state.user = {
                        "name": f"고객({phone_suffix})",
                        "phone": phone_suffix,
                        "coupon": user_data["coupon"], # 기존 쿠폰액 로드
                        "stamps": user_data["stamps"], # 기존 스탬프 수 로드
                        "orders": user_data["orders"]  # 기존 주문 내역 로드
                    }
                    st.success(f"{st.session_state.user['name']}님, 로그인되었습니다.")
                    st.rerun()
                else:
                    st.error("비밀번호가 일치하지 않습니다.")
            else:
                # 신규 가입
                st.session_state.users_db[phone_suffix] = {
                    "pass": password,
                    "coupon": WELCOME_COUPON_AMOUNT,
                    "stamps": 0, # 스탬프 초기화
                    "orders": [] # 주문 내역 초기화
                }
                st.session_state.logged_in = True
                st.session_state.user = {
                    "name": f"고객({phone_suffix})",
                    "phone": phone_suffix,
                    "coupon": WELCOME_COUPON_AMOUNT,
                    "stamps": 0, # 스탬프 초기화
                    "orders": [] # 주문 내역 초기화
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
    # 음료는 필터링된 목록을 그대로 사용, 베이커리는 (이미 score가 반영된) 스코어 기준으로 상위 15개 사용
    drinks_to_use = drinks_df.to_dict("records")
    bakery_to_use = bakery_df.sort_values(by="score", ascending=False).head(15).to_dict("records")

    # 베이커리 개수가 0개면 조합을 시도할 필요 없이 음료만 계산
    combos = itertools.combinations(bakery_to_use, n_bakery) if n_bakery > 0 else [[]]

    for d in drinks_to_use:
        # 음료 스코어는 기본 1 (이 부분은 변경 없음)
        d_score = d.get("score", 1) 

        for b_combo in combos:
            total_price = d["price"] * n_people + sum(b["price"] for b in b_combo)

            if total_price <= max_budget:
                # 총 스코어 계산 (음료 스코어 + (인기+취향 가산점이 이미 반영된) 베이커리 스코어 합산)
                total_score = d_score + sum(b["score"] for b in b_combo)

                found_results.append({
                    "drink": d, 
                    "bakery": b_combo, 
                    "total": total_price, 
                    "score": total_score
                })
    return found_results

# ---------------- 주문 완료 처리 ----------------
def process_order_completion(phone_suffix, order_id, df_cart, total, final_total, coupon_used_amount):
    """주문 완료 후 스탬프 적립, 주문 내역 저장 및 쿠폰 발행을 처리합니다."""
    
    # 1. 주문 내역 저장
    order_history_item = {
        "id": order_id,
        "date": now_ts(),
        "items": df_cart[["name", "qty", "unit_price"]].to_dict("records"),
        "total": int(total),
        "final_total": int(final_total),
        "coupon_used": int(coupon_used_amount),
        "stamps_earned": 1 
    }
    # users_db와 session_state.user에 모두 저장
    st.session_state.users_db[phone_suffix]['orders'].insert(0, order_history_item) # 최신순으로
    st.session_state.user['orders'] = st.session_state.users_db[phone_suffix]['orders']

    # 2. 쿠폰 사용 처리 (차감)
    if coupon_used_amount > 0:
        st.session_state.user['coupon'] -= coupon_used_amount
        st.session_state.users_db[phone_suffix]['coupon'] -= coupon_used_amount
        st.toast(f"{money(coupon_used_amount)} 쿠폰이 사용되었습니다.", icon="💳")

    # 3. 스탬프 적립
    st.session_state.user['stamps'] += 1
    st.session_state.users_db[phone_suffix]['stamps'] += 1
    
    st.toast(f"주문이 완료되어 스탬프 1개가 적립되었습니다! ❤️", icon="🎉")

    # 4. 스탬프 목표 달성 확인 및 리워드 지급
    current_stamps = st.session_state.user['stamps']
    
    if current_stamps >= STAMP_GOAL:
        # 리워드 지급
        st.session_state.user['coupon'] += STAMP_REWARD_AMOUNT
        st.session_state.users_db[phone_suffix]['coupon'] += STAMP_REWARD_AMOUNT
        
        # 스탬프 리셋 (남은 스탬프 유지)
        st.session_state.user['stamps'] = current_stamps - STAMP_GOAL
        st.session_state.users_db[phone_suffix]['stamps'] = current_stamps - STAMP_GOAL
        
        st.balloons()
        st.success(f"🎉 **스탬프 {STAMP_GOAL}개 달성!** {money(STAMP_REWARD_AMOUNT)} 상당의 아메리카노 쿠폰이 추가 지급되었습니다.")
    
    # 5. 장바구니 비우고 새로고침
    st.session_state.cart = []
    st.rerun()

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
    tab_reco, tab_menu, tab_cart, tab_history = st.tabs(["🤖 AI 메뉴 추천", "📋 메뉴판", "🛍️ 장바구니", "❤️ 스탬프 & 내역"])

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
                bakery_base = bakery_df.copy() # 기본 스코어 (인기 점수 포함)

                n_people_val = st.session_state.n_people

                # 최대 예산 계산
                if st.session_state.budget_choice == "금액 직접 입력":
                    budget_per_person = st.session_state.get('input_budget_val', 0)
                    max_budget = budget_per_person * n_people_val
                    if max_budget <= 0:
                        st.error("총 예산이 0원 이하입니다. 예산을 높이거나 '무제한'을 선택해주세요.")
                        st.session_state.reco_results = []
                        st.session_state.is_reco_fallback = False
                        return
                else:
                    max_budget = float('inf') # 무제한

                # --- Phase 1: 엄격한 조건 (선택 태그 모두 포함 및 점수 부스팅 적용) ---
                bakery_strict = bakery_base.copy()
                
                if st.session_state.sel_tags and st.session_state.n_bakery > 0:
                    tagset = set(st.session_state.sel_tags)
                    
                    # 1. 엄격한 필터: **선택된 태그를 모두 포함하는** 베이커리만 선택
                    # 주의: 조합 시 (n_bakery) 개를 뽑기 때문에, 태그를 모두 포함하는 메뉴가 여러 개 필요하지 않을 수 있음.
                    # 대신, 선택된 태그 중 하나라도 포함하는 메뉴에는 가산점을 크게 부여
                    
                    # **필터링:** 선택된 태그 중 하나라도 포함하는 메뉴로 필터링 (조합의 수를 너무 줄이지 않기 위함)
                    bakery_strict = bakery_strict[bakery_strict["tags_list"].apply(lambda xs: not tagset.isdisjoint(set(xs)))]
                    
                    # 2. **취향 가산점 부스팅**: 필터링된 메뉴 중 일치 태그 수만큼 점수를 크게 높여서 추천 순위 보장
                    bakery_strict["score"] = bakery_strict.apply(
                        lambda row: row["score"] + (len(set(row["tags_list"]) & tagset) * TAG_BONUS_SCORE), 
                        axis=1
                    )

                # 가산점이 반영된 strict 목록으로 조합 시도
                # n_bakery가 0일 경우, bakery_strict는 모든 베이커리 메뉴를 포함하되 태그 점수 부스팅은 적용 안 됨.
                # (n_bakery=0 일 때 combos = [[]] 이므로 bakery_df를 통째로 사용해도 무방하나, 성능을 위해 상위 15개만 사용)
                bakery_use_for_reco = bakery_strict if st.session_state.n_bakery > 0 and st.session_state.sel_tags else bakery_base
                results = find_combinations(drinks, bakery_use_for_reco, n_people_val, st.session_state.n_bakery, max_budget)
                is_fallback = False

                # --- Phase 2: 폴백 (예산은 맞지만 태그 조건에 안 맞는 경우) ---
                if not results and st.session_state.sel_tags:
                    is_fallback = True
                    # 태그 필터링 없이 (기본 인기 점수만 반영된) 전체 베이커리 목록으로 다시 시도
                    results = find_combinations(drinks, bakery_base, n_people_val, st.session_state.n_bakery, max_budget)

                if not results:
                    st.warning("조건에 맞는 메뉴 조합을 찾지 못했습니다. 인원수, 예산, 베이커리 개수 등의 조건을 완화하거나 변경해보세요.")
                    st.session_state.reco_results = []
                    st.session_state.is_reco_fallback = False
                else:
                    # 최종 정렬: 스코어 내림차순 (취향 가산점이 반영되어 취향 일치 메뉴가 최우선), 총액 오름차순
                    sorted_results = sorted(results, key=lambda x: (-x["score"], x["total"]))[:3]
                    st.session_state.reco_results = sorted_results
                    st.session_state.is_reco_fallback = is_fallback
                    st.toast("추천 메뉴 조합이 성공적으로 생성되었습니다!")

        # 세션에 저장된 추천 결과를 출력합니다.
        if st.session_state.reco_results:
            st.subheader("2. AI 추천 세트")

            if st.session_state.is_reco_fallback:
                st.info("⚠️ **선택하신 태그 조건을 만족하는 조합을 찾지 못해** 가격/인기 메뉴를 기준으로 유사 추천되었습니다. 조건을 완화하면 더 많은 조합을 볼 수 있습니다.")

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
                            # 선택한 태그를 포함하는 경우 하이라이트
                            tag_highlight = "✨ " if len(set(b['tags_list']) & set(st.session_state.sel_tags)) > 0 else ""
                            st.write(f"- {tag_highlight}{pop_icon}{b['name']} ({money(b['price'])})")
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
                        st.toast(f"**{item['name']}**을 삭제했습니다.")
                        st.rerun()

            st.markdown("---")
            total = int(df_cart["total_price"].sum())

            # --- 쿠폰 적용 (개선) ---
            st.subheader("🎫 쿠폰함")
            coupon_amount = st.session_state.user.get('coupon', 0)
            
            if coupon_amount > 0:
                max_use = min(coupon_amount, total)
                coupon_used_amount = st.slider(
                    f"사용할 쿠폰 금액 (보유: {money(coupon_amount)})", 
                    0, max_use, 0, step=1000, 
                    help=f"최대 {money(max_use)}까지 사용할 수 있습니다."
                )
            else:
                st.write("현재 사용 가능한 쿠폰이 없습니다. 😭")
                coupon_used_amount = 0

            discount = coupon_used_amount
            final_total = max(0, total - discount)
            
            st.markdown("---")
            st.subheader(f"총 주문 금액: {money(total)}")
            st.write(f"적용 할인 (쿠폰): - **{money(discount)}**")
            st.markdown(f"## 최종 결제 금액: **{money(final_total)}**")
            st.markdown("---")


            note = st.text_area("요청사항", height=50)

            
            # --- 주문 완료 버튼 ---
            if st.button("주문 완료 및 매장 알림", type="primary", use_container_width=True):
                phone_suffix = st.session_state.user['phone']
                oid = f"O{datetime.now().strftime('%m%d%H%M%S')}"

                # 1. 이메일 전송 (알림)
                ok, err = send_order_email(
                    [OWNER_EMAIL_PRIMARY], SHOP_NAME, oid, 
                    df_cart.to_dict("records"), final_total, note
                )
                
                # 2. 주문 처리 및 스탬프/내역 업데이트
                if ok:
                    st.success(f"주문번호 **#{oid}** 접수 완료. 최종 금액: {money(final_total)} (카운터 결제)")
                    
                    # process_order_completion에서 rerun()을 호출하며, 쿠폰/스탬프 처리 및 장바구니 비우기 완료
                    process_order_completion(phone_suffix, oid, df_cart, total, final_total, coupon_used_amount)
                else:
                    # 이메일 알림 실패 시에도 (개발 환경 에러) 주문 처리는 진행하는 것이 일반적이나,
                    # 매장 알림이 중요하므로 이메일 실패 시 주문 접수를 막고 에러를 표시
                    st.error(f"주문 알림 이메일 전송에 실패했습니다: {err}. 매장 알림이 중요하므로 주문은 접수되지 않았습니다. 관리자에게 문의해주세요.")


    # ===== 스탬프 & 주문 내역 =====
    with tab_history:
        st.header("❤️ 스탬프 & 주문 내역")
        
        # --- 스탬프 현황 ---
        current_stamps = st.session_state.user.get('stamps', 0)
        st.subheader("스탬프 적립 현황")
        
        # Custom display for stamps
        heart_display = "❤️" * current_stamps + "🤍" * max(0, STAMP_GOAL - current_stamps)
        st.markdown(f"""
            ### 현재 스탬프: {heart_display} ({current_stamps}/{STAMP_GOAL}개)
            다음 리워드까지 **{max(0, STAMP_GOAL - current_stamps)}**개 남았습니다.
            
            **🎁 리워드:** 스탬프 {STAMP_GOAL}개 달성 시 **{money(STAMP_REWARD_AMOUNT)}** 상당의 쿠폰 증정!
        """)
        st.markdown("---")

        # --- 쿠폰 잔액 확인 ---
        st.subheader("🎫 현재 쿠폰 잔액")
        st.info(f"사용 가능한 쿠폰 금액: **{money(st.session_state.user.get('coupon', 0))}**")
        st.markdown("---")

        # --- 주문 내역 ---
        st.subheader("최근 주문 내역")
        orders = st.session_state.user.get('orders', [])
        
        if not orders:
            st.info("아직 주문 내역이 없습니다. 지금 첫 주문을 완료하고 스탬프를 적립하세요!")
        else:
            for order in orders:
                # 주문 내역은 최신순으로 표시
                with st.expander(f"**[{order['date'].split(' ')[0]}]** 주문번호 #{order['id']} | 최종 결제: **{money(order['final_total'])}**", expanded=False):
                    st.markdown(f"**주문 시간:** {order['date']}")
                    st.markdown(f"**총 금액:** {money(order['total'])}")
                    st.markdown(f"**쿠폰 사용:** - {money(order['coupon_used'])}")
                    st.markdown(f"**적립 스탬프:** {order['stamps_earned']}개")
                    st.markdown("---")
                    st.markdown("**주문 상품 목록**")
                    for item in order['items']:
                        st.write(f"- {item['name']} x {item['qty']} ({money(item['unit_price'])}/개)")

# ---------------- 메인 실행 ----------------
if __name__ == "__main__":
    if st.session_state.logged_in:
        show_main_app()
    else:
        show_login_page()
