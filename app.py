import streamlit as st
import pandas as pd
import itertools, os, re, smtplib, ssl, uuid
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime
from PIL import Image
import json 
import base64 # <-- Base64 모듈 추가

# ---------------- 기본 설정 ----------------
st.set_page_config(page_title="AI 베이커리 추천·주문", layout="wide")

# Secret variables for configuration (replace with actual values in st.secrets)
SHOP_NAME = st.secrets.get("SHOP_NAME", "Lucy Bakery")
OWNER_EMAIL_PRIMARY = st.secrets.get("OWNER_EMAIL_PRIMARY", "owner@example.com") # 사장님 이메일 (주문 알림용)

# ****************** 쿠폰 및 리워드 설정 ******************
MIN_DISCOUNT_PURCHASE = 20000 # 10% 할인 쿠폰 적용을 위한 최소 구매 금액 (20,000원)
DISCOUNT_RATE = 0.1           # 10% 할인율
WELCOME_DISCOUNT_COUNT = 1    # 신규 가입 시 지급하는 10% 쿠폰 개수

AMERICANO_PRICE = 4000        # 아메리카노 기준 가격
STAMP_REWARD_AMOUNT = AMERICANO_PRICE # 스탬프 10개 달성 시 지급할 쿠폰 금액 (4,000원)
STAMP_GOAL = 10               # 아메리카노 리워드 목표 스탬프 수
# ****************************************************

SMTP_HOST = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(st.secrets.get("SMTP_PORT", "465"))
SMTP_USER = st.secrets.get("SMTP_USER", "noreply@example.com") # 발신 이메일
SMTP_PASS = st.secrets.get("SMTP_PASS", "your_smtp_password") # 발신 이메일 비밀번호
POPULAR_BONUS_SCORE = 1 # 인기 메뉴에 부여할 가산점
TAG_BONUS_SCORE = 5 # 선택 태그 일치 메뉴에 부여할 가산점

# JSON 파일 경로 설정
DATA_FILE = "user_data.json"

# ****************** 이미지 파일 경로 정의 ******************
LOGIN_IMAGES_FILES = [
    "poster2.jpg", 
    "event1.jpg",   
    "poster1.jpg"   
]
# *********************************************************

# ---------------- 이미지 유틸리티 함수 (Base64 인코딩) ----------------
def get_base64_image(image_file):
    """파일을 읽어 Base64 문자열로 변환합니다. Streamlit Cloud 환경에서 CSS 배경 이미지 로딩 안정화."""
    try:
        with open(image_file, "rb") as f:
            mime_type = "image/jpeg"
            if image_file.lower().endswith(".png"):
                mime_type = "image/png"

            return f"data:{mime_type};base64,{base64.b64encode(f.read()).decode()}"
    except FileNotFoundError:
        print(f"경고: 배경 이미지 파일 '{image_file}'을 찾을 수 없습니다.")
        return None

# ****************** 이미지 데이터 사전 처리 ******************
# 스크립트 실행 시 이미지 파일을 미리 Base64로 인코딩합니다.
ENCODED_LOGIN_IMAGES = [
    data for file_name in LOGIN_IMAGES_FILES 
    if (data := get_base64_image(file_name)) is not None
]
# *********************************************************


# ---------------- JSON 유틸리티 함수 (데이터 영속성) ----------------

def load_user_data():
    """
    JSON 파일에서 사용자 데이터를 불러옵니다. 파일이 없으면 빈 딕셔너리를 반환합니다.
    """
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    else:
        return {}

