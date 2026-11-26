"""Ghi và đọc dữ liệu trên hợp đồng DonationLedger (Polygon Amoy).

Nếu chưa cấu hình PRIVATE_KEY + CONTRACT_ADDRESS, chạy ở chế độ "offline":
không ghi lên chuỗi, giao diện sẽ hiện rõ "chưa ghi lên blockchain".
"""
import json
import threading

from web3 import Web3

import config

_lock = threading.Lock()  # tránh trùng nonce khi nhiều callback đến cùng lúc


class Ledger:
    def __init__(self, w3: Web3 | None = None, private_key: str = "", address: str = "",
                 chain_id: int | None = None):
        self.private_key = private_key or config.PRIVATE_KEY
        self.address = address or config.CONTRACT_ADDRESS
        self.enabled = bool(self.private_key and self.address)
        self.w3 = w3
        self.chain_id = chain_id or config.CHAIN_ID
        if not self.enabled:
            return
        if self.w3 is None:
            self.w3 = Web3(Web3.HTTPProvider(config.POLYGON_RPC_URL, request_kwargs={"timeout": 60}))
        abi = json.loads(config.CONTRACT_JSON.read_text(encoding="utf-8"))["abi"]
        self.contract = self.w3.eth.contract(address=Web3.to_checksum_address(self.address), abi=abi)
        self.account = self.w3.eth.account.from_key(self.private_key)

    @property
    def mode(self) -> str:
        return "polygon-amoy" if self.enabled else "offline"

    def tx_url(self, tx_hash: str) -> str:
        return f"{config.EXPLORER_URL}/tx/{tx_hash}"

    def contract_url(self) -> str:
        return f"{config.EXPLORER_URL}/address/{self.address}" if self.enabled else ""

    def _fees(self) -> dict:
        block = self.w3.eth.get_block("latest")
        base = block.get("baseFeePerGas")
        if base is None:  # mạng không hỗ trợ EIP-1559
            return {"gasPrice": self.w3.eth.gas_price}
        # Polygon yêu cầu phí ưu tiên tối thiểu ~25 gwei
        try:
            prio = max(self.w3.eth.max_priority_fee, Web3.to_wei(30, "gwei"))
        except Exception:
            prio = Web3.to_wei(30, "gwei")
        return {"maxPriorityFeePerGas": prio, "maxFeePerGas": base * 2 + prio}

    def _send(self, fn) -> str:
        with _lock:
            tx = fn.build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "chainId": self.chain_id,
                **self._fees(),
            })
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt["status"] != 1:
            raise RuntimeError("Giao dịch blockchain thất bại")
        return "0x" + bytes(receipt["transactionHash"]).hex().removeprefix("0x")

    def record_donation(self, fund_id: str, amount: int, momo_txn_id: str) -> str | None:
        if not self.enabled:
            return None
        return self._send(self.contract.functions.recordDonation(fund_id, int(amount), str(momo_txn_id)))

    def record_disbursement(self, fund_id: str, amount: int, purpose: str, evidence_hash: bytes) -> str | None:
        if not self.enabled:
            return None
        return self._send(self.contract.functions.recordDisbursement(fund_id, int(amount), purpose, evidence_hash))

    def totals(self, fund_id: str) -> dict | None:
        """Đọc tổng tiền vào/ra trực tiếp từ chuỗi (không qua database)."""
        if not self.enabled:
            return None
        return {
            "in": self.contract.functions.totalIn(fund_id).call(),
            "out": self.contract.functions.totalOut(fund_id).call(),
        }
