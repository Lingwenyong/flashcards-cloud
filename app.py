
import json
import re
from io import BytesIO

import requests
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from pypdf import PdfReader

st.set_page_config(
    page_title="Flashcards",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

upload_cards_component = components.declare_component(
    "upload_cards",
    path="components/upload_cards",
)
deck_grid_component = components.declare_component(
    "deck_grid",
    path="components/deck_grid",
)
study_component = components.declare_component(
    "study_component",
    path="components/study",
)

# -----------------------
# Session state
# -----------------------
defaults = {
    "screen": "home",
    "access_token": None,
    "refresh_token": None,
    "user": None,
    "active_deck": None,
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# -----------------------
# Styling
# -----------------------
st.markdown("""
<style>
[data-testid="stSidebar"] {display:none;}
#MainMenu, footer {visibility:hidden;}
[data-testid="stHeader"] {background:transparent;}
.block-container {
    max-width: 1100px;
    padding-top: 1.4rem;
    padding-bottom: 2rem;
}
.title {
    font-size:2.2rem;
    font-weight:740;
    letter-spacing:-.045em;
    text-align:center;
}
.subtitle {
    text-align:center;
    color:#777;
    font-size:1rem;
    margin-top:.2rem;
    margin-bottom:1.8rem;
}
.account-line {
    color:#777;
    font-size:.9rem;
    text-align:right;
}
div[data-testid="stFileUploader"] {
    max-width:760px;
    margin:0 auto;
}
div[data-testid="stFileUploaderDropzone"] {
    border-radius:18px;
    border:1.5px dashed #cfcfcf;
    padding:18px;
    background:#fcfcfc;
}
div[data-testid="stButton"] > button {
    border-radius:12px;
}
.login-box {
    max-width:460px;
    margin:60px auto 0 auto;
}
</style>
""", unsafe_allow_html=True)

# -----------------------
# Secrets / configuration
# -----------------------
def secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return None

SUPABASE_URL = secret("SUPABASE_URL")
SUPABASE_ANON_KEY = secret("SUPABASE_ANON_KEY")
OPENAI_API_KEY = secret("OPENAI_API_KEY")

def configuration_ready():
    return all([SUPABASE_URL, SUPABASE_ANON_KEY, OPENAI_API_KEY])

# -----------------------
# Supabase helpers
# -----------------------
def auth_headers(token=None):
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def signup(email, password):
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/signup",
        headers=auth_headers(),
        json={"email": email, "password": password},
        timeout=30,
    )
    data = r.json() if r.content else {}
    if not r.ok:
        raise RuntimeError(data.get("msg") or data.get("error_description") or data.get("message") or r.text)
    return data

def signin(email, password):
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers=auth_headers(),
        json={"email": email, "password": password},
        timeout=30,
    )
    data = r.json() if r.content else {}
    if not r.ok:
        raise RuntimeError(data.get("error_description") or data.get("msg") or data.get("message") or r.text)
    return data

def refresh_session():
    token = st.session_state.refresh_token
    if not token:
        return False
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
        headers=auth_headers(),
        json={"refresh_token": token},
        timeout=30,
    )
    if not r.ok:
        return False
    data = r.json()
    st.session_state.access_token = data.get("access_token")
    st.session_state.refresh_token = data.get("refresh_token")
    st.session_state.user = data.get("user")
    return True

def db_request(method, endpoint, *, params=None, payload=None, retry=True):
    token = st.session_state.access_token
    r = requests.request(
        method,
        f"{SUPABASE_URL}/rest/v1/{endpoint}",
        headers={
            **auth_headers(token),
            "Prefer": "return=representation",
        },
        params=params,
        json=payload,
        timeout=30,
    )
    if r.status_code == 401 and retry and refresh_session():
        return db_request(method, endpoint, params=params, payload=payload, retry=False)
    if not r.ok:
        try:
            message = r.json().get("message") or r.json().get("hint") or r.text
        except Exception:
            message = r.text
        raise RuntimeError(message)
    return r.json() if r.content else None

def load_decks():
    return db_request(
        "GET",
        "decks",
        params={
            "select": "id,name,source_files,cards,created_at,last_index",
            "order": "created_at.desc",
        },
    ) or []

