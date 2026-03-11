from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def root():
    return {"status": "Stackr API is running ⚡"}

@app.get("/api/dashboard/summary")
def dashboard():
    return {"total_balance": 24830, "monthly_income": 8340, "tax_vault": 4820, "portfolio_value": 11240}

@app.get("/api/tax/calculate")
def tax(income: float, tax_rate: float = 0.28):
    return {"income": income, "tax_amount": round(income * tax_rate, 2), "spendable": round(income * (1 - tax_rate), 2)}
