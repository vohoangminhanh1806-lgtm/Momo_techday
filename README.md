# Kết Nối Thiện Nguyện — AI × MoMo × Blockchain

Demo cho cuộc thi MoMo TechDay 2026.

- Người dùng mô tả mong muốn bằng lời, ví dụ "Bé bị tim bẩm sinh cần phẫu thuật". **AI** đề xuất quỹ phù hợp trong 4 quỹ hỗ trợ trẻ em và nêu lý do.
- Người dùng quyên góp qua **MoMo**.
- Mỗi khoản tiền vào (quyên góp) và tiền ra (quỹ chi) được ghi lên **Polygon Amoy testnet**, kèm link Polygonscan để ai cũng kiểm tra được.
- **AI** đọc dòng tiền và tóm tắt cho người không biết blockchain.

```
Người dùng ──hỏi──> AI đề xuất quỹ ──chọn──> MoMo (sandbox) ──IPN/redirect──> Backend ──recordDonation──> Polygon Amoy
                                                                                     └──> Trang "Minh bạch dòng tiền" + AI tóm tắt
```

## Cấu trúc thư mục

| Đường dẫn | Nội dung |
| --- | --- |
| `backend/main.py` | API FastAPI: đề xuất quỹ, tạo thanh toán, nhận IPN, sổ cái, ghi khoản chi |
| `backend/ai.py` | AI: đề xuất quỹ + tóm tắt dòng tiền (LLM; tự chuyển sang bộ nhãn nhu cầu nếu LLM lỗi) |
| `backend/funds.py` | Đọc danh sách quỹ từ Excel, gắn nhãn nhu cầu (tim bẩm sinh, hàm ếch, dinh dưỡng...) |
| `backend/momo.py` | Ký và gọi API Cổng thanh toán MoMo v2, kiểm tra chữ ký IPN |
| `backend/chain.py` | Gọi hợp đồng thông minh qua web3.py |
| `backend/data/funds.xlsx` | **Danh sách quỹ** — file Excel của đội (4 quỹ hỗ trợ trẻ em), server đọc trực tiếp |
| `contracts/DonationLedger.sol` | Hợp đồng: `recordDonation`, `recordDisbursement`, tổng tiền vào/ra |
| `contracts/DonationLedger.json` | ABI + bytecode đã biên dịch sẵn (solc 0.8.24) |
| `contracts/deploy.py` | Script deploy lên Amoy |
| `frontend/index.html` | Giao diện (1 file, không cần build) |
| `tests/test_local.py` | Test toàn bộ luồng trên blockchain giả lập |

---

## 1. Chạy nhanh trong 5 phút (chế độ giả lập)

Chế độ này chưa cần khóa MoMo, ví blockchain hay API key AI. Dùng để cả đội xem giao diện ngay.

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
uvicorn main:app --reload --port 8000
```

Mở http://localhost:8000 rồi thử hỏi AI → Quyên góp → bấm "Xác nhận thanh toán" (giả lập) → xem tab "Minh bạch dòng tiền".

Ba nhãn trên đầu trang cho biết hệ thống đang ở chế độ nào (MoMo thật hay giả lập, đã có blockchain chưa, AI là LLM hay từ khóa).

---

## 2. Bật AI thật (LLM)

Dùng được bất kỳ API nào tương thích chuẩn OpenAI. Điền vào `backend/.env`, ví dụ với Google Gemini (có gói miễn phí, lấy key tại Google AI Studio):

```
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_API_KEY=<key của bạn>
LLM_MODEL=gemini-2.5-flash
```

Khởi động lại server. Nếu LLM lỗi lúc demo (mất mạng, hết quota), hệ thống tự chuyển sang bộ đề xuất theo từ khóa, nên buổi demo không bị dừng giữa chừng.

**Chống AI bịa:** backend chỉ chấp nhận `fund_id` có trong file Excel. Quỹ do AI tự nghĩ ra sẽ bị loại.

---

## 3. Bật blockchain (Polygon Amoy testnet)

1. Cài MetaMask và **tạo một ví mới chỉ để demo**. Không dùng ví có tiền thật.
2. Thêm mạng Polygon Amoy vào MetaMask: RPC `https://rpc-amoy.polygon.technology`, Chain ID `80002`, ký hiệu `POL`, explorer `https://amoy.polygonscan.com`.
3. Lấy POL testnet miễn phí tại https://faucet.polygon.technology/.
4. MetaMask → Account details → Show private key → dán vào `PRIVATE_KEY=` trong `backend/.env`.
5. Deploy hợp đồng (chạy từ thư mục gốc dự án):
   ```bash
   python contracts/deploy.py
   ```
   Script sẽ in ra dòng `CONTRACT_ADDRESS=0x...`. Dán dòng này vào `backend/.env`, rồi khởi động lại server.

   *Cách khác:* mở https://remix.ethereum.org, dán `DonationLedger.sol`, biên dịch, rồi Deploy với "Injected Provider – MetaMask". Copy địa chỉ hợp đồng vào `.env`.

