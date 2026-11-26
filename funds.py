"""Đọc danh sách quỹ trực tiếp từ file Excel data/funds.xlsx.

Cả đội chỉ cần sửa file Excel rồi khởi động lại (hoặc chờ server tự đọc lại khi file thay đổi).
Cột được nhận theo TÊN tiêu đề (không phân biệt hoa thường, có dấu hay không), nên có thể đổi thứ tự cột:

  Bắt buộc : "Tên Quỹ / Tổ chức", "Lĩnh vực hỗ trợ chính", "Phạm vi hỗ trợ"
  Tùy chọn : "Thông tin nền tảng", "Website chính thức", "Trang dự án trên MoMo",
             "ID" (mã quỹ cố định), "Sao kê" (link trang sao kê), "Địa chỉ hợp đồng"

Lưu ý: mã quỹ (id) được ghi lên blockchain. Sau khi đã có giao dịch, đừng đổi tên quỹ;
nếu cần đổi tên, thêm cột "ID" và giữ nguyên mã cũ.
"""
import re
import threading
import unicodedata

from openpyxl import load_workbook

import config


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d")


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", strip_accents(s)).strip("-")[:60]


# ---------------------------------------------------------------- bộ nhãn nhu cầu
# Dùng CHUNG cho cả mô tả quỹ và câu hỏi của người dùng → so khớp nhãn với nhãn.
# Từ khóa KHÔNG dấu: so với văn bản đã bỏ dấu (người dùng gõ không dấu vẫn khớp).
# Từ khóa CÓ dấu: so với văn bản gốc — dùng khi bỏ dấu sẽ nhầm (mắt/mặt, mổ/mồ côi).
# So khớp theo nguyên từ, không khớp một phần từ ("hoc" không khớp "hoc duong" của "khoa học").
NEED_TAGS: dict[str, list[str]] = {
    "trẻ em": ["tre em", "tre", "be", "em be", "thieu nhi", "con nho", "benh nhi", "nhi khoa", "chau be"],
    "y tế": ["y te", "benh", "dieu tri", "chua benh", "phau thuat", "mổ", "vien phi", "suc khoe", "kham benh", "om"],
    "phẫu thuật": ["phau thuat", "mổ", "ca mổ"],
    "tim bẩm sinh": ["tim", "nhip tim", "benh tim"],
    "dị tật bẩm sinh": ["di tat", "di dang"],
    "hàm mặt (khe hở môi, hàm ếch)": ["khe ho moi", "ham ech", "sut moi", "ham mat", "so mat", "hàm mặt", "sọ mặt", "môi"],
    "mắt": ["mắt", "mù", "thi luc", "khiem thi", "can thi", "đục thủy tinh thể"],
    "chỉnh hình": ["chinh hinh", "xuong", "di chung tai nan", "tai nan", "cot song", "bàn chân", "chân"],
    "tiêu hóa": ["tieu hoa", "ruot", "da day"],
    "trẻ sinh non": ["sinh non", "so sinh"],
    "hồi sức cấp cứu": ["cap cuu", "hoi suc"],
    "nha khoa, trị liệu ngôn ngữ": ["nha khoa", "rang", "ngon ngu", "noi ngong", "phat am"],
    "giáo dục, học bổng": ["giao duc", "hoc bong", "di hoc", "hoc sinh", "sinh vien", "truong hoc", "sach vo", "nu sinh", "hoc tap"],
    "trẻ mồ côi": ["mồ côi", "bao tro"],
    "dinh dưỡng": ["dinh duong", "suy dinh duong", "thap coi", "tam voc", "bua an", "bua trua", "sữa", "đói", "thiếu ăn"],
    "bảo vệ trẻ em": ["bao luc", "xam hai", "bao ve tre em", "bi danh", "lam dung", "bao hanh"],
    "tài năng": ["tai nang", "nang khieu", "uom mam"],
    "phục hồi chức năng": ["phuc hoi chuc nang", "vat ly tri lieu"],
    "dân tộc thiểu số": ["dan toc", "dan toc thieu so"],
}

REGION_TAGS: dict[str, list[str]] = {
    "Toàn quốc": ["toan quoc", "ca nuoc", "63 tinh"],
    "Miền núi, vùng sâu vùng xa": ["mien nui", "vung sau", "vung xa", "vung cao", "ha giang", "lao cai", "tay bac",
                                   "dien bien", "son la", "cao bang", "lai chau", "tay nguyen", "ban lang"],
}


