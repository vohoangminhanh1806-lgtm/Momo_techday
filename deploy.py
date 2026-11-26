"""Deploy DonationLedger lên Polygon Amoy testnet.

Cách dùng (từ thư mục gốc dự án):
    python contracts/deploy.py
Yêu cầu: backend/.env đã có PRIVATE_KEY (ví có POL testnet từ faucet).
In ra CONTRACT_ADDRESS để dán vào backend/.env.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

rpc = os.getenv("POLYGON_RPC_URL", "https://rpc-amoy.polygon.technology")
chain_id = int(os.getenv("CHAIN_ID", "80002"))
pk = os.getenv("PRIVATE_KEY", "").strip()
if not pk:
    sys.exit("Thiếu PRIVATE_KEY trong backend/.env")

compiled = json.loads((ROOT / "contracts" / "DonationLedger.json").read_text(encoding="utf-8"))
w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 60}))
if not w3.is_connected():
    sys.exit(f"Không kết nối được RPC: {rpc}")
acct = w3.eth.account.from_key(pk)
balance = w3.eth.get_balance(acct.address)
print("Ví deploy:", acct.address, "| số dư:", Web3.from_wei(balance, "ether"), "POL")
if balance == 0:
    sys.exit("Ví chưa có POL testnet. Lấy tại faucet: https://faucet.polygon.technology/")

Contract = w3.eth.contract(abi=compiled["abi"], bytecode=compiled["bytecode"])
base = w3.eth.get_block("latest")["baseFeePerGas"]
prio = max(w3.eth.max_priority_fee, Web3.to_wei(30, "gwei"))
tx = Contract.constructor().build_transaction({
    "from": acct.address,
    "nonce": w3.eth.get_transaction_count(acct.address),
    "chainId": chain_id,
    "maxPriorityFeePerGas": prio,
    "maxFeePerGas": base * 2 + prio,
})
signed = acct.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print("Đang chờ xác nhận… tx:", tx_hash.hex())
receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
explorer = os.getenv("EXPLORER_URL", "https://amoy.polygonscan.com").rstrip("/")
print("\n✅ Deploy xong!")
print("CONTRACT_ADDRESS=" + receipt["contractAddress"])
print("Xem:", f"{explorer}/address/{receipt['contractAddress']}")
