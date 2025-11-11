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
SMTP_PORT = st.secrets.get("SMTP_PORT", 587)
SMTP_SENDER = st.secrets.get("SMTP_SENDER", "your_smtp_user@example.com")
SMTP_PASSWORD = st.secrets.get("SMTP_PASSWORD", "your_smtp_password")

# ----------------- 유틸리티 함수 ------------------
def money(amount):
    """숫자를 원화 형식 문자열로 포맷"""
    return f"{amount:,.0f}원"

def send_email(to_addr, subject, body):
    """이메일 전송 함수 (Streamlit Secrets 필요)"""
    try:
        msg = MIMEText(body, 'html')
        msg['Subject'] = subject
        msg['From'] = SMTP_SENDER
        msg['To'] = to_addr
        msg['Date'] = formatdate(localtime=True)

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_SENDER, SMTP_PASSWORD)
            server.sendmail(SMTP_SENDER, to_addr, msg.as_string())
        return True
    except Exception as e:
        # st.error(f"이메일 전송 실패: {e}") # 개발 모드에서만 표시
        print(f"이메일 전송 실패: {e}")
        return False

def init_session_state():
    """세션 상태 초기화 (사용자, 메뉴, 장바구니 등)"""
    
    # 1. 인증 상태 및 사용자 정보
    if 'auth_status' not in st.session_state:
        st.session_state.auth_status = 'guest' # 'guest', 'logged_in'
    if 'user' not in st.session_state:
        # 더미 사용자 데이터: 실제 앱에서는 DB에서 가져와야 함
        st.session_state.user = {
            'email': 'guest@example.com',
            'nickname': '손님',
            'orders': [],
            'stamps': 0,
            'coupon_amount': 0, # 금액 쿠폰 (스탬프 리워드)
            'coupon_count': WELCOME_DISCOUNT_COUNT # 10% 할인 쿠폰 (신규 가입 혜택)
        }
    
    # 2. 메뉴 데이터 (더미 데이터)
    if 'menu' not in st.session_state:
        st.session_state.menu = pd.DataFrame({
            'id': [1, 2, 3, 4, 5, 6, 7, 8],
            'category': ['빵', '빵', '빵', '케이크', '음료', '음료', '음료', '케이크'],
            'name': ['소금빵', '잠봉 뵈르', '크로와상', '딸기 생크림 케이크', '아메리카노', '카페 라떼', '오렌지 주스', '에그 타르트'],
            'price': [3500, 6500, 4500, 35000, 4000, 5000, 5500, 3000],
            'description': [
                '겉은 바삭, 속은 촉촉한 기본에 충실한 소금빵', 
                '바게트와 햄, 앵커 버터의 완벽한 조화', 
                '프랑스산 밀가루로 만든 풍미 가득한 크로와상', 
                '신선한 딸기가 가득! 기념일 필수 아이템', 
                '고소한 풍미의 시그니처 블렌딩 커피', 
                '깊은 에스프레소와 부드러운 우유의 만남', 
                '100% 착즙 오렌지 주스',
                '부드러운 커스터드와 바삭한 파이'
            ],
            'image_file': ['salt_bread.jpg', 'jambon_beurre.jpg', 'croissant.jpg', 'strawberry_cake.jpg', 'americano.jpg', 'latte.jpg', 'orange_juice.jpg', 'egg_tart.jpg']
        })
    
    # 3. 장바구니
    if 'cart' not in st.session_state:
        st.session_state.cart = []
    
    # 4. 결제 관련 상태
    if 'current_order_total' not in st.session_state:
        st.session_state.current_order_total = 0
    if 'applied_discount' not in st.session_state:
        st.session_state.applied_discount = {'type': None, 'amount': 0}

# ----------------- 인증 및 사용자 관리 ------------------