def _words(text: str) -> str:
    return " " + re.sub(r"[^\w]+", " ", text.lower()) + " "


def tag_text(text: str, table: dict[str, list[str]]) -> list[str]:
    plain = _words(strip_accents(text))
    accented = _words(unicodedata.normalize("NFC", text))
    out = []
    for label, kws in table.items():
        for k in kws:
            hay = plain if k.isascii() else accented
            if f" {k} " in hay:
                out.append(label)
                break
    return out


def matched_keywords(text: str, label: str, table: dict[str, list[str]] = NEED_TAGS) -> list[str]:
    plain = _words(strip_accents(text))
    accented = _words(unicodedata.normalize("NFC", text))
    return [k for k in table.get(label, []) if f" {k} " in (plain if k.isascii() else accented)]


# ---------------------------------------------------------------- đọc Excel
COLUMN_ALIASES = {
    "name": ["ten quy", "to chuc"],
    "focus": ["linh vuc"],
    "scope": ["pham vi"],
    "background": ["thong tin nen tang", "gioi thieu"],
    "website": ["website"],
    "momo_url": ["momo"],
    "id": ["id", "ma quy"],
    "statement_url": ["sao ke"],
    "contract_address": ["dia chi hop dong", "contract"],
}


def _map_headers(headers: list) -> dict[str, int]:
    mapping = {}
    for idx, h in enumerate(headers):
        if h is None:
            continue
        hs = strip_accents(h).strip()
        for key, aliases in COLUMN_ALIASES.items():
            if key in mapping:
                continue
            if key == "id":
                if hs in aliases:
                    mapping[key] = idx
            elif any(a in hs for a in aliases):
                mapping[key] = idx
                break
    missing = [k for k in ("name", "focus", "scope") if k not in mapping]
    if missing:
        raise ValueError(f"File Excel thiếu cột bắt buộc: {missing}. Tiêu đề đọc được: {headers}")
    return mapping


def _clean(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


def short_name(name: str) -> str:
    """'Quỹ Vì Tầm Vóc Việt (VSF)' → 'Quỹ Vì Tầm Vóc Việt'."""
    return re.sub(r"\s*\(.*?\)\s*$", "", name).strip() or name


def read_funds_xlsx(path=None) -> list[dict]:
    wb = load_workbook(path or config.FUNDS_XLSX, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    header_i = next(i for i, r in enumerate(rows) if r and any(c is not None for c in r))
    cols = _map_headers(list(rows[header_i]))
    funds, seen = [], set()
    for r in rows[header_i + 1:]:
        get = lambda k: _clean(r[cols[k]]) if k in cols and cols[k] < len(r) else ""
        name = get("name")
        if not name:
            continue
        fid = get("id") or slugify(short_name(name))
        if fid in seen:
            raise ValueError(f"Trùng mã quỹ '{fid}'. Thêm cột ID để phân biệt.")
        seen.add(fid)
        focus, scope, background = get("focus"), get("scope"), get("background")
        statement_url = get("statement_url") or None
        funds.append({
            "id": fid,
            "name": name,
            "short_name": short_name(name),
            "focus": focus,  # nguyên văn cột "Lĩnh vực hỗ trợ chính"
            "scope": scope,  # nguyên văn cột "Phạm vi hỗ trợ"
            "background": background,
            "website": get("website") or None,
            "momo_url": get("momo_url") or None,
            "statement_url": statement_url,
            "contract_address": get("contract_address") or None,
            # các trường giao diện đang dùng
            "fields": tag_text(focus + " " + background + " trẻ em", NEED_TAGS),  # file này là quỹ hỗ trợ trẻ em
            "regions": tag_text(scope, REGION_TAGS) or [scope],
            "description": focus,
            # None = file chưa có thông tin sao kê (KHÔNG có nghĩa là quỹ không công khai)
            "public_statement": True if statement_url else None,
            "sample": False,
        })
    if not funds:
        raise ValueError("File Excel không có dòng quỹ nào")
    return funds


# ---------------------------------------------------------------- cache theo thời điểm sửa file
_cache = {"mtime": None, "funds": []}
_lock = threading.Lock()


def load_funds() -> list[dict]:
    mtime = config.FUNDS_XLSX.stat().st_mtime
    with _lock:
        if _cache["mtime"] != mtime:
            _cache["funds"] = read_funds_xlsx()
            _cache["mtime"] = mtime
        return _cache["funds"]
