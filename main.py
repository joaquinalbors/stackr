from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import stripe
import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# Plaid setup
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID", "")
PLAID_SECRET = os.getenv("PLAID_SECRET", "")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")

plaid_config = plaid.Configuration(
    host=getattr(plaid.Environment, PLAID_ENV.capitalize(), plaid.Environment.Sandbox),
    api_key={"clientId": PLAID_CLIENT_ID, "secret": PLAID_SECRET}
)
plaid_client = plaid_api.PlaidApi(plaid.ApiClient(plaid_config))

# In-memory store for demo (replace with DB in production)
user_access_tokens = {}

class PublicTokenRequest(BaseModel):
    public_token: str
    user_id: str = "default"

class UserPreferences(BaseModel):
    user_id: str = "default"
    tax_pct: float = 28.0
    invest_pct: float = 10.0
    spend_pct: float = 62.0
    risk_score: int = 5
    risk_profile: str = "moderate"
    time_horizon: str = "5-10"
    income_stability: str = "variable"
    investment_goal: str = "growth"
    tos_accepted: bool = False
    tos_accepted_at: str = ""

app = FastAPI(title="Apexa API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "status": "Apexa API running ⚡",
        "version": "2.0.0",
        "stripe": "connected" if stripe.api_key else "not configured"
    }

@app.get("/api/dashboard/summary")
def get_dashboard_summary():
    balance_available = 24830.00
    try:
        if stripe.api_key:
            balance = stripe.Balance.retrieve()
            real = sum(b["amount"] for b in balance["available"]) / 100
            if real > 0:
                balance_available = real
    except:
        pass
    return {
        "total_balance": balance_available,
        "monthly_income": 8340.00,
        "tax_vault": 4820.00,
        "tax_vault_target": 6200.00,
        "portfolio_value": 11240.00,
        "tax_rate": 0.28,
        "next_tax_due": "April 15, 2026",
        "platforms_connected": 5,
        "auto_invest_amount": 500,
        "stripe_connected": bool(stripe.api_key)
    }

@app.get("/api/stripe/balance")
def get_stripe_balance():
    try:
        if not stripe.api_key:
            raise Exception("No key")
        balance = stripe.Balance.retrieve()
        available = sum(b["amount"] for b in balance["available"]) / 100
        pending = sum(b["amount"] for b in balance["pending"]) / 100
        return {
            "available": available,
            "pending": pending,
            "currency": "usd",
            "status": "live",
            "stripe_connected": True
        }
    except Exception as e:
        return {
            "available": 24830.00,
            "pending": 1200.00,
            "currency": "usd",
            "status": "demo",
            "stripe_connected": False,
            "error": str(e)
        }

@app.get("/api/stripe/transactions")
def get_transactions():
    try:
        if stripe.api_key:
            charges = stripe.Charge.list(limit=10)
            if charges.data:
                txns = []
                for c in charges.data:
                    txns.append({
                        "platform": c.description or "Stripe Payment",
                        "amount": c.amount / 100,
                        "date": "Recent transaction",
                        "type": "credit"
                    })
                return {"transactions": txns, "source": "live"}
    except:
        pass
    return {
        "transactions": [
            {"platform": "OnlyFans", "amount": 18000, "date": "Mar 10 · 28% → Tax Vault", "type": "credit"},
            {"platform": "YouTube", "amount": 3420, "date": "Mar 08 · 28% → Tax Vault", "type": "credit"},
            {"platform": "Brand Deal", "amount": 1600, "date": "Mar 05", "type": "credit"},
            {"platform": "Alpaca Auto-invest", "amount": -500, "date": "Mar 01 · SPY + QQQ", "type": "debit"},
            {"platform": "Patreon", "amount": 720, "date": "Feb 28", "type": "credit"},
        ],
        "source": "demo"
    }

@app.get("/api/tax/calculate")
def calculate_tax(income: float, tax_rate: float = 0.28):
    tax_amount = round(income * tax_rate, 2)
    spendable = round(income - tax_amount, 2)
    return {"income": income, "tax_rate": tax_rate, "tax_amount": tax_amount, "spendable": spendable}

