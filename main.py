"""Backend demo: AI đề xuất quỹ + thanh toán MoMo + ghi bằng chứng lên Polygon Amoy.

Chạy:  uvicorn main:app --reload --port 8000   (trong thư mục backend)
"""
import hashlib
import json
import threading
import time
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import ai
import config
import funds as funds_mod
import momo
from chain import Ledger

app = FastAPI(title="Kết Nối Thiện Nguyện – demo MoMo TechDay")
ledger = Ledger()
_store_lock = threading.Lock()


# ---------------------------------------------------------------- lưu trữ đơn giản (file JSON)
def load_funds() -> list[dict]:
    try:
        return funds_mod.load_funds()  # đọc từ data/funds.xlsx
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(500, f"Lỗi đọc file quỹ data/funds.xlsx: {e}")


def get_fund(fund_id: str) -> dict:
    for f in load_funds():
        if f["id"] == fund_id:
            return f
    raise HTTPException(404, "Không tìm thấy quỹ")


def load_store() -> dict:
    if config.ORDERS_FILE.exists():
        return json.loads(config.ORDERS_FILE.read_text(encoding="utf-8"))
    return {"orders": {}, "disbursements": []}


def save_store(store: dict) -> None:
    tmp = config.ORDERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(config.ORDERS_FILE)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- thông tin hệ thống
@app.get("/api/status")
def status():
    return {
        "payment_mode": config.PAYMENT_MODE,
        "chain_mode": ledger.mode,
        "contract_url": ledger.contract_url(),
        "ai_engine": "llm" if ai.llm_enabled() else "keyword",
    }


@app.get("/api/funds")
def list_funds():
    """Danh sách quỹ (đọc từ Excel). Có thêm website, momo_url, focus, scope, background."""
    return load_funds()


# ---------------------------------------------------------------- AI
class RecommendIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)


@app.post("/api/recommend")
def recommend(body: RecommendIn):
    fund_list = load_funds()
    res = ai.recommend(body.query, fund_list)
    by_id = {f["id"]: f for f in fund_list}
    return {
        "engine": res["engine"],
        "results": [{"fund": by_id[r["fund_id"]], "reason": r["reason"]} for r in res["results"]],
    }


def fund_stats(fund_id: str) -> dict:
    store = load_store()
    dons = [o for o in store["orders"].values() if o["fund_id"] == fund_id and o["status"] == "paid"]
    outs = [d for d in store["disbursements"] if d["fund_id"] == fund_id]
    times = [o["paid_at"] for o in dons] + [d["created_at"] for d in outs]
    now = datetime.now(timezone.utc)

    def days(iso):
        return (now - datetime.fromisoformat(iso)).days if iso else None

    stats = {
        "donation_count": len(dons),
        "total_in": sum(o["amount"] for o in dons),
        "disbursement_count": len(outs),
        "total_out": sum(d["amount"] for d in outs),
        "disbursements": [{"amount": d["amount"], "purpose": d["purpose"]} for d in outs[-5:]],
        "days_since_last_update": days(max(times)) if times else None,
        "days_since_last_disbursement": days(max(d["created_at"] for d in outs)) if outs else None,
    }
    onchain = None
    try:
        onchain = ledger.totals(fund_id)
    except Exception as e:
        print("Không đọc được từ chuỗi:", e)
    if onchain:
        stats["onchain_total_in"], stats["onchain_total_out"] = onchain["in"], onchain["out"]
    return stats


@app.get("/api/funds/{fund_id}/summary")
def fund_summary(fund_id: str):
    fund = get_fund(fund_id)
    stats = fund_stats(fund_id)
    return {"stats": stats, **ai.summarize_fund(fund, stats)}


# ---------------------------------------------------------------- quyên góp
class DonateIn(BaseModel):
    fund_id: str
    amount: int = Field(ge=1000, le=50_000_000)  # VND; MoMo test yêu cầu tối thiểu 1.000đ