def login(email, password):
    """로그인 처리 (더미 로직)"""
    # 실제 앱에서는 DB에서 사용자 검증 로직이 필요함
    if email and password:
        st.session_state.auth_status = 'logged_in'
        # 더미 데이터 업데이트
        st.session_state.user['email'] = email
        st.session_state.user['nickname'] = email.split('@')[0]
        st.success(f"{st.session_state.user['nickname']}님, 환영합니다!")
        st.rerun()
    else:
        st.error("이메일과 비밀번호를 입력해주세요.")

def register(email, password, password_confirm):
    """회원가입 처리 (더미 로직)"""
    if not (email and password and password_confirm):
        st.error("모든 필드를 채워주세요.")
        return
    if password != password_confirm:
        st.error("비밀번호 확인이 일치하지 않습니다.")
        return
    
    # 실제 앱에서는 DB에 사용자 정보 저장 및 중복 확인 필요
    st.session_state.auth_status = 'logged_in'
    st.session_state.user = {
        'email': email,
        'nickname': email.split('@')[0],
        'orders': [],
        'stamps': 0,
        'coupon_amount': 0,
        'coupon_count': WELCOME_DISCOUNT_COUNT # 신규 가입 혜택 쿠폰 지급
    }
    st.success(f"회원가입 완료! {WELCOME_DISCOUNT_COUNT}개의 10% 할인 쿠폰이 지급되었습니다.")
    st.rerun()
    
def logout():
    """로그아웃 처리"""
    st.session_state.auth_status = 'guest'
    st.session_state.cart = []
    st.session_state.user = {
        'email': 'guest@example.com',
        'nickname': '손님',
        'orders': [],
        'stamps': 0,
        'coupon_amount': 0,
        'coupon_count': 0
    }
    st.info("로그아웃 되었습니다.")
    st.rerun()

# ----------------- UI 렌더링 함수 ------------------

def render_image(file_name, width=100):
    """Base64 인코딩을 사용하여 로컬 이미지를 렌더링 (Streamlit 실행 환경에 따라 적절한 경로 설정 필요)"""
    try:
        # 실제 환경에서는 이미지를 웹 경로에 올리거나, Streamlit Static File 기능을 사용해야 함
        # 여기서는 더미 이미지를 Base64로 인코딩하여 표시하는 로직을 사용합니다.
        
        # --- Base64 Dummy Image Logic ---
        # 실제 이미지가 아닌, 파일명에 따른 placeholder SVG를 생성합니다.
        # Streamlit 앱을 로컬에서 실행할 경우, 해당 이미지 파일이 같은 디렉토리에 있어야 합니다.
        
        # 간단한 더미 이미지 생성 (SVG)
        text = file_name.split('.')[0].replace('_', ' ').title()
        svg_content = f"""
        <svg width="{width*2}" height="{width}" xmlns="http://www.w3.org/2000/svg">
            <rect width="100%" height="100%" fill="#E0F7FA"/>
            <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="{width*0.1}px" fill="#00796B">{text}</text>
        </svg>
        """
        b64_img = base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')
        return f'<img src="data:image/svg+xml;base64,{b64_img}" style="width:100%; height:auto; border-radius: 8px;"/>'
    except Exception as e:
        # print(f"Error rendering image: {e}") # 개발 모드에서만 표시
        return f'<div style="width:100px; height:100px; background-color: #ccc; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: white;">Image Error</div>'

def add_to_cart(item_id, name, price):
    """장바구니에 아이템 추가"""
    # 이미 장바구니에 있는 항목인지 확인
    for item in st.session_state.cart:
        if item['id'] == item_id:
            item['quantity'] += 1
            st.toast(f"**{name}** 수량이 1개 증가했습니다. (총 {item['quantity']}개)")
            update_order_total()
            return

    # 새로운 항목 추가
    st.session_state.cart.append({'id': item_id, 'name': name, 'price': price, 'quantity': 1})
    st.toast(f"**{name}** 1개가 장바구니에 담겼습니다.")
    update_order_total()

