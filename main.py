from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os
import stripe
import httpx
from datetime import datetime
import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
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

# Alpaca setup
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# Stripe subscription products
STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO", "")
STRIPE_PRICE_PREMIUM = os.getenv("STRIPE_PRICE_PREMIUM", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

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

STATE_TAX_RATES = {
    "AL":0.05,"AK":0,"AZ":0.025,"AR":0.047,"CA":0.093,"CO":0.044,"CT":0.0699,"DE":0.066,
    "FL":0,"GA":0.0549,"HI":0.0825,"ID":0.058,"IL":0.0495,"IN":0.0315,"IA":0.06,"KS":0.057,
    "KY":0.04,"LA":0.0425,"ME":0.0715,"MD":0.0575,"MA":0.05,"MI":0.0425,"MN":0.0985,
    "MS":0.05,"MO":0.048,"MT":0.059,"NE":0.0664,"NV":0,"NH":0,"NJ":0.0897,"NM":0.059,
    "NY":0.0685,"NC":0.0475,"ND":0.0195,"OH":0.04,"OK":0.0475,"OR":0.099,"PA":0.0307,
    "PR":0,"RI":0.0599,"SC":0.064,"SD":0,"TN":0,"TX":0,"UT":0.0485,"VT":0.0875,
    "VA":0.0575,"WA":0,"WV":0.052,"WI":0.0765,"WY":0,"DC":0.0895
}

@app.get("/api/tax/calculate-detailed")
def calculate_tax_detailed(
    annual_income: float, filing_status: str = "single", state: str = "TX",
    annual_expenses: float = 0, home_office: bool = False, w2_income: float = 0,
    w2_withholding: float = 0, tax_credits: float = 0, prior_payments: float = 0
):
    # Business deductions
    home_office_deduction = 1500 if home_office else 0
    total_deductions = annual_expenses + home_office_deduction
    net_se_income = max(annual_income - total_deductions, 0)

    # Self-employment tax (only on creator income, not W-2)
    se_taxable = net_se_income * 0.9235
    se_tax = round(se_taxable * 0.153, 2)
    se_deduction = round(se_tax / 2, 2)

    # QBI deduction — 20% of qualified business income (simplified)
    # Phase-out starts at $191,950 single / $383,900 married
    qbi_limit = 191950 if filing_status == "single" else 383900
    if net_se_income <= qbi_limit:
        qbi_deduction = round(net_se_income * 0.20, 2)
    else:
        qbi_deduction = round(qbi_limit * 0.20, 2)

    # AGI includes both SE and W-2
    total_income = net_se_income + w2_income
    agi = total_income - se_deduction

    # Standard deduction based on filing status
    std_ded = {"single": 14600, "married": 29200, "head": 21900}
    standard_deduction = std_ded.get(filing_status, 14600)

    # Taxable income after standard deduction + QBI
    taxable_income = max(agi - standard_deduction - qbi_deduction, 0)

    federal_tax = calc_federal_tax(taxable_income)

    # Apply tax credits (reduce tax dollar-for-dollar)
    federal_tax = max(federal_tax - tax_credits, 0)

    # State tax (all 50 states + DC)
    state_rate = STATE_TAX_RATES.get(state.upper(), 0.05)
    state_tax = round(taxable_income * state_rate, 2)
    no_state_tax = state_rate == 0

    # Total tax before credits/payments
    total_tax = round(se_tax + federal_tax + state_tax, 2)

    # What's still owed after withholdings and prior payments
    already_paid = w2_withholding + prior_payments
    remaining_owed = max(total_tax - already_paid, 0)

    effective_rate = round((total_tax / (annual_income + w2_income)) * 100, 1) if (annual_income + w2_income) > 0 else 0
    quarterly = round(remaining_owed / 4, 2)

    # Tax savings from deductions
    total_savings = round(total_deductions + qbi_deduction + standard_deduction, 2)

    return {
        "annual_income": annual_income,
        "self_employment_tax": se_tax,
        "federal_income_tax": round(federal_tax, 2),
        "state_tax": state_tax,
        "state": state.upper(),
        "total_estimated_tax": total_tax,
        "already_paid": already_paid,
        "remaining_owed": round(remaining_owed, 2),
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
            "w2_income": w2_income,
            "business_expenses": annual_expenses,
            "home_office_deduction": home_office_deduction,
            "net_se_income": round(net_se_income, 2),
            "se_tax_deduction": se_deduction,
            "qbi_deduction": qbi_deduction,
            "agi": round(agi, 2),
            "standard_deduction": standard_deduction,
            "taxable_income": round(taxable_income, 2),
            "tax_credits_applied": tax_credits,
            "w2_withholding": w2_withholding,
            "prior_quarterly_payments": prior_payments,
            "total_deduction_savings": total_savings
        },
        "no_state_tax": no_state_tax,
        "state_rate_pct": round(state_rate * 100, 1),
        "filing_status": filing_status,
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

# --- Plaid Transactions & Expense Categorization ---

DEDUCTION_CATEGORIES = {
    "Software": ["adobe", "canva", "notion", "figma", "dropbox", "google workspace", "microsoft", "zoom", "slack", "chatgpt", "openai", "midjourney"],
    "Equipment": ["apple", "best buy", "b&h photo", "amazon", "newegg", "adorama"],
    "Internet & Phone": ["verizon", "at&t", "t-mobile", "comcast", "xfinity", "spectrum", "cox"],
    "Advertising": ["facebook ads", "meta ads", "google ads", "tiktok ads", "instagram", "twitter ads", "pinterest"],
    "Travel": ["uber", "lyft", "airbnb", "hotel", "airlines", "southwest", "delta", "united", "american airlines", "jetblue"],
    "Meals (50%)": ["doordash", "grubhub", "uber eats", "restaurant"],
    "Education": ["udemy", "skillshare", "masterclass", "coursera", "linkedin learning"],
    "Professional Services": ["legal", "attorney", "accountant", "cpa", "bookkeeper"],
    "Office Supplies": ["staples", "office depot", "target", "walmart"],
    "Subscriptions": ["patreon", "substack", "mailchimp", "convertkit", "beehiiv"],
}

def categorize_expense(description: str) -> dict:
    desc_lower = description.lower()
    for category, keywords in DEDUCTION_CATEGORIES.items():
        for kw in keywords:
            if kw in desc_lower:
                return {"category": category, "deductible": True, "match": kw}
    return {"category": None, "deductible": False, "match": None}

@app.get("/api/plaid/transactions")
def get_plaid_transactions(user_id: str = "default", days: int = 90):
    access_token = user_access_tokens.get(user_id)
    if not access_token:
        # Demo data
        demo_txns = [
            {"date": "2026-03-15", "description": "Adobe Creative Cloud", "amount": -54.99, "category": "Software", "deductible": True},
            {"date": "2026-03-12", "description": "Amazon - Ring Light", "amount": -89.99, "category": "Equipment", "deductible": True},
            {"date": "2026-03-10", "description": "Starbucks", "amount": -6.50, "category": None, "deductible": False},
            {"date": "2026-03-08", "description": "Verizon Wireless", "amount": -85.00, "category": "Internet & Phone", "deductible": True},
            {"date": "2026-03-05", "description": "TikTok Ads", "amount": -200.00, "category": "Advertising", "deductible": True},
            {"date": "2026-03-03", "description": "Uber Eats", "amount": -32.00, "category": "Meals (50%)", "deductible": True},
            {"date": "2026-03-01", "description": "Canva Pro", "amount": -12.99, "category": "Software", "deductible": True},
            {"date": "2026-02-28", "description": "Netflix", "amount": -15.99, "category": None, "deductible": False},
            {"date": "2026-02-25", "description": "Google Ads", "amount": -150.00, "category": "Advertising", "deductible": True},
            {"date": "2026-02-20", "description": "Zoom Pro", "amount": -13.33, "category": "Software", "deductible": True},
        ]
        total_deductible = sum(abs(t["amount"]) for t in demo_txns if t["deductible"])
        return {"transactions": demo_txns, "total_deductible": round(total_deductible, 2), "period_days": days, "source": "demo"}
    try:
        from datetime import date, timedelta
        end = date.today()
        start = end - timedelta(days=days)
        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start,
            end_date=end,
            options=TransactionsGetRequestOptions(count=100)
        )
        response = plaid_client.transactions_get(request)
        txns = []
        for t in response.transactions:
            cat_info = categorize_expense(t.name or "")
            txns.append({
                "date": str(t.date),
                "description": t.name,
                "amount": -t.amount,
                "category": cat_info["category"],
                "deductible": cat_info["deductible"],
                "plaid_category": t.category,
            })
        total_deductible = sum(abs(t["amount"]) for t in txns if t["deductible"])
        return {"transactions": txns, "total_deductible": round(total_deductible, 2), "period_days": days, "source": "live"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/plaid/deduction-summary")
def get_deduction_summary(user_id: str = "default"):
    txns_response = get_plaid_transactions(user_id, 365)
    txns = txns_response["transactions"]
    by_category = {}
    for t in txns:
        if t["deductible"] and t["category"]:
            cat = t["category"]
            if cat not in by_category:
                by_category[cat] = {"category": cat, "total": 0, "count": 0}
            by_category[cat]["total"] = round(by_category[cat]["total"] + abs(t["amount"]), 2)
            by_category[cat]["count"] += 1
    categories = sorted(by_category.values(), key=lambda x: x["total"], reverse=True)
    total = sum(c["total"] for c in categories)
    estimated_savings = round(total * 0.28, 2)
    return {
        "categories": categories,
        "total_deductible": round(total, 2),
        "estimated_tax_savings": estimated_savings,
        "period": "Last 12 months",
        "source": txns_response["source"],
        "disclaimer": "Deduction categories are estimates. Consult a CPA to confirm eligibility."
    }

# --- Alpaca Trading & Rebalancing ---

async def alpaca_request(method: str, path: str, data: dict = None) -> dict:
    if not ALPACA_API_KEY:
        return None
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    }
    async with httpx.AsyncClient() as client:
        url = f"{ALPACA_BASE_URL}{path}"
        if method == "GET":
            r = await client.get(url, headers=headers)
        elif method == "POST":
            r = await client.post(url, headers=headers, json=data)
        elif method == "DELETE":
            r = await client.delete(url, headers=headers)
        else:
            return None
        if r.status_code >= 400:
            return {"error": r.text, "status": r.status_code}
        return r.json() if r.text else {}

