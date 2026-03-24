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
