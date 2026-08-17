# Cài môi trường Windows Server GPU bằng uv

Tài liệu này dùng cho Windows Server có GPU NVIDIA. Mục tiêu là tạo `.venv` nằm ngay trong dự án và cài thư viện bằng các lệnh dễ copy/paste trong terminal VS Code.

## 1. Thư mục không cần deploy
Không copy `.venv` từ máy test lên server mới. Hãy tạo `.venv` trực tiếp trên server bằng `uv`.

## 2. Mở terminal tại thư mục dự án

Trong VS Code, mở đúng thư mục chứa `run_server.py`, sau đó chạy:

```powershell
Test-Path .\run_server.py
nvidia-smi
```

Nếu `Test-Path` trả về `True` và `nvidia-smi` thấy GPU NVIDIA thì tiếp tục.

## 3. Cài uv nếu server chưa có

```powershell
Set-ExecutionPolicy -Scope Process Bypass
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Đóng terminal, mở terminal mới rồi kiểm tra:

```powershell
uv --version
```

## 4. Tạo môi trường `.venv`

Dự án hiện chạy theo Python 3.11, nên dùng Python 3.11 cho server.

```powershell
uv python install 3.11
uv venv --python 3.11 --relocatable --seed .venv
.\.venv\Scripts\python.exe --version
```

Từ đây trở đi không cần activate môi trường. Luôn dùng `\.venv\Scripts\python.exe` hoặc `uv pip --python .\.venv\Scripts\python.exe`.

## 5. Cài toàn bộ thư viện cần thiết

Copy nguyên khối lệnh này vào terminal VS Code:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade paddlepaddle-gpu==3.3.1 `
  -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

.\.venv\Scripts\python.exe -m pip install --upgrade --force-reinstall `
  "paddlepaddle-gpu==3.3.1" `
  --index-url https://pypi.org/simple `
  --extra-index-url https://www.paddlepaddle.org.cn/packages/stable/cu126/ `
  --retries 10 `
  --timeout 120

.\.venv\Scripts\python.exe -m pip install --upgrade `
  "paddleocr[all]==3.7.0" `
  "paddlex==3.7.2"

uv pip install `
  --python .\.venv\Scripts\python.exe `
  "torch==2.6.0+cu126" `
  "torchvision==0.21.0+cu126" `
  "torchaudio==2.6.0+cu126" `
  --index https://download.pytorch.org/whl/cu126

uv pip install `
  --python .\.venv\Scripts\python.exe `
  -r .\docs\requirements_server_windows_gpu.txt
```

Ghi chú ngắn:

- Paddle dùng CUDA 12.9 theo đúng lệnh bạn chọn.
- PyTorch đang dùng CUDA 12.6 vì dự án hiện đã chạy/test với bộ `torch==2.6.0+cu126`.
- Nếu sau này muốn đồng bộ PyTorch CUDA 12.9, cần nâng PyTorch sang bản mới hơn và test lại LLM.
- `requirements_server_windows_gpu.txt` chỉ chứa thư viện mã nguồn đang dùng trực tiếp, không phải toàn bộ môi trường test.

## 6. Kiểm tra sau khi cài

Copy nguyên khối này để kiểm tra nhanh:

```powershell
.\.venv\Scripts\python.exe -c "import paddle; print('Paddle:', paddle.__version__); print('Paddle CUDA:', paddle.is_compiled_with_cuda()); print('Paddle GPU count:', paddle.device.cuda.device_count())"

.\.venv\Scripts\python.exe -c "import torch; print('Torch:', torch.__version__); print('Torch CUDA:', torch.version.cuda); print('Torch CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE')"

.\.venv\Scripts\python.exe -m pip check
```

Kết quả mong muốn:

- Paddle CUDA là `True`.
- Torch CUDA available là `True`.
- `pip check` không báo lỗi dependency.

## 7. Tạo file `.env`

Tạo file `.env` cạnh `run_server.py` với nội dung tối thiểu:

```dotenv
HOST=0.0.0.0
PORT=4444
LOG_LEVEL=info

GPU_INDEX=0
CUDA_GPU_INDEX=0
REQUIRE_CUDA=true
REQUIRE_CUDA_GPU0=false
DEVICE=gpu

PADDLEX_HOME=Cache
LLM_HF_HOME=Models
LLM_LOCAL_MODELS_DIR=Models
LLM_AUTOLOAD_SPECIAL=false
```

Không thêm `PROJECT_ROOT=D:\...` vào `.env`. Mã nguồn tự nhận thư mục gốc theo vị trí hiện tại của dự án.

Sau khi kiểm tra xong model LLM, nếu muốn server tự load model khi start thì đổi:

```dotenv
LLM_AUTOLOAD_SPECIAL=true
```

## 8. Kiểm tra thư mục model và dữ liệu

```powershell
New-Item -ItemType Directory -Force -Path .\Cache, .\Logs, .\Outputs | Out-Null
Get-ChildItem .\Models -Force
```

`Models\` phải được copy riêng từ máy test nếu server cần chạy model local. Thư mục này không được Git quản lý.

## 9. Chạy server

```powershell
.\.venv\Scripts\python.exe .\run_server.py
```

Mở terminal thứ hai để kiểm tra:

```powershell
Invoke-RestMethod http://127.0.0.1:4444/ping
```

Nếu cần cho máy khác truy cập port `4444`, mở PowerShell quyền Administrator và chạy:

```powershell
New-NetFirewallRule `
  -DisplayName "PaddleOCR API 4444" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 4444 `
  -Action Allow
```

## 10. Khi di chuyển dự án sang thư mục khác

Nếu chỉ đổi vị trí thư mục trên cùng server:

1. Dừng server.
2. Di chuyển cả thư mục dự án, bao gồm `.venv`.
3. Mở lại thư mục mới bằng VS Code.
4. Chạy lại:

```powershell
.\.venv\Scripts\python.exe .\run_server.py
```

Nếu `.venv` lỗi sau khi di chuyển, tạo lại môi trường:

```powershell
Rename-Item -LiteralPath .\.venv -NewName ".venv_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
uv venv --python 3.11 --relocatable --seed .venv
```

Sau đó chạy lại mục 5 để cài thư viện.

## 11. Checklist nhanh

- `nvidia-smi` nhận GPU.
- `.venv\Scripts\python.exe --version` là Python 3.11.
- Paddle CUDA là `True`.
- Torch CUDA available là `True`.
- `Models\` đã có đủ model production.
- `.env` không chứa `PROJECT_ROOT` tuyệt đối.
- Server chạy được bằng `.\.venv\Scripts\python.exe .\run_server.py`.
- Endpoint `/ping` phản hồi thành công.