def create_deck(name, source_files, cards):
    user_id = st.session_state.user["id"]
    result = db_request(
        "POST",
        "decks",
        payload={
            "user_id": user_id,
            "name": name,
            "source_files": source_files,
            "cards": cards,
            "last_index": 0,
        },
    )
    return result[0] if result else None

def delete_deck(deck_id):
    db_request(
        "DELETE",
        "decks",
        params={"id": f"eq.{deck_id}"},
    )

def save_position(deck_id, index):
    db_request(
        "PATCH",
        "decks",
        params={"id": f"eq.{deck_id}"},
        payload={"last_index": int(index)},
    )

# -----------------------
# Flashcard helpers
# -----------------------
def extract_uploaded_pdf(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.getvalue()))
    parts = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if text.strip():
            parts.append(f"\n--- {uploaded_file.name} / PAGE {i} ---\n{text}")
    return "\n".join(parts)

def clean_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    left, right = text.find("["), text.rfind("]")
    if left >= 0 and right >= left:
        text = text[left:right + 1]
    return json.loads(text)

def build_prompt(source, count, exam, studies, debates):
    return f"""
Create approximately {count} revision flashcards from ALL uploaded notes.

Rules:
- Cover important examinable content throughout all uploaded files.
- Do not invent information.
- One clear idea per card.
- Keep answers concise but complete.
- Avoid duplicates and near-duplicates.
- Preserve technical terminology, definitions, procedures, results, treatments, numbers and distinctions.
- {"Use exam-focused wording." if exam else "Use clear general revision wording."}
- {"Include named/example studies where relevant." if studies else "Do NOT make flashcards about named/example studies unless essential to a core concept."}
- {"Include issues and debates." if debates else "Do NOT make flashcards about issues and debates."}
- For psychology, prioritise definitions, explanations, symptoms/features, causes, treatments, procedures,
  results, strengths/weaknesses and important distinctions.
- Never say "according to the notes" or "according to the PDF".

Return ONLY valid JSON:
[
  {{
    "question":"Question",
    "answer":"Answer",
    "topic":"Short topic"
  }}
]

NOTES:
{source}
"""

# -----------------------
# Missing configuration
# -----------------------
if not configuration_ready():
    st.markdown('<div class="title">Flashcards</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitle">One-time cloud setup is required before this version can run.</div>',
        unsafe_allow_html=True,
    )
    st.error("Cloud settings are missing.")
    st.markdown(
        """
Add these three secrets in Streamlit Cloud:

- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

The included **SETUP.md** walks you through the exact setup.
"""
    )
    st.stop()