@app.get("/api/alpaca/account")
async def get_alpaca_account():
    result = await alpaca_request("GET", "/v2/account")
    if not result:
        return {
            "cash": 24830.00, "portfolio_value": 11240.00,
            "buying_power": 24830.00, "equity": 36070.00,
            "status": "ACTIVE", "source": "demo",
            "configured": False
        }
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])
    return {
        "cash": float(result.get("cash", 0)),
        "portfolio_value": float(result.get("portfolio_value", 0)),
        "buying_power": float(result.get("buying_power", 0)),
        "equity": float(result.get("equity", 0)),
        "status": result.get("status", "UNKNOWN"),
        "source": "live",
        "configured": True
    }

@app.get("/api/alpaca/positions")
async def get_alpaca_positions():
    result = await alpaca_request("GET", "/v2/positions")
    if not result or isinstance(result, dict):
        return {"positions": MODEL_PORTFOLIOS["moderate"]["allocations"], "source": "demo"}
    positions = []
    for p in result:
        positions.append({
            "ticker": p["symbol"],
            "name": p.get("name", p["symbol"]),
            "shares": float(p["qty"]),
            "value": float(p["market_value"]),
            "cost_basis": float(p["cost_basis"]),
            "unrealized_pl": float(p["unrealized_pl"]),
            "unrealized_pl_pct": float(p["unrealized_plpc"]) * 100,
            "current_price": float(p["current_price"]),
        })
    return {"positions": positions, "source": "live"}

