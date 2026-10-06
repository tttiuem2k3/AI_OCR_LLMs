# Hướng dẫn training PP-OCRv6 nhận diện tiếng Việt trên Kaggle

Tài liệu này hướng dẫn fine-tune **model Text Recognition `PP-OCRv6_medium_rec`** để nhận diện văn bản tiếng Việt. Quy trình được tổng hợp từ:

- `train-code-paddleocr.ipynb` trong cùng thư mục.
- `Training_INF.txt`, chứa đường dẫn notebook Kaggle tham khảo.

> Phạm vi của hướng dẫn là training **Text Recognition**. Model Text Detection không được train lại; khi suy luận sẽ dùng model detection chính thức `PP-OCRv6_medium_det`.

## 1. Kết quả đầu ra

Sau khi hoàn thành, cần thu được:

```text
/kaggle/working/PaddleOCR/Model/vi_PP-OCRv6_medium_rec/
├── best_accuracy.pdparams
├── best_accuracy.pdopt
├── best_accuracy.states
├── latest.pdparams
├── latest.pdopt
└── latest.states

/kaggle/working/PP-OCRv6_medium_rec_infer/
├── inference.json hoặc inference.yml
└── inference.pdiparams
```

Trong đó:

- `best_accuracy.*`: checkpoint có metric validation tốt nhất.
- `latest.*`: checkpoint mới nhất, dùng để tiếp tục training.
- `PP-OCRv6_medium_rec_infer`: model inference dùng trong ứng dụng.

## 2. Môi trường training

Quy trình mẫu chạy trên **Kaggle Notebook**.

Cấu hình notebook:

1. Bật GPU trong `Settings > Accelerator`.
2. Bật Internet để clone PaddleOCR và tải pretrained model.
3. Add các Kaggle Dataset cần thiết.
4. Nên chạy từ kernel mới để tránh xung đột package đã cài trước đó.

Notebook tham khảo được ghi trong `Training_INF.txt`:

```text
https://www.kaggle.com/code/thnhtrn412/train-paddleocr-24072026
```

## 3. Dataset cần chuẩn bị

Notebook mẫu sử dụng các dataset sau:

| Mục đích | Đường dẫn Kaggle mẫu |
|---|---|
| Dữ liệu train/validation | `/kaggle/input/datasets/thnhtrn412/data-ocr-train-v4/Data_OCR_Train` |
| File PDF/ảnh để test | `/kaggle/input/datasets/thnhtrn412/data-test-ocr` |
| Từ điển ký tự | `/kaggle/input/datasets/ttt2k3/dict-for-ocr/custom_dict.txt` |
| Checkpoint để resume | `/kaggle/input/datasets/thnhtrc/pp-ocrv6-rec-checkpoint` |

Cấu trúc dữ liệu recognition đề xuất:

```text
Data_OCR_Train/
├── images/
│   ├── image_000001.jpg
│   ├── image_000002.jpg
│   └── ...
├── Train.txt
└── Val.txt
```

Mỗi dòng trong `Train.txt` hoặc `Val.txt` có định dạng:

```text
images/image_000001.jpg<TAB>Nội dung tiếng Việt chính xác
images/image_000002.jpg<TAB>Cộng hòa xã hội chủ nghĩa Việt Nam
```

`<TAB>` phải là ký tự tab thật, không phải chuỗi hai ký tự `\t`.

Yêu cầu dữ liệu:

- File label lưu bằng UTF-8 hoặc UTF-8 BOM.
- Ảnh phải tồn tại tương ứng với đường dẫn trong label.
- Nhãn phải giữ đúng chữ hoa, chữ thường, dấu tiếng Việt, chữ số và ký hiệu.
- Mọi ký tự trong label phải tồn tại trong `custom_dict.txt`.
- Với cấu hình bên dưới, nhãn không nên dài quá `25` ký tự. Nếu dữ liệu dài hơn, phải tăng `max_text_length` và kiểm tra lại bộ nhớ GPU.
- Không để các ảnh cùng nguồn xuất hiện đồng thời trong tập train và validation.

