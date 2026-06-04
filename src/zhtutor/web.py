#!/usr/bin/env python3
"""중국어 학습 튜터 — Gradio 웹 UI.

탭: 회화(텍스트/음성 입력 + 스트리밍 + 발음 자동재생) / 단어장 / 복습(SRS).
실행: zhw  (또는 python -m zhtutor.web) → http://127.0.0.1:7860
"""
import os
import random
import sys
import tempfile

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
import gradio as gr  # noqa: E402

from zhtutor import cli as z  # noqa: E402
from zhtutor import core as zc  # noqa: E402
from zhtutor import gloss  # noqa: E402
from zhtutor import repo  # noqa: E402

MODEL = "deepseek-v4-pro"
ASR_MODEL = "small"
ASR_LANG = "zh"
MAX_TOKENS = 1024

KEY = z.load_key()
VOICE = z.detect_voice()


def _new_messages():
    msgs = [{"role": "system", "content": z.SYSTEM_PROMPT}]
    due = zc.due_cards(z.load_vocab(), zc.today_iso())
    ctx = zc.format_due_context(due)
    if ctx:
        msgs.append({"role": "system", "content": ctx})
    return msgs


def _tmp_wav():
    f = tempfile.NamedTemporaryFile(prefix="zhtts_", suffix=".wav", delete=False)
    f.close()
    return f.name


def respond(user_text, history, messages):
    history = list(history or [])
    user_text = (user_text or "").strip()
    if not user_text:
        yield history, messages, None, ""
        return
    if not KEY:
        history.append({"role": "assistant",
                        "content": "DEEPSEEK_API_KEY 가 없습니다. 키체인 등록 후 재실행."})
        yield history, messages, None, ""
        return

    messages = messages + [{"role": "user", "content": user_text}]
    history = history + [{"role": "user", "content": user_text},
                         {"role": "assistant", "content": ""}]
    yield history, messages, None, ""

    acc = ""
    try:
        for chunk in z.stream_chat_iter(KEY, messages, MODEL, False, MAX_TOKENS):
            acc += chunk
            history[-1]["content"] = acc
            yield history, messages, None, ""
    except RuntimeError as e:
        history[-1]["content"] = f"[오류] {e}"
        yield history, messages, None, ""
        return

    messages = messages + [{"role": "assistant", "content": acc}]
    if len(messages) > 21:  # system + 최근 20
        messages = [messages[0]] + messages[-20:]

    audio = None
    cn = "".join(zc.extract_chinese_list(acc))
    if cn and VOICE:
        audio = z.tts_to_file(cn, VOICE, _tmp_wav())
    yield history, messages, audio, ""


def transcribe_mic(audio_path):
    if not audio_path:
        return "(녹음이 비어 있어요 — ● 녹음 후 ■ 정지를 누르세요)"
    try:
        model = z.ensure_asr(ASR_MODEL)
        text = z.transcribe(audio_path, model, ASR_LANG)
        return text or "(인식 실패 — 조용한 곳에서 또박또박 다시)"
    except Exception as e:
        return f"(인식 오류: {e})"


# ---- 단어장 탭 ----
VOCAB_HEADERS = ["汉字", "핀인", "뜻", "box", "due", "횟수"]


def vocab_rows():
    return [[e.get("hanzi", ""), e.get("pinyin", ""), e.get("ko", ""),
             e.get("box", 1), e.get("due", "-"), e.get("count", 1)]
            for e in z.load_vocab()]


def save_last(messages):
    reply = next((m["content"] for m in reversed(messages or [])
                  if m.get("role") == "assistant"), "")
    triples = zc.parse_triples(reply)
    if not triples:
        return vocab_rows(), "저장할 항목이 없습니다 (회화를 먼저 진행하세요)"
    v = z.load_vocab()
    added = sum(zc.add_entry(v, t["hanzi"], t.get("pinyin", ""), t.get("ko", ""))
                for t in triples)
    z.save_vocab(v)
    return vocab_rows(), f"📒 {added}개 새로 저장 (총 {len(v)}개)"


def add_word(word):
    word = (word or "").strip()
    if not word:
        return vocab_rows(), "단어를 입력하세요", ""
    try:
        from pypinyin import Style, lazy_pinyin
        py = " ".join(lazy_pinyin(zc.han_only(word) or word, style=Style.TONE))
    except Exception:
        py = ""
    # 캐시 → HSK 내장 사전 → (미스·키 있을 때만) DeepSeek
    def _fetch():
        if not KEY:
            return None
        try:
            return z.complete(
                KEY, f"중국어 '{word}' 의 한국어 뜻을 아주 짧게 한 줄로만 답해."
                " 설명·부가 문장 없이 뜻만.", MODEL)
        except RuntimeError:
            return None
    ko = gloss.resolve_gloss(word, online_fetch=_fetch)
    v = z.load_vocab()
    is_new = zc.add_entry(v, word, py, ko)
    z.save_vocab(v)
    state = "추가" if is_new else "이미 있음(횟수+1)"
    return vocab_rows(), f"📒 {state}: {word} ({py}) — {ko}  [총 {len(v)}개]", ""