@app.get("/api/tax/summary")
def get_tax_summary():
    return {
        "q1_target": 6200.00, "q1_saved": 4820.00, "q1_shortfall": 1380.00,
        "q1_due": "April 15, 2026", "ytd_withheld": 4820.00,
        "tax_rate": 0.28, "state": "Puerto Rico", "state_tax": 0.00
    }

@app.get("/api/alpaca/portfolio")
def get_portfolio():
    return {
        "total_value": 11240.00, "total_invested": 9500.00,
        "unrealized_gain": 1740.00, "return_pct": 18.3,
        "weekly_change": 348.20, "weekly_change_pct": 3.2,
        "auto_invest_active": True, "auto_invest_amount": 500,
        "holdings": [
            {"ticker": "SPY", "name": "S&P 500 ETF", "shares": 12.4, "value": 5620.00, "return_pct": 8.2},
            {"ticker": "QQQ", "name": "Nasdaq 100 ETF", "shares": 8.2, "value": 3480.00, "return_pct": 9.1},
            {"ticker": "JEPI", "name": "JPM Income ETF", "shares": 18.6, "value": 1240.00, "return_pct": 2.4},
            {"ticker": "IWM", "name": "Russell 2000 ETF", "shares": 5.1, "value": 740.00, "return_pct": -1.2},
        ]
    }

@app.get("/api/income/sources")
def get_income_sources():
    return {
        "month": "March 2026", "total": 24090.00,
        "sources": [
            {"platform": "OnlyFans", "amount": 18000, "pct": 72},
            {"platform": "YouTube", "amount": 3420, "pct": 14},
            {"platform": "Brand Deals", "amount": 1600, "pct": 6},
            {"platform": "Patreon", "amount": 720, "pct": 3},
            {"platform": "Merch", "amount": 350, "pct": 1},
        ]
    }

@app.get("/api/user/profile")
def get_profile():
    return {
        "name": "Creator", "handle": "@creator", "plan": "Pro",
        "tax_rate": 0.28, "state": "Puerto Rico",
        "platforms": ["OnlyFans", "YouTube", "Patreon", "Brand Deals", "Merch"],
        "services_connected": ["Stripe Treasury", "Plaid"],
        "services_pending": ["Taxfyle", "OnlyFans"]
    }

# --- User Preferences ---
user_preferences_store = {}

@app.post("/api/user/preferences")
def save_preferences(prefs: UserPreferences):
    total = prefs.tax_pct + prefs.invest_pct + prefs.spend_pct
    if abs(total - 100.0) > 0.5:
        raise HTTPException(status_code=400, detail=f"Percentages must sum to 100 (got {total})")
    user_preferences_store[prefs.user_id] = prefs.dict()
    return {"status": "saved", "preferences": prefs.dict()}

@app.get("/api/user/preferences")
def get_preferences(user_id: str = "default"):
    return user_preferences_store.get(user_id, {
        "user_id": user_id, "tax_pct": 28.0, "invest_pct": 10.0, "spend_pct": 62.0,
        "risk_score": 5, "risk_profile": "moderate", "time_horizon": "5-10",
        "income_stability": "variable", "investment_goal": "growth",
        "tos_accepted": False, "tos_accepted_at": ""
    })

# --- Detailed Tax Calculation ---

FEDERAL_BRACKETS_2026 = [
    (11600, 0.10), (47150, 0.12), (100525, 0.22),
    (191950, 0.24), (243725, 0.32), (609350, 0.35), (float('inf'), 0.37)
]

def calc_federal_tax(taxable_income: float) -> float:
    tax = 0.0
    prev = 0
    for bracket, rate in FEDERAL_BRACKETS_2026:
        if taxable_income <= prev:
            break
        taxed = min(taxable_income, bracket) - prev
        tax += taxed * rate
        prev = bracket
    return round(tax, 2)