Từ đây, mỗi khoản quyên góp thành công sẽ có link Polygonscan. Ví dùng để deploy chính là ví được phép ghi (recorder).

---

## 4. Bật MoMo sandbox

1. Lấy khóa test (`partnerCode`, `accessKey`, `secretKey`) trên trang dành cho developer của MoMo: https://developers.momo.vn. Mục "Cổng thanh toán" có hướng dẫn và bộ khóa test dùng cho code mẫu.
2. Điền vào `backend/.env`:
   ```
   PAYMENT_MODE=momo
   MOMO_PARTNER_CODE=...
   MOMO_ACCESS_KEY=...
   MOMO_SECRET_KEY=...
   ```
3. **IPN cần URL công khai.** MoMo gọi về server của bạn, mà `localhost` thì MoMo không gọi tới được. Tạo URL công khai bằng ngrok:
   ```bash
   ngrok http 8000
   ```
   Copy URL dạng `https://xxxx.ngrok-free.app` vào `PUBLIC_BASE_URL=`, rồi khởi động lại server.
4. Thanh toán thử bằng app MoMo bản test (hoặc trang test của MoMo) theo hướng dẫn trên developers.momo.vn.

**Phòng hờ:** khi MoMo chuyển trình duyệt về `/api/momo/return`, backend cũng kiểm tra chữ ký và ghi nhận giao dịch. Vì vậy dù IPN chưa tới (ngrok lỗi), đơn vẫn được xử lý. Mỗi đơn chỉ xử lý một lần.

**Nếu MoMo sandbox trục trặc ngay lúc thuyết trình:** đổi `PAYMENT_MODE=simulate` để demo tiếp. Trang giả lập có ghi rõ "không trừ tiền thật". Nên nói thẳng với ban giám khảo là đang dùng chế độ dự phòng.

---

## 5. Quỹ ghi khoản chi (tiền ra)

Trong bản demo, khoản chi được ghi qua API (chưa có giao diện cho quỹ). Chỉ mã hash của chứng từ được ghi lên chuỗi, còn bản thân chứng từ thì không.

```bash
curl -X POST http://localhost:8000/api/disbursements -H "Content-Type: application/json" \
  -d '{"admin_token":"doi-ma-nay","fund_id":"quy-trai-tim-be-nho","amount":30000,"purpose":"Mua thuốc sau mổ cho bé A","evidence":"hoa-don-001.jpg"}'
```

Nhớ đổi `ADMIN_TOKEN` trong `.env` trước khi demo.

---

## 6. Dữ liệu quỹ: sửa trực tiếp file Excel

Server đọc thẳng `backend/data/funds.xlsx` (sheet đầu tiên). Khi file thay đổi, server tự đọc lại, không cần chép dữ liệu sang file khác.

**Các cột được nhận theo tên tiêu đề**, nên đổi thứ tự cột cũng không sao:

| Cột | Bắt buộc | Dùng để |
| --- | --- | --- |
| Tên Quỹ / Tổ chức | Có | Tên hiển thị. Phần trong ngoặc được bỏ khi hiện tên ngắn |
| Lĩnh vực hỗ trợ chính | Có | AI đọc cột này để đề xuất. Viết càng cụ thể (bệnh gì, chương trình gì), AI đề xuất càng đúng |
| Phạm vi hỗ trợ | Có | Khu vực hoạt động. Chữ "miền núi, vùng sâu vùng xa" giúp quỹ được ưu tiên khi người dùng hỏi về vùng cao |
| Thông tin nền tảng | Không | Đưa cho LLM làm ngữ cảnh |
| Website chính thức, Trang dự án trên MoMo | Không | Trả về trong API `/api/funds` (`website`, `momo_url`) |
| ID | Không | Mã quỹ cố định. Không có cột này thì mã được tạo từ tên, ví dụ `quy-vi-tam-voc-viet` |
| Sao kê (link) | Không | Có link thì giao diện hiện nhãn "Có công khai sao kê" |
| Địa chỉ hợp đồng | Không | Dành cho quỹ đã có hợp đồng riêng |