def save_user_data(data):
    """
    현재 사용자 데이터를 JSON 파일에 저장합니다.
    """
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ---------------- 디자인 테마 적용 (Base64 이미지 사용) ----------------
def set_custom_style(is_login=False):
    BG_COLOR = "#FAF8F1"        
    CARD_COLOR = "#F8F6F4"      
    TEXT_COLOR = "#3E2723"      
    PRIMARY_COLOR = "#A1887F" 
    ACCENT_COLOR = "#795548"  

    num_images = len(ENCODED_LOGIN_IMAGES)
    image_keyframes = ""
    
    # Base64로 인코딩된 이미지 리스트 사용
    if is_login and num_images > 0:
        step = 100 / num_images
        keyframes_list = []
        
        for i, img_data in enumerate(ENCODED_LOGIN_IMAGES):
            if i == 0:
                # 0%와 100%는 첫 번째 이미지 (애니메이션 루프를 위해)
                keyframes_list.append(f"0% {{ background-image: url('{img_data}'); }}")
                keyframes_list.append(f"100% {{ background-image: url('{ENCODED_LOGIN_IMAGES[0]}'); }}")
            
            start_percent = i * step
            end_percent = (i + 1) * step
            
            # 현재 이미지가 시작하고 유지되는 시점
            keyframes_list.append(f"{start_percent:.1f}% {{ background-image: url('{img_data}'); }}")
            
            # 다음 이미지로 전환
            if i < num_images - 1:
                next_img_data = ENCODED_LOGIN_IMAGES[i + 1]
                keyframes_list.append(f"{end_percent:.1f}% {{ background-image: url('{next_img_data}'); }}")

        image_keyframes = "\n".join(keyframes_list)

    # 로그인 페이지에만 배경 이미지를 적용하는 CSS
    login_css = ""
    if is_login and num_images > 0:
        login_css = f"""
        @keyframes imageAnimation {{
            {image_keyframes}
        }}

        .stApp > header, .stApp > footer {{
            background: none !important;
        }}
        .stApp {{
            background-color: {BG_COLOR};
            animation: imageAnimation {num_images * 5}s infinite ease-in-out;
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            transition: background-image 1s ease-in-out;
        }}
        .main .block-container {{
            background: none;
            padding-top: 2rem;
        }}
        
        div[data-testid="stForm"] {{
            background-color: {CARD_COLOR}D0;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(5px);
            margin: 0 auto;
            max-width: 450px;
        }}
        .stApp h1, .stApp h2, .stApp h3, .stApp .stMarkdown, .stApp .stText, .stApp .stLabel {{
            color: {TEXT_COLOR} !important;
            text-shadow: 1px 1px 2px rgba(255, 255, 255, 0.5);
        }}
        """

    # 일반 앱 페이지의 CSS
    app_css = f"""
    .stApp {{
        background-color: {BG_COLOR};
        color: {TEXT_COLOR};
        font-family: 'Malgun Gothic', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }}
    .block-container {{
        background-color: {BG_COLOR};
        padding-top: 2rem;
    }}
    """
    
    # 공통 CSS
    common_css = f"""
    <style>
    {app_css if not is_login else login_css}
    
    h1, h2, h3, h4, h5, h6, .stMarkdown, .stText, .stLabel {{
        color: {TEXT_COLOR} !important;
        font-family: inherit;
    }}
    div[data-testid="stTextInput"] > div:first-child, 
    div[data-testid="stNumberInput"] > div:first-child, 
    div[data-testid="stSelectbox"] > div:first-child, 
    div[data-testid="stMultiSelect"] > div:first-child,
    div[data-testid="stRadio"], div[data-testid="stSlider"] {{
        background-color: {CARD_COLOR}; 
        border-radius: 12px;
        padding: 10px;
        border: 1px solid {PRIMARY_COLOR}30;
        box-shadow: 1px 1px 3px rgba(0, 0, 0, 0.05);
    }}
    div[data-testid="stRadio"] label {{ padding: 5px 0; }}
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
    .stButton button[data-testid*="primary"] {{
        background-color: {ACCENT_COLOR};
    }}
    .stButton button[data-testid*="primary"]:hover {{
        background-color: #BCAAA4;
    }}
    div[data-testid="stAlert"] {{
        border-left: 5px solid {ACCENT_COLOR};
        background-color: {CARD_COLOR};
        color: {TEXT_COLOR};
        border-radius: 12px;
        box-shadow: 1px 1px 5px rgba(0, 0, 0, 0.1);
    }}
    .stTabs [data-baseweb="tab-list"] {{
        gap: 15px;
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
        background-color: {CARD_COLOR};
        color: {TEXT_COLOR} !important;
        border-bottom: 3px solid {ACCENT_COLOR} !important;
        box-shadow: 0 -2px 5px rgba(0, 0, 0, 0.05);
    }}
    .stMarkdown caption {{
        color: {PRIMARY_COLOR} !important;
    }}
    hr {{
        border-top: 1px solid {PRIMARY_COLOR}50;
    }}
    </style>
    """
    st.markdown(common_css, unsafe_allow_html=True)