@app.get("/api/tax/calculate-detailed")
def calculate_tax_detailed(annual_income: float, filing_status: str = "single", state: str = "PR"):
    se_taxable = annual_income * 0.9235
    se_tax = round(se_taxable * 0.153, 2)
    se_deduction = round(se_tax / 2, 2)
    agi = annual_income - se_deduction
    standard_deduction = 14600 if filing_status == "single" else 29200
    taxable_income = max(agi - standard_deduction, 0)
    federal_tax = calc_federal_tax(taxable_income)
    state_rates = {"PR": 0, "CA": 0.093, "NY": 0.0685, "TX": 0, "FL": 0, "WA": 0, "NV": 0}
    state_rate = state_rates.get(state.upper(), 0.05)
    state_tax = round(taxable_income * state_rate, 2)
    total_tax = round(se_tax + federal_tax + state_tax, 2)
    effective_rate = round((total_tax / annual_income) * 100, 1) if annual_income > 0 else 0
    quarterly = round(total_tax / 4, 2)
    return {
        "annual_income": annual_income,
        "self_employment_tax": se_tax,
        "federal_income_tax": federal_tax,
        "state_tax": state_tax,
        "state": state.upper(),
        "total_estimated_tax": total_tax,
        "effective_rate": effective_rate,
        "quarterly_payment": quarterly,
        "quarterly_schedule": [
            {"quarter": "Q1", "due": "April 15, 2026", "amount": quarterly},
            {"quarter": "Q2", "due": "June 16, 2026", "amount": quarterly},
            {"quarter": "Q3", "due": "September 15, 2026", "amount": quarterly},
            {"quarter": "Q4", "due": "January 15, 2027", "amount": quarterly},
        ],
        "breakdown": {
            "gross_income": annual_income,
            "se_tax_deduction": se_deduction,
            "agi": round(agi, 2),
            "standard_deduction": standard_deduction,
            "taxable_income": round(taxable_income, 2)
        },
        "disclaimer": "This is an estimate only, not tax advice. Consult a licensed CPA for tax filing."
    }

# --- Model Portfolio ---

MODEL_PORTFOLIOS = {
    "conservative": {
        "name": "Conservative", "description": "Capital preservation with modest growth. Lower volatility, steadier returns.",
        "allocations": [
            {"ticker": "BND", "name": "Vanguard Total Bond ETF", "pct": 60},
            {"ticker": "SPY", "name": "S&P 500 ETF", "pct": 20},
            {"ticker": "JEPI", "name": "JPM Equity Premium Income", "pct": 10},
            {"ticker": "SGOV", "name": "iShares 0-3 Month Treasury", "pct": 10},
        ],
        "expected_return": "4-6%", "risk_level": "Low"
    },
    "moderate": {
        "name": "Moderate", "description": "Balanced growth and income. Mix of stocks and bonds for steady compounding.",
        "allocations": [
            {"ticker": "SPY", "name": "S&P 500 ETF", "pct": 50},
            {"ticker": "QQQ", "name": "Nasdaq 100 ETF", "pct": 25},
            {"ticker": "JEPI", "name": "JPM Equity Premium Income", "pct": 15},
            {"ticker": "BND", "name": "Vanguard Total Bond ETF", "pct": 10},
        ],
        "expected_return": "7-10%", "risk_level": "Medium"
    },
    "growth": {
        "name": "Growth", "description": "Aggressive growth focus. Higher potential returns with more volatility.",
        "allocations": [
            {"ticker": "SPY", "name": "S&P 500 ETF", "pct": 45},
            {"ticker": "QQQ", "name": "Nasdaq 100 ETF", "pct": 35},
            {"ticker": "IWM", "name": "Russell 2000 ETF", "pct": 15},
            {"ticker": "BND", "name": "Vanguard Total Bond ETF", "pct": 5},
        ],
        "expected_return": "10-14%", "risk_level": "High"
    },
    "aggressive": {
        "name": "Aggressive", "description": "Maximum growth potential. High volatility, suited for long time horizons.",
        "allocations": [
            {"ticker": "QQQ", "name": "Nasdaq 100 ETF", "pct": 40},
            {"ticker": "SPY", "name": "S&P 500 ETF", "pct": 35},
            {"ticker": "IWM", "name": "Russell 2000 ETF", "pct": 20},
            {"ticker": "ARKK", "name": "ARK Innovation ETF", "pct": 5},
        ],
        "expected_return": "12-18%", "risk_level": "Very High"
    }
}