def del_word(word):
    word = (word or "").strip()
    if not word:
        return vocab_rows(), "단어를 입력하세요", ""
    n = repo.delete_vocab(z.USER_ID, word)
    msg = f"🗑 삭제: {word}" if n else f"(단어장에 없음: {word})"
    return vocab_rows(), msg, ""


def import_hsk(level, n):
    data = z._load_hsk(level)
    if not data:
        return vocab_rows(), f"알 수 없는 레벨: {level}"
    limit = int(n) if n else None
    v = z.load_vocab()
    added = zc.merge_hsk(v, data["entries"], limit)
    z.save_vocab(v)
    return (vocab_rows(),
            f"📥 {data['level']} — 새로 {added}개 추가 (총 {len(v)}개) · "
            "뜻은 영어 임시값, 학습하며 한국어로 보강하세요")


# ---- 복습 탭 (SRS) ----
def _rev_progress(st):
    return f"진행 {st['i'] + 1}/{len(st['queue'])}  (정답 {st['correct']}/{st['done']})"


def _rev_prompt(st):
    c = st["queue"][st["i"]]
    return (f"### 뜻: {c['ko'] or '(뜻 없음)'}\n"
            "중국어로 답해보세요 (타이핑 또는 🎤 녹음 후 **채점**)")


def _empty_rev():
    return {"queue": [], "i": 0, "done": 0, "correct": 0, "graded": False}


def review_start(mode, st):
    v = z.load_vocab()
    today = zc.today_iso()
    cards = list(v) if mode == "전체" else zc.due_cards(v, today)
    random.shuffle(cards)
    queue = [{"hanzi": c["hanzi"], "ko": c.get("ko", ""),
              "pinyin": c.get("pinyin", "")} for c in cards]
    st = {"queue": queue, "i": 0, "done": 0, "correct": 0, "graded": False}
    if not queue:
        return (st, "복습할 카드가 없습니다 (오늘 due 없음 — '전체' 선택 가능)",
                "", "", None, "", None)
    return st, _rev_progress(st), _rev_prompt(st), "", None, "", None


def review_grade(st, text, mic):
    if not st or not st.get("queue"):
        return st, "먼저 '복습 시작'을 누르세요", None, ""
    if st.get("graded"):
        return st, "(이미 채점됨 — '다음'을 누르세요)", None, _rev_progress(st)
    c = st["queue"][st["i"]]
    target = c["hanzi"]
    correct, detail = False, ""
    if mic:
        try:
            heard = z.transcribe(mic, z.ensure_asr(ASR_MODEL), ASR_LANG)
        except Exception as e:
            heard, detail = "", f"(인식 오류: {e})"
        if heard:
            res = zc.score_pronunciation(target, heard)
            if res is None:
                correct = zc.han_only(heard) == zc.han_only(target)
                detail = f"🎤 {heard}"
            else:
                correct = res["score"] >= zc.SRS_PASS
                detail = f"🎤 {heard} ({res['h_disp']}) · 점수 {res['score']}/100"
                if res["problems"]:
                    detail += " — " + "; ".join(res["problems"][:2])
    elif (text or "").strip():
        correct = zc.han_only(text) == zc.han_only(target)
        detail = f"입력: {text}"
    else:
        detail = "답이 없어 '모름'으로 처리"
    v = z.load_vocab()
    today = zc.today_iso()
    for e in v:
        if e.get("hanzi") == target:
            zc.schedule(e, correct, today)
            break
    z.save_vocab(v)
    z.log_review(target, correct, today)
    st = {**st, "graded": True, "done": st["done"] + 1,
          "correct": st["correct"] + (1 if correct else 0)}
    mark = "✅ 정답" if correct else "❌ 오답"
    result = f"{mark}\n\n**{target}**  {c['pinyin']}  — {c['ko']}\n\n{detail}"
    audio = z.tts_to_file(target, VOICE, _tmp_wav()) if VOICE else None
    return st, result, audio, _rev_progress(st)