class OrderRequest(BaseModel):
    symbol: str
    amount: float
    side: str = "buy"

@app.post("/api/alpaca/order")
async def place_alpaca_order(order: OrderRequest):
    if not ALPACA_API_KEY:
        return {
            "status": "demo", "message": f"Demo: Would {order.side} ${order.amount} of {order.symbol}",
            "order_id": "demo-" + order.symbol.lower(),
            "configured": False
        }
    result = await alpaca_request("POST", "/v2/orders", {
        "symbol": order.symbol,
        "notional": str(order.amount),
        "side": order.side,
        "type": "market",
        "time_in_force": "day",
    })
    if not result or "error" in result:
        raise HTTPException(status_code=400, detail=result.get("error", "Order failed"))
    return {
        "status": "filled" if result.get("status") == "filled" else result.get("status", "submitted"),
        "order_id": result.get("id"),
        "symbol": order.symbol,
        "amount": order.amount,
        "side": order.side,
        "source": "live"
    }

class RebalanceRequest(BaseModel):
    risk_score: int = 5
    total_amount: float = 500.0

@app.post("/api/alpaca/rebalance")
async def rebalance_portfolio(req: RebalanceRequest):
    portfolio = get_model_portfolio(req.risk_score)
    orders = []
    for alloc in portfolio["allocations"]:
        amount = round(req.total_amount * alloc["pct"] / 100, 2)
        if amount < 1:
            continue
        if ALPACA_API_KEY:
            result = await alpaca_request("POST", "/v2/orders", {
                "symbol": alloc["ticker"],
                "notional": str(amount),
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            })
            orders.append({
                "ticker": alloc["ticker"], "amount": amount, "pct": alloc["pct"],
                "status": result.get("status", "submitted") if result and "error" not in result else "failed",
                "source": "live"
            })
        else:
            orders.append({
                "ticker": alloc["ticker"], "amount": amount, "pct": alloc["pct"],
                "status": "demo", "source": "demo"
            })
    return {
        "profile": portfolio["name"],
        "risk_score": req.risk_score,
        "total_invested": req.total_amount,
        "orders": orders,
        "disclaimer": "Trades executed by Alpaca Securities LLC, member FINRA/SIPC. This is not investment advice."
    }