# ---------------- 유틸 ----------------
def money(x): return f"{int(x):,}원"
def now_ts(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def normalize_str(s): return re.sub(r"\s+"," ",str(s).strip()) if pd.notna(s) else ""

# ---------------- 이메일 ----------------
def send_order_email(to_emails, shop_name, order_id, items, total, note):
    """주문 완료 시 사장님에게 알림 이메일을 전송합니다."""
    if not SMTP_USER or not SMTP_PASS or OWNER_EMAIL_PRIMARY == "owner@example.com":
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
        drink_df  = normalize_columns(pd.read_csv("Drink_menu.csv"), is_drink=True)
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
# JSON 파일에서 데이터 로드
if "users_db" not in st.session_state: st.session_state.users_db = load_user_data()

# ---------------- 로그인 페이지 ----------------
def show_login_page():
    # 로그인 페이지에만 배경 이미지 적용
    set_custom_style(is_login=True)
    
    # 로그인 폼을 중앙에 배치하기 위해 컬럼 사용
    c_left, c_center, c_right = st.columns([1, 2, 1])

    with c_center:
        st.markdown(f"**<h1 style='text-align: center; margin-top: 15vh;'>🥐 {SHOP_NAME}</h1>**", unsafe_allow_html=True)
        st.header("휴대폰 번호 뒷자리로 로그인/회원가입")

        with st.form("login_form"):
            phone_suffix = st.text_input("휴대폰 번호 뒷 4자리", max_chars=4, placeholder="0000")
            password = st.text_input("비밀번호 (6자리)", type="password", max_chars=6, placeholder="******")

            submitted = st.form_submit_button("로그인 / 가입", type="primary", use_container_width=True)

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
                        user_data.setdefault("stamps", 0)
                        user_data.pop("coupon", None) 
                        user_data.setdefault("coupon_count", 0) 
                        user_data.setdefault("coupon_amount", 0)
                        user_data.setdefault("orders", [])

                        st.session_state.logged_in = True
                        st.session_state.user = {
                            "name": f"고객({phone_suffix})",
                            "phone": phone_suffix,
                            "coupon_count": user_data["coupon_count"], 
                            "coupon_amount": user_data["coupon_amount"],
                            "stamps": user_data["stamps"],
                            "orders": user_data["orders"]
                        }
                        st.success(f"{st.session_state.user['name']}님, 로그인되었습니다.")
                        st.rerun()
                    else:
                        st.error("비밀번호가 일치하지 않습니다.")
                else:
                    # 신규 가입
                    st.session_state.users_db[phone_suffix] = {
                        "pass": password,
                        "coupon_count": WELCOME_DISCOUNT_COUNT, 
                        "coupon_amount": 0, 
                        "stamps": 0,
                        "orders": []
                    }
                    st.session_state.logged_in = True
                    st.session_state.user = {
                        "name": f"고객({phone_suffix})",
                        "phone": phone_suffix,
                        "coupon_count": WELCOME_DISCOUNT_COUNT, 
                        "coupon_amount": 0,
                        "stamps": 0,
                        "orders": []
                    }
                    st.success(f"회원가입이 완료되었으며, **10% 할인 쿠폰 1개**가 지급되었습니다!")
                    st.balloons()
                    
                    save_user_data(st.session_state.users_db)
                    
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
    drinks_to_use = drinks_df.to_dict("records")
    bakery_to_use = bakery_df.sort_values(by="score", ascending=False).head(15).to_dict("records")

    # 베이커리 개수가 0개면 조합을 시도할 필요 없이 음료만 계산
    combos = itertools.combinations(bakery_to_use, n_bakery) if n_bakery > 0 else [[]]

    for d in drinks_to_use:
        d_score = d.get("score", 1) 

        for b_combo in combos:
            total_price = d["price"] * n_people + sum(b["price"] for b in b_combo)

            if total_price <= max_budget:
                total_score = d_score + sum(b["score"] for b in b_combo)

                found_results.append({
                    "drink": d, 
                    "bakery": b_combo, 
                    "total": total_price, 
                    "score": total_score
                })
    return found_results

# ---------------- 주문 완료 처리 ----------------
def process_order_completion(phone_suffix, order_id, df_cart, total, final_total, discount_type, discount_amount):
    """주문 완료 후 스탬프 적립, 주문 내역 저장 및 쿠폰 발행을 처리합니다."""
    
    # 1. 주문 내역 저장
    order_history_item = {
        "id": order_id,
        "date": now_ts(),
        "items": df_cart[["name", "qty", "unit_price"]].to_dict("records"),
        "total": int(total),
        "final_total": int(final_total),
        "discount_type": discount_type, 
        "discount_amount": int(discount_amount), 
        "stamps_earned": 1 
    }
    st.session_state.users_db[phone_suffix]['orders'].insert(0, order_history_item)
    st.session_state.user['orders'] = st.session_state.users_db[phone_suffix]['orders']

    # 2. 쿠폰 사용 처리 (차감)
    if discount_type == "Amount":
        st.session_state.user['coupon_amount'] -= discount_amount
        st.session_state.users_db[phone_suffix]['coupon_amount'] -= discount_amount
        st.toast(f"금액 쿠폰 {money(discount_amount)}이(가) 사용되었습니다.", icon="💳")
    elif discount_type == "Rate":
        st.session_state.user['coupon_count'] -= 1
        st.session_state.users_db[phone_suffix]['coupon_count'] -= 1
        st.toast("10% 할인 쿠폰 1개가 사용되었습니다.", icon="💳")

    # 3. 스탬프 적립
    st.session_state.user['stamps'] += 1
    st.session_state.users_db[phone_suffix]['stamps'] += 1
    
    st.toast(f"주문이 완료되어 스탬프 1개가 적립되었습니다! ❤️", icon="🎉")

    # 4. 스탬프 목표 달성 확인 및 리워드 지급
    current_stamps = st.session_state.user['stamps']
    
    if current_stamps >= STAMP_GOAL:
        st.session_state.user['coupon_amount'] += STAMP_REWARD_AMOUNT
        st.session_state.users_db[phone_suffix]['coupon_amount'] += STAMP_REWARD_AMOUNT
        
        st.session_state.user['stamps'] = current_stamps - STAMP_GOAL
        st.session_state.users_db[phone_suffix]['stamps'] = current_stamps - STAMP_GOAL
        
        st.balloons()
        st.success(f"🎉 **스탬프 {STAMP_GOAL}개 달성!** 아메리카노 1잔에 해당하는 **{money(STAMP_REWARD_AMOUNT)}** 금액 쿠폰이 추가 지급되었습니다.")
    
    # 데이터 저장
    save_user_data(st.session_state.users_db)
    
    # 5. 장바구니 비우고 새로고침
    st.session_state.cart = []
    st.rerun()

# ---------------- 메인 앱 페이지 ----------------
def show_main_app():
    set_custom_style(is_login=False) 
    st.title("🥐 AI 베이커리 추천·주문")

    c_user, c_coupon, c_logout = st.columns([4, 4, 2])
    with c_user:
        st.success(f"**{st.session_state.user.get('name', '고객')}**님, 환영합니다!")
    with c_coupon:
        amount = st.session_state.user.get('coupon_amount', 0)
        count = st.session_state.user.get('coupon_count', 0)
        st.info(f"금액 쿠폰: **{money(amount)}** | 10% 쿠폰: **{count}개**")
    with c_logout:
        if st.button("로그아웃", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user = {}
            st.session_state.cart = []
            st.session_state.reco_results = []
            st.session_state.is_reco_fallback = False
            st.session_state.users_db = load_user_data()
            st.success("로그아웃되었습니다.")
            st.rerun()

    st.markdown("---")
    
    # ****************** 오늘의 추천 메뉴 및 이벤트 ******************
    st.subheader("📢 오늘의 혜택 & 추천 메뉴")
    tab_event, tab_reco_jam, tab_reco_salt = st.tabs(["🎁 이벤트", "🥪 오늘의 추천: 잠봉 뵈르", "☕ 오늘의 추천: 아메리카노 & 소금빵"])
    
    with tab_event:
        st.image("event1.jpg", caption="앱 사용 인증샷으로 쿠키도 받고 디저트 세트도 받으세요!", use_column_width=True)
    
    with tab_reco_jam:
        st.image("poster2.jpg", caption="오늘의 든든한 점심 추천! 바삭한 바게트에 햄과 버터의 환상적인 조화!", use_column_width=True)
    
    with tab_reco_salt:
        st.image("poster1.jpg", caption="국민 조합! 짭짤 고소한 소금빵과 시원한 아메리카노 세트!", use_column_width=True)
    
    st.markdown("---")
    # *************************************************************************


    # ---------------- 탭 ----------------
    tab_reco, tab_menu, tab_cart, tab_history = st.tabs(["🤖 AI 메뉴 추천", "📋 메뉴판", "🛍️ 장바구니", "❤️ 스탬프 & 내역"])

    # ===== 추천 로직 =====
    with tab_reco:
        st.header("AI 맞춤형 메뉴 추천")

        st.subheader("1. 추천 조건 설정")
        c1, c2, c3 = st.columns(3)
        with c1:
            n_people = st.number_input("인원 수 (음료 잔 수)", 1, 20, 2, key="n_people")
            budget_choice = st.radio("1인 예산 기준", ["무제한", "금액 직접 입력"], index=1, key="budget_choice")
            input_budget_val = 0
            if budget_choice == "금액 직접 입력":
                input_budget_val = st.number_input("1인 예산 금액 (원)", min_value=1, value=7500, step=500, key="input_budget_val")

        with c2:
            n_bakery = st.slider("베이커리 개수", 0, 5, 2, key="n_bakery")
            sel_cats = st.multiselect("원하는 음료 카테고리", drink_categories, default=drink_categories, key="sel_cats")

        with c3:
            sel_tags = st.multiselect("원하는 베이커리 태그 (최대 3개)", bakery_tags, max_selections=3, key="sel_tags")

        st.markdown("---")

        if st.button("AI 추천 보기", type="primary", use_container_width=True):
            with st.spinner("최적의 메뉴를 조합하고 있습니다..."):

                drinks = drink_df[drink_df["category"].isin(st.session_state.sel_cats)] if st.session_state.sel_cats else drink_df
                bakery_base = bakery_df.copy()

                n_people_val = st.session_state.n_people

                if st.session_state.budget_choice == "금액 직접 입력":
                    budget_per_person = st.session_state.get('input_budget_val', 0)
                    max_budget = budget_per_person * n_people_val
                    if max_budget <= 0:
                        st.error("총 예산이 0원 이하입니다. 예산을 높이거나 '무제한'을 선택해주세요.")
                        st.session_state.reco_results = []
                        st.session_state.is_reco_fallback = False
                        
                else:
                    max_budget = float('inf') 

                bakery_strict = bakery_base.copy()
                
                if st.session_state.sel_tags and st.session_state.n_bakery > 0:
                    tagset = set(st.session_state.sel_tags)
                    bakery_strict = bakery_strict[bakery_strict["tags_list"].apply(lambda xs: not tagset.isdisjoint(set(xs)))]
                    bakery_strict["score"] = bakery_strict.apply(
                        lambda row: row["score"] + (len(set(row["tags_list"]) & tagset) * TAG_BONUS_SCORE), 
                        axis=1
                    )

                bakery_use_for_reco = bakery_strict if st.session_state.n_bakery > 0 and st.session_state.sel_tags else bakery_base
                results = find_combinations(drinks, bakery_use_for_reco, n_people_val, st.session_state.n_bakery, max_budget)
                is_fallback = False

                if not results and st.session_state.sel_tags:
                    is_fallback = True
                    results = find_combinations(drinks, bakery_base, n_people_val, st.session_state.n_bakery, max_budget)

                if not results:
                    st.warning("조건에 맞는 메뉴 조합을 찾지 못했습니다. 인원수, 예산, 베이커리 개수 등의 조건을 완화하거나 변경해보세요.")
                    st.session_state.reco_results = []
                    st.session_state.is_reco_fallback = False
                else:
                    sorted_results = sorted(results, key=lambda x: (-x["score"], x["total"]))[:3]
                    st.session_state.reco_results = sorted_results
                    st.session_state.is_reco_fallback = is_fallback
                    st.toast("추천 메뉴 조합이 성공적으로 생성되었습니다!")

        if st.session_state.reco_results:
            st.subheader("2. AI 추천 세트")

            if st.session_state.is_reco_fallback:
                st.info("⚠️ **선택하신 태그 조건을 만족하는 조합을 찾지 못해** 가격/인기 메뉴를 기준으로 유사 추천되었습니다. 조건을 완화하면 더 많은 조합을 볼 수 있습니다.")

            current_n_people = st.session_state.n_people

            for i, r in enumerate(st.session_state.reco_results, start=1):
                st.markdown(f"**--- 추천 세트 {i} (스코어: {r['score']}, 금액: {money(r['total'])}) ---**")

                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("##### ☕ 음료")
                    st.write(f"**{r['drink']['name']}** ({money(r['drink']['price'])} x {current_n_people}잔)")
                    st.caption(f"카테고리: {r['drink']['category']}")

                    if st.button(f"🛒 음료 {current_n_people}잔 담기", key=f"d_reco_{i}", use_container_width=True, type="secondary"):
                        add_item_to_cart(r["drink"], qty=current_n_people)

                with col2:
                    st.markdown(f"##### 🥐 베이커리 ({len(r['bakery'])}개)")

                    if r["bakery"]:
                        for j, b in enumerate(r["bakery"]):
                            pop_icon = "⭐ " if "인기" in b["tags_list"] else ""
                            tag_highlight = "✨ " if len(set(b['tags_list']) & set(st.session_state.sel_tags)) > 0 else ""
                            st.write(f"- {tag_highlight}{pop_icon}{b['name']} ({money(b['price'])})")
                            st.caption(f"태그: {', '.join(b['tags_list'])}")

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

        for i, item in bakery_df.iterrows():
            pop_icon = "⭐ " if "인기" in item["tags_list"] else ""

            c1, c2, c3, c4 = st.columns([3, 2, 4, 2])
            with c1: st.write(f"**{pop_icon}{item['name']}**")
            with c2: st.write(money(item['price']))
            with c3: st.caption(f"태그: {', '.join(item['tags_list'])}")
            with c4:
                if c4.button("🛒 담기", key=f"menu_b_{item['item_id']}", use_container_width=True, type="secondary"):
                    add_item_to_cart(item, qty=1)

        st.markdown("---")

        st.subheader("☕ 음료 메뉴")
        st.caption(f"총 {len(drink_df)}개 품목")

        for i, item in drink_df.iterrows():
            c1, c2, c3, c4 = st.columns([3, 2, 4, 2])
            with c1: st.write(f"**{item['name']}**")
            with c2: st.write(money(item['price']))
            with c3: st.caption(f"카테고리: {item['category']}")
            with c4:
                if c4.button("🛒 담기", key=f"menu_d_{item['item_id']}", use_container_width=True, type="secondary"):
                    add_item_to_cart(item, qty=1)


    # ===== 장바구니 (쿠폰 로직 수정) =====
    with tab_cart:
        st.header("🛍️ 장바구니")

        if not st.session_state.cart:
            st.info("장바구니가 비어 있습니다. AI 추천 탭이나 메뉴판 탭에서 상품을 담아주세요.")
        else:
            df_cart = pd.DataFrame(st.session_state.cart)
            df_cart["total_price"] = df_cart["qty"] * df_cart["unit_price"]

            st.markdown("##### 현재 장바구니 목록")

            for i in range(len(df_cart)):
                item = df_cart.iloc[i]
                qty_key = f"qty_{item['item_id']}_{i}"
                remove_key = f"rm_{item['item_id']}_{i}"

                c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 2, 1])

                with c1: st.write(f"**{item['name']}**")
                with c2: st.write(money(item['unit_price']))
                with c3:
                    qty = st.number_input("수량", 1, 99, int(item["qty"]), key=qty_key, label_visibility="collapsed")
                    if qty != item["qty"]:
                        st.session_state.cart[i]["qty"] = int(qty)
                        st.rerun()

                with c4: st.write(f"**{money(item['total_price'])}**")
                with c5:
                    if st.button("X", key=remove_key, type="secondary"):
                        st.session_state.cart.pop(i)
                        st.toast(f"**{item['name']}**을 삭제했습니다.")
                        st.rerun()

            st.markdown("---")
            total = int(df_cart["total_price"].sum())
            
            # --- 쿠폰 적용 (금액 쿠폰 vs 10% 쿠폰) ---
            st.subheader("🎫 쿠폰 적용")
            coupon_amount = st.session_state.user.get('coupon_amount', 0)
            coupon_count = st.session_state.user.get('coupon_count', 0)
            
            discount_type = None
            discount_amount = 0

            st.markdown(f"""
                <div style='padding: 10px; border: 1px solid #A1887F50; border-radius: 8px; margin-bottom: 15px;'>
                **보유 쿠폰 현황**
                <br>
                💰 금액 쿠폰: **{money(coupon_amount)}**
                <br>
                📉 10% 할인 쿠폰 (2만원 이상 구매 시): **{coupon_count}개**
                </div>
            """, unsafe_allow_html=True)
            
            # 1. 쿠폰 사용 선택 (라디오 버튼)
            options = ["할인 미적용"]
            if coupon_amount > 0:
                options.append(f"금액 쿠폰 사용 (최대 {money(coupon_amount)})")
            if coupon_count > 0:
                options.append(f"10% 할인 쿠폰 사용 (2만원 이상 구매 시)")
            
            coupon_selection = st.radio("사용할 쿠폰 선택", options, index=0, key="coupon_choice")

            # 2. 선택에 따른 할인 계산
            if "금액 쿠폰" in coupon_selection:
                max_use = min(coupon_amount, total)
                applied_amount = st.slider(
                    f"사용할 금액 (최대 {money(max_use)})", 
                    0, max_use, max_use, step=1000, 
                    key="amount_discount"
                )
                discount_type = "Amount"
                discount_amount = applied_amount

            elif "10% 할인 쿠폰" in coupon_selection:
                if coupon_count > 0:
                    if total >= MIN_DISCOUNT_PURCHASE:
                        discount_amount = int(total * DISCOUNT_RATE)
                        st.success(f"10% 할인 적용! 총 {money(discount_amount)}이 할인됩니다.")
                        discount_type = "Rate"
                    else:
                        st.warning(f"10% 할인 쿠폰은 **{money(MIN_DISCOUNT_PURCHASE)} 이상** 구매 시에만 적용됩니다. (현재 금액: {money(total)})")
                        discount_type = None
                        discount_amount = 0
                else:
                    discount_type = None
                    discount_amount = 0
            
            final_total = max(0, total - discount_amount)
            
            st.markdown("---")
            st.subheader(f"총 주문 금액: {money(total)}")
            st.write(f"적용 할인: - **{money(discount_amount)}**")
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
                    
                    process_order_completion(
                        phone_suffix, oid, df_cart, total, final_total, 
                        discount_type, discount_amount 
                    )
                else:
                    st.error(f"주문 알림 이메일 전송에 실패했습니다: {err}. 관리자에게 문의해주세요.")


    # ===== 스탬프 & 주문 내역 (금액 쿠폰/10% 쿠폰 분리) =====
    with tab_history:
        st.header("❤️ 스탬프 & 주문 내역")
        
        # --- 스탬프 현황 ---
        current_stamps = st.session_state.user.get('stamps', 0)
        st.subheader("스탬프 적립 현황")
        
        heart_display = "❤️" * current_stamps + "🤍" * max(0, STAMP_GOAL - current_stamps)
        st.markdown(f"""
            ### 현재 스탬프: {heart_display} ({current_stamps}/{STAMP_GOAL}개)
            다음 리워드까지 **{max(0, STAMP_GOAL - current_stamps)}**개 남았습니다.
            
            **🎁 리워드:** 스탬프 {STAMP_GOAL}개 달성 시 **아메리카노 1잔** ( {money(STAMP_REWARD_AMOUNT)} 금액 쿠폰) 증정!
        """)
        st.markdown("---")

        # --- 쿠폰 잔액 확인 ---
        st.subheader("🎫 현재 쿠폰 잔액")
        amount = st.session_state.user.get('coupon_amount', 0)
        count = st.session_state.user.get('coupon_count', 0)
        st.info(f"**💰 금액 쿠폰:** **{money(amount)}** (스탬프 리워드)\n\n"
                f"**📉 10% 할인 쿠폰:** **{count}개** (신규 가입 혜택, 2만원 이상 구매 시)")
        st.markdown("---")

        # --- 주문 내역 ---
        st.subheader("최근 주문 내역")
        orders = st.session_state.user.get('orders', [])
        
        if not orders:
            st.info("아직 주문 내역이 없습니다. 지금 첫 주문을 완료하고 스탬프를 적립하세요!")
        else:
            for order in orders:
                discount_info = f"할인: - {money(order['discount_amount'])} ({order['discount_type'] if order['discount_type'] else '없음'})"
                
                with st.expander(f"**[{order['date'].split(' ')[0]}]** 주문번호 #{order['id']} | 최종 결제: **{money(order['final_total'])}**", expanded=False):
                    st.markdown(f"**주문 시간:** {order['date']}")
                    st.markdown(f"**총 금액:** {money(order['total'])}")
                    st.markdown(f"**{discount_info}**")
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
