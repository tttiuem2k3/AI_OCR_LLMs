# Hướng dẫn cài đặt và sử dụng PaddleOCR

Tài liệu này hướng dẫn cài đặt PaddleOCR trong một môi trường Python độc lập và chạy chương trình OCR mẫu. Nội dung được viết cho PaddleOCR 3.x và nên được kiểm tra lại khi nâng cấp phiên bản lớn.

## 1. PaddleOCR là gì?

PaddleOCR là bộ công cụ OCR mã nguồn mở dựa trên PaddlePaddle. Một pipeline OCR thông thường gồm hai bước chính:

1. **Text Detection**: tìm vị trí các vùng chứa chữ trong ảnh.
2. **Text Recognition**: nhận diện nội dung văn bản trong từng vùng đã phát hiện.

Ngoài ra, pipeline có thể dùng thêm các mô-đun hiệu chỉnh hướng tài liệu, xoay dòng chữ và tiền xử lý tài liệu.

## 2. Yêu cầu môi trường

- Python 3.8 đến 3.12. Nên dùng Python 3.10 hoặc 3.11 để dễ tương thích thư viện.
- `pip` phiên bản mới.
- Windows, Linux hoặc macOS.
- Có thể chạy bằng CPU. Muốn dùng GPU cần cài đúng bản PaddlePaddle tương thích với CUDA và driver của máy.

Kiểm tra Python:

```powershell
python --version
python -m pip --version
```

## 3. Tạo môi trường ảo

Ví dụ trên Windows PowerShell:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
```

Linux hoặc macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

## 4. Cài PaddlePaddle

PaddleOCR sử dụng PaddlePaddle làm backend tính toán. Chỉ chọn một trong hai phương án CPU hoặc GPU.

### Phương án A: CPU

```powershell
python -m pip install paddlepaddle
```

### Phương án B: GPU

Không nên sao chép cố định một lệnh GPU nếu chưa biết phiên bản CUDA của máy. Hãy mở trang cài đặt PaddlePaddle chính thức, chọn hệ điều hành, Python, CUDA và cách cài đặt phù hợp, sau đó chạy lệnh được cung cấp.

Sau khi cài, kiểm tra PaddlePaddle:

```powershell
python -c "import paddle; print('PaddlePaddle:', paddle.__version__); paddle.utils.run_check()"
```

## 5. Cài PaddleOCR

Vì code mẫu dùng `PPStructureV3` cho OCR tài liệu, nên cài PaddleOCR kèm các phụ thuộc đầy đủ. PP-OCRv6 được hỗ trợ từ PaddleOCR 3.7, nên dùng bản `3.7` trở lên:

```powershell
python -m pip install --upgrade "paddleocr[all]>=3.7"
```

Nếu chỉ dùng OCR ảnh cơ bản bằng `PaddleOCR` thì có thể cài gói nhẹ hơn:

```powershell
python -m pip install --upgrade "paddleocr>=3.7"
```

Kiểm tra phiên bản:

```powershell
python -c "import paddleocr; print('PaddleOCR:', paddleocr.__version__)"
```

## 6. Chạy chương trình mẫu

File mẫu đi kèm:

```text
sample_paddleocr_extract.py
```

Chạy OCR bằng CPU:

```powershell
python sample_paddleocr_extract.py "D:\du_lieu\anh_can_ocr.jpg" --output "D:\du_lieu\ket_qua.txt"
```

Chạy OCR bằng GPU số 0:

```powershell
python sample_paddleocr_extract.py "D:\du_lieu\anh_can_ocr.jpg" --device gpu:0 --output "D:\du_lieu\ket_qua.txt"
```

Chạy bằng model local, không tải model online:

```powershell
python sample_paddleocr_extract.py "D:\du_lieu\anh_can_ocr.jpg" --device gpu --local-only `
  --det-model-dir "E:\Asoft\AI_BEM\BEM_AI_PROJECT\Models\PP-OCRv6_medium_det_infer" `
  --rec-model-dir "E:\Asoft\AI_BEM\BEM_AI_PROJECT\Models\PP-OCRv6_medium_rec_infer" `
  --layout-model-dir "E:\Asoft\AI_BEM\BEM_AI_PROJECT\Models\PP-DocLayout_plus-L_infer" `
  --output "D:\du_lieu\ket_qua.txt"
