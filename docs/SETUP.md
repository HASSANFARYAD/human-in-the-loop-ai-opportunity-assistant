# Setup Guide

## Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB 6+ (local or Atlas)
- One or more AI provider API keys (optional for some features)

## Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Copy and edit environment variables:

```bash
cp .env.example .env
```

Required settings:
- `MONGODB_URL` — MongoDB connection string
- `JWT_SECRET_KEY` — At least 32 characters in production

Optional but strongly recommended:
- `OPENAI_API_KEY` — Primary AI provider
- `GOOGLE_CREDENTIALS_FILE` — Gmail integration

See `CONFIGURATION.md` for complete variable reference.

### Run

```bash
uvicorn job_assistant.api:app --reload --port 8000
```

API available at `http://localhost:8000/api/v1/health`

## Frontend Setup

```bash
cd frontend
npm install
```

### Configuration

```bash
# Create .env.local with:
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Run

```bash
npm run dev
```

Frontend available at `http://localhost:3000`

## Testing

```bash
cd backend
python -m pytest tests/ -v
```

See `TESTING.md` for details.

## Deployment

See `DEPLOYMENT.md` for production deployment options.