## 4. Cài PaddlePaddle và PaddleOCR

Notebook gốc dùng:

- PaddlePaddle GPU `3.3.1`.
- PaddleOCR source tag `v3.7.0`.
- CUDA package `cu130`.

Chạy cell sau:

```python
import sys

PYTHON = sys.executable

# Xóa các phiên bản có thể gây xung đột.
!{PYTHON} -m pip uninstall -y \
    paddleocr \
    paddlex \
    paddlepaddle \
    paddlepaddle-gpu

!{PYTHON} -m pip install -q --upgrade pip setuptools wheel

# Lệnh này dành cho runtime CUDA 13 của notebook mẫu.
!{PYTHON} -m pip install paddlepaddle-gpu==3.3.1 \
    -i https://www.paddlepaddle.org.cn/packages/stable/cu130/

!{PYTHON} -m pip install -q "paddleocr[all]==3.7.0"
```

> Nếu Kaggle thay đổi CUDA runtime, không cài máy móc wheel `cu130`. Hãy chọn wheel PaddlePaddle tương thích với CUDA hiện tại của notebook.

Kiểm tra môi trường:

```python
import paddle
import paddleocr
import paddlex

print("PaddlePaddle:", paddle.__version__)
print("PaddleOCR:", paddleocr.__version__)
print("PaddleX:", paddlex.__version__)
print("Paddle device:", paddle.device.get_device())
print("GPU count:", paddle.device.cuda.device_count())

paddle.utils.run_check()
```

## 5. Clone source PaddleOCR phục vụ training

Gói `paddleocr` dùng để inference, nhưng các script `tools/train.py`, `tools/eval.py` và `tools/export_model.py` nằm trong source repository.

```bash
%%bash
set -e

apt-get update -qq
apt-get install -y -qq poppler-utils pngcrush

rm -rf /kaggle/working/PaddleOCR
git clone -q --depth 1 --branch v3.7.0 \
  https://github.com/PaddlePaddle/PaddleOCR.git \
  /kaggle/working/PaddleOCR

python -m pip install -q --upgrade pip setuptools wheel
python -m pip install -q \
  -r /kaggle/working/PaddleOCR/requirements.txt

# Chỉ giữ một bản OpenCV để tránh lỗi import cv2.
python -m pip uninstall -y \
  opencv-python \
  opencv-contrib-python \
  opencv-python-headless \
  opencv-contrib-python-headless \
  >/dev/null 2>&1 || true

python -m pip install -q \
  "numpy==1.26.4" \
  "Pillow>=10,<12" \
  "opencv-contrib-python-headless>=4.8,<4.12" \
  "imgaug==0.4.0" \
  "albumentations<2" \
  "scikit-image<0.23" \
  shapely \
  pyclipper \
  rapidfuzz \
  tqdm \
  lmdb \
  pdf2image \
  matplotlib
```

Kiểm tra lại:

```python
import sys
import cv2
import numpy as np
import paddle

print("Python:", sys.version.split()[0])
print("Paddle:", paddle.__version__)
print("NumPy:", np.__version__)
print("OpenCV:", cv2.__version__)
print("GPU count:", paddle.device.cuda.device_count())
```

## 6. Kiểm tra nhanh dữ liệu

Trước khi training, nên hiển thị ngẫu nhiên một số ảnh cùng label để phát hiện lỗi đường dẫn, encoding hoặc gán nhãn.