def update_cart_item(index, new_quantity):
    """장바구니 아이템 수량 업데이트"""
    if new_quantity > 0:
        st.session_state.cart[index]['quantity'] = new_quantity
    else:
        del st.session_state.cart[index] # 수량이 0이면 제거

    update_order_total()
    # 장바구니 UI를 다시 그리기 위해 rerun 필요
    st.rerun() 

def update_order_total():
    """장바구니 내용 기반으로 주문 총액 계산 및 할인 적용"""
    total = sum(item['price'] * item['quantity'] for item in st.session_state.cart)
    st.session_state.current_order_total = total
    
    # 할인 초기화
    st.session_state.applied_discount = {'type': None, 'amount': 0}
    
    # 10% 할인 쿠폰 적용 (조건: 2만원 이상, 쿠폰 개수 1개 이상)
    coupon_count = st.session_state.user.get('coupon_count', 0)
    if coupon_count > 0 and total >= MIN_DISCOUNT_PURCHASE:
        discount_amount = int(total * DISCOUNT_RATE)
        st.session_state.applied_discount = {'type': '10% 할인 쿠폰', 'amount': discount_amount}
        return total - discount_amount
    
    # 금액 쿠폰 적용 (금액 쿠폰이 있을 경우)
    coupon_amount = st.session_state.user.get('coupon_amount', 0)
    if coupon_amount > 0:
        # 금액 쿠폰은 10% 쿠폰보다 우선순위가 낮다고 가정하거나, 10% 쿠폰이 적용되지 않을 때만 적용
        if st.session_state.applied_discount['amount'] == 0:
            discount_amount = min(total, coupon_amount) # 총액을 넘지 않도록
            st.session_state.applied_discount = {'type': '금액 쿠폰 (스탬프 리워드)', 'amount': discount_amount}
            return total - discount_amount
        
    return total - st.session_state.applied_discount['amount']

