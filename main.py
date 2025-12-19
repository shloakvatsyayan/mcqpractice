import json
import random
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple
import streamlit as st

# Note that this is very rushed code for a specific purpose, might not work for everyone.

SETS_DIR = Path(__file__).parent / "sets"
REFRESH_INTERVAL_SEC = 2

st.set_page_config(page_title="MCQ Practice", layout="centered")

def _rerun():
    try:
        st.rerun()
    except AttributeError:
        st.rerun()


def sets_signature() -> str:
    if not SETS_DIR.exists():
        return "MISSING_DIR"

    parts = []
    for f in sorted(SETS_DIR.glob("*.json")):
        try:
            stat = f.stat()
            parts.append(f"{f.name}:{stat.st_mtime_ns}:{stat.st_size}")
        except OSError:
            continue
    return "|".join(parts) if parts else "EMPTY_DIR"


@st.cache_data(show_spinner=False)
def load_sets(_signature: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    sets_by_name: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []

    if not SETS_DIR.exists():
        errors.append(f"Missing folder: {SETS_DIR}")
        return sets_by_name, errors

    for file in sorted(SETS_DIR.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"{file.name}: invalid JSON ({e})")
            continue

        set_name = data.get("set_name")
        questions = data.get("questions")
        if not isinstance(set_name, str) or not set_name.strip():
            errors.append(f"{file.name}: missing/invalid 'set_name'")
            continue
        if not isinstance(questions, list) or len(questions) == 0:
            errors.append(f"{file.name}: missing/invalid 'questions' (must be a non-empty list)")
            continue

        ok = True
        for qi, q in enumerate(questions):
            if not isinstance(q, dict):
                errors.append(f"{file.name}: question #{qi+1} is not an object")
                ok = False
                break
            if not isinstance(q.get("question"), str) or not q["question"].strip():
                errors.append(f"{file.name}: question #{qi+1} missing/invalid 'question'")
                ok = False
                break
            opts = q.get("options")
            if not isinstance(opts, list) or len(opts) < 2 or not all(isinstance(x, str) for x in opts):
                errors.append(f"{file.name}: question #{qi+1} missing/invalid 'options' (need 2+ strings)")
                ok = False
                break
            ca = q.get("correct_answer")
            if not isinstance(ca, str) or ca not in opts:
                errors.append(f"{file.name}: question #{qi+1} 'correct_answer' must match one of the options")
                ok = False
                break

        if not ok:
            continue

        if set_name in sets_by_name:
            errors.append(f"{file.name}: duplicate set_name '{set_name}' (overwriting previous)")
        data["_source_file"] = file.name
        sets_by_name[set_name] = data

    return sets_by_name, errors


def init_state():
    st.session_state.setdefault("selected_set_name", None)
    st.session_state.setdefault("quiz_set_id", None)
    st.session_state.setdefault("order", [])
    st.session_state.setdefault("pos", 0)
    st.session_state.setdefault("finished", False)
    st.session_state.setdefault("answers", {})
    st.session_state.setdefault("checked", {})  # Track which questions have been checked (for instant mode)
    st.session_state.setdefault("last_poll", 0.0)
    st.session_state.setdefault("last_sig", "")
    st.session_state.setdefault("feedback_mode", "instant")


def start_quiz_for_set(set_data: Dict[str, Any], randomize: bool = True):
    questions = set_data["questions"]
    set_id = set_data.get("set_id") or set_data.get("set_name") or "set"

    st.session_state.quiz_set_id = str(set_id)
    order = list(range(len(questions)))
    if randomize:
        random.shuffle(order)
    st.session_state.order = order
    st.session_state.pos = 0
    st.session_state.finished = False
    st.session_state.answers = {}
    st.session_state.checked = {}


def current_question_index() -> int:
    return st.session_state.order[st.session_state.pos]


def answer_key(set_id: str, q_index: int) -> str:
    return f"choice__{set_id}__{q_index}"


def maybe_poll_and_refresh(current_sig: str, quiz_active: bool):
    now = time.time()
    if quiz_active:
        st.session_state.last_sig = current_sig
        st.session_state.last_poll = now
        return

    if now - st.session_state.last_poll < REFRESH_INTERVAL_SEC:
        return

    st.session_state.last_poll = now
    if st.session_state.last_sig and st.session_state.last_sig != current_sig:
        st.session_state.last_sig = current_sig
        _rerun()
    else:
        st.session_state.last_sig = current_sig


init_state()

sig = sets_signature()
sets_by_name, validation_errors = load_sets(sig)

quiz_active = bool(st.session_state.quiz_set_id) and not st.session_state.finished
maybe_poll_and_refresh(sig, quiz_active=quiz_active)

st.sidebar.title("MCQ Practice")

if validation_errors:
    with st.sidebar.expander("Set validation warnings", expanded=False):
        for e in validation_errors:
            st.warning(e)

if not sets_by_name:
    st.sidebar.error("No valid question sets found. Put JSON files in the /sets folder.")
    st.stop()

set_names_sorted = sorted(sets_by_name.keys(), key=lambda s: s.lower())

selected = st.sidebar.selectbox(
    "Choose a question set",
    options=set_names_sorted,
    index=set_names_sorted.index(st.session_state.selected_set_name)
    if st.session_state.selected_set_name in set_names_sorted else 0,
)

if selected != st.session_state.selected_set_name:
    st.session_state.selected_set_name = selected
    # Randomize only for instant mode
    randomize = st.session_state.feedback_mode == "instant"
    start_quiz_for_set(sets_by_name[selected], randomize=randomize)
    _rerun()

set_data = sets_by_name[st.session_state.selected_set_name]
questions = set_data["questions"]
set_id = str(set_data.get("set_id") or set_data["set_name"])

st.sidebar.caption(f"Source: {set_data.get('_source_file', 'unknown')}")
st.sidebar.write(f"Questions: **{len(questions)}**")

feedback_mode = st.sidebar.radio(
    "Feedback mode",
    options=["instant", "long_test"],
    index=0 if st.session_state.feedback_mode == "instant" else 1,
    format_func=lambda x: "Instant feedback" if x == "instant" else "Long test (feedback at end)",
    help="Instant feedback shows results immediately. Long test shows all results at the end."
)

if feedback_mode != st.session_state.feedback_mode:
    st.session_state.feedback_mode = feedback_mode
    # Restart quiz when mode changes
    randomize = feedback_mode == "instant"
    start_quiz_for_set(set_data, randomize=randomize)
    _rerun()

if st.sidebar.button("Restart quiz", use_container_width=True):
    # Randomize for instant mode, keep order for long test mode
    randomize = st.session_state.feedback_mode == "instant"
    start_quiz_for_set(set_data, randomize=randomize)
    _rerun()

st.title(set_data["set_name"])
desc = set_data.get("description", "")
if desc:
    st.caption(desc)

if st.session_state.finished or st.session_state.pos >= len(st.session_state.order):
    st.session_state.finished = True

    score = 0
    correct_answers = []
    incorrect_answers = []
    
    for i, q in enumerate(questions):
        user_answer = st.session_state.answers.get(i)
        is_correct = user_answer == q["correct_answer"]
        if is_correct:
            score += 1
            correct_answers.append((i, q, user_answer))
        else:
            incorrect_answers.append((i, q, user_answer))

    st.subheader("Quiz complete")
    st.metric("Score", f"{score} / {len(questions)}")

    st.progress(score / max(1, len(questions)))

    # Add custom CSS for color coding
    st.markdown("""
    <style>
    div[data-testid="stExpander"]:has(> div > div > div > div:contains("✅")) {
        border-left: 5px solid #00cc00;
    }
    div[data-testid="stExpander"]:has(> div > div > div > div:contains("❌")) {
        border-left: 5px solid #ff0000;
    }
    </style>
    """, unsafe_allow_html=True)

    # Separate correct and incorrect answers into collapsibles with color coding
    with st.expander(f"✅ Correct Answers ({len(correct_answers)})", expanded=True):
        if correct_answers:
            for i, q, user_answer in correct_answers:
                st.markdown(f"**Q{i+1}. {q['question']}**")
                st.markdown(f"Your answer: **{user_answer}**")
                st.markdown(f"Correct answer: **{q['correct_answer']}**")
                st.divider()
        else:
            st.write("No correct answers.")
    
    with st.expander(f"❌ Incorrect Answers ({len(incorrect_answers)})", expanded=True):
        if incorrect_answers:
            for i, q, user_answer in incorrect_answers:
                st.markdown(f"**Q{i+1}. {q['question']}**")
                st.markdown(f"Your answer: {user_answer if user_answer else 'Not answered'}")
                st.markdown(f"Correct answer: **{q['correct_answer']}**")
                st.divider()
        else:
            st.write("No incorrect answers. Great job!")

    st.stop()

q_idx = current_question_index()
q = questions[q_idx]

answered_count = len(st.session_state.answers)
st.progress(st.session_state.pos / max(1, len(st.session_state.order)))

st.markdown(f"### Question {st.session_state.pos + 1} of {len(st.session_state.order)}")
st.write(q["question"])

choice_k = answer_key(set_id, q_idx)
prev_answer = st.session_state.answers.get(q_idx)
default_index = q["options"].index(prev_answer) if prev_answer in q["options"] else 0
is_checked = st.session_state.checked.get(q_idx, False)

# Show instant feedback if checked in instant mode
if st.session_state.feedback_mode == "instant" and is_checked:
    is_correct = prev_answer == q["correct_answer"]
    if is_correct:
        st.success("✓ Correct!")
    else:
        st.error(f"✗ Incorrect. Correct answer: **{q['correct_answer']}**")
    st.divider()

with st.form(key=f"form__{set_id}__{q_idx}", clear_on_submit=False):
    st.radio(
        "Select an answer",
        q["options"],
        index=default_index,
        key=choice_k,
        disabled=(st.session_state.feedback_mode == "instant" and is_checked),
    )

    if st.session_state.feedback_mode == "instant":
        # Instant feedback mode: Check Answer and Next Question buttons
        c1, c2 = st.columns([1, 1])
        check_clicked = c1.form_submit_button("✓ Check Answer", use_container_width=True, disabled=is_checked)
        is_last_question = st.session_state.pos >= len(st.session_state.order) - 1
        next_button_text = "Finish Quiz ✅" if is_last_question else "Next Question ➡️"
        next_clicked = c2.form_submit_button(next_button_text, use_container_width=True, disabled=not is_checked)
    else:
        # Long test mode: Previous, Next, Finish buttons
        c1, c2, c3 = st.columns([1, 1, 1])
        prev_clicked = c1.form_submit_button("⬅️ Previous", use_container_width=True, disabled=(st.session_state.pos == 0))
        next_clicked = c2.form_submit_button("Next ➡️", use_container_width=True)
        finish_clicked = c3.form_submit_button("Finish ✅", use_container_width=True)

if st.session_state.feedback_mode == "instant":
    # Handle instant feedback mode
    if check_clicked:
        current_answer = st.session_state.get(choice_k)
        st.session_state.answers[q_idx] = current_answer
        st.session_state.checked[q_idx] = True
        _rerun()
    
    if next_clicked and is_checked:
        if st.session_state.pos < len(st.session_state.order) - 1:
            st.session_state.pos += 1
            _rerun()
        else:
            st.session_state.finished = True
            _rerun()
else:
    # Handle long test mode
    if prev_clicked or next_clicked or finish_clicked:
        st.session_state.answers[q_idx] = st.session_state.get(choice_k)

    if prev_clicked:
        st.session_state.pos = max(0, st.session_state.pos - 1)
        _rerun()

    if next_clicked:
        if st.session_state.pos < len(st.session_state.order) - 1:
            st.session_state.pos += 1
            _rerun()
        else:
            st.session_state.finished = True
            _rerun()

    if finish_clicked:
        st.session_state.finished = True
        _rerun()
