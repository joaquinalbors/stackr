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

# --- Stripe Connect — Creator Accounts & Income Splitting ---

class CreatorAccountRequest(BaseModel):
    email: str
    first_name: str = ""
    last_name: str = ""

@app.post("/api/connect/create-account")
def create_connected_account(req: CreatorAccountRequest):
    """Create a Stripe Connect Express account for a creator."""
    if not stripe.api_key:
        return {"account_id": "acct_demo_123", "status": "demo", "message": "Stripe not configured."}
    try:
        account = stripe.Account.create(
            type="express",
            country="US",
            email=req.email,
            capabilities={"transfers": {"requested": True}},
            business_type="individual",
            individual={"first_name": req.first_name, "last_name": req.last_name, "email": req.email},
            metadata={"platform": "apexa", "type": "creator"},
        )
        return {"account_id": account.id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/connect/onboarding-link")
def create_onboarding_link(account_id: str):
    """Generate Stripe Connect onboarding link for a creator to verify identity."""
    if not stripe.api_key:
        return {"url": "#", "status": "demo"}
    try:
        link = stripe.AccountLink.create(
            account=account_id,
            refresh_url="https://joaquinalbors.github.io/stackr/",
            return_url="https://joaquinalbors.github.io/stackr/",
            type="account_onboarding",
        )
        return {"url": link.url, "status": "live"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/connect/account-status")
def get_connect_account_status(account_id: str = ""):
    """Check if a creator's Connect account is fully set up."""
    if not stripe.api_key or not account_id:
        return {"verified": False, "payouts_enabled": False, "charges_enabled": False, "source": "demo"}
    try:
        account = stripe.Account.retrieve(account_id)
        return {
            "verified": account.details_submitted,
            "payouts_enabled": account.payouts_enabled,
            "charges_enabled": account.charges_enabled,
            "email": account.email,
            "source": "live"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class SplitPaymentRequest(BaseModel):
    amount: float  # Total payment amount in dollars
    user_id: str = "default"
    description: str = "Creator income"

@app.post("/api/connect/split-payment")
def split_incoming_payment(req: SplitPaymentRequest):
    """
    Simulate/execute income splitting based on user's allocation preferences.
    Splits incoming payment into tax vault, investment, and spending.
    """
    # Get user allocation preferences
    prefs = user_preferences_store.get(req.user_id, {
        "tax_pct": 28.0, "invest_pct": 10.0, "spend_pct": 62.0
    })
    tax_pct = prefs.get("tax_pct", 28.0)
    invest_pct = prefs.get("invest_pct", 10.0)
    spend_pct = prefs.get("spend_pct", 62.0)

    tax_amount = round(req.amount * tax_pct / 100, 2)
    invest_amount = round(req.amount * invest_pct / 100, 2)
    spend_amount = round(req.amount - tax_amount - invest_amount, 2)

    splits = {
        "total_payment": req.amount,
        "tax_vault": {"amount": tax_amount, "pct": tax_pct, "destination": "Stripe Treasury — Tax Vault"},
        "investments": {"amount": invest_amount, "pct": invest_pct, "destination": "DriveWealth — Managed Portfolio"},
        "spending": {"amount": spend_amount, "pct": spend_pct, "destination": "Stripe Treasury — Available Balance"},
        "description": req.description,
    }

    if not stripe.api_key:
        return {**splits, "status": "demo", "message": "Demo mode — no real transfers executed.",
                "disclaimer": "Funds held by Stripe Treasury. Investments managed by DriveWealth. Apexa does not hold funds."}

    # In production: execute actual transfers via Stripe Treasury
    # stripe.Transfer.create(amount=int(tax_amount*100), currency="usd", destination=tax_vault_account)
    # stripe.Transfer.create(amount=int(invest_amount*100), currency="usd", destination=drivewealth_funding_account)
    return {**splits, "status": "executed",
            "disclaimer": "Funds held by Stripe Treasury. Investments managed by DriveWealth. Apexa does not hold funds."}

@app.post("/api/connect/simulate-income")
def simulate_income_event(amount: float = 5000, platform: str = "YouTube", user_id: str = "default"):
    """
    Simulate a creator receiving income — shows how it would be split.
    Used for onboarding preview and dashboard projections.
    """
    prefs = user_preferences_store.get(user_id, {
        "tax_pct": 28.0, "invest_pct": 10.0, "spend_pct": 62.0
    })
    tax_pct = prefs.get("tax_pct", 28.0)
    invest_pct = prefs.get("invest_pct", 10.0)

    tax = round(amount * tax_pct / 100, 2)
    invest = round(amount * invest_pct / 100, 2)
    spend = round(amount - tax - invest, 2)

    return {
        "platform": platform,
        "gross_payment": amount,
        "split": [
            {"bucket": "Tax Vault", "amount": tax, "icon": "🔒", "provider": "Stripe Treasury"},
            {"bucket": "Investments", "amount": invest, "icon": "📈", "provider": "DriveWealth"},
            {"bucket": "Spending", "amount": spend, "icon": "💰", "provider": "Stripe Treasury"},
        ],
        "disclaimer": "Funds held by Stripe Treasury. Investments managed by DriveWealth. Apexa does not hold or manage funds."
    }

# --- Agency Management (Sandbox) ---

import uuid

# In-memory stores for agency sandbox data
agency_store = {}
agency_creators_store = {}
agency_payouts_store = {}

class AgencyOnboardRequest(BaseModel):
    name: str
    ein: str
    contact_email: str
    platforms: List[str]
    estimated_volume: float

class AgencyInviteCreatorRequest(BaseModel):
    agency_id: str
    creator_name: str
    creator_email: str
    platform: str
    split_percentage: float

class CreatorPayoutItem(BaseModel):
    creator_id: str
    gross_amount: float

class AgencyProcessPayoutRequest(BaseModel):
    agency_id: str
    payouts: List[CreatorPayoutItem]

@app.post("/api/agency/onboard")
def agency_onboard(req: AgencyOnboardRequest):
    """Create an agency profile. Sandbox mode simulates Stripe Connect account creation."""
    agency_id = f"agency_{uuid.uuid4().hex[:12]}"
    simulated_stripe_account = f"acct_sandbox_{uuid.uuid4().hex[:10]}"
    agency_store[agency_id] = {
        "agency_id": agency_id,
        "name": req.name,
        "ein": req.ein,
        "contact_email": req.contact_email,
        "platforms": req.platforms,
        "estimated_volume": req.estimated_volume,
        "stripe_connect_account": simulated_stripe_account,
        "created_at": datetime.utcnow().isoformat(),
        "status": "active",
    }
    agency_creators_store[agency_id] = []
    agency_payouts_store[agency_id] = []
    return {
        "agency_id": agency_id,
        "stripe_connect_account": simulated_stripe_account,
        "status": "active",
        "source": "sandbox",
        "disclaimer": "This is sandbox/demo data. No real Stripe Connect account was created. For production use, integrate with Stripe Connect onboarding."
    }

@app.post("/api/agency/invite-creator")
def agency_invite_creator(req: AgencyInviteCreatorRequest):
    """Invite a creator to join the agency roster."""
    if req.agency_id not in agency_store:
        raise HTTPException(status_code=404, detail=f"Agency {req.agency_id} not found.")
    if req.split_percentage < 0 or req.split_percentage > 100:
        raise HTTPException(status_code=400, detail="split_percentage must be between 0 and 100.")
    creator_id = f"creator_{uuid.uuid4().hex[:10]}"
    invite = {
        "creator_id": creator_id,
        "creator_name": req.creator_name,
        "creator_email": req.creator_email,
        "platform": req.platform,
        "split_percentage": req.split_percentage,
        "status": "invited",
        "invited_at": datetime.utcnow().isoformat(),
        "total_volume": 0.0,
    }
    agency_creators_store.setdefault(req.agency_id, []).append(invite)
    return {
        "creator_id": creator_id,
        "invite_status": "invited",
        "creator_name": req.creator_name,
        "creator_email": req.creator_email,
        "platform": req.platform,
        "split_percentage": req.split_percentage,
        "source": "sandbox",
        "disclaimer": "This is sandbox/demo data. No real invitation email was sent. In production, an email invite would be dispatched to the creator."
    }

@app.post("/api/agency/process-payout")
def agency_process_payout(req: AgencyProcessPayoutRequest):
    """Process payouts for creators under the agency. Calculates splits, applies 1.5% processing fee."""
    if req.agency_id not in agency_store:
        raise HTTPException(status_code=404, detail=f"Agency {req.agency_id} not found.")

    PROCESSING_FEE_RATE = 0.015
    creators_map = {c["creator_id"]: c for c in agency_creators_store.get(req.agency_id, [])}
    payout_results = []
    total_gross = 0.0
    total_agency_cut = 0.0
    total_processing_fee = 0.0
    total_net_to_creators = 0.0

    for item in req.payouts:
        creator = creators_map.get(item.creator_id)
        if not creator:
            payout_results.append({
                "creator_id": item.creator_id,
                "error": f"Creator {item.creator_id} not found in agency roster."
            })
            continue

        split_pct = creator["split_percentage"]
        agency_cut = round(item.gross_amount * split_pct / 100, 2)
        processing_fee = round(item.gross_amount * PROCESSING_FEE_RATE, 2)
        net_to_creator = round(item.gross_amount - agency_cut - processing_fee, 2)

        total_gross += item.gross_amount
        total_agency_cut += agency_cut
        total_processing_fee += processing_fee
        total_net_to_creators += net_to_creator

        # Update creator total volume
        creator["total_volume"] = round(creator["total_volume"] + item.gross_amount, 2)

        payout_results.append({
            "creator_id": item.creator_id,
            "creator_name": creator["creator_name"],
            "gross_amount": item.gross_amount,
            "split_percentage": split_pct,
            "agency_cut": agency_cut,
            "processing_fee": processing_fee,
            "net_to_creator": net_to_creator,
        })

    # Store payout record
    payout_record = {
        "payout_id": f"payout_{uuid.uuid4().hex[:10]}",
        "agency_id": req.agency_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total_gross": round(total_gross, 2),
        "total_agency_cut": round(total_agency_cut, 2),
        "total_processing_fee": round(total_processing_fee, 2),
        "total_net_to_creators": round(total_net_to_creators, 2),
        "creator_payouts": payout_results,
        "status": "completed",
    }
    agency_payouts_store.setdefault(req.agency_id, []).append(payout_record)

    return {
        "payout_id": payout_record["payout_id"],
        "total_gross": round(total_gross, 2),
        "agency_cut": round(total_agency_cut, 2),
        "processing_fee": round(total_processing_fee, 2),
        "net_to_creators": round(total_net_to_creators, 2),
        "creator_payouts": payout_results,
        "status": "completed",
        "source": "sandbox",
        "disclaimer": "This is sandbox/demo data. No real funds were transferred. Processing fee of 1.5% is simulated. In production, payouts would be executed via Stripe Connect transfers."
    }

@app.get("/api/agency/roster")
def agency_roster(agency_id: str):
    """Returns the list of creators under the agency."""
    if agency_id not in agency_store:
        raise HTTPException(status_code=404, detail=f"Agency {agency_id} not found.")
    creators = agency_creators_store.get(agency_id, [])
    return {
        "agency_id": agency_id,
        "agency_name": agency_store[agency_id]["name"],
        "creator_count": len(creators),
        "creators": [
            {
                "creator_id": c["creator_id"],
                "creator_name": c["creator_name"],
                "creator_email": c["creator_email"],
                "platform": c["platform"],
                "split_percentage": c["split_percentage"],
                "total_volume": c["total_volume"],
                "status": c["status"],
            }
            for c in creators
        ],
        "source": "sandbox",
        "disclaimer": "This is sandbox/demo data. Creator roster is stored in memory and will reset on server restart."
    }

@app.get("/api/agency/payouts")
def agency_payouts(agency_id: str):
    """Returns payout history for the agency."""
    if agency_id not in agency_store:
        raise HTTPException(status_code=404, detail=f"Agency {agency_id} not found.")
    payouts = agency_payouts_store.get(agency_id, [])
    return {
        "agency_id": agency_id,
        "agency_name": agency_store[agency_id]["name"],
        "total_payouts": len(payouts),
        "payouts": [
            {
                "payout_id": p["payout_id"],
                "timestamp": p["timestamp"],
                "total_gross": p["total_gross"],
                "agency_cut": p["total_agency_cut"],
                "processing_fee": p["total_processing_fee"],
                "net_to_creators": p["total_net_to_creators"],
                "creator_count": len(p["creator_payouts"]),
                "status": p["status"],
            }
            for p in payouts
        ],
        "source": "sandbox",
        "disclaimer": "This is sandbox/demo data. Payout history is stored in memory and will reset on server restart."
    }

@app.get("/api/agency/stats")
def agency_stats(agency_id: str):
    """Returns agency dashboard stats."""
    if agency_id not in agency_store:
        raise HTTPException(status_code=404, detail=f"Agency {agency_id} not found.")
    agency = agency_store[agency_id]
    creators = agency_creators_store.get(agency_id, [])
    payouts = agency_payouts_store.get(agency_id, [])

    total_volume = sum(p["total_gross"] for p in payouts)
    total_revenue = sum(p["total_processing_fee"] for p in payouts)
    creator_count = len(creators)
    avg_split = round(sum(c["split_percentage"] for c in creators) / creator_count, 2) if creator_count > 0 else 0.0

    # Simulated monthly subscription revenue based on creator count
    MONTHLY_SUB_PER_CREATOR = 29.99
    monthly_sub_revenue = round(creator_count * MONTHLY_SUB_PER_CREATOR, 2)

    return {
        "agency_id": agency_id,
        "agency_name": agency["name"],
        "total_volume": round(total_volume, 2),
        "total_revenue": round(total_revenue, 2),
        "creator_count": creator_count,
        "avg_split": avg_split,
        "monthly_sub_revenue": monthly_sub_revenue,
        "platforms": agency["platforms"],
        "status": agency["status"],
        "source": "sandbox",
        "disclaimer": "This is sandbox/demo data. Stats are computed from in-memory sandbox transactions. Monthly subscription revenue is simulated at $29.99 per creator."
    }
