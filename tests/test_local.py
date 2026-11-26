# Kiểm tra toàn bộ luồng trên blockchain giả lập cục bộ (không cần mạng).
# Cài thêm: pip install "eth-tester[py-evm]"  rồi chạy:  python tests/test_local.py
import json, sys, os, tempfile, time
from pathlib import Path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import config
config.ORDERS_FILE = Path(tempfile.mkdtemp()) / "orders.json"
from fastapi.testclient import TestClient
from web3 import Web3, EthereumTesterProvider
from eth_tester import EthereumTester, PyEVMBackend
import main, momo
from chain import Ledger

# --- chain local
w3 = Web3(EthereumTesterProvider(EthereumTester(PyEVMBackend())))
c = json.loads(config.CONTRACT_JSON.read_text())
acct = w3.eth.account.create()
w3.eth.send_transaction({"from": w3.eth.accounts[0], "to": acct.address, "value": 10**19})
tx = w3.eth.contract(abi=c["abi"], bytecode=c["bytecode"]).constructor().build_transaction(
    {"from": acct.address, "nonce": 0, "chainId": w3.eth.chain_id, "maxPriorityFeePerGas": 10**9, "maxFeePerGas": 10**10})
addr = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction))["contractAddress"]
main.ledger = Ledger(w3=w3, private_key=acct.key.hex(), address=addr, chain_id=w3.eth.chain_id)

cl = TestClient(main.app)
print("status", cl.get("/api/status").json())
print("home", cl.get("/").status_code, "funds", len(cl.get("/api/funds").json()))
for q in ["Tôi muốn giúp trẻ em bị bệnh tim bẩm sinh", "giúp bé bị hở hàm ếch", "trẻ vùng cao suy dinh dưỡng", "abc xyz"]:
    r = cl.post("/api/recommend", json={"query": q}).json()
    print("REC", q, "->", r["engine"], [(x["fund"]["id"], x["reason"]) for x in r["results"]])

# --- simulate flow
config.PAYMENT_MODE = "simulate"
d = cl.post("/api/donate", json={"fund_id": "vinacapital-foundation", "amount": 50000}).json(); print("donate", d)
print("sim page", cl.get(d["pay_url"]).status_code)
r = cl.post(d["pay_url"], follow_redirects=False); print("confirm", r.status_code, r.headers["location"])
o = cl.get("/api/orders/" + d["order_id"]).json(); print("order", o["status"], o["tx_hash"] is not None, o["chain_error"])
r = cl.post(d["pay_url"], follow_redirects=False); print("double confirm ok?", cl.get("/api/orders/" + d["order_id"]).json()["tx_hash"] == o["tx_hash"])

# --- MoMo IPN with signature
config.PAYMENT_MODE = "momo"; config.MOMO_ACCESS_KEY = "AK"; config.MOMO_SECRET_KEY = "SK"; config.MOMO_PARTNER_CODE = "PC"
# create order directly (no network): patch create_payment
momo.create_payment = lambda oid, amt, info, extra="": {"resultCode": 0, "payUrl": "https://test-payment.momo.vn/x"}
d2 = cl.post("/api/donate", json={"fund_id": "vinacapital-foundation", "amount": 20000}).json(); print("donate2", d2["pay_url"])
ipn = {"partnerCode": "PC", "orderId": d2["order_id"], "requestId": d2["order_id"], "amount": 20000, "orderInfo": "x",
       "orderType": "momo_wallet", "transId": 4088878653, "resultCode": 0, "message": "Thành công.", "payType": "qr",
       "responseTime": 1721720663942, "extraData": ""}
bad = dict(ipn, signature="00"); print("bad sig", cl.post("/api/momo/ipn", json=bad).status_code)
ipn["signature"] = momo.sign_result(ipn)
print("ipn", cl.post("/api/momo/ipn", json=ipn).status_code)
o2 = cl.get("/api/orders/" + d2["order_id"]).json(); print("order2", o2["status"], o2["momo_trans_id"], bool(o2["tx_hash"]))
# return URL replay (idempotent)
q = {k: str(v) for k, v in ipn.items()}
r = cl.get("/api/momo/return", params=q, follow_redirects=False); print("return", r.status_code, r.headers["location"])
# amount tampering
d3 = cl.post("/api/donate", json={"fund_id": "operation-smile-vietnam", "amount": 100000}).json()
t = dict(ipn, orderId=d3["order_id"], requestId=d3["order_id"], amount=1000, transId=1); t["signature"] = momo.sign_result(t)
cl.post("/api/momo/ipn", json=t); print("tamper ->", cl.get("/api/orders/" + d3["order_id"]).json()["status"])

# --- disbursement + ledger + summary
print("disb bad token", cl.post("/api/disbursements", json={"admin_token": "x", "fund_id": "vinacapital-foundation", "amount": 30000, "purpose": "Mua thuốc", "evidence": "hoadon"}).status_code)
print("disb", cl.post("/api/disbursements", json={"admin_token": config.ADMIN_TOKEN, "fund_id": "vinacapital-foundation", "amount": 30000, "purpose": "Mua thuốc sau mổ", "evidence": "hoadon-001.jpg"}).json()["tx_hash"] is not None)
L = cl.get("/api/ledger").json(); print("ledger", len(L["donations"]), L["totals"])
print("summary", cl.get("/api/funds/vinacapital-foundation/summary").json())