def complete_order():
    """주문 완료 처리"""
    if not st.session_state.cart:
        st.warning("장바구니가 비어있습니다. 상품을 담아주세요.")
        return

    # 총액 계산 및 할인 적용 최종 확인
    total = sum(item['price'] * item['quantity'] for item in st.session_state.cart)
    discount_info = st.session_state.applied_discount
    final_total = update_order_total()

    # 쿠폰 사용 처리 (로그인 상태일 경우만)
    if st.session_state.auth_status == 'logged_in':
        if discount_info['type'] == '10% 할인 쿠폰':
            st.session_state.user['coupon_count'] -= 1
        elif discount_info['type'] == '금액 쿠폰 (스탬프 리워드)':
            st.session_state.user['coupon_amount'] = 0
            
        # 스탬프 적립 (주문 1건당 1개 적립)
        stamps_earned = 1
        st.session_state.user['stamps'] += stamps_earned
        
        # 리워드 확인
        reward_message = ""
        if st.session_state.user['stamps'] >= STAMP_GOAL:
            st.session_state.user['stamps'] -= STAMP_GOAL # 스탬프 차감
            st.session_state.user['coupon_amount'] += STAMP_REWARD_AMOUNT # 금액 쿠폰 지급
            reward_message = f"🎉 **{STAMP_GOAL}개 스탬프 달성!** {money(STAMP_REWARD_AMOUNT)} 금액 쿠폰이 지급되었습니다."

    else:
        # 비로그인 상태는 쿠폰 사용 및 스탬프 적립 불가
        stamps_earned = 0
        reward_message = "로그인하시면 스탬프 적립 및 쿠폰 사용이 가능합니다."

    # 주문 내역 생성
    order_id = str(uuid.uuid4()).split('-')[0].upper()
    order_data = {
        'id': order_id,
        'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'items': st.session_state.cart,
        'total': total,
        'discount_type': discount_info['type'],
        'discount_amount': discount_info['amount'],
        'final_total': final_total,
        'stamps_earned': stamps_earned
    }
    
    # 주문 내역 저장
    if st.session_state.auth_status == 'logged_in':
        st.session_state.user['orders'].append(order_data)

    # 고객에게 주문 확인 메시지 표시
    st.success(f"**주문이 완료되었습니다! (주문번호: #{order_id})**")
    st.info(f"최종 결제 금액: **{money(final_total)}**")
    if reward_message:
        st.markdown(reward_message)

    # 사장님께 이메일 알림 (더미)
    order_items_html = "<ul>"
    for item in st.session_state.cart:
        order_items_html += f"<li>{item['name']} x {item['quantity']} ({money(item['price'])}/개)</li>"
    order_items_html += "</ul>"
    
    email_body = f"""
    <h2>✅ 신규 주문이 접수되었습니다! (주문번호: #{order_id})</h2>
    <p><strong>주문 시간:</strong> {order_data['date']}</p>
    <p><strong>주문 고객:</strong> {st.session_state.user['nickname']} ({st.session_state.user['email']})</p>
    <p><strong>주문 상품:</strong></p>
    {order_items_html}
    <p><strong>총 상품 금액:</strong> {money(total)}</p>
    <p><strong>할인 금액:</strong> - {money(discount_info['amount'])} ({discount_info['type'] if discount_info['type'] else '없음'})</p>
    <p><strong>최종 결제 금액:</strong> <strong>{money(final_total)}</strong></p>
    <p>결제 내역을 확인하고 고객에게 상품을 준비해주세요.</p>
    """
    send_email(OWNER_EMAIL_PRIMARY, f"[{SHOP_NAME}] 신규 주문 접수! (ID: #{order_id})", email_body)

    # 장바구니 비우기
    st.session_state.cart = []
    st.session_state.current_order_total = 0
    st.session_state.applied_discount = {'type': None, 'amount': 0}
    
    # 주문 완료 후 메인 페이지로 이동 (optional: 대신 영수증 화면을 보여줄 수도 있음)
    st.rerun()

def show_auth_form():
    """로그인/회원가입 폼 표시"""
    st.header(SHOP_NAME)
    st.subheader("회원 로그인 / 가입")
    
    auth_tab, reg_tab = st.tabs(["로그인", "회원가입"])
    
    with auth_tab:
        with st.form("login_form"):
            login_email = st.text_input("이메일", key="login_email")
            login_password = st.text_input("비밀번호", type="password", key="login_password")
            submitted = st.form_submit_button("로그인")
            if submitted:
                login(login_email, login_password)

    with reg_tab:
        with st.form("register_form"):
            reg_email = st.text_input("이메일", key="reg_email")
            reg_password = st.text_input("비밀번호 (4자 이상)", type="password", key="reg_password")
            reg_password_confirm = st.text_input("비밀번호 확인", type="password", key="reg_password_confirm")
            reg_submitted = st.form_submit_button("회원가입 및 10% 쿠폰 받기")
            if reg_submitted:
                register(reg_email, reg_password, reg_password_confirm)

def show_header():
    """앱 헤더 (네비게이션 및 인증 상태)"""
    col_logo, col_nav, col_auth = st.columns([1, 2, 1])
    
    with col_logo:
        st.title(SHOP_NAME)
    
    with col_nav:
        nav = st.radio(
            "Navigation", 
            options=["홈", "메뉴", "마이페이지", "AI 추천"], 
            horizontal=True,
            label_visibility="collapsed",
            key='current_page'
        )

    with col_auth:
        if st.session_state.auth_status == 'logged_in':
            st.markdown(f"**{st.session_state.user['nickname']}**님 | {st.session_state.user['stamps']}/{STAMP_GOAL} 스탬프")
            if st.button("로그아웃"):
                logout()
        else:
            if st.button("로그인 / 가입"):
                st.session_state.current_page = "로그인/가입"
    
    st.markdown("<hr/>", unsafe_allow_html=True) # 구분선

