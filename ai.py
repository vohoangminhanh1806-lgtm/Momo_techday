"""Phần AI:
1. recommend(): hiểu câu hỏi tự nhiên của người dùng → đề xuất quỹ phù hợp kèm lý do.
2. summarize_fund(): đọc dữ liệu dòng tiền (vào/ra) → tóm tắt dễ hiểu cho người không biết blockchain.

Dùng bất kỳ LLM nào có API tương thích OpenAI (OpenAI, Google Gemini, Groq, OpenRouter...).
Nếu chưa có API key hoặc LLM lỗi, tự chuyển sang bộ đề xuất theo từ khóa để demo không bị gián đoạn.
"""
import json
import re

import httpx

import config
import funds as funds_mod


# ---------------------------------------------------------------- LLM helper
def _llm(messages: list[dict], max_tokens: int = 800) -> str:
    r = httpx.post(
        f"{config.LLM_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
        json={"model": config.LLM_MODEL, "messages": messages, "temperature": 0.3, "max_tokens": max_tokens},
        timeout=45,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _extract_json(text: str):
    m = re.search(r"\[.*\]|\{.*\}", text, re.S)
    if not m:
        raise ValueError("LLM không trả JSON")
    return json.loads(m.group(0))


def llm_enabled() -> bool:
    return bool(config.LLM_API_KEY)


# ---------------------------------------------------------------- Đề xuất quỹ
RECOMMEND_SYSTEM = """Bạn là trợ lý giúp người dùng MoMo chọn quỹ từ thiện hỗ trợ trẻ em phù hợp.
Chỉ được chọn trong danh sách quỹ được cung cấp và chỉ dựa vào thông tin trong danh sách, không bịa thêm
chương trình, số liệu hay thành tích. Chọn quỹ có chương trình khớp nhất với tình huống cụ thể người dùng nêu
(bệnh gì, nhu cầu gì, ở đâu). Lý do phải nhắc đúng chương trình/lĩnh vực của quỹ đó.
Trả lời DUY NHẤT một mảng JSON, tối đa 3 phần tử, xếp từ phù hợp nhất:
[{"fund_id": "...", "reason": "1-2 câu tiếng Việt"}]
Nếu không quỹ nào phù hợp, trả về []."""


def _llm_recommend(query: str, fund_list: list[dict]) -> list[dict]:
    compact = [
        {"id": f["id"], "ten": f["name"], "linh_vuc": f["focus"], "pham_vi": f["scope"], "gioi_thieu": f["background"]}
        for f in fund_list
    ]
    content = _llm([
        {"role": "system", "content": RECOMMEND_SYSTEM},
        {"role": "user", "content": f"Danh sách quỹ:\n{json.dumps(compact, ensure_ascii=False)}\n\nMong muốn của người dùng: {query}"},
    ])
    ids = {f["id"] for f in fund_list}
    out = []
    for item in _extract_json(content):
        if isinstance(item, dict) and item.get("fund_id") in ids:  # chặn quỹ bịa
            out.append({"fund_id": item["fund_id"], "reason": str(item.get("reason", ""))[:400]})
    return out[:3]


GENERIC_TAGS = {"trẻ em", "y tế"}  # nhãn chung, quỹ nào trong file cũng có → điểm thấp


def _lower_first(t: str) -> str:
    return t[0].lower() + t[1:] if t else t


def _snippet(fund: dict, label: str) -> str:
    """Trích cụm trong cột 'Lĩnh vực hỗ trợ chính' nói về nhu cầu `label`."""
    hit = lambda t: label in funds_mod.tag_text(t, funds_mod.NEED_TAGS)
    focus = fund["focus"]
    # 1) ưu tiên các mục liệt kê trong ngoặc: "Y tế (phẫu thuật tim..., chăm sóc trẻ sinh non)"
    for m in re.finditer(r"([^()]*)\(([^()]*)\)", focus):
        before, inner = m.group(1), m.group(2)
        for item in (x.strip(" .") for x in inner.split(",")):
            if item and hit(item):
                if len(item.split()) >= 3:
                    return _lower_first(item)
                ctx = re.sub(r"^(và|Y tế đa khoa,?)\s*", "", before.strip(" ,.;"), flags=re.I)
                return f"{_lower_first(ctx)} (có {item})"
    # 2) các vế còn lại, bỏ phần trong ngoặc
    rest = re.sub(r"\([^()]*\)", "", focus)
    for part in re.split(r"[;]|, |\.\s", rest):
        part = re.sub(r"^và\s+", "", part.strip(" .,:"))
        if part and hit(part):
            return _lower_first(part)
    return ""


def _keyword_recommend(query: str, fund_list: list[dict]) -> list[dict]:
    want = funds_mod.tag_text(query, funds_mod.NEED_TAGS)
    want_region = funds_mod.tag_text(query, funds_mod.REGION_TAGS)
    specific = [t for t in want if t not in GENERIC_TAGS]
    scored = []
    for f in fund_list:
        hit_specific = [t for t in specific if t in f["fields"]]
        hit_generic = [t for t in want if t in GENERIC_TAGS and t in f["fields"]]
        if specific and not hit_specific:
            continue  # người dùng nêu nhu cầu cụ thể mà quỹ không làm → bỏ
        if not hit_specific and not hit_generic:
            continue
        score = 5 * len(hit_specific) + len(hit_generic)
        score += len(hit_specific) / max(len(f["fields"]), 1)  # ngang điểm → ưu tiên quỹ chuyên sâu hơn
        hit_region = [r for r in want_region if r in f["regions"]]
        score += 2 * len(hit_region)

        if hit_specific:
            snips = [s for s in dict.fromkeys(_snippet(f, t) for t in hit_specific) if s]
            reason = f"Khớp nhu cầu {', '.join(hit_specific)}: quỹ hỗ trợ " + ("; ".join(snips[:2]) or _lower_first(f["focus"]))
        else:
            reason = "Quỹ hỗ trợ " + f["focus"][0].lower() + f["focus"][1:]
        reason = reason.rstrip(". ") + "."
        if hit_region:
            reason += " Quỹ tập trung hoạt động tại " + ", ".join(r.lower() for r in hit_region) + "."
        elif f["scope"]:
            reason += f" Phạm vi: {f['scope'][0].lower() + f['scope'][1:]}."
        scored.append((score, {"fund_id": f["id"], "reason": reason}))
    scored.sort(key=lambda x: -x[0])
    return [s[1] for s in scored[:3]]


def recommend(query: str, fund_list: list[dict]) -> dict:
    if llm_enabled():
        try:
            return {"engine": "llm", "results": _llm_recommend(query, fund_list)}
        except Exception as e:  # mạng lỗi, hết quota... → không làm hỏng demo
            print("LLM lỗi, chuyển sang từ khóa:", e)
    return {"engine": "keyword", "results": _keyword_recommend(query, fund_list)}


# ---------------------------------------------------------------- Tóm tắt dòng tiền
SUMMARY_SYSTEM = """Bạn giải thích dòng tiền của một quỹ từ thiện cho người dùng phổ thông, bằng tiếng Việt.
Chỉ dùng số liệu được cung cấp, không suy đoán thêm. Viết 3-4 câu ngắn:
tổng tiền nhận, tổng đã chi và chi cho việc gì, số dư, lần cập nhật gần nhất cách đây bao lâu.
Nếu quá 7 ngày chưa cập nhật khoản chi nào trong khi vẫn còn số dư, nhắc nhẹ điều đó.
Không dùng thuật ngữ blockchain; chỉ nói "dữ liệu đã được lưu công khai, không sửa được"."""


def _vnd(n: int) -> str:
    return f"{n:,.0f}".replace(",", ".") + " đ"


def _template_summary(fund: dict, stats: dict) -> str:
    s = (f"{fund.get('short_name', fund['name'])} đã nhận {stats['donation_count']} khoản quyên góp, tổng {_vnd(stats['total_in'])}. "
         f"Quỹ đã công bố {stats['disbursement_count']} khoản chi, tổng {_vnd(stats['total_out'])}; "
         f"số dư còn {_vnd(stats['total_in'] - stats['total_out'])}. ")
    d = stats.get("days_since_last_update")
    if d is not None:
        s += "Lần cập nhật gần nhất là hôm nay. " if d == 0 else f"Lần cập nhật gần nhất cách đây {d} ngày. "
    last_out = stats.get("days_since_last_disbursement")
    if stats["total_in"] > stats["total_out"] and last_out is not None and last_out > 7:
        s += "Quỹ chưa cập nhật khoản chi nào trong hơn 7 ngày qua. "
    return s + "Dữ liệu đã được lưu công khai, không sửa được."


def summarize_fund(fund: dict, stats: dict) -> dict:
    if llm_enabled():
        try:
            text = _llm([
                {"role": "system", "content": SUMMARY_SYSTEM},
                {"role": "user", "content": json.dumps({"quỹ": fund["name"], **stats}, ensure_ascii=False)},
            ], max_tokens=400)
            return {"engine": "llm", "summary": text.strip()}
        except Exception as e:
            print("LLM lỗi, dùng mẫu câu:", e)
    return {"engine": "template", "summary": _template_summary(fund, stats)}