@app.get("/api/alpaca/trading-status")
async def alpaca_trading_status():
    return {
        "configured": bool(ALPACA_API_KEY),
        "environment": "paper" if "paper" in ALPACA_BASE_URL else "live",
        "base_url": ALPACA_BASE_URL
    }

# --- Stripe Subscriptions ---

class CheckoutRequest(BaseModel):
    plan: str  # "pro" or "premium"
    success_url: str = "https://joaquinalbors.github.io/stackr/"
    cancel_url: str = "https://joaquinalbors.github.io/stackr/"

@app.post("/api/stripe/create-checkout")
def create_checkout(req: CheckoutRequest):
    if not stripe.api_key:
        return {"url": "#", "status": "demo", "message": "Stripe not configured. Demo mode."}
    price_id = STRIPE_PRICE_PRO if req.plan == "pro" else STRIPE_PRICE_PREMIUM
    if not price_id:
        return {"url": "#", "status": "demo", "message": f"No price ID set for {req.plan} plan."}
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=req.success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=req.cancel_url,
        )
        return {"url": session.url, "session_id": session.id, "status": "live"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/stripe/create-portal")
def create_billing_portal(customer_id: str = ""):
    if not stripe.api_key or not customer_id:
        return {"url": "#", "status": "demo", "message": "Billing portal demo mode."}
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url="https://joaquinalbors.github.io/stackr/",
        )
        return {"url": session.url, "status": "live"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/stripe/subscription-status")
def get_subscription_status(customer_id: str = ""):
    if not stripe.api_key or not customer_id:
        return {"plan": "free", "status": "active", "source": "demo"}
    try:
        subs = stripe.Subscription.list(customer=customer_id, limit=1)
        if subs.data:
            sub = subs.data[0]
            price_id = sub["items"]["data"][0]["price"]["id"]
            plan = "premium" if price_id == STRIPE_PRICE_PREMIUM else "pro"
            return {"plan": plan, "status": sub["status"], "current_period_end": sub["current_period_end"], "source": "live"}
        return {"plan": "free", "status": "active", "source": "live"}
    except Exception as e:
        return {"plan": "free", "status": "active", "source": "demo", "error": str(e)}