# -----------------------
# Login / sign-up screen
# -----------------------
if not st.session_state.user:
    st.markdown('<div class="title">Flashcards</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitle">Your decks, available on all your devices.</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    login_tab, signup_tab = st.tabs(["Sign in", "Create account"])

    with login_tab:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Sign in", type="primary", use_container_width=True):
            try:
                data = signin(email.strip(), password)
                st.session_state.access_token = data.get("access_token")
                st.session_state.refresh_token = data.get("refresh_token")
                st.session_state.user = data.get("user")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    with signup_tab:
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Create account", type="primary", use_container_width=True):
            try:
                data = signup(new_email.strip(), new_password)
                if data.get("access_token"):
                    st.session_state.access_token = data.get("access_token")
                    st.session_state.refresh_token = data.get("refresh_token")
                    st.session_state.user = data.get("user")
                    st.rerun()
                else:
                    st.success("Account created. Check your email to confirm it, then sign in.")
            except Exception as e:
                st.error(str(e))
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# -----------------------
# Home
# -----------------------
if st.session_state.screen == "home":
    st.markdown('<div class="title">Flashcards</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitle">Add your notes, generate a deck, and study anywhere.</div>',
        unsafe_allow_html=True,
    )

    l, r = st.columns([4, 1], vertical_alignment="center")
    with r:
        st.markdown(
            f'<div class="account-line">{st.session_state.user.get("email","")}</div>',
            unsafe_allow_html=True,
        )
        if st.button("Sign out", use_container_width=True):
            for key in ["access_token", "refresh_token", "user", "active_deck"]:
                st.session_state[key] = None
            st.rerun()

    uploads = st.file_uploader(
        "Add PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploads:
        upload_cards_component(
            files=[{"name": f.name, "size": len(f.getvalue())} for f in uploads],
            key="uploaded_cards_view",
        )

        with st.container(border=True):
            st.subheader("Create flashcards")
            c1, c2 = st.columns([2, 3])
            with c1:
                card_count = st.select_slider(
                    "Number of cards",
                    options=[20, 40, 60, 80, 100, 120],
                    value=60,
                )
            with c2:
                exam = st.toggle("Exam focused", value=True)
                studies = st.toggle("Example studies", value=False)
                debates = st.toggle("Issues & debates", value=False)

            if st.button("Generate Flashcards  →", type="primary", use_container_width=True):
                try:
                    with st.status("Creating your flashcards…", expanded=False) as status:
                        status.write("Reading your notes")
                        source = "\n".join(extract_uploaded_pdf(f) for f in uploads)
                        if len(source.strip()) < 100:
                            raise ValueError("The uploaded PDF has little or no selectable text.")

                        status.write("Writing flashcards")
                        client = OpenAI(api_key=OPENAI_API_KEY)
                        response = client.responses.create(
                            model="gpt-5-mini",
                            input=build_prompt(
                                source[:260000],
                                card_count,
                                exam,
                                studies,
                                debates,
                            ),
                        )
                        raw = clean_json(response.output_text)
                        cards = [
                            {
                                "question": str(c["question"]).strip(),
                                "answer": str(c["answer"]).strip(),
                                "topic": str(c.get("topic", "")).strip(),
                            }
                            for c in raw
                            if isinstance(c, dict)
                            and str(c.get("question", "")).strip()
                            and str(c.get("answer", "")).strip()
                        ]
                        if not cards:
                            raise ValueError("No usable flashcards were generated.")

                        base = re.sub(r"\.pdf$", "", uploads[0].name, flags=re.I)
                        deck_name = (
                            f"{base} Flashcards"
                            if len(uploads) == 1
                            else "Combined Notes Flashcards"
                        )
                        deck = create_deck(
                            deck_name,
                            [f.name for f in uploads],
                            cards,
                        )
                        status.update(label=f"{len(cards)} cards saved", state="complete")
                        st.session_state.active_deck = deck
                        st.session_state.screen = "study"
                        st.rerun()
                except Exception as e:
                    st.error("Flashcard generation failed.")
                    st.code(str(e))

    try:
        decks = load_decks()
    except Exception as e:
        st.error(f"Could not load your saved decks: {e}")
        decks = []

    if decks:
        st.write("")
        st.subheader("Your flashcard decks")

        deck_action = deck_grid_component(
            decks=[
                {
                    "id": d["id"],
                    "name": d["name"],
                    "count": len(d.get("cards", [])),
                }
                for d in decks
            ],
            key="cloud_deck_grid",
            default=None,
        )

        if isinstance(deck_action, dict):
            action = deck_action.get("action")
            deck_id = deck_action.get("id")
            selected = next((d for d in decks if d["id"] == deck_id), None)

            if action == "study" and selected:
                st.session_state.active_deck = selected
                st.session_state.screen = "study"
                st.rerun()

            elif action == "delete" and selected:
                try:
                    delete_deck(deck_id)
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not delete this deck: {e}")

# -----------------------
# Study
# -----------------------
elif st.session_state.screen == "study":
    deck = st.session_state.active_deck

    if not deck:
        st.session_state.screen = "home"
        st.rerun()

    result = study_component(
        deck_name=deck.get("name", "Flashcards"),
        cards=deck.get("cards", []),
        start_index=int(deck.get("last_index") or 0),
        key=f"study_{deck['id']}",
        default=None,
    )

    if isinstance(result, dict) and result.get("action") == "back":
        try:
            index = int(result.get("index") or 0)
            save_position(deck["id"], index)
        except Exception:
            pass
        st.session_state.active_deck = None
        st.session_state.screen = "home"
        st.rerun()