@app.get("/api/alpaca/model-portfolio")
def get_model_portfolio(risk_score: int = 5):
    if risk_score <= 3:
        profile = "conservative"
    elif risk_score <= 6:
        profile = "moderate"
    elif risk_score <= 8:
        profile = "growth"
    else:
        profile = "aggressive"
    portfolio = MODEL_PORTFOLIOS[profile]
    return {
        **portfolio,
        "risk_score": risk_score,
        "profile_key": profile,
        "disclaimer": "Portfolio recommendations powered by Alpaca Securities LLC, member FINRA/SIPC. This is not investment advice. Past performance does not guarantee future results."
    }

# --- Allocation Simulation ---

@app.get("/api/income/simulate-allocation")
def simulate_allocation(monthly_income: float = 8000, tax_pct: float = 28, invest_pct: float = 10, spend_pct: float = 62):
    months = []
    tax_vault = 0
    invest_total = 0
    spend_total = 0
    tax_monthly = round(monthly_income * tax_pct / 100, 2)
    invest_monthly = round(monthly_income * invest_pct / 100, 2)
    spend_monthly = round(monthly_income * spend_pct / 100, 2)
    quarterly_due = {4: "Q1 Apr 15", 6: "Q2 Jun 16", 9: "Q3 Sep 15", 12: "Q4 Jan 15"}
    for m in range(1, 13):
        tax_vault += tax_monthly
        invest_total += invest_monthly
        spend_total += spend_monthly
        payment = 0
        if m in quarterly_due:
            payment = round(tax_vault * 0.9, 2)
            tax_vault = round(tax_vault - payment, 2)
        months.append({
            "month": m, "tax_vault": round(tax_vault, 2),
            "invest_total": round(invest_total, 2), "spend_total": round(spend_total, 2),
            "quarterly_payment": payment, "quarterly_label": quarterly_due.get(m, "")
        })
    return {
        "monthly_income": monthly_income,
        "allocation": {"tax_pct": tax_pct, "invest_pct": invest_pct, "spend_pct": spend_pct},
        "monthly_amounts": {"tax": tax_monthly, "invest": invest_monthly, "spend": spend_monthly},
        "projection": months,
        "annual_summary": {
            "total_income": round(monthly_income * 12, 2),
            "total_invested": round(invest_monthly * 12, 2),
            "total_tax_payments": sum(m["quarterly_payment"] for m in months)
        }
    }

# --- Plaid Endpoints ---

@app.post("/api/plaid/create-link-token")
def create_link_token(user_id: str = "default"):
    try:
        request = LinkTokenCreateRequest(
            products=[Products("transactions"), Products("auth")],
            client_name="Apexa",
            country_codes=[CountryCode("US")],
            language="en",
            user=LinkTokenCreateRequestUser(client_user_id=user_id)
        )
        response = plaid_client.link_token_create(request)
        return {"link_token": response.link_token}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/plaid/exchange-token")
def exchange_public_token(req: PublicTokenRequest):
    try:
        exchange_request = ItemPublicTokenExchangeRequest(public_token=req.public_token)
        response = plaid_client.item_public_token_exchange(exchange_request)
        user_access_tokens[req.user_id] = response.access_token
        return {"status": "connected", "item_id": response.item_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/plaid/accounts")
def get_accounts(user_id: str = "default"):
    access_token = user_access_tokens.get(user_id)
    if not access_token:
        return {
            "accounts": [
                {"name": "Chase Checking", "type": "depository", "subtype": "checking", "balance": 4820.50, "mask": "4521"},
                {"name": "Chase Savings", "type": "depository", "subtype": "savings", "balance": 12340.00, "mask": "8832"},
            ],
            "source": "demo"
        }
    try:
        request = AccountsGetRequest(access_token=access_token)
        response = plaid_client.accounts_get(request)
        accounts = []
        for acct in response.accounts:
            accounts.append({
                "name": acct.name,
                "type": acct.type.value,
                "subtype": acct.subtype.value if acct.subtype else None,
                "balance": acct.balances.current,
                "mask": acct.mask
            })
        return {"accounts": accounts, "source": "live"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/plaid/status")
def plaid_status():
    return {
        "configured": bool(PLAID_CLIENT_ID and PLAID_SECRET),
        "environment": PLAID_ENV,
        "connected_users": len(user_access_tokens)
    }