```

Chương trình sẽ:

1. Khởi tạo `PPStructureV3` với model detection `PP-OCRv6_medium_det`, recognition `PP-OCRv6_medium_rec` và layout `PP-DocLayout_plus-L`.
2. Dùng model local nếu truyền `--*-model-dir` và `--local-only`; nếu không, PaddleOCR có thể tải model từ nguồn chính thức ở lần chạy đầu tiên.
3. Chạy OCR cho file đầu vào.
4. Ghi văn bản đã nhận diện vào file `.txt`.
5. Ghi kết quả chi tiết dạng JSON vào thư mục `<tên-file-output>_details`.

## 7. Tùy chọn của chương trình mẫu

```text
python sample_paddleocr_extract.py INPUT [--output OUTPUT] [--device DEVICE]
                                    [--det-model-name NAME] [--rec-model-name NAME]
                                    [--layout-model-name NAME]
                                    [--det-model-dir DIR] [--rec-model-dir DIR]
                                    [--layout-model-dir DIR] [--local-only]
                                    [--visualize]
```

- `INPUT`: đường dẫn file ảnh hoặc tài liệu cần OCR.
- `--output`: file văn bản đầu ra. Mặc định là `<tên-file-input>_ocr.txt`.
- `--device`: `cpu`, `gpu`, `gpu:0`, `gpu:1`, ... Mặc định của file mẫu là `cpu`; production thường dùng `gpu`.
- `--det-model-name`: model detection, mặc định `PP-OCRv6_medium_det`.
- `--rec-model-name`: model recognition, mặc định `PP-OCRv6_medium_rec`.
- `--layout-model-name`: model layout, mặc định `PP-DocLayout_plus-L`.
- `--det-model-dir`, `--rec-model-dir`, `--layout-model-dir`: đường dẫn model local nếu không muốn tải model online.
- `--local-only`: đặt `PADDLE_PDX_MODEL_SOURCE=LOCAL` để chỉ dùng model local.
- `--visualize`: lưu thêm ảnh trực quan hóa kết quả OCR.

## 8. Lưu ý khi OCR tiếng Việt

- Với `PPStructureV3`, không dùng `lang="vi"`/`ocr_version` như API `PaddleOCR`; hãy chọn model recognition PP-OCRv6 multilingual, ví dụ `PP-OCRv6_medium_rec`.
- Ảnh đầu vào nên rõ, đủ sáng, ít nghiêng và có độ phân giải phù hợp.
- Model dựng sẵn phù hợp để chạy thử và làm baseline, nhưng không bảo đảm chính xác cho mọi loại tài liệu.
- Tài liệu có font đặc thù, ảnh camera, chữ nhỏ, dấu tiếng Việt bị mờ, biểu mẫu nội bộ hoặc bố cục cố định thường cần dữ liệu thực tế để đánh giá và fine-tune.
- Trước khi train, nên tạo tập kiểm thử đại diện và đo riêng độ chính xác detection, recognition và toàn pipeline.

## 9. Xử lý lỗi thường gặp

### Không import được `paddle`

Đảm bảo môi trường ảo đang được kích hoạt và đã cài `paddlepaddle` hoặc bản GPU tương ứng.

### Lỗi CUDA hoặc không nhận GPU

Kiểm tra driver NVIDIA, phiên bản CUDA được PaddlePaddle hỗ trợ và gói PaddlePaddle GPU đã cài. Có thể chuyển tạm sang CPU bằng `--device cpu` để xác nhận code hoạt động.

### Lần chạy đầu tiên chậm

Đây là hành vi bình thường khi PaddleOCR tải model về cache. Máy cần có kết nối mạng hoặc phải cấu hình đường dẫn model cục bộ.

### Kết quả tiếng Việt sai dấu

Kiểm tra model recognition đang dùng có phải `PP-OCRv6_medium_rec` hoặc model tiếng Việt đã fine-tune hay không. Nếu lỗi lặp lại trên dữ liệu nghiệp vụ, xem tài liệu `02_MO_HINH_OCR_TIENG_VIET.md` để lập kế hoạch fine-tune.

## 10. Tài liệu chính thức

- PaddleOCR Installation: <https://www.paddleocr.ai/main/en/version3.x/installation.html>
- General OCR Pipeline: <https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html>
- PaddleOCR GitHub: <https://github.com/PaddlePaddle/PaddleOCR>
- PaddlePaddle Installation: <https://www.paddlepaddle.org.cn/install/quick>