@app.post("/api/donate")
def donate(body: DonateIn):
    fund = get_fund(body.fund_id)
    order_id = f"KNTN{int(time.time())}{uuid.uuid4().hex[:6].upper()}"
    order = {
        "order_id": order_id, "fund_id": fund["id"], "fund_name": fund["short_name"], "amount": body.amount,
        "status": "pending", "created_at": now_iso(), "paid_at": None,
        "momo_trans_id": None, "tx_hash": None, "tx_url": None, "chain_error": None,
    }
    with _store_lock:
        store = load_store()
        store["orders"][order_id] = order
        save_store(store)

    if config.PAYMENT_MODE == "momo":
        try:
            data = momo.create_payment(order_id, body.amount, f"Quyen gop {fund['id']}")  # orderInfo để không dấu cho an toàn
        except Exception as e:
            raise HTTPException(502, f"Không tạo được thanh toán MoMo: {e}")
        return {"order_id": order_id, "pay_url": data.get("payUrl"), "qr_code_url": data.get("qrCodeUrl"),
                "deeplink": data.get("deeplink"), "mode": "momo"}
    return {"order_id": order_id, "pay_url": f"/simulate-pay/{order_id}", "mode": "simulate"}


def mark_paid(order_id: str, amount: int, trans_id: str) -> dict | None:
    """Đánh dấu đã thanh toán (chạy được nhiều lần, chỉ xử lý 1 lần). Trả về đơn nếu cần ghi lên chuỗi."""
    with _store_lock:
        store = load_store()
        order = store["orders"].get(order_id)
        if not order or order["status"] != "pending":
            return None
        if int(amount) != int(order["amount"]):
            order["status"] = "amount_mismatch"
            save_store(store)
            return None
        order.update(status="paid", paid_at=now_iso(), momo_trans_id=str(trans_id))
        save_store(store)
        return dict(order)


def write_to_chain(order: dict) -> None:
    """Chạy nền: ghi khoản quyên góp lên Polygon Amoy rồi lưu tx hash."""
    tx_hash, err = None, None
    try:
        tx_hash = ledger.record_donation(order["fund_id"], order["amount"], order["momo_trans_id"])
    except Exception as e:
        err = str(e)[:300]
        print("Ghi blockchain lỗi:", e)
    with _store_lock:
        store = load_store()
        o = store["orders"][order["order_id"]]
        o["tx_hash"] = tx_hash
        o["tx_url"] = ledger.tx_url(tx_hash) if tx_hash else None
        o["chain_error"] = err
        save_store(store)


def handle_result(params: dict, background: BackgroundTasks) -> bool:
    if not momo.verify_result_signature(params):
        print("Sai chữ ký MoMo:", params.get("orderId"))
        return False
    if str(params.get("resultCode")) != "0":
        with _store_lock:
            store = load_store()
            o = store["orders"].get(params.get("orderId"))
            if o and o["status"] == "pending":
                o["status"] = "failed"
                save_store(store)
        return True
    order = mark_paid(params["orderId"], int(params["amount"]), params["transId"])
    if order:
        background.add_task(write_to_chain, order)
    return True


@app.post("/api/momo/ipn")
async def momo_ipn(request: Request, background: BackgroundTasks):
    """MoMo gọi vào đây (server-to-server) khi thanh toán xong. Cần URL công khai (ngrok)."""
    params = await request.json()
    if not handle_result(params, background):
        raise HTTPException(400, "invalid signature")
    return Response(status_code=204)


@app.get("/api/momo/return")
def momo_return(request: Request, background: BackgroundTasks):
    """Trình duyệt được MoMo chuyển về đây. Cũng xử lý kết quả, phòng khi IPN chưa tới."""
    params = dict(request.query_params)
    handle_result(params, background)
    return RedirectResponse(f"/?order={params.get('orderId', '')}")


@app.get("/api/orders/{order_id}")
def get_order(order_id: str):
    order = load_store()["orders"].get(order_id)
    if not order:
        raise HTTPException(404, "Không tìm thấy giao dịch")
    return order


