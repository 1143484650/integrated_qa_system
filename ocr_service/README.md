# OCR Service

Independent CPU PP-Structure OCR service for document ingestion.

The first-stage deployment keeps OCR in a separate CPU container. This keeps the
main QA service lightweight and leaves GPU migration as a later deployment
choice.

## Run

```bash
docker compose -f docker-compose.yml -f docker-compose.ocr.yml up -d --build ocr-service
```

## API

```bash
curl -F "file=@rag_qa/data/samples/ocr_04.png" http://localhost:8010/parse/image
```

Set `OCR_SERVICE_URL=http://ocr-service:8010` for containers in the same compose network, or `http://localhost:8010` for local Python processes.