```python
from pathlib import Path
from PIL import Image
import matplotlib.pyplot as plt
import random

DATA_DIR = Path(
    "/kaggle/input/datasets/thnhtrn412/"
    "data-ocr-train-v4/Data_OCR_Train"
)
LABEL_FILE = DATA_DIR / "Train.txt"
SAMPLE_COUNT = 5
random.seed(2026)

samples = []

with LABEL_FILE.open("r", encoding="utf-8-sig") as label_file:
    for line_number, line in enumerate(label_file, start=1):
        line = line.rstrip("\r\n")
        if "\t" not in line:
            continue

        image_name, label = line.split("\t", 1)
        item = (DATA_DIR / image_name, image_name, label)

        if len(samples) < SAMPLE_COUNT:
            samples.append(item)
        else:
            replace_index = random.randint(1, line_number)
            if replace_index <= SAMPLE_COUNT:
                samples[replace_index - 1] = item

fig, axes = plt.subplots(SAMPLE_COUNT, 1, figsize=(18, SAMPLE_COUNT * 2.5))

for axis, (image_path, image_name, label) in zip(axes, samples):
    with Image.open(image_path) as image:
        axis.imshow(image.convert("RGB"))
    axis.set_title(f"{image_name}\nLabel: {label}", loc="left", fontsize=10)
    axis.axis("off")

plt.tight_layout()
plt.show()
```

## 7. Tải pretrained model PP-OCRv6

Fine-tune nên bắt đầu từ pretrained weights thay vì train ngẫu nhiên từ đầu.

```bash
!wget -q \
  https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv6_medium_rec_pretrained.pdparams \
  -O /kaggle/working/PaddleOCR/PP-OCRv6_medium_rec_pretrained.pdparams
```

Kiểm tra file:

```bash
!ls -lh /kaggle/working/PaddleOCR/PP-OCRv6_medium_rec_pretrained.pdparams
```

## 8. Chuẩn bị từ điển tiếng Việt

Notebook dùng file `custom_dict.txt` đã được chuẩn bị trong Kaggle Dataset:

```bash
!cp \
  /kaggle/input/datasets/ttt2k3/dict-for-ocr/custom_dict.txt \
  /kaggle/working/PaddleOCR/custom_dict.txt
```

Kiểm tra từ điển:

```python
from pathlib import Path

DICT_PATH = Path("/kaggle/working/PaddleOCR/custom_dict.txt")
characters = DICT_PATH.read_text(encoding="utf-8-sig").splitlines()

print("Số ký tự:", len(characters))
print("Có ký tự đ:", "đ" in characters)
print("Có ký tự Đ:", "Đ" in characters)
```

Nếu dataset chứa ký tự không có trong từ điển, model sẽ không thể học và xuất đúng ký tự đó.

## 9. Tạo cấu hình training

Tạo file `/kaggle/working/PaddleOCR/vi_PP-OCRv6_medium_rec.yml`:

