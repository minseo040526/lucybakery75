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
# NOTE: Streamlit Secrets가 설정되지 않은 환경에서도 작동하도록 기본값 설정
SHOP_NAME = st.secrets.get("SHOP_NAME", "Lucy Bakery")
OWNER_EMAIL_PRIMARY = st.secrets.get("OWNER_EMAIL_PRIMARY", "owner@example.com") # 사장님 이메일 (주문 알림용)
WELCOME_COUPON_AMOUNT = int(st.secrets.get("WELCOME_COUPON_AMOUNT", "2000"))
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
        # 이메일 전송 기능이 비활성화되었더라도 주문 처리는 계속 진행해야 함
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
        # st.error(f"이메일 전송 오류: {e}") # 사용자에게 에러 메시지 노출 방지
        return False, str(e)

# ---------------- 메뉴 로드 ----------------
@st.cache_data
def load_menu_data():
    """CSV 파일을 읽고 데이터프레임을 전처리하고 스코어를 부여합니다."""
    
    BAKERY_FILE = "Bakery_menu - Bakery_menu.csv"
    DRINK_FILE = "Drink_menu - Drink_menu.csv"
    
    # 파일 존재 여부 확인 및 명확한 오류 메시지 제공
    if not os.path.exists(BAKERY_FILE):
        st.error(f"🚨 **[필수 파일 오류]** 베이커리 메뉴 파일 **'{BAKERY_FILE}'**을(를) 찾을 수 없습니다. 파일을 올바르게 업로드했는지 확인하거나 파일명을 수정해주세요.")
        st.stop()
    if not os.path.exists(DRINK_FILE):
        st.error(f"🚨 **[필수 파일 오류]** 음료 메뉴 파일 **'{DRINK_FILE}'**을(를) 찾을 수 없습니다. 파일을 올바르게 업로드했는지 확인하거나 파일명을 수정해주세요.")
        st.stop()
        
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

    # 파일 읽기
    bakery_df = normalize_columns(pd.read_csv(BAKERY_FILE), is_drink=False)
    drink_df  = normalize_columns(pd.read_csv(DRINK_FILE), is_drink=True)
    
    drink_categories = sorted(drink_df["category"].dropna().unique())
    bakery_tags = sorted({t for arr in bakery_df["tags_list"] for t in arr if t})
    
    return bakery_df, drink_df, drink_categories, bakery_tags

try:
    bakery_df, drink_df, drink_categories, bakery_tags = load_menu_data()
except Exception as e:
    # load_menu_data 내부에서 st.stop()을 호출하지만, 혹시 모를 경우를 대비하여
    if "필수 파일 오류" not in str(e):
        st.error(f"메뉴 데이터를 로드하는 중 심각한 오류가 발생했습니다: {e}")
    # 함수 내에서 이미 st.stop()을 호출했으므로 여기서는 추가 조치 없음
    # st.stop()

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

    # 이미지 파일 이름 (사용자가 마지막으로 업로드한 파일 사용)
    IMAGE_FILE_NAME = "제목을 입력해주세요.jpg"
    
    # 1. 앱 대표 이미지 표시
    st.markdown("##") # 공간 확보
    try:
        # 파일 존재 여부를 확인하고 이미지를 표시합니다.
        if os.path.exists(IMAGE_FILE_NAME):
            st.image(IMAGE_FILE_NAME, use_column_width=True, caption="환영합니다! 오늘 하루도 달콤하게 시작하세요.")
        else:
            st.warning(f"⚠️ 대표 이미지 파일 **'{IMAGE_FILE_NAME}'**을 찾을 수 없습니다. 경로를 확인해주세요.")

    except Exception:
        # 혹시 모를 로딩 오류 처리
        st.warning("이미지를 로드하는 중 오류가 발생했습니다.")

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
                user_data = st.session_state.users_db[phone_suffix]
                if user_data["pass"] == password:
                    # 누락된 키 초기화
                    user_data.setdefault("stamps", 0)
                    user_data.setdefault("orders", [])

                    st.session_state.logged_in = True
                    st.session_state.user = {
                        "name": f"고객({phone_suffix})",
                        "phone": phone_suffix,
                        "coupon": user_data["coupon"],
                        "stamps": user_data["stamps"], 
                        "orders": user_data["orders"],
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
                    "stamps": 0,
                    "orders": [],
                }
                st.session_state.logged_in = True
                st.session_state.user = {
                    "name": f"고객({phone_suffix})",
                    "phone": phone_suffix,
                    "coupon": WELCOME_COUPON_AMOUNT,
                    "stamps": 0,
                    "orders": [],
                }
                st.success(f"회원가입이 완료되었으며, {money(WELCOME_COUPON_AMOUNT)} 쿠폰이 지급되었습니다!")
                st.balloons()
                st.rerun()

