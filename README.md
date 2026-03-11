# Stackr ⚡
### The all-in-one financial app for content creators

---

## What this is
Stackr connects banking, investing, taxes, and transfers into one clean interface built specifically for creators. Zero operational risk — all transactions pass through licensed API partners.

**API Partners**
- 💳 Stripe Treasury — banking
- 🦙 Alpaca — investing
- 🔄 Dwolla — transfers
- 🧾 TaxSlayer — tax filing
- 👨‍💼 Taxfyle — CPA matching

---

## Project Structure
```
stackr/
├── backend/          # Python FastAPI
│   ├── main.py       # All API endpoints
│   ├── requirements.txt
│   └── .env.example  # Copy to .env and add your keys
└── frontend/         # React (coming soon)
```

---

## Setup Instructions

### Backend (Python)

**Step 1 — Go into backend folder**
```bash
cd backend
```

**Step 2 — Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Step 3 — Install dependencies**
```bash
pip install -r requirements.txt
```

**Step 4 — Set up environment variables**
```bash
cp .env.example .env
```
Open `.env` and add your Stripe keys from stripe.com/dashboard

**Step 5 — Run the server**
```bash
uvicorn main:app --reload
```

**Step 6 — Test it's working**
Open your browser and go to:
```
http://localhost:8000
http://localhost:8000/docs
```

You should see the Stackr API running with interactive docs.

---

## API Endpoints

| Method | Endpoint | What it does |
|--------|----------|--------------|
| GET | `/` | Health check |
| GET | `/api/dashboard/summary` | Main dashboard data |
| POST | `/api/tax/calculate` | Calculate tax withholding |
| POST | `/api/income/log` | Log income from platform |
| GET | `/api/stripe/balance` | Get Stripe balance |
| GET | `/api/stripe/transactions` | Get recent transactions |

---

## Test the Tax Calculator
Once running, open `http://localhost:8000/docs` and try this:

```json
POST /api/tax/calculate
{
  "income": 5000,
  "tax_rate": 0.28
}
```

Returns:
```json
{
  "income": 5000,
  "tax_rate": 0.28,
  "tax_amount": 1400,
  "spendable": 3600,
  "message": "$1400 sent to Tax Vault, $3600 available to spend"
}
```

---

Built with FastAPI · Stripe · Alpaca · Claude API