```python
from pathlib import Path

PADDLEOCR_DIR = Path("/kaggle/working/PaddleOCR")
CONFIG_PATH = PADDLEOCR_DIR / "vi_PP-OCRv6_medium_rec.yml"

YAML_CONTENT = """Global:
  model_name: PP-OCRv6_medium_rec
  debug: false
  use_gpu: true
  epoch_num: 14
  log_smooth_window: 20
  print_batch_step: 500
  save_model_dir: ./Model/vi_PP-OCRv6_medium_rec
  save_epoch_step: 1
  eval_batch_step: [0, 3567]
  cal_metric_during_train: true
  pretrained_model:
  checkpoints:
  save_inference_dir:
  use_visualdl: false
  infer_img:
  character_dict_path: /kaggle/working/PaddleOCR/custom_dict.txt
  max_text_length: &max_text_length 25
  infer_mode: false
  use_space_char: true
  distributed: false
  save_res_path: ./output/rec/predicts_ppocrv6_medium.txt
  d2s_train_image_shape: [3, 48, 320]

Optimizer:
  name: Adam
  beta1: 0.9
  beta2: 0.999
  lr:
    name: Cosine
    learning_rate: 0.00005
    warmup_epoch: 0
  regularizer:
    name: L2
    factor: 3.0e-05

Architecture:
  model_type: rec
  algorithm: SVTR_LCNet
  Transform:
  Backbone:
    name: PPLCNetV4
    model_size: medium
  Head:
    name: MultiHead
    head_list:
      - CTCHead:
          Neck:
            name: lightsvtr
            dims: 192
            depth: 2
            mlp_ratio: 4.0
            local_kernel: 7
            use_guide: false
          Head:
            fc_decay: 0.00001
      - NRTRHead:
          nrtr_dim: 512
          max_text_length: *max_text_length

Loss:
  name: MultiLoss
  loss_config_list:
    - CTCLoss:
    - NRTRLoss:

PostProcess:
  name: CTCLabelDecode

Metric:
  name: RecMetric
  main_indicator: acc

Train:
  dataset:
    name: MultiScaleDataSet
    ds_width: false
    data_dir: /kaggle/input/datasets/thnhtrn412/data-ocr-train-v4/Data_OCR_Train
    ext_op_transform_idx: 1
    label_file_list:
      - /kaggle/input/datasets/thnhtrn412/data-ocr-train-v4/Data_OCR_Train/Train.txt
    ratio_list:
      - 1.0
    transforms:
      - DecodeImage:
          img_mode: BGR
          channel_first: false
      - RecConAug:
          prob: 0.5
          ext_data_num: 2
          image_shape: [48, 320, 3]
          max_text_length: *max_text_length
      - RecAug:
      - MultiLabelEncode:
          gtc_encode: NRTRLabelEncode
      - KeepKeys:
          keep_keys:
            - image
            - label_ctc
            - label_gtc
            - length
            - valid_ratio
  sampler:
    name: MultiScaleSampler
    scales: [[320, 32], [320, 48], [320, 64]]
    first_bs: &batch_size 64
    fix_bs: false
    divided_factor: [8, 16]
    is_training: true
  loader:
    shuffle: true
    batch_size_per_card: *batch_size
    drop_last: true
    num_workers: 8

Eval:
  dataset:
    name: SimpleDataSet
    data_dir: /kaggle/input/datasets/thnhtrn412/data-ocr-train-v4/Data_OCR_Train
    label_file_list:
      - /kaggle/input/datasets/thnhtrn412/data-ocr-train-v4/Data_OCR_Train/Val.txt
    transforms:
      - DecodeImage:
          img_mode: BGR
          channel_first: false
      - MultiLabelEncode:
          gtc_encode: NRTRLabelEncode
      - RecResizeImg:
          image_shape: [3, 48, 320]
      - KeepKeys:
          keep_keys:
            - image
            - label_ctc
            - label_gtc
            - length
            - valid_ratio
  loader:
    shuffle: false
    drop_last: false
    batch_size_per_card: 128
    num_workers: 4
"""

CONFIG_PATH.write_text(YAML_CONTENT, encoding="utf-8")
print("Wrote:", CONFIG_PATH)
```

### Các tham số cần điều chỉnh

| Tham số | Ý nghĩa | Khi cần đổi |
|---|---|---|
| `epoch_num` | Tổng số epoch | Tăng khi model chưa hội tụ |
| `learning_rate` | Learning rate | Giảm nếu metric dao động mạnh |
| `max_text_length` | Độ dài nhãn tối đa | Tăng nếu có chuỗi dài hơn 25 ký tự |
| `first_bs` | Batch size train | Giảm nếu GPU hết bộ nhớ |
| `batch_size_per_card` trong Eval | Batch size validation | Giảm nếu validation OOM |
| `eval_batch_step` | Chu kỳ chạy validation | Điều chỉnh theo số batch mỗi epoch |
| `num_workers` | Số tiến trình đọc dữ liệu | Giảm nếu Kaggle thiếu RAM hoặc treo dataloader |

## 10. Training lần đầu từ pretrained model

```bash
%cd /kaggle/working/PaddleOCR

!python tools/train.py \
  -c vi_PP-OCRv6_medium_rec.yml \
  -o Global.pretrained_model=./PP-OCRv6_medium_rec_pretrained.pdparams
```

Checkpoint sẽ được ghi vào:

```text
/kaggle/working/PaddleOCR/Model/vi_PP-OCRv6_medium_rec
```

Theo dõi các giá trị chính trong log:

