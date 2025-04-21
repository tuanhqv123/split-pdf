# PDF Splitter Tool

Công cụ đơn giản để chia nhỏ file PDF theo trang.

## Tính năng

- Tải lên PDF từ máy tính hoặc URL (bao gồm cả Google Drive)
- Chia PDF theo nhiều khoảng trang khác nhau (ví dụ: 1-5,8-10,15-20)
- Cung cấp API webhook để tích hợp với các hệ thống khác
- Hỗ trợ cả web UI và API endpoint

## Cài đặt

```bash
# Clone repository (nếu bạn sử dụng Git)
git clone <repository-url>
cd split-pdf

# Cài đặt các thư viện cần thiết
pip install -r requirements.txt
```

## Chạy ứng dụng Web UI (Streamlit)

```bash
streamlit run app.py
```

Ứng dụng sẽ chạy trên trình duyệt tại địa chỉ: http://localhost:8501

## Chạy API Server (FastAPI)

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

API server sẽ chạy tại: http://localhost:8000

Bạn có thể truy cập tài liệu API tự động tại: http://localhost:8000/docs

## Sử dụng API (Webhook)

API cung cấp hai endpoint chính để xử lý việc chia nhỏ PDF:

### 1. Chia PDF từ URL

**Endpoint**: `/split-pdf-url/`

**Method**: POST

**Form Data**:

- `url`: URL của file PDF (hỗ trợ cả Google Drive)
- `ranges`: Các khoảng trang cần chia (ví dụ: "1-5,8-10,15-20")

**Ví dụ sử dụng cURL**:

```bash
curl -X POST "http://localhost:8000/split-pdf-url/" \
  -F "url=https://example.com/sample.pdf" \
  -F "ranges=1-5,8-10"
```

### 2. Chia PDF từ file tải lên

**Endpoint**: `/split-pdf-upload/`

**Method**: POST

**Form Data**:

- `file`: File PDF tải lên
- `ranges`: Các khoảng trang cần chia (ví dụ: "1-5,8-10,15-20")

**Ví dụ sử dụng cURL**:

```bash
curl -X POST "http://localhost:8000/split-pdf-upload/" \
  -F "file=@/path/to/your/file.pdf" \
  -F "ranges=1-5,8-10"
```

### Kết quả trả về

API sẽ trả về JSON với các thông tin sau:

```json
{
  "message": "Successfully split PDF into 2 files.",
  "total_pages": 20,
  "files": [
    {
      "range": "1-5",
      "download_url": "http://localhost:8000/download/split_1-5_abc123.pdf",
      "filename": "split_1-5.pdf"
    },
    {
      "range": "8-10",
      "download_url": "http://localhost:8000/download/split_8-10_def456.pdf",
      "filename": "split_8-10.pdf"
    }
  ]
}
```

### 3. Tải xuống file đã chia

**Endpoint**: `/download/{filename}`

**Method**: GET

Link tải được cung cấp trong kết quả của API chia PDF.

## Triển khai lên Internet

Dưới đây là hướng dẫn triển khai lên các nền tảng phổ biến:

### 1. Triển khai Streamlit UI lên Streamlit Cloud

1. Đẩy code của bạn lên GitHub repository
2. Đăng ký tài khoản tại [Streamlit Cloud](https://streamlit.io/cloud)
3. Kết nối với GitHub repository của bạn
4. Chọn file `app.py` làm file chính để triển khai

### 2. Triển khai API lên Render

1. Đăng ký tài khoản tại [Render](https://render.com)
2. Tạo một "Web Service" mới và kết nối với repository của bạn
3. Cấu hình như sau:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn api:app --host 0.0.0.0 --port $PORT`
4. Thêm biến môi trường `BASE_URL` với giá trị là URL của dịch vụ Render của bạn

### 3. Triển khai lên Heroku

1. Tạo file `Procfile` với nội dung:

```
web: uvicorn api:app --host=0.0.0.0 --port=$PORT
```

2. Đẩy code lên Heroku:

```bash
heroku create your-app-name
git push heroku main
```

3. Thêm biến môi trường `BASE_URL` với giá trị là URL của ứng dụng Heroku của bạn:

```bash
heroku config:set BASE_URL=https://your-app-name.herokuapp.com
```

## Lưu ý

- Các file đã chia sẽ được lưu trữ tạm thời trong 1 giờ, sau đó sẽ bị xóa tự động
- Đối với URL từ Google Drive, file phải được chia sẻ công khai với "Anyone with the link"
- Khi triển khai, hãy đảm bảo thiết lập biến môi trường `BASE_URL` đúng với domain của bạn
