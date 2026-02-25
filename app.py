import streamlit as st
import fitz  # PyMuPDF
import base64
import json
import io
import os
from PIL import Image
from openai import OpenAI
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# ==========================================
# 1. 전역 설정 및 세션 초기화
# ==========================================
st.set_page_config(page_title="전문 용어 퀴즈 마스터", page_icon="📖", layout="centered")

def init_session_state():
    defaults = {
        "quiz_data": [],
        "current_index": 0,
        "score": 0,
        "wrong_answers": [],
        "quiz_started": False,
        "submitted": False,
        "last_is_correct": None  # 최신 제출의 정답 여부 저장
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

default_key = os.getenv("OPENAI_API_KEY", "").strip()
api_key = st.sidebar.text_input("OpenAI API Key", value=default_key, type="password", key="openai_api_key_sidebar").strip()
client = OpenAI(api_key=api_key) if api_key else None

# ==========================================
# 2. 유틸리티 및 AI 함수
# ==========================================
def encode_image(image_bytes):
    return base64.b64encode(image_bytes).decode('utf-8')

def process_uploaded_file(uploaded_file):
    image_list = []
    try:
        uploaded_file.seek(0)
        content = uploaded_file.read()
        if "pdf" in uploaded_file.type:
            doc = fitz.open(stream=content, filetype="pdf")
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                image_list.append(io.BytesIO(pix.tobytes("png")).getvalue())
        else:
            image_list.append(content)
        return image_list
    except Exception as e:
        st.error(f"파일 처리 오류: {e}")
        return []

def parse_vocabulary_with_ai(images):
    if not client: return None
    prompt = (
        "이미지 내의 표에서 약어(abbr), 영문 풀네임(full_name), 한국어 뜻(meaning)을 추출해. "
        "반드시 JSON 객체 형식으로 응답해. 예: {\"data\": [{\"abbr\": \"...\", \"full_name\": \"...\", \"meaning\": \"...\"}]}"
    )
    content = [{"type": "text", "text": prompt}]
    for img in images:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image(img)}"}})
    try:
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": content}], response_format={"type": "json_object"})
        data = json.loads(response.choices[0].message.content)
        return data.get("data", []) if isinstance(data, dict) else data
    except Exception as e:
        st.error(f"AI 분석 오류: {e}")
        return None

# ==========================================
# 3. 메인 UI 및 퀴즈 로직
# ==========================================
st.title("🚢 전문 용어 주관식 퀴즈")

if not st.session_state.quiz_started:
    st.info("💡 PDF 또는 이미지 단어장을 업로드해 주세요.")
    uploaded_file = st.file_uploader("파일 업로드", type=["pdf", "jpg", "png"])
    if uploaded_file and st.button("🚀 퀴즈 시작", use_container_width=True):
        with st.spinner("분석 중..."):
            images = process_uploaded_file(uploaded_file)
            data = parse_vocabulary_with_ai(images)
            if data:
                st.session_state.quiz_data = data
                st.session_state.quiz_started = True
                st.rerun()

elif st.session_state.current_index < len(st.session_state.quiz_data):
    curr_idx = st.session_state.current_index
    curr_q = st.session_state.quiz_data[curr_idx]
    
    st.progress((curr_idx) / len(st.session_state.quiz_data))
    st.subheader(f"문제 {curr_idx + 1} / {len(st.session_state.quiz_data)}")
    st.markdown(f"<div style='background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center; font-size: 30px; font-weight: bold;'>{curr_q.get('abbr', '')}</div>", unsafe_allow_html=True)
    
    # 입력창
    user_answer = st.text_input("영문 풀네임과 뜻을 모두 입력하세요 (예: Full Name 뜻)", key=f"q_{curr_idx}", disabled=st.session_state.submitted).strip()
    
    # ------------------------------------------
    # 제출 및 다음 버튼 로직
    # ------------------------------------------
    if not st.session_state.submitted:
        if st.button("✅ 정답 제출", use_container_width=True):
            if user_answer:
                st.session_state.submitted = True
                correct_full_name = curr_q.get('full_name', '').strip()
                correct_meaning = curr_q.get('meaning', '').strip()
                
                # 공백을 제거하고 대소문자를 무시하여 비교 (유연한 채점)
                def clean(text):
                    return "".join(text.split()).lower()

                user_clean = clean(user_answer)
                full_clean = clean(correct_full_name)
                meaning_clean = clean(correct_meaning)

                # 영문 풀네임과 한글 뜻이 모두 사용자 입력에 포함되어 있는지 확인
                if full_clean in user_clean and meaning_clean in user_clean:
                    st.session_state.last_is_correct = True
                    st.session_state.score += 1
                else:
                    st.session_state.last_is_correct = False
                    st.session_state.wrong_answers.append({
                        "약어": curr_q.get('abbr', ''),
                        "내 답": user_answer,
                        "정답": f"{correct_full_name} ({correct_meaning})",
                        "의미": correct_meaning
                    })
                st.rerun()
            else:
                st.warning("답을 입력해 주세요.")
    else:
        # 피드백 표시 (제출 후에만 보임)
        if st.session_state.last_is_correct:
            st.success(f"🎯 정답입니다! | 뜻: {curr_q.get('meaning', '')}")
        else:
            st.error(f"😰 틀렸습니다! | 정답: {curr_q.get('full_name', '')}")
            st.info(f"의미: {curr_q.get('meaning', '')}")
        
        if st.button("다음 문제로 ➡️", use_container_width=True):
            st.session_state.current_index += 1
            st.session_state.submitted = False
            st.session_state.last_is_correct = None
            st.rerun()

    # ------------------------------------------
    # 실시간 오답 노트 (화면 하단)
    # ------------------------------------------
    if st.session_state.wrong_answers:
        st.divider()
        st.subheader("⚠️ 실시간 오답 노트")
        st.dataframe(st.session_state.wrong_answers, use_container_width=True, hide_index=True)

else:
    # 최종 결과
    st.balloons()
    st.header("🏁 퀴즈 종료!")
    st.metric("최종 점수", f"{st.session_state.score} / {len(st.session_state.quiz_data)}")
    if st.session_state.wrong_answers:
        st.subheader("📚 전체 오답 리스트")
        st.table(st.session_state.wrong_answers)
    if st.button("처음으로 돌아가기", use_container_width=True):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

st.markdown("<style>footer {visibility: hidden;}</style>", unsafe_allow_html=True)