def review_next(st):
    if not st or not st.get("queue"):
        return st, "먼저 '복습 시작'을 누르세요", "", "", None, "", None
    st = {**st, "i": st["i"] + 1, "graded": False}
    if st["i"] >= len(st["queue"]):
        msg = f"📖 복습 끝 — {st['done']}개 중 {st['correct']}개 정답 (저장됨)"
        return st, msg, "", "", None, "", None
    return st, _rev_progress(st), _rev_prompt(st), "", None, "", None


# ---- 통계 탭 (Phase 2) ----
DAILY_HEADERS = ["날짜", "학습", "정답", "정확도"]
BOX_HEADERS = ["box", "카드 수"]
DUE_HEADERS = ["구간", "수"]


def _stats_summary(vocab, reviews, today):
    if not vocab and not reviews:
        return "*(아직 단어장도 복습 기록도 없어요 — 회화 탭에서 시작해 보세요)*"
    streak = zc.streak_days(reviews, today)
    acc_all = zc.accuracy(reviews)
    since_7 = zc.add_days(today, -6)
    acc_7 = zc.accuracy(reviews, since=since_7)
    if acc_all is None:
        acc_line = "복습 기록 없음"
    else:
        total = len(reviews)
        line = f"전체 **{acc_all * 100:.0f}%** ({int(round(acc_all * total))}/{total})"
        if acc_7 is not None:
            n_7 = sum(1 for r in reviews if r["day"] >= since_7)
            line += (f"  ·  최근 7일 **{acc_7 * 100:.0f}%** "
                     f"({int(round(acc_7 * n_7))}/{n_7})")
        acc_line = line
    return (f"### 📊 학습 통계 ({today})\n"
            f"- 🔥 **연속 학습일**: {streak}일\n"
            f"- 🎯 **정확도**: {acc_line}")


def _daily_rows(reviews, today):
    rows = []
    for d in zc.daily_counts(reviews, today, 7):
        acc = f"{d['correct'] / d['n'] * 100:.0f}%" if d['n'] else "-"
        tag = "오늘" if d['day'] == today else d['day']
        rows.append([tag, d['n'], d['correct'], acc])
    return rows


def _box_rows(vocab):
    box = zc.box_distribution(vocab)
    return [[f"box {b}", box[b]] for b in (1, 2, 3, 4, 5)] + [["미시작", box[None]]]


def _due_rows(vocab, today):
    f = zc.due_forecast(vocab, today)
    return [["오늘 (지난 것 포함)", f["today"]],
            ["내일", f["tomorrow"]],
            ["이번 주 (2~7일)", f["this_week"]],
            ["나중", f["later"]],
            ["예약 없음", f["no_due"]]]


def stats_load():
    vocab = z.load_vocab()
    reviews = repo.get_review_log(z.USER_ID)
    today = zc.today_iso()
    return (_stats_summary(vocab, reviews, today),
            _daily_rows(reviews, today),
            _box_rows(vocab),
            _due_rows(vocab, today))