# ---------------------------------------------------------------- chế độ giả lập (dự phòng)
@app.get("/simulate-pay/{order_id}", response_class=HTMLResponse)
def simulate_page(order_id: str):
    order = get_order(order_id)
    return f"""<!doctype html><html lang="vi"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Thanh toán giả lập</title>
<body style="font-family:system-ui;background:#fdf2f8;display:grid;place-items:center;min-height:100vh;margin:0">
<form method="post" action="/simulate-pay/{order_id}" style="background:#fff;padding:32px;border-radius:16px;max-width:360px;text-align:center;box-shadow:0 8px 30px #0001">
<p style="color:#a50064;font-weight:700;margin:0">CHẾ ĐỘ GIẢ LẬP – không trừ tiền thật</p>
<h2>{order['fund_name']}</h2><p style="font-size:28px;font-weight:700">{order['amount']:,} đ</p>
<button style="background:#a50064;color:#fff;border:0;border-radius:10px;padding:14px 24px;font-size:16px;cursor:pointer">Xác nhận thanh toán</button>
</form></body></html>"""


@app.post("/simulate-pay/{order_id}")
def simulate_confirm(order_id: str, background: BackgroundTasks):
    if config.PAYMENT_MODE != "simulate":
        raise HTTPException(403, "Chỉ dùng ở chế độ giả lập")
    order = get_order(order_id)
    trans_id = str(int(time.time() * 1000))
    order_ok = mark_paid(order_id, order["amount"], f"SIM{trans_id}")
    if order_ok:
        background.add_task(write_to_chain, order_ok)
    return RedirectResponse(f"/?order={order_id}", status_code=303)


# ---------------------------------------------------------------- minh bạch
@app.get("/api/ledger")
def public_ledger():
    store = load_store()
    paid = sorted((o for o in store["orders"].values() if o["status"] == "paid"),
                  key=lambda o: o["paid_at"], reverse=True)
    donations = [{
        "time": o["paid_at"], "fund_id": o["fund_id"], "fund_name": o["fund_name"], "amount": o["amount"],
        "momo_trans_id": o["momo_trans_id"], "tx_hash": o["tx_hash"], "tx_url": o["tx_url"],
    } for o in paid]
    totals = {}
    for o in paid:
        t = totals.setdefault(o["fund_id"], {"fund_name": o["fund_name"], "in": 0, "out": 0})
        t["in"] += o["amount"]
    for d in store["disbursements"]:
        t = totals.setdefault(d["fund_id"], {"fund_name": d["fund_name"], "in": 0, "out": 0})
        t["out"] += d["amount"]
    return {"donations": donations, "disbursements": sorted(store["disbursements"], key=lambda d: d["created_at"], reverse=True),
            "totals": totals, "chain_mode": ledger.mode, "contract_url": ledger.contract_url()}


class DisburseIn(BaseModel):
    admin_token: str
    fund_id: str
    amount: int = Field(gt=0)
    purpose: str = Field(min_length=3, max_length=200)
    evidence: str = Field(min_length=3, description="Mô tả/đường dẫn chứng từ; chỉ lưu mã hash lên chuỗi")


@app.post("/api/disbursements")
def add_disbursement(body: DisburseIn):
    if body.admin_token != config.ADMIN_TOKEN:
        raise HTTPException(403, "Sai mã quản trị")
    fund = get_fund(body.fund_id)
    evidence_hash = hashlib.sha256(body.evidence.encode()).digest()
    tx_hash = ledger.record_disbursement(fund["id"], body.amount, body.purpose, evidence_hash)
    item = {"fund_id": fund["id"], "fund_name": fund["short_name"], "amount": body.amount, "purpose": body.purpose,
            "evidence_hash": "0x" + evidence_hash.hex(), "created_at": now_iso(),
            "tx_hash": tx_hash, "tx_url": ledger.tx_url(tx_hash) if tx_hash else None}
    with _store_lock:
        store = load_store()
        store["disbursements"].append(item)
        save_store(store)
    return item


# ---------------------------------------------------------------- giao diện
app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