# ---------------- 장바구니 추가 헬퍼 ----------------
def add_item_to_cart(item, qty=1):
    """장바구니에 아이템을 추가하고 토스트 메시지를 표시합니다."""
    # 이미 장바구니에 있는 항목인지 확인
    found = False
    for cart_item in st.session_state.cart:
        if cart_item['item_id'] == item['item_id']:
            cart_item['qty'] += qty
            found = True
            break
    
    if not found:
        # 새 항목 추가
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
    # 베이커리는 (이미 score가 반영된) 스코어 기준으로 상위 15개 사용
    bakery_to_use = bakery_df.sort_values(by="score", ascending=False).head(15).to_dict("records")
    
    for d in drinks_to_use:
        # 음료 스코어는 기본 1 (이 부분은 변경 없음)
        d_score = d.get("score", 1) 
        
        combos = itertools.combinations(bakery_to_use, n_bakery) if n_bakery > 0 else [[]]

        for b_combo in combos:
            # 예산 설정이 무제한이 아닐 경우에만 계산
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
def process_order_completion(phone_suffix, order_id, total, final_total, use_coupon, note):
    """주문 완료 후 스탬프 적립, 주문 내역 저장 및 쿠폰 발행을 처리하고 이메일을 전송합니다."""
    
    # 주문 상세 정보 DataFrame 생성 (주문 내역 및 이메일 전송에 사용)
    df_cart = pd.DataFrame(st.session_state.cart)

    # 1. 주문 내역 저장
    order_history_item = {
        "id": order_id,
        "date": now_ts(),
        "items": df_cart[["name", "qty", "unit_price"]].to_dict("records"),
        "total": int(total),
        "final_total": int(final_total),
        "coupon_used": st.session_state.user.get('coupon', 0) if use_coupon else 0,
        "stamps_earned": 1, 
        "note": note
    }
    # users_db와 session_state.user에 모두 저장
    st.session_state.users_db[phone_suffix]['orders'].insert(0, order_history_item) # 최신순으로
    st.session_state.user['orders'] = st.session_state.users_db[phone_suffix]['orders']

    # 2. 쿠폰 사용 처리
    if use_coupon:
        st.session_state.user['coupon'] = 0
        st.session_state.users_db[phone_suffix]['coupon'] = 0

    # 3. 스탬프 적립
    st.session_state.user['stamps'] += 1
    st.session_state.users_db[phone_suffix]['stamps'] += 1
    
    # 4. 스탬프 목표 달성 확인 및 리워드 지급
    current_stamps = st.session_state.user['stamps']
    
    if current_stamps >= STAMP_GOAL:
        # 리워드 지급
        st.session_state.user['coupon'] += STAMP_REWARD_AMOUNT
        st.session_state.users_db[phone_suffix]['coupon'] += STAMP_REWARD_AMOUNT
        
        # 스탬프 리셋
        st.session_state.user['stamps'] = current_stamps - STAMP_GOAL
        st.session_state.users_db[phone_suffix]['stamps'] = current_stamps - STAMP_GOAL
        
        st.balloons()
        st.success(f"🎉 **스탬프 {STAMP_GOAL}개 달성!** {money(STAMP_REWARD_AMOUNT)} 쿠폰이 추가 지급되었습니다. 축하합니다!")

    # 5. 사장님에게 이메일 알림 전송 (비동기 처리 대신 바로 실행)
    success, error_msg = send_order_email(
        [OWNER_EMAIL_PRIMARY], 
        SHOP_NAME, order_id, 
        order_history_item['items'], 
        total, note
    )
    if not success:
        st.warning(f"사장님께 주문 알림 이메일 전송에 실패했습니다. (오류: {error_msg}). 주문 처리는 완료되었습니다.")
    
    # 6. 사용자에게 최종 메시지
    st.toast(f"주문이 완료되어 스탬프 1개가 적립되었습니다! ❤️", icon="🎉")
    
    # 7. 장바구니 비우고 새로고침
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
                    if max_budget == 0:
                        st.error("1인 예산이 0원으로 설정되었습니다. 예산을 높이거나 '무제한'을 선택해주세요.")
                        st.session_state.reco_results = []
                        st.session_state.is_reco_fallback = False
                        return
                else:
                    max_budget = float('inf') # 무제한

                # --- Phase 1: 엄격한 조건 (태그 필터링 및 점수 부스팅 적용) ---
                bakery_strict = bakery_base.copy()
                
                if st.session_state.sel_tags:
                    tagset = set(st.session_state.sel_tags)
                    
                    # 1. 엄격한 필터: 선택된 태그 중 하나 이상을 포함하는 베이커리만 선택
                    bakery_strict = bakery_strict[bakery_strict["tags_list"].apply(lambda xs: not tagset.isdisjoint(set(xs)))]
                    
                    # 2. **취향 가산점 부스팅**: 필터링된 메뉴의 점수를 크게 높여서 추천 순위 보장
                    bakery_strict["score"] = bakery_strict.apply(
                        lambda row: row["score"] + TAG_BONUS_SCORE, 
                        axis=1
                    )
                
                # 가산점이 반영된 strict 목록으로 조합 시도
                results = find_combinations(drinks, bakery_strict, n_people_val, st.session_state.n_bakery, max_budget)
                is_fallback = False

                # --- Phase 2: 폴백 (유사 메뉴 추천) ---
                if not results and st.session_state.sel_tags:
                    is_fallback = True
                    # 태그 필터링을 풀고 (점수 부스팅 없이) 전체 베이커리 목록으로 다시 시도
                    results = find_combinations(drinks, bakery_base, n_people_val, st.session_state.n_bakery, max_budget)

                if not results:
                    st.warning("조건에 맞는 메뉴 조합을 찾지 못했습니다. 조건을 완화하거나 변경해보세요.")
                    st.session_state.reco_results = []
                    st.session_state.is_reco_fallback = False
                else:
                    # 결과 정렬 및 저장
                    results.sort(key=lambda x: x["score"], reverse=True)
                    st.session_state.reco_results = results[:5] # 상위 5개만 표시
                    st.session_state.is_reco_fallback = is_fallback
            st.rerun() # 추천 결과 표시를 위해 다시 실행

        # --- 추천 결과 표시 ---
        if st.session_state.reco_results:
            st.subheader("2. 추천 결과 (AI 스코어 기준)")
            
            if st.session_state.is_reco_fallback:
                st.info("💡 **참고:** 선택하신 태그 조합의 메뉴는 찾지 못했지만, **예산과 인원수에 맞는 인기 메뉴**를 대신 추천해 드립니다.")
            
            for i, reco in enumerate(st.session_state.reco_results):
                with st.expander(f"✨ 추천 {i+1}. 총액: {money(reco['total'])} (AI 스코어: {reco['score']:.1f})", expanded=(i==0)):
                    
                    # --- 추천 조합 상세 ---
                    col_info, col_order = st.columns([5, 2])
                    
                    with col_info:
                        st.caption(f"**음료 ({reco['drink']['name']})** x {n_people_val}잔")
                        
                        # 베이커리 목록 출력
                        if reco['bakery']:
                            st.caption(f"**베이커리 ({len(reco['bakery'])}개)**")
                            for b in reco['bakery']:
                                tags = ", ".join(f"#{t}" for t in b["tags_list"])
                                st.markdown(f"- {b['name']} ({money(b['price'])}) <sub>{tags}</sub>", unsafe_allow_html=True)
                        else:
                            st.markdown("- 베이커리 메뉴 없음")
                        
                    with col_order:
                        st.markdown("---")
                        # 전체 조합을 장바구니에 담기 버튼
                        if st.button(f"추천 {i+1} 전체 장바구니에 담기", key=f"add_reco_{i}", type="primary", use_container_width=True):
                            # 음료 추가 (인원수만큼)
                            add_item_to_cart(reco['drink'], n_people_val)
                            # 베이커리 추가 (각 1개씩)
                            for b in reco['bakery']:
                                add_item_to_cart(b, 1)
                            
                            st.toast(f"추천 {i+1} 조합이 모두 장바구니에 추가되었습니다!", icon="✅")
                            st.rerun() # 토스트 표시 후 재실행

    # ===== 메뉴판 =====
    with tab_menu:
        st.header("📋 전체 메뉴판")
        
        # 베이커리
        st.subheader("갓 구운 베이커리 🍞")
        bakery_cols = st.columns(3)
        for i, item in enumerate(bakery_df.to_dict("records")):
            with bakery_cols[i % 3]:
                with st.container(border=True):
                    tags = ", ".join(f"#{t}" for t in item["tags_list"])
                    st.markdown(f"**{item['name']}**")
                    st.markdown(f"가격: **{money(item['price'])}**")
                    st.caption(tags)
                    if st.button("장바구니 담기", key=f"add_b_{item['item_id']}", use_container_width=True):
                        add_item_to_cart(item)

        st.markdown("---")
        
        # 음료
        st.subheader("신선한 음료 ☕")
        for category in drink_categories:
            st.caption(f"**{category}**")
            cat_df = drink_df[drink_df["category"] == category]
            
            drink_cols = st.columns(3)
            for i, item in enumerate(cat_df.to_dict("records")):
                with drink_cols[i % 3]:
                    with st.container(border=True):
                        st.markdown(f"**{item['name']}**")
                        st.markdown(f"가격: **{money(item['price'])}**")
                        if st.button("장바구니 담기", key=f"add_d_{item['item_id']}", use_container_width=True):
                            add_item_to_cart(item)

    # ===== 장바구니 =====
    with tab_cart:
        st.header("🛍️ 장바구니")
        
        if not st.session_state.cart:
            st.info("장바구니가 비어있습니다. 메뉴를 담아보세요!")
            
        else:
            # 장바구니 목록 표시
            df_cart = pd.DataFrame(st.session_state.cart)
            df_cart["가격"] = df_cart.apply(lambda row: money(row["unit_price"]), axis=1)
            df_cart["총액"] = df_cart.apply(lambda row: money(row["unit_price"] * row["qty"]), axis=1)
            
            display_df = df_cart[["name", "category", "qty", "가격", "총액"]].rename(
                columns={"name": "메뉴명", "category": "종류", "qty": "수량"}
            )
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # 총액 계산
            total_price = df_cart["unit_price"].dot(df_cart["qty"])
            st.markdown(f"### 최종 주문 금액 (할인 전): **{money(total_price)}**")

            st.markdown("---")
            
            # --- 결제 및 주문 ---
            st.subheader("결제 및 주문하기")
            
            use_coupon = st.checkbox(
                f"쿠폰 사용하기 ({money(st.session_state.user.get('coupon', 0))} 전액)", 
                value=st.session_state.user.get('coupon', 0) > 0,
                disabled=st.session_state.user.get('coupon', 0) == 0,
                key="use_coupon"
            )

            coupon_discount = st.session_state.user.get('coupon', 0) if use_coupon else 0
            final_total = max(0, total_price - coupon_discount)

            st.markdown(f"**할인 적용 금액:** {money(coupon_discount)}")
            st.markdown(f"### **최종 결제 금액 (현장 결제):** <span style='color:{ACCENT_COLOR}; font-size: 1.5em; font-weight: bold;'>{money(final_total)}</span>", unsafe_allow_html=True)
            
            note = st.text_area("요청사항 (ex. 포장 요청, 픽업 시간 등)", key="order_note")

            if st.button("주문 완료 및 현장 결제", key="complete_order", type="primary", use_container_width=True):
                # 주문 ID 생성
                order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{st.session_state.user['phone']}"
                
                # 주문 처리 함수 호출
                process_order_completion(
                    st.session_state.user['phone'], 
                    order_id, 
                    total_price, 
                    final_total, 
                    use_coupon,
                    note
                )


    # ===== 스탬프 & 내역 =====
    with tab_history:
        st.header("❤️ 스탬프 & 주문 내역")

        st.subheader("스탬프 적립 현황")
        stamps = st.session_state.user.get('stamps', 0)
        
        col_stamp, col_goal = st.columns(2)
        with col_stamp:
            st.metric("현재 스탬프", f"{stamps}개")
        with col_goal:
            remaining = STAMP_GOAL - (stamps % STAMP_GOAL)
            st.metric("다음 리워드까지", f"{remaining}개 남음")
            
        progress_ratio = (stamps % STAMP_GOAL) / STAMP_GOAL
        st.progress(progress_ratio)
        st.caption(f"스탬프 {STAMP_GOAL}개 달성 시 **{money(STAMP_REWARD_AMOUNT)}** 쿠폰이 지급됩니다.")
        
        st.markdown("---")

        st.subheader("나의 주문 내역")
        orders = st.session_state.user.get('orders', [])
        
        if not orders:
            st.info("아직 주문 내역이 없습니다.")
        else:
            for order in orders:
                with st.expander(f"주문일시: {order['date']} | 최종 결제: {money(order['final_total'])}", expanded=False):
                    st.caption(f"**주문번호:** {order['id']}")
                    st.caption(f"**총 주문액 (할인 전):** {money(order['total'])}")
                    st.caption(f"**쿠폰 사용액:** {money(order['coupon_used'])}")
                    st.caption(f"**적립 스탬프:** {order['stamps_earned']}개")
                    st.caption(f"**요청사항:** {order.get('note', '없음')}")
                    
                    st.markdown("---")
                    st.markdown("**주문 상품:**")
                    
                    # 주문 상품 목록 테이블로 표시
                    items_df = pd.DataFrame(order['items'])
                    items_df['단가'] = items_df['unit_price'].apply(money)
                    items_df['총액'] = items_df.apply(lambda row: money(row['unit_price'] * row['qty']), axis=1)
                    st.dataframe(
                        items_df.rename(columns={'name':'메뉴명', 'qty':'수량'}),
                        hide_index=True,
                        use_container_width=True,
                        column_order=('메뉴명', '수량', '단가', '총액')
                    )


# ---------------- 메인 실행 ----------------
if st.session_state.logged_in:
    show_main_app()
else:
    show_login_page()