def show_main_app():
    """메인 앱 콘텐츠 렌더링"""
    
    show_header()
    
    if st.session_state.current_page == "홈":
        st.header("✨ 따뜻하고 맛있는 빵, 지금 만나보세요!")
        
        # ****************** 오늘의 추천 메뉴 및 이벤트 ******************
        st.subheader("📢 오늘의 혜택 & 추천 메뉴")
        
        # 탭을 유지하되, 각 탭 내부에 expander를 사용하여 내용을 접을 수 있게 함
        tab_event, tab_reco_jam, tab_reco_salt = st.tabs(["🎁 이벤트", "🥪 오늘의 추천: 잠봉 뵈르", "☕ 오늘의 추천: 아메리카노 & 소금빵"])
        
        with tab_event:
            # st.expander를 추가하여 이미지를 접을 수 있게 함 (기본 펼쳐짐)
            with st.expander("이벤트 상세 보기", expanded=True): 
                st.image("event1.jpg", caption="앱 사용 인증샷으로 쿠키도 받고 디저트 세트도 받으세요!", use_column_width=True)
        
        with tab_reco_jam:
            # st.expander를 추가하여 이미지를 접을 수 있게 함 (기본 펼쳐짐)
            with st.expander("잠봉 뵈르 추천 보기", expanded=True):
                st.image("poster2.jpg", caption="오늘의 든든한 점심 추천! 바삭한 바게트에 햄과 버터의 환상적인 조화!", use_column_width=True)
        
        with tab_reco_salt:
            # st.expander를 추가하여 이미지를 접을 수 있게 함 (기본 펼쳐짐)
            with st.expander("소금빵 세트 추천 보기", expanded=True):
                st.image("poster1.jpg", caption="국민 조합! 짭짤 고소한 소금빵과 시원한 아메리카노 세트!", use_column_width=True)
        
        st.markdown("---")
        # *************************************************************************

        st.subheader("🔥 인기 메뉴")
        
        # 인기 메뉴 4개만 표시 (더미)
        top_items = st.session_state.menu.iloc[[0, 1, 3, 4]]
        cols = st.columns(4)
        
        for i, item in top_items.iterrows():
            with cols[i]:
                st.markdown(render_image(item['image_file'], width=150), unsafe_allow_html=True)
                st.markdown(f"**{item['name']}**")
                st.markdown(f"💰 {money(item['price'])}")
                if st.button("장바구니", key=f"home_add_{item['id']}"):
                    add_to_cart(item['id'], item['name'], item['price'])
                    
    elif st.session_state.current_page == "메뉴":
        show_menu()
        
    elif st.session_state.current_page == "마이페이지":
        show_mypage()
        
    elif st.session_state.current_page == "AI 추천":
        show_ai_recommendation()
        
    elif st.session_state.current_page == "로그인/가입":
        show_auth_form()
    
    # 모든 페이지 하단에 장바구니 위젯 표시
    show_cart_widget()

def show_menu():
    """전체 메뉴 페이지"""
    st.header("📋 전체 메뉴")
    
    # 카테고리 필터
    categories = ['전체'] + st.session_state.menu['category'].unique().tolist()
    selected_category = st.selectbox("카테고리 선택", categories, index=0)

    # 필터링
    if selected_category == '전체':
        filtered_menu = st.session_state.menu
    else:
        filtered_menu = st.session_state.menu[st.session_state.menu['category'] == selected_category]
    
    # 메뉴 표시
    cols_per_row = 4
    num_items = len(filtered_menu)
    
    for i in range(0, num_items, cols_per_row):
        cols = st.columns(cols_per_row)
        for j in range(cols_per_row):
            item_index = i + j
            if item_index < num_items:
                item = filtered_menu.iloc[item_index]
                with cols[j]:
                    st.markdown(render_image(item['image_file'], width=150), unsafe_allow_html=True)
                    st.markdown(f"**{item['name']}**")
                    st.markdown(f"💰 {money(item['price'])}")
                    st.caption(item['description'])
                    if st.button("장바구니 담기", key=f"menu_add_{item['id']}"):
                        add_to_cart(item['id'], item['name'], item['price'])