- `loss`: tổng loss, nên giảm dần.
- `acc`: tỷ lệ chuỗi nhận diện đúng hoàn toàn.
- `norm_edit_dis`: normalized edit distance; càng gần `1.0` càng tốt.
- `best_epoch`: epoch có metric validation tốt nhất.

## 11. Tiếp tục training từ checkpoint

Checkpoint prefix không có phần mở rộng. Ví dụ prefix `latest` tương ứng với:

```text
latest.pdparams
latest.pdopt
latest.states
```

Ví dụ resume từ Kaggle Dataset:

```bash
%cd /kaggle/working/PaddleOCR

!python tools/train.py \
  -c vi_PP-OCRv6_medium_rec.yml \
  -o \
  Global.epoch_num=28 \
  Global.checkpoints=/kaggle/input/datasets/thnhtrc/pp-ocrv6-rec-checkpoint/vi_PP-OCRv6_medium_rec_check_point/latest
```

> Quan trọng: `Global.epoch_num` là tổng epoch mục tiêu, không phải số epoch chạy thêm. Nếu checkpoint đã hoàn thành epoch `14` mà cấu hình vẫn đặt `epoch_num: 14`, PaddleOCR sẽ bắt đầu từ epoch `15` nhưng không còn epoch nào để chạy. Muốn train thêm 14 epoch, hãy đặt tổng mục tiêu thành `28`.

Không dùng `Global.pretrained_model` đồng thời với `Global.checkpoints`:

- `pretrained_model`: nạp trọng số ban đầu, optimizer bắt đầu mới.
- `checkpoints`: khôi phục cả model, optimizer, trạng thái epoch và metric.

## 12. Đóng gói checkpoint để lưu lại

```python
from pathlib import Path
import zipfile

CHECKPOINT_DIR = Path(
    "/kaggle/working/PaddleOCR/Model/vi_PP-OCRv6_medium_rec"
)
OUTPUT_ZIP = Path(
    "/kaggle/working/vi_PP-OCRv6_medium_rec_checkpoint.zip"
)
LATEST_FILES = (
    "latest.pdparams",
    "latest.pdopt",
    "latest.states",
)

if not CHECKPOINT_DIR.is_dir():
    raise FileNotFoundError(f"Không tìm thấy checkpoint: {CHECKPOINT_DIR}")

missing_files = [
    file_name
    for file_name in LATEST_FILES
    if not (CHECKPOINT_DIR / file_name).is_file()
]
if missing_files:
    raise FileNotFoundError("Thiếu checkpoint: " + ", ".join(missing_files))

OUTPUT_ZIP.unlink(missing_ok=True)

with zipfile.ZipFile(
    OUTPUT_ZIP,
    mode="w",
    compression=zipfile.ZIP_DEFLATED,
    compresslevel=6,
) as zip_file:
    for file_name in LATEST_FILES:
        source_file = CHECKPOINT_DIR / file_name
        zip_file.write(
            source_file,
            arcname=f"{CHECKPOINT_DIR.name}/{file_name}",
        )

with zipfile.ZipFile(OUTPUT_ZIP, mode="r") as zip_file:
    damaged_file = zip_file.testzip()
    if damaged_file is not None:
        raise RuntimeError(f"File ZIP bị lỗi tại: {damaged_file}")

print("Created:", OUTPUT_ZIP)
print("Size:", f"{OUTPUT_ZIP.stat().st_size / (1024 ** 2):.2f} MB")
```

Sau đó tải ZIP về máy hoặc tạo Kaggle Dataset mới để dùng cho lần resume tiếp theo.

## 13. Evaluation model

Đánh giá checkpoint tốt nhất trên tập `Val.txt`:

```bash
%cd /kaggle/working/PaddleOCR

!python tools/eval.py \
  -c vi_PP-OCRv6_medium_rec.yml \
  -o Global.checkpoints=/kaggle/working/PaddleOCR/Model/vi_PP-OCRv6_medium_rec/best_accuracy
```

Một lần chạy trong notebook nguồn cho kết quả tham khảo:

```text
acc: 0.8934553119022445
norm_edit_dis: 0.9732320766616636
fps: 192.9094063109501
```

Các con số này chỉ là kết quả của dataset và checkpoint tại thời điểm notebook chạy, không phải mức đảm bảo cho dataset khác.

Cách đọc metric:

- `acc`: tỷ lệ mẫu được nhận diện đúng toàn bộ chuỗi.
- `norm_edit_dis`: mức tương đồng ký tự; phù hợp để đánh giá trường hợp chỉ sai một vài ký tự hoặc dấu.
- `fps`: tốc độ benchmark trong môi trường evaluation hiện tại.

Đối với tiếng Việt, nên thống kê thêm lỗi riêng cho `ă`, `â`, `đ`, `ê`, `ô`, `ơ`, `ư` và các dấu thanh.

## 14. Export model recognition sang inference

Export checkpoint `best_accuracy`:

```bash
%cd /kaggle/working/PaddleOCR

!python tools/export_model.py \
  -c vi_PP-OCRv6_medium_rec.yml \
  -o \
  Global.pretrained_model=/kaggle/working/PaddleOCR/Model/vi_PP-OCRv6_medium_rec/best_accuracy \
  Global.save_inference_dir=/kaggle/working/PP-OCRv6_medium_rec_infer
```

Kiểm tra output:

```bash
!find /kaggle/working/PP-OCRv6_medium_rec_infer \
  -maxdepth 1 \
  -type f \
  -print
```

Đóng gói để tải về:

```bash
%cd /kaggle/working

!zip -qr \
  PP-OCRv6_medium_rec_infer.zip \
  PP-OCRv6_medium_rec_infer/

!ls -lh PP-OCRv6_medium_rec_infer.zip
```

Notebook nguồn tạo file ZIP khoảng `55 MB`; kích thước thực tế có thể thay đổi theo phiên bản model.

## 15. Tải model detection chính thức

Training ở trên chỉ tạo model recognition. Cần kết hợp với model detection khi chạy OCR toàn trang.

```bash
!wget -q --show-progress \
  -O /kaggle/working/PP-OCRv6_medium_det_infer.tar \
  https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv6_medium_det_infer.tar

%cd /kaggle/working
!tar -xf PP-OCRv6_medium_det_infer.tar

!find /kaggle/working/PP-OCRv6_medium_det_infer \
  -maxdepth 1 \
  -type f \
  -print
```

Thư mục detection hợp lệ thường có:

```text
inference.pdiparams
inference.yml
inference.json
```

## 16. Smoke test model đã export

Dùng general OCR pipeline để kiểm tra nhanh detection chính thức và recognition đã fine-tune:

```python
from pathlib import Path
import paddle
from paddleocr import PaddleOCR

DET_DIR = Path("/kaggle/working/PP-OCRv6_medium_det_infer")
REC_DIR = Path("/kaggle/working/PP-OCRv6_medium_rec_infer")
INPUT_FILE = Path(
    "/kaggle/input/datasets/thnhtrn412/data-test-ocr/Data_test/IN_40.pdf"
)
OUTPUT_DIR = Path("/kaggle/working/test_ppocrv6_custom")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEVICE = "gpu:0" if paddle.device.cuda.device_count() > 0 else "cpu"
paddle.set_device(DEVICE)

pipeline = PaddleOCR(
    device=DEVICE,
    engine="paddle_static",
    ocr_version="PP-OCRv6",
    text_detection_model_name="PP-OCRv6_medium_det",
    text_detection_model_dir=str(DET_DIR),
    text_recognition_model_name="PP-OCRv6_medium_rec",
    text_recognition_model_dir=str(REC_DIR),
    text_recognition_batch_size=8,
    text_rec_input_shape=(3, 48, 320),
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)

results = list(pipeline.predict(input=str(INPUT_FILE)))

for result in results:
    result.print()
    result.save_to_json(save_path=str(OUTPUT_DIR))
    result.save_to_img(save_path=str(OUTPUT_DIR))

print("Output:", OUTPUT_DIR)
```