**Lưu ý quan trọng:** mã quỹ được ghi lên blockchain. Sau khi đã có giao dịch, **đừng đổi tên quỹ**. Nếu buộc phải đổi, thêm cột `ID` và giữ nguyên mã cũ.

Mã của 4 quỹ hiện tại: `quy-tu-thien-nang-buoc-tuoi-tho`, `operation-smile-vietnam`, `vinacapital-foundation`, `quy-vi-tam-voc-viet`.

**Muốn AI hiểu thêm nhu cầu mới** (ví dụ "ung thư", "tự kỷ"): thêm một dòng vào `NEED_TAGS` trong `backend/funds.py`. Từ khóa viết không dấu. Riêng các từ dễ nhầm khi bỏ dấu thì giữ dấu, ví dụ "mắt" và "mặt", "mổ" và "mồ côi".

Câu hỏi thử và kết quả (chế độ từ khóa, chưa có LLM):

| Câu hỏi | Quỹ được đề xuất |
| --- | --- |
| Bé bị tim bẩm sinh cần phẫu thuật | Nâng Bước Tuổi Thơ, VinaCapital Foundation |
| Giúp bé bị hở hàm ếch | Operation Smile Vietnam, Nâng Bước Tuổi Thơ |
| Trẻ vùng cao suy dinh dưỡng | Quỹ Vì Tầm Vóc Việt |
| Học bổng cho nữ sinh dân tộc / em bé sinh non / trẻ mồ côi | VinaCapital Foundation |
| Trẻ bị bạo lực, xâm hại | Quỹ Vì Tầm Vóc Việt |
| Cứu trợ lũ lụt | (không có quỹ phù hợp → AI nói rõ là chưa tìm thấy) |

## 7. Kiểm tra

```bash
pip install "eth-tester[py-evm]"
python tests/test_local.py
```

Test chạy toàn bộ luồng trên một blockchain giả lập. Các trường hợp được kiểm tra:

- quyên góp → ghi lên chuỗi;
- chặn IPN sai chữ ký;
- chặn sửa số tiền;
- chặn ghi trùng một giao dịch MoMo;
- chặn ví lạ ghi vào sổ;
- ghi khoản chi, tổng tiền vào/ra đọc từ chuỗi, AI tóm tắt.

---

## 8. Kịch bản demo (video 2–3 phút)

1. Gõ: "Giúp bé bị hở hàm ếch" → AI đề xuất Operation Smile kèm lý do trích đúng chương trình của quỹ.
2. Chọn quỹ → 50.000đ → thanh toán MoMo → quay về trang, thấy "Đã ghi lên blockchain".
3. Bấm link Polygonscan → chỉ vào giao dịch thật trên chuỗi. Nhấn mạnh: không ai sửa được, kể cả đội phát triển.
4. Chạy lệnh curl ghi một khoản chi → mở tab "Minh bạch dòng tiền" → bấm "AI tóm tắt".
5. Kết: người dùng MoMo không cần biết blockchain, phần minh bạch do hệ thống tự làm.

## Giới hạn của bản demo (nên nói thẳng nếu ban giám khảo hỏi)

- Tiền thật đi qua MoMo. Blockchain chỉ lưu **bằng chứng** của khoản tiền, không giữ tiền.
- Khoản chi do quỹ tự khai. Blockchain bảo đảm khoản đã khai thì không sửa được, nhưng không bảo đảm quỹ khai đủ. Hướng phát triển: MoMo đối soát tự động khi quỹ chi qua ví MoMo.
- Đơn hàng lưu trong file JSON. Bản thật cần dùng database.
- Không lưu tên hay số điện thoại người quyên góp lên chuỗi.