def show_mypage():
    """마이페이지 (스탬프, 쿠폰, 주문 내역)"""
    if st.session_state.auth_status != 'logged_in':
        st.warning("로그인 후 이용 가능한 페이지입니다.")
        st.session_state.current_page = "로그인/가입"
        st.rerun()
        return

    st.header(f"👋 {st.session_state.user['nickname']}님의 마이페이지")
    
    tab_status, tab_history = st.tabs(["내 정보/리워드", "주문 내역"])
    
    with tab_status:
        # --- 스탬프 현황 ---
        st.subheader("☕ 스탬프 현황")
        current_stamps = st.session_state.user.get('stamps', 0)
        
        st.markdown(f"현재 스탬프: **{current_stamps} / {STAMP_GOAL}개**")
        st.progress(current_stamps / STAMP_GOAL)
        st.info(f"스탬프 **{STAMP_GOAL}개** 달성 시, {money(STAMP_REWARD_AMOUNT)} 금액 쿠폰이 지급됩니다.")
        st.markdown("---")

        # --- 쿠폰 현황 ---
        st.subheader("🎁 쿠폰함")
        amount = st.session_state.user.get('coupon_amount', 0)
        count = st.session_state.user.get('coupon_count', 0)
        
        st.info(f"**💰 금액 쿠폰:** **{money(amount)}** (스탬프 리워드)\n\n"
                f"**📉 10% 할인 쿠폰:** **{count}개** (신규 가입 혜택, {money(MIN_DISCOUNT_PURCHASE)} 이상 구매 시)")
        st.markdown("---")

        # --- 사용자 정보 ---
        st.subheader("사용자 정보")
        st.markdown(f"**이메일:** {st.session_state.user['email']}")
        st.markdown(f"**닉네임:** {st.session_state.user['nickname']}")
        
    with tab_history:
        # --- 주문 내역 --
        st.subheader("최근 주문 내역")
        orders = st.session_state.user.get('orders', [])
        
        if not orders:
            st.info("아직 주문 내역이 없습니다. 지금 첫 주문을 완료하고 스탬프를 적립하세요!")
        else:
            # 최신 주문부터 표시
            for order in reversed(orders):
                discount_info = f"할인: - {money(order['discount_amount'])} ({order['discount_type'] if order['discount_type'] else '없음'})"
                
                with st.expander(f"**[{order['date'].split(' ')[0]}]** 주문번호 #{order['id']} | 최종 결제: **{money(order['final_total'])}**", expanded=False):
                    st.markdown(f"**주문 시간:** {order['date']}")
                    
                    st.markdown("**주문 상품:**")
                    item_list = ""
                    for item in order['items']:
                        item_list += f"- {item['name']} x {item['quantity']} ({money(item['price'])}/개)\n"
                    st.markdown(item_list)
                    
                    st.markdown("---")
                    st.markdown(f"**총 상품 금액:** {money(order['total'])}")
                    st.markdown(f"**{discount_info}**")
                    st.markdown(f"**적립 스탬프:** {order['stamps_earned']}개")
                    st.markdown(f"**최종 결제 금액:** **{money(order['final_total'])}**")