Việc dùng `text_rec_input_shape=(3, 48, 320)` phải đồng bộ với cấu hình train và export.

Sau khi smoke test thành công, có thể dùng thư mục recognition inference này trong `PPStructureV3` bằng các tham số:

```python
text_recognition_model_name="PP-OCRv6_medium_rec"
text_recognition_model_dir="/path/to/PP-OCRv6_medium_rec_infer"
```

## 17. Lỗi thường gặp

### Training không chạy khi resume

Nguyên nhân thường là checkpoint đã ở epoch bằng hoặc lớn hơn `Global.epoch_num`.

Cách xử lý: tăng tổng `Global.epoch_num`, ví dụ từ `14` lên `28`.

### CUDA hoặc PaddlePaddle không tương thích

Biểu hiện thường là không nhận GPU, lỗi load thư viện CUDA hoặc `paddle.utils.run_check()` thất bại.

Cách xử lý: kiểm tra CUDA runtime của Kaggle và cài đúng PaddlePaddle wheel. Không mặc định mọi runtime đều dùng `cu130`.

### Lỗi import OpenCV

Notebook chủ động uninstall toàn bộ biến thể OpenCV rồi chỉ cài `opencv-contrib-python-headless`. Không cài đồng thời nhiều gói OpenCV.

### Hết bộ nhớ GPU

Giảm lần lượt:

1. `Train.sampler.first_bs`, ví dụ `64` xuống `32` hoặc `16`.
2. `Eval.loader.batch_size_per_card`, ví dụ `128` xuống `64`.
3. `num_workers`, nếu lỗi liên quan RAM hoặc dataloader.

### Ký tự tiếng Việt bị bỏ hoặc nhận sai

Kiểm tra:

- Ký tự đã có trong `custom_dict.txt` chưa.
- Label có đúng UTF-8 không.
- `use_space_char` có phù hợp không.
- Label có vượt `max_text_length` không.
- Ảnh có đủ độ phân giải để nhìn rõ dấu không.

### Không tìm thấy ảnh trong Train.txt hoặc Val.txt

Đường dẫn bên trái ký tự tab được nối với `data_dir`. Không dùng đường dẫn sai gốc hoặc tên file khác chữ hoa/chữ thường.

### Export thiếu file inference

Đảm bảo lệnh export dùng prefix checkpoint, ví dụ `best_accuracy`, không thêm `.pdparams` vào cuối đường dẫn.

## 18. Checklist trước khi kết thúc

- [ ] Kaggle đã bật GPU và Internet.
- [ ] PaddlePaddle nhận GPU thành công.
- [ ] PaddleOCR source đúng tag `v3.7.0`.
- [ ] `Train.txt` và `Val.txt` dùng ký tự tab thật.
- [ ] Tất cả ảnh trong label đều tồn tại.
- [ ] `custom_dict.txt` chứa đầy đủ ký tự tiếng Việt.
- [ ] Pretrained model đã tải thành công.
- [ ] Training tạo được `best_accuracy.*` và `latest.*`.
- [ ] Evaluation đã chạy trên tập validation cố định.
- [ ] Model recognition đã export sang inference.
- [ ] Model inference đã được ZIP và tải về.
- [ ] Smoke test sử dụng đúng `text_rec_input_shape=(3, 48, 320)`.

## 19. Quy trình rút gọn

```text
Chuẩn bị dataset + dictionary
        ↓
Cài PaddlePaddle/PaddleOCR
        ↓
Clone PaddleOCR v3.7.0
        ↓
Tải PP-OCRv6_medium_rec pretrained
        ↓
Tạo vi_PP-OCRv6_medium_rec.yml
        ↓
Train từ pretrained hoặc resume checkpoint
        ↓
Eval best_accuracy
        ↓
Export PP-OCRv6_medium_rec_infer
        ↓
Kết hợp PP-OCRv6_medium_det_infer để smoke test
        ↓
Đưa recognition inference vào pipeline triển khai
```
