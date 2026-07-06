# OCR Runtime

## Purpose

The project uses a separate local OCR runtime for PP-Structure document parsing. Do not install PaddleOCR dependencies into the main QA environment unless explicitly requested.

## Default Local Runtime

- Conda executable: `D:\Tools\Anaconda\Scripts\conda.exe`
- Environment name: `qa-ocr`
- Environment path: `D:\Tools\Anaconda\envs\qa-ocr`
- Python executable: `D:\Tools\Anaconda\envs\qa-ocr\python.exe`
- Python version: `3.10`

## Required Packages

Install OCR dependencies from `ocr_service\requirements.txt`.

The known-good local package set includes:

- `numpy==1.26.4`
- `opencv-python-headless==4.10.0.84`
- `paddleocr==2.10.0`
- `paddlepaddle==2.6.2`
- `protobuf==3.20.2`
- `fastapi==0.139.0`
- `uvicorn==0.50.1`
- `python-multipart==0.0.32`

After installing PaddleOCR, remove GUI OpenCV packages and keep only headless OpenCV:

```powershell
& 'D:\Tools\Anaconda\envs\qa-ocr\python.exe' -m pip uninstall -y opencv-python opencv-contrib-python
& 'D:\Tools\Anaconda\envs\qa-ocr\python.exe' -m pip install --force-reinstall --no-deps "opencv-python-headless>=4.8.0,<4.11.0" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## Running The OCR Service

Run the OCR service with the dedicated environment:

```powershell
Set-Location D:\heima\26_5_5\integrated_qa_system\ocr_service
& 'D:\Tools\Anaconda\envs\qa-ocr\python.exe' -m uvicorn app:app --host 0.0.0.0 --port 8010
```

The main QA process should call it through:

```powershell
$env:OCR_SERVICE_URL = "http://localhost:8010"
```

## Current CPU Feature Scope

The initial local CPU runtime uses PP-Structure for layout-aware OCR, but keeps table structure recognition disabled:

- `layout=True`
- `ocr=True`
- `table=False`
- `formula=False`
- `image_orientation=False`
- `use_gpu=False`

This combination is verified on Windows with `paddlepaddle==2.6.2`. Enabling `table=True` currently fails in this environment with a Paddle native tensor dimension error, so table structure extraction should be treated as a later compatibility task.

Model files are cached under:

```text
C:\Users\Losangeles\.paddleocr\whl
```

## Known Issue: Local Windows Table Model

On the current Windows local CPU conda runtime, PP-Structure table recognition fails during engine initialization.

Verified environment:

- OS/runtime: Windows local conda environment
- Conda env: `qa-ocr`
- Python: `3.10`
- `paddlepaddle==2.6.2`
- `paddleocr==2.10.0`
- `numpy==1.26.4`
- `opencv-python-headless==4.10.0.84`

Reproduction matrix:

- `PPStructure(layout=True, table=False, formula=False, image_orientation=False, use_gpu=False)` works.
- `PPStructure(layout=False, table=True, formula=False, image_orientation=False, use_gpu=False)` fails.
- `PPStructure(layout=True, table=True, formula=False, image_orientation=False, use_gpu=False)` fails.

Observed error:

```text
(PreconditionNotMet) Tensor's dimension is out of bound.Tensor's dimension must be equal or less than the size of its memory.But received Tensor's dimension is 8, memory's size is 0.
[operator < scale > error]
```

Interpretation:

- PP-Structure supports table recognition, but this local Windows CPU dependency/model combination fails when loading the table model.
- The failure is in Paddle native inference initialization, not in project parsing code.
- Keep `table=False` for the current local CPU runtime until this is verified on another machine or runtime.

Recommended validation paths:

- Try the same `qa-ocr` dependency set on another Windows machine.
- Prefer Linux, WSL, or Docker Linux for full PP-Structure table recognition compatibility testing.
- If table recognition is required locally, test alternate `paddlepaddle` / `paddleocr` version pairs before changing project code.

## Operational Rules

- Use the `qa-ocr` conda environment for local CPU OCR work.
- Keep OCR dependencies isolated from the main QA environment.
- Prefer `opencv-python-headless`; avoid `opencv-python` and `opencv-contrib-python` in this environment.
- Keep `numpy<2.0` with PaddlePaddle 2.6.x to avoid native runtime incompatibilities.
- Do not enable PP-Structure table recognition in the local CPU runtime until the Paddle/table-model compatibility issue is resolved.
- Docker is optional for OCR during early-stage local development.
