# Bookkeeping Automation Platform

A Python-based platform for automated invoice and receipt processing using vision language models (vLLM or OpenRouter with Qwen Vision models).

## Architecture

### Option 1: Local vLLM (Self-hosted)
```
┌─────────────────┐
│  Svelte UI      │  (Port 3000)
│  (Frontend)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FastAPI        │  (Port 8080)
│  (Backend)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  vLLM Server    │  (Port 8000)
│  (Qwen2-VL)     │
└─────────────────┘
```

### Option 2: OpenRouter (Cloud API)
```
┌─────────────────┐
│  Svelte UI      │  (Port 3000)
│  (Frontend)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FastAPI        │  (Port 8080)
│  (Backend)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  OpenRouter API │  (Cloud)
│  (Qwen3-VL)     │
└─────────────────┘
```

## Quick Start with OpenRouter 
### Prerequisites

- OpenRouter API key ([Get one here](https://openrouter.ai/))
- Docker and Docker Compose
- No GPU required!

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd bookkeeping-automation
```

2. Create `.env` file from example:
```bash
cp .env.example .env
```

3. Edit `.env` and add your OpenRouter API key:
```env
PROVIDER=openrouter
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=qwen/qwen3-vl-8b-instruct
```

4. Start services with the default docker-compose (OpenRouter):
```bash
docker-compose up -d
```

This will start:
- Backend API on port 8080 (configured for OpenRouter)
- Frontend UI on port 3000

Or run manually:
```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

5. Access the UI:
```
http://localhost:3000  (or http://localhost:5173 for npm dev)
```

## Quick Start with Self-Hosted vLLM (GPU Required)


### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd bookkeeping-automation
```

2. Create `.env` file from example:
```bash
cp .env.example .env
```

3. Edit `.env` and configure for vLLM:
```env
PROVIDER=vllm
HUGGING_FACE_HUB_TOKEN=your_token_here
MODEL_NAME=Qwen/Qwen2-VL-7B-Instruct
```

4. Start all services with the self-hosted compose file:
```bash
docker-compose -f docker-compose.selfhosted.yml up -d
```

This will start:
- vLLM server with Qwen2-VL model on port 8000 (requires GPU)
- Backend API on port 8080 (configured for vLLM)
- Frontend UI on port 3000

5. Access the UI:
```
http://localhost:3000
```

**Note**: First startup will download the model (~15GB), which may take some time.

## Manual Setup (Development)

### Backend Setup

1. Install system dependencies (Ubuntu/Debian):
```bash
sudo apt-get update
sudo apt-get install -y poppler-utils python3-dev
```

2. Create and activate virtual environment:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

4. Start vLLM server separately (requires GPU):
```bash
vllm serve Qwen/Qwen2-VL-7B-Instruct --port 8000 --host 0.0.0.0
```

5. Start the backend API:
```bash
cd backend
export VLLM_HOST=localhost
export VLLM_PORT=8000
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### Frontend Setup

1. Install Node.js dependencies:
```bash
cd frontend
npm install
```

2. Start development server:
```bash
npm run dev
```

3. Access the UI at `http://localhost:5173`

## API Usage

### Endpoints

#### Health Check
```bash
GET http://localhost:8080/health
```

Response:
```json
{
  "status": "healthy",
  "model_loaded": true,
  "available_templates": ["default_invoice", "detailed_invoice", "simple_receipt"],
  "provider": "openrouter",
  "model_name": "qwen/qwen3-vl-8b-instruct"
}
```

#### List Templates
```bash
GET http://localhost:8080/templates
```

#### Process Document
```bash
POST http://localhost:8080/process
Content-Type: multipart/form-data

file: <image or PDF file>
buyer: "Acme Corp" (optional)
template: "default_invoice" (optional, default: default_invoice)
```

Example with curl:
```bash
curl -X POST http://localhost:8080/process \
  -F "file=@invoice.pdf" \
  -F "buyer=Acme Corp" \
  -F "template=default_invoice"
```

Response:
```json
{
  "success": true,
  "data": {
    "invoice_number": "INV-2024-001",
    "invoice_date": "2024-01-15",
    "payment_date": "2024-01-20",
    "service_date": "2024-01-10",
    "service_provider": "ABC Services Inc.",
    "buyer": "Acme Corp",
    "amount": 1500.00,
    "currency": "USD",
    "description": "Consulting services",
    "payment_method": "banktransfer"
  },
  "error": null,
  "raw_response": "{...}"
}
```

#### Token Usage & Cost Tracking
```bash
GET http://localhost:8080/token-costs
```

Query parameters:
- `limit` (integer, 1-1000): Maximum number of records to return (default: 100)
- `offset` (integer): Number of records to skip for pagination (default: 0)
- `provider` (string): Filter by provider (`openrouter` or `vllm`)
- `buyer` (string): Filter by buyer name
- `start_date` (datetime): Filter records after this date (ISO format)
- `end_date` (datetime): Filter records before this date (ISO format)

Example:
```bash
# Get all token usage records
curl http://localhost:8080/token-costs

# Get last 50 records for OpenRouter
curl "http://localhost:8080/token-costs?limit=50&provider=openrouter"

# Get costs for specific date range
curl "http://localhost:8080/token-costs?start_date=2024-01-01T00:00:00&end_date=2024-12-31T23:59:59"
```

Response:
```json
{
  "records": [
    {
      "id": 1,
      "timestamp": "2024-01-15T10:30:00",
      "filename": "invoice.pdf",
      "buyer": "Acme Corp",
      "template": "default_invoice",
      "provider": "openrouter",
      "model_name": "qwen/qwen3-vl-8b-instruct",
      "prompt_tokens": 1250,
      "completion_tokens": 350,
      "total_tokens": 1600,
      "prompt_cost": 0.00025,
      "completion_cost": 0.00007,
      "total_cost": 0.00032,
      "success": true,
      "error_message": null,
      "num_images": 1
    }
  ],
  "stats": {
    "total_requests": 150,
    "successful_requests": 145,
    "failed_requests": 5,
    "total_prompt_tokens": 187500,
    "total_completion_tokens": 52500,
    "total_tokens": 240000,
    "total_cost_usd": 0.048,
    "total_images_processed": 150
  },
  "provider_breakdown": [
    {
      "provider": "openrouter",
      "total_requests": 150,
      "total_tokens": 240000,
      "total_cost_usd": 0.048
    }
  ],
  "total_records": 150,
  "limit": 100,
  "offset": 0
}
```

**Token Cost Storage:**
- All API calls are automatically tracked in a SQLite database (`token_usage.db`)
- Database is created automatically on first run
- Costs are calculated using real-time pricing data from OpenRouter API
- Historical data persists across application restarts
- Use the `/token-costs` endpoint to retrieve and analyze usage

**Pricing:**
- **OpenRouter**: Pricing is fetched dynamically from OpenRouter's API (https://openrouter.ai/api/v1/models)
  - Pricing is fetched automatically at application startup
  - Pricing is cached for 24 hours to minimize API calls
  - Falls back to default pricing if API is unavailable
  - Costs vary by model (e.g., Qwen3-VL is typically $0.20 per 1M tokens)
- **vLLM (self-hosted)**: $0.00 (no per-token cost)

## Configuration

### Prompt Templates

Edit `backend/config/prompts.yaml` to customize extraction templates:

```yaml
custom_template:
  name: "Custom Invoice Extraction"
  description: "Extract custom fields"
  system_prompt: |
    You are an expert at analyzing invoices.

  user_prompt: |
    Extract the following fields:
    - field1: Description
    - field2: Description

    {buyer_context}

    Return ONLY valid JSON.
```

Available templates:
- `default_invoice`: Standard invoice/receipt extraction
- `detailed_invoice`: Detailed extraction with line items
- `simple_receipt`: Basic receipt information

### Reload Configuration

Reload prompts without restarting:
```bash
POST http://localhost:8080/reload-config
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PROVIDER` | Vision provider (`openrouter` or `vllm`) | `openrouter` |
| `OPENROUTER_API_KEY` | OpenRouter API key | Required when `PROVIDER=openrouter` |
| `OPENROUTER_API_BASE` | OpenRouter API base URL | `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | OpenRouter model name | `qwen/qwen3-vl-8b-instruct` |
| `MODEL_NAME` | vLLM model name | `Qwen/Qwen2-VL-7B-Instruct` |
| `VLLM_HOST` | vLLM server host | `vllm` (Docker) / `localhost` |
| `VLLM_PORT` | vLLM server port | `8000` |
| `MAX_FILE_SIZE_MB` | Max upload size in MB | `10` |
| `HUGGING_FACE_HUB_TOKEN` | HF token for model download | Required for vLLM |



## Docker Compose Files

- **docker-compose.yml** (default): Uses OpenRouter API for cloud-based inference. No GPU required.
- **docker-compose.selfhosted.yml**: Uses local vLLM with GPU for self-hosted inference.

## Supported File Formats

- **Images**: JPG, JPEG, PNG
- **Documents**: PDF (multi-page supported)

## Use Cases

### Standalone API Usage

Perfect for:
- Batch processing invoices
- Integrating with existing systems
- Building custom workflows
- Automated bookkeeping pipelines

### UI Demo

Great for:
- Testing and validation
- Quick document processing
- Demonstrating capabilities
- Non-technical users

### Custom Workflows

The `buyer` parameter enables:
- Customer-specific processing
- Multi-tenant applications
- Improved service provider detection
- Contextual extraction


## Troubleshooting

### OpenRouter Issues

**Error**: "API key required"
- Ensure `OPENROUTER_API_KEY` is set in `.env`
- Verify the API key is valid at https://openrouter.ai/
- Check that `PROVIDER=openrouter` is set

**Error**: "Model not found" or "Invalid model"
- Verify model name is `qwen/qwen3-vl-8b-instruct`
- Check OpenRouter model availability at https://openrouter.ai/models
- Ensure your API key has access to the model

**Error**: "Rate limit exceeded"
- Check your OpenRouter account usage limits
- Consider upgrading your OpenRouter plan
- Implement request throttling in your application

### vLLM Issues

**Error**: "CUDA out of memory"
- Reduce `--max-model-len` in docker-compose.yml
- Use a smaller model variant
- Ensure sufficient GPU memory

**Error**: "Model not found"
- Check Hugging Face token in `.env`
- Verify model name is correct
- Check internet connection for model download

### Backend Issues

**Error**: "Connection refused to vLLM"
- Ensure vLLM service is running (if using vLLM provider)
- Check `VLLM_HOST` and `VLLM_PORT` settings
- Verify vLLM is accessible on port 8000

**Error**: "Provider not configured correctly"
- Check `PROVIDER` setting in `.env` (must be `vllm` or `openrouter`)
- Ensure required API keys are set for the chosen provider
- Review backend logs for specific error messages

### Frontend Issues

**Error**: "API calls fail"
- Check backend is running on port 8080
- Verify CORS settings if accessing from different domain
- Check nginx proxy configuration in production

**Note**: Frontend Routing Behavior
- The frontend is a Single Page Application (SPA) without client-side routing
- All URLs (/, /templates, /health, etc.) serve the same interface
- This is expected behavior - the API endpoints (/api/health, /api/templates, /api/process) work correctly
- The nginx configuration uses `try_files $uri $uri/ /index.html;` which serves index.html for all routes
- API endpoints are accessed via /api/* and properly proxied to the backend

## Performance Considerations

- **First Request**: May be slow due to model loading
- **PDF Processing**: Multi-page PDFs process each page sequentially
- **Image Size**: Large images are automatically resized to 1024x1024
- **Concurrent Requests**: vLLM handles concurrent requests efficiently

