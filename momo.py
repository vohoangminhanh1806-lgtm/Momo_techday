"""Tích hợp Cổng thanh toán MoMo (API v2, môi trường test).

Tài liệu: https://developers.momo.vn  (mục "Cổng thanh toán" → "Thanh toán một lần").
Chữ ký = HMAC-SHA256(secretKey, chuỗi raw các tham số xếp theo a-z).
"""
import hashlib
import hmac

import httpx

import config


def _sign(raw: str) -> str:
    return hmac.new(config.MOMO_SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()


def create_payment(order_id: str, amount: int, order_info: str, extra_data: str = "") -> dict:
    """Tạo yêu cầu thanh toán. Trả về JSON của MoMo (có payUrl, deeplink, qrCodeUrl)."""
    request_id = order_id
    ipn_url = f"{config.PUBLIC_BASE_URL}/api/momo/ipn"
    redirect_url = f"{config.APP_BASE_URL}/api/momo/return"
    raw = (
        f"accessKey={config.MOMO_ACCESS_KEY}&amount={amount}&extraData={extra_data}"
        f"&ipnUrl={ipn_url}&orderId={order_id}&orderInfo={order_info}"
        f"&partnerCode={config.MOMO_PARTNER_CODE}&redirectUrl={redirect_url}"
        f"&requestId={request_id}&requestType={config.MOMO_REQUEST_TYPE}"
    )
    body = {
        "partnerCode": config.MOMO_PARTNER_CODE,
        "accessKey": config.MOMO_ACCESS_KEY,
        "requestId": request_id,
        "amount": str(amount),
        "orderId": order_id,
        "orderInfo": order_info,
        "redirectUrl": redirect_url,
        "ipnUrl": ipn_url,
        "extraData": extra_data,
        "requestType": config.MOMO_REQUEST_TYPE,
        "signature": _sign(raw),
        "lang": "vi",
    }
    r = httpx.post(config.MOMO_ENDPOINT, json=body, timeout=30)
    data = r.json()
    if data.get("resultCode") != 0:
        raise RuntimeError(f"MoMo từ chối: {data.get('resultCode')} - {data.get('message')}")
    return data


IPN_FIELDS = [
    "accessKey", "amount", "extraData", "message", "orderId", "orderInfo", "orderType",
    "partnerCode", "payType", "requestId", "responseTime", "resultCode", "transId",
]


def verify_result_signature(params: dict) -> bool:
    """Kiểm tra chữ ký của IPN (POST) hoặc redirect (GET query) do MoMo gửi về."""
    values = {k: params.get(k, "") for k in IPN_FIELDS}
    values["accessKey"] = config.MOMO_ACCESS_KEY
    raw = "&".join(f"{k}={values[k]}" for k in IPN_FIELDS)
    expected = _sign(raw)
    return hmac.compare_digest(expected, str(params.get("signature", "")))


def sign_result(params: dict) -> str:
    """Dùng cho chế độ giả lập và cho test: tạo chữ ký giống MoMo."""
    values = {k: params.get(k, "") for k in IPN_FIELDS}
    values["accessKey"] = config.MOMO_ACCESS_KEY
    return _sign("&".join(f"{k}={values[k]}" for k in IPN_FIELDS))