def show_ai_recommendation():
    """AI 추천 페이지 (더미 로직)"""
    st.header("🤖 AI 맞춤 추천")
    st.info("고객님의 구매 패턴과 현재 날씨를 기반으로 최적의 빵과 음료 조합을 추천해 드립니다.")

    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("오늘의 날씨 기반 추천")
        st.markdown("현재 날씨: 맑음 (25°C)")
        st.success("🌞 날씨가 좋으니 시원한 음료와 가벼운 디저트가 어떨까요?")
        
        # 추천 메뉴 (더미)
        reco_items = st.session_state.menu.iloc[[4, 7]] # 아메리카노, 에그타르트
        
        st.markdown("---")
        for item in reco_items.itertuples():
            st.markdown(f"**{item.name}** ({money(item.price)})")
            st.caption(item.description)
            if st.button(f"'{item.name}' 장바구니 담기", key=f"ai_add_{item.id}"):
                add_to_cart(item.id, item.name, item.price)

    with col2:
        st.subheader("구매 기록 기반 추천")
        if st.session_state.auth_status == 'logged_in':
            st.warning(f"고객님은 주로 '{st.session_state.menu.iloc[1]['name']}'와 '{st.session_state.menu.iloc[5]['name']}'를 구매하셨습니다.")
            st.info("이번에는 **'크로와상'**에 도전해보세요!")
            
            reco_item = st.session_state.menu.iloc[2] # 크로와상
            st.markdown("---")
            st.markdown(f"**{reco_item['name']}** ({money(reco_item['price'])})")
            st.caption(reco_item['description'])
            if st.button(f"'{reco_item['name']}' 장바구니 담기", key=f"ai_add_2_{reco_item['id']}"):
                add_to_cart(reco_item['id'], reco_item['name'], reco_item['price'])
        else:
            st.info("로그인하시면 더 정교한 맞춤 추천을 받을 수 있습니다.")

def show_cart_widget():
    """장바구니 위젯 (사이드바)"""
    with st.sidebar:
        st.header("🛒 장바구니")
        
        if not st.session_state.cart:
            st.info("장바구니가 비어 있습니다.")
            return

        # 장바구니 항목 표시
        cart_total = st.session_state.current_order_total
        final_total = update_order_total()
        discount_info = st.session_state.applied_discount
        
        for index, item in enumerate(st.session_state.cart):
            col_name, col_qty, col_price = st.columns([3, 2, 2])
            with col_name:
                st.markdown(f"**{item['name']}**")
            with col_qty:
                # 수량 조절용 넘버 인풋
                new_qty = st.number_input(
                    "수량", 
                    min_value=0, 
                    value=item['quantity'], 
                    key=f"qty_{item['id']}_{index}",
                    label_visibility="collapsed",
                    on_change=update_cart_item,
                    args=(index, ) # on_change에 전달할 인자 (index만 필요)
                )
                if new_qty != item['quantity'] and new_qty >= 0:
                     update_cart_item(index, new_qty)
                     
            with col_price:
                st.markdown(f"{money(item['price'] * item['quantity'])}")
                
        st.markdown("---")
        
        st.markdown(f"**총 상품 금액:** {money(cart_total)}")
        
        if discount_info['amount'] > 0:
            st.success(f"**할인 적용:** - {money(discount_info['amount'])} ({discount_info['type']})")
        
        st.markdown(f"**최종 결제 금액:** **{money(final_total)}**")
        
        if st.session_state.auth_status == 'logged_in':
            st.caption(f"10% 할인 쿠폰: {st.session_state.user.get('coupon_count', 0)}개 보유 ({money(MIN_DISCOUNT_PURCHASE)} 이상 구매 시 자동 적용)")
            st.caption(f"금액 쿠폰: {money(st.session_state.user.get('coupon_amount', 0))} 보유")
        else:
            st.caption("로그인하시면 쿠폰 사용 및 스탬프 적립이 가능합니다.")
            
        if st.button("결제하기", use_container_width=True, type="primary"):
            complete_order()

# ----------------- 메인 실행 ------------------
if __name__ == "__main__":
    init_session_state()
    
    # 탭 네비게이션을 위해 초기 페이지 설정
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "홈"
    
    show_main_app()