def build():
    with gr.Blocks(title="中文 튜터") as demo:
        gr.Markdown("# 中文 회화 튜터\n"
                    "한국어/중국어로 입력하거나 🎤로 말해보세요. "
                    "답변의 중국어 발음은 자동 재생됩니다.")
        gr.Markdown("🦁 *Brave에서 녹음이 무음이면: 주소창 사자 아이콘 → 이 사이트 "
                    "Shields Down(또는 'Block fingerprinting' 끄기) → 새로고침*")
        st_messages = gr.State(_new_messages())
        with gr.Tabs():
            with gr.Tab("회화"):
                chatbot = gr.Chatbot(height=440, label="대화")
                tts = gr.Audio(label="발음 (자동 재생)", autoplay=True,
                               interactive=False)
                with gr.Row():
                    txt = gr.Textbox(placeholder="한국어/중국어 입력 후 Enter…",
                                     scale=5, show_label=False)
                    send = gr.Button("전송", scale=1, variant="primary")
                with gr.Accordion("🎤 음성 입력 (● 녹음 → ■ 정지하면 자동 인식)",
                                  open=False):
                    mic = gr.Audio(sources=["microphone"], type="filepath",
                                   label="녹음 (■ 정지하면 자동으로 입력칸에 인식)")
                    rec_btn = gr.Button("다시 인식")
                clear = gr.Button("새 대화")

                outs = [chatbot, st_messages, tts, txt]
                send.click(respond, [txt, chatbot, st_messages], outs)
                txt.submit(respond, [txt, chatbot, st_messages], outs)
                mic.stop_recording(transcribe_mic, [mic], [txt])
                rec_btn.click(transcribe_mic, [mic], [txt])
                clear.click(lambda: ([], _new_messages(), None, ""), None, outs)

            with gr.Tab("단어장"):
                vocab_df = gr.Dataframe(headers=VOCAB_HEADERS, value=vocab_rows(),
                                        interactive=False, wrap=True, label="단어장")
                vocab_msg = gr.Markdown("")
                with gr.Row():
                    save_btn = gr.Button("💾 직전 답변 저장")
                    refresh_btn = gr.Button("🔄 새로고침")
                with gr.Row():
                    add_txt = gr.Textbox(placeholder="추가할 중국어 (예: 你好)",
                                         scale=4, show_label=False)
                    add_btn = gr.Button("➕ 추가", scale=1, variant="primary")
                with gr.Row():
                    del_txt = gr.Textbox(placeholder="삭제할 중국어 (예: 你好)",
                                         scale=4, show_label=False)
                    del_btn = gr.Button("🗑 삭제", scale=1)
                with gr.Row():
                    imp_level = gr.Dropdown(["hsk1", "hsk2"], value="hsk1",
                                            label="HSK 레벨", scale=1)
                    imp_n = gr.Number(label="개수 (비우면 전체)",
                                      precision=0, scale=1, value=None)
                    imp_btn = gr.Button("📥 HSK 가져오기", scale=1)
                save_btn.click(save_last, [st_messages], [vocab_df, vocab_msg])
                refresh_btn.click(lambda: vocab_rows(), None, [vocab_df])
                add_btn.click(add_word, [add_txt], [vocab_df, vocab_msg, add_txt])
                add_txt.submit(add_word, [add_txt], [vocab_df, vocab_msg, add_txt])
                del_btn.click(del_word, [del_txt], [vocab_df, vocab_msg, del_txt])
                del_txt.submit(del_word, [del_txt], [vocab_df, vocab_msg, del_txt])
                imp_btn.click(import_hsk, [imp_level, imp_n],
                              [vocab_df, vocab_msg])

            with gr.Tab("복습"):
                st_rev = gr.State(_empty_rev())
                rev_mode = gr.Radio(["오늘 due", "전체"], value="오늘 due",
                                    label="복습 범위")
                rev_start = gr.Button("복습 시작", variant="primary")
                rev_status = gr.Markdown("‘복습 시작’을 누르세요.")
                rev_prompt = gr.Markdown("")
                with gr.Row():
                    rev_text = gr.Textbox(placeholder="중국어로 답…", scale=4,
                                          show_label=False)
                    rev_mic = gr.Audio(sources=["microphone"], type="filepath",
                                       label="🎤 음성 답 (■ 정지 후 채점)", scale=2)
                with gr.Row():
                    rev_grade = gr.Button("채점", variant="primary")
                    rev_next = gr.Button("다음")
                rev_result = gr.Markdown("")
                rev_tts = gr.Audio(label="정답 발음", autoplay=True,
                                   interactive=False)

                start_out = [st_rev, rev_status, rev_prompt, rev_result,
                             rev_tts, rev_text, rev_mic]
                rev_start.click(review_start, [rev_mode, st_rev], start_out)
                rev_grade.click(review_grade, [st_rev, rev_text, rev_mic],
                                [st_rev, rev_result, rev_tts, rev_status])
                rev_next.click(review_next, [st_rev], start_out)
                rev_mic.stop_recording(
                    lambda: "🎤 녹음 완료 — ‘채점’을 누르세요", None, [rev_result])

            with gr.Tab("통계"):
                stats_md = gr.Markdown("탭을 처음 열면 자동으로 채워집니다.")
                stats_btn = gr.Button("🔄 새로고침")
                stats_daily = gr.Dataframe(headers=DAILY_HEADERS, interactive=False,
                                           label="최근 7일 학습")
                stats_box = gr.Dataframe(headers=BOX_HEADERS, interactive=False,
                                         label="box 분포 (Leitner SRS)")
                stats_due = gr.Dataframe(headers=DUE_HEADERS, interactive=False,
                                         label="복습 예보")
                stats_outs = [stats_md, stats_daily, stats_box, stats_due]
                stats_btn.click(stats_load, None, stats_outs)
                demo.load(stats_load, None, stats_outs)
    return demo


def main():
    if not KEY:
        print("경고: DEEPSEEK_API_KEY 없음 — 키체인 등록 후 실행하세요.", file=sys.stderr)
    if VOICE is None:
        print("경고: 중국어 음성(Tingting) 미설치 — 발음 재생은 비활성.", file=sys.stderr)
    try:
        z.db.init(z.VOCAB_PATH, z.USER_ID)
    except Exception as e:
        print(f"DB 초기화 실패: {e}", file=sys.stderr)
        sys.exit(1)
    build().launch(server_name="127.0.0.1", inbrowser=True, show_error=True)


if __name__ == "__main__":
    main()
