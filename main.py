"""
Apexa — Creator Finance Platform
Backend API v1.1
© 2026 Albors Advisory LLC

FastAPI backend powering the Apexa fintech platform for content creators.
Stack: Plaid (bank linking) → Stripe Connect (brand payouts) → Atomic (Tax Vault, investing)
       Tight/Hurdlr (accounting + tax data layer)
"""

import os
import time
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
import stripe
import httpx

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Apexa API",
    description="Creator Finance Platform — Tax Vault, Invest, Bank",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://apexa-app.netlify.app",
        "http://localhost:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Environment variables (Railway env vars)
# ---------------------------------------------------------------------------
STRIPE_SECRET_KEY       = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET   = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PLAID_CLIENT_ID         = os.getenv("PLAID_CLIENT_ID", "")
PLAID_SECRET            = os.getenv("PLAID_SECRET", "")
PLAID_ENV               = os.getenv("PLAID_ENV", "sandbox")   # sandbox | development | production
ATOMIC_API_KEY          = os.getenv("ATOMIC_API_KEY", "")
TIGHT_API_KEY           = os.getenv("TIGHT_API_KEY", "")
JWT_SECRET              = os.getenv("JWT_SECRET", "apexa-beta-secret-change-me")

stripe.api_key = STRIPE_SECRET_KEY

PLAID_BASE_URLS = {
    "sandbox":     "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production":  "https://production.plaid.com",
}
PLAID_BASE = PLAID_BASE_URLS.get(PLAID_ENV, "https://sandbox.plaid.com")

# ---------------------------------------------------------------------------
# In-memory store (replace with PostgreSQL for production)
# ---------------------------------------------------------------------------
users_db: dict = {}     # email -> user dict
sessions_db: dict = {}  # token -> email

# ---------------------------------------------------------------------------
# Default auto-split percentages (creator can customize)
# ---------------------------------------------------------------------------
DEFAULT_SPLIT = {
    "tax_vault_pct":  0.25,   # 25% to Atomic Tax Vault (HYSA)
    "invest_pct":     0.15,   # 15% to Atomic Portfolio
    "spendable_pct":  0.60,   # 60% to Atomic Spendable
}

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class UserSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str
    platform: str = "independent"  # independent, youtube, twitch, podcast, etc.

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class IncomeEntry(BaseModel):
    amount: float = Field(gt=0)
    source: str = "brand_deal"
    description: Optional[str] = None

class TaxVaultConfig(BaseModel):
    tax_rate: float = Field(ge=0.0, le=0.60, default=0.28)
    auto_vault: bool = True

class SplitConfig(BaseModel):
    tax_vault_pct: float = Field(ge=0.0, le=1.0, default=0.25)
    invest_pct:    float = Field(ge=0.0, le=1.0, default=0.15)
    spendable_pct: float = Field(ge=0.0, le=1.0, default=0.60)

class PlaidExchangeRequest(BaseModel):
    public_token: str
    account_id: str

class BrandPayoutRequest(BaseModel):
    creator_email: EmailStr
    amount: float = Field(gt=0)
    description: Optional[str] = "Brand payment via Apexa"

class CreatorWithdrawRequest(BaseModel):
    amount: float = Field(gt=0)

class StripeConnectRequest(BaseModel):
    country: str = "US"

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def create_token(email: str) -> str:
    payload = f"{email}:{time.time()}"
    token = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    sessions_db[token] = email
    return token

def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ")[1]
    email = sessions_db.get(token)
    if not email or email not in users_db:
        raise HTTPException(status_code=401, detail="Invalid session")
    return users_db[email]

# ---------------------------------------------------------------------------
# Plaid helpers
# ---------------------------------------------------------------------------

def _plaid_post(path: str, body: dict) -> dict:
    """Authenticated POST to Plaid REST API."""
    if not PLAID_CLIENT_ID or not PLAID_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Plaid not configured — add PLAID_CLIENT_ID and PLAID_SECRET to Railway env vars"
        )
    with httpx.Client() as client:
        resp = client.post(
            f"{PLAID_BASE}{path}",
            json={**body, "client_id": PLAID_CLIENT_ID, "secret": PLAID_SECRET},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

# ---------------------------------------------------------------------------
# Health & info
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "status": "Apexa API is running",
        "version": "1.1.0",
        "stack": {
            "plaid":   "bank linking",
            "stripe":  "brand payouts + billing",
            "atomic":  "tax vault + investing",
            "tight":   "accounting + tax",
        },
        "services": {
            "stripe": bool(STRIPE_SECRET_KEY),
            "plaid":  bool(PLAID_CLIENT_ID and PLAID_SECRET),
            "atomic": bool(ATOMIC_API_KEY),
            "tight":  bool(TIGHT_API_KEY),
        },
    }

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/api/auth/signup")
def signup(data: UserSignup):
    if data.email in users_db:
        raise HTTPException(status_code=400, detail="Email already registered")

    users_db[data.email] = {
        "email":              data.email,
        "name":               data.name,
        "password_hash":      hash_password(data.password),
        "platform":           data.platform,
        "created_at":         datetime.utcnow().isoformat(),
        # Tax settings
        "tax_rate":           0.28,
        "auto_vault":         True,
        # Split config (Atomic routing)
        "split":              DEFAULT_SPLIT.copy(),
        # Balances (synced from Atomic in production)
        "total_income":       0.0,
        "tax_vault_balance":  0.0,
        "invest_balance":     0.0,
        "spendable_balance":  0.0,
        # Stripe
        "stripe_customer_id": None,
        "stripe_connect_id":  None,
        "stripe_bank_id":     None,
        # Plaid
        "plaid_access_token": None,
        "plaid_account_id":   None,
        "bank_name":          None,
        "bank_last4":         None,
        # Atomic
        "atomic_account_id":  None,
        # History
        "income_history":     [],
        "transfer_history":   [],
    }

    token = create_token(data.email)
    return {"token": token, "user": {"email": data.email, "name": data.name}}


@app.post("/api/auth/login")
def login(data: UserLogin):
    user = users_db.get(data.email)
    if not user or user["password_hash"] != hash_password(data.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(data.email)
    return {"token": token, "user": {"email": user["email"], "name": user["name"]}}

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/api/dashboard/summary")
def dashboard(user: dict = Depends(get_current_user)):
    split = user.get("split", DEFAULT_SPLIT)
    return {
        "name":              user["name"],
        "platform":          user["platform"],
        "total_income":      user["total_income"],
        "tax_vault_balance": user["tax_vault_balance"],
        "invest_balance":    user["invest_balance"],
        "spendable_balance": user["spendable_balance"],
        "tax_rate":          user["tax_rate"],
        "auto_vault":        user["auto_vault"],
        "split_config":      split,
        "bank_linked":       bool(user.get("plaid_access_token")),
        "bank_name":         user.get("bank_name"),
        "bank_last4":        user.get("bank_last4"),
        "recent_income":     user["income_history"][-10:],
        "recent_transfers":  user["transfer_history"][-10:],
    }

# ---------------------------------------------------------------------------
# Income & Auto-Split (Atomic routing logic)
# ---------------------------------------------------------------------------

@app.post("/api/income/add")
def add_income(entry: IncomeEntry, user: dict = Depends(get_current_user)):
    """
    Record creator income and fire auto-split to Atomic sub-accounts.
    Tax Vault % goes to HYSA, Invest % to Portfolio, remainder to Spendable.
    """
    split = user.get("split", DEFAULT_SPLIT)

    tax_vault_amt = round(entry.amount * split["tax_vault_pct"], 2)
    invest_amt    = round(entry.amount * split["invest_pct"], 2)
    spendable_amt = round(entry.amount - tax_vault_amt - invest_amt, 2)

    user["total_income"]      += entry.amount
    user["tax_vault_balance"] += tax_vault_amt
    user["invest_balance"]    += invest_amt
    user["spendable_balance"] += spendable_amt

    record = {
        "amount":      entry.amount,
        "source":      entry.source,
        "description": entry.description,
        "split": {
            "tax_vault":  tax_vault_amt,
            "investing":  invest_amt,
            "spendable":  spendable_amt,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
    user["income_history"].append(record)

    # TODO: POST to Atomic API to route funds
    # atomic_split(user["atomic_account_id"], tax_vault_amt, invest_amt, spendable_amt)

    return {
        "message": f"${entry.amount} received — auto-split fired",
        "split": {
            "tax_vault": f"${tax_vault_amt} to Atomic Tax Vault (HYSA)",
            "investing":  f"${invest_amt} to Atomic Portfolio",
            "spendable":  f"${spendable_amt} to Spendable",
        },
        "balances": {
            "total_income": user["total_income"],
            "tax_vault":    user["tax_vault_balance"],
            "investing":    user["invest_balance"],
            "spendable":    user["spendable_balance"],
        },
    }


@app.put("/api/income/split-config")
def update_split(config: SplitConfig, user: dict = Depends(get_current_user)):
    """Update the auto-split percentages for Tax Vault / Investing / Spendable."""
    total = config.tax_vault_pct + config.invest_pct + config.spendable_pct
    if abs(total - 1.0) > 0.001:
        raise HTTPException(
            status_code=400,
            detail=f"Split percentages must sum to 100% (got {total*100:.1f}%)"
        )
    user["split"] = {
        "tax_vault_pct": config.tax_vault_pct,
        "invest_pct":    config.invest_pct,
        "spendable_pct": config.spendable_pct,
    }
    return {"message": "Split config updated", "split": user["split"]}

# ---------------------------------------------------------------------------
# Tax Vault
# ---------------------------------------------------------------------------

@app.get("/api/tax/calculate")
def calculate_tax(income: float, tax_rate: float = 0.28):
    return {
        "income":         income,
        "tax_amount":     round(income * tax_rate, 2),
        "spendable":      round(income * (1 - tax_rate), 2),
        "effective_rate": tax_rate,
    }

@app.put("/api/tax/configure")
def configure_tax(config: TaxVaultConfig, user: dict = Depends(get_current_user)):
    user["tax_rate"]   = config.tax_rate
    user["auto_vault"] = config.auto_vault
    return {"message": "Tax vault updated", "tax_rate": user["tax_rate"], "auto_vault": user["auto_vault"]}

@app.get("/api/tax/summary")
def tax_summary(user: dict = Depends(get_current_user)):
    quarterly_estimate = round(user["tax_vault_balance"] / 4, 2)
    return {
        "total_income":                user["total_income"],
        "tax_vault_balance":           user["tax_vault_balance"],
        "tax_rate":                    user["tax_rate"],
        "estimated_quarterly_payment": quarterly_estimate,
        "next_quarterly_due":          _next_quarterly_date(),
    }

def _next_quarterly_date() -> str:
    now = datetime.utcnow()
    quarterly_dates = [
        datetime(now.year, 4, 15),
        datetime(now.year, 6, 15),
        datetime(now.year, 9, 15),
        datetime(now.year + 1, 1, 15),
    ]
    for d in quarterly_dates:
        if d > now:
            return d.strftime("%Y-%m-%d")
    return quarterly_dates[0].replace(year=now.year + 1).strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# PLAID — Bank Account Linking
# ---------------------------------------------------------------------------

@app.post("/api/plaid/create-link-token")
def plaid_create_link_token(user: dict = Depends(get_current_user)):
    """
    Step 1 of bank linking.
    Frontend uses this token to open Plaid Link so the creator connects their bank.
    """
    body = {
        "user":          {"client_user_id": user["email"]},
        "client_name":   "Apexa",
        "products":      ["auth"],
        "country_codes": ["US"],
        "language":      "en",
    }
    data = _plaid_post("/link/token/create", body)
    return {"link_token": data["link_token"]}


@app.post("/api/plaid/exchange-token")
def plaid_exchange_token(data: PlaidExchangeRequest, user: dict = Depends(get_current_user)):
    """
    Step 2 of bank linking.
    Exchange the public_token from Plaid Link for an access_token.
    Generate a Stripe processor token so Stripe can ACH to this bank account.
    Attach the bank to the creator's Stripe Connect Custom account.
    """
    # Exchange public token for access token
    exchange     = _plaid_post("/item/public_token/exchange", {"public_token": data.public_token})
    access_token = exchange["access_token"]

    # Get bank account details for display
    auth_data    = _plaid_post("/auth/get", {
        "access_token": access_token,
        "options": {"account_ids": [data.account_id]},
    })
    account_info = next(
        (a for a in auth_data.get("accounts", []) if a["account_id"] == data.account_id), {}
    )

    # Create Stripe processor token directly from Plaid
    processor        = _plaid_post("/processor/stripe/bank_account_token/create", {
        "access_token": access_token,
        "account_id":   data.account_id,
    })
    stripe_bank_token = processor["stripe_bank_account_token"]

    # Attach bank to creator's Stripe Connect Custom account
    if not user.get("stripe_connect_id"):
        raise HTTPException(
            status_code=400,
            detail="Create Stripe Connect account first via /api/stripe/connect/create-account"
        )

    try:
        bank_account = stripe.Account.create_external_account(
            user["stripe_connect_id"],
            external_account=stripe_bank_token,
        )
        user["plaid_access_token"] = access_token
        user["plaid_account_id"]   = data.account_id
        user["bank_name"]          = account_info.get("name", "Bank")
        user["bank_last4"]         = account_info.get("mask", "****")
        user["stripe_bank_id"]     = bank_account.id

        return {
            "message":        "Bank account linked and verified",
            "bank_name":      user["bank_name"],
            "bank_last4":     user["bank_last4"],
            "stripe_bank_id": bank_account.id,
            "status":         bank_account.status,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/plaid/bank-status")
def plaid_bank_status(user: dict = Depends(get_current_user)):
    return {
        "bank_linked": bool(user.get("plaid_access_token")),
        "bank_name":   user.get("bank_name"),
        "bank_last4":  user.get("bank_last4"),
    }

# ---------------------------------------------------------------------------
# STRIPE CONNECT — Creator Accounts & Payouts
# ---------------------------------------------------------------------------

@app.post("/api/stripe/connect/create-account")
def create_connect_account(data: StripeConnectRequest, user: dict = Depends(get_current_user)):
    """
    Create a Stripe Connect Custom account for the creator.
    Custom = Apexa controls everything, bank attached programmatically via Plaid.
    """
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    if user.get("stripe_connect_id"):
        return {"connect_id": user["stripe_connect_id"], "message": "Connect account already exists"}

    try:
        account = stripe.Account.create(
            type="custom",
            country=data.country,
            email=user["email"],
            capabilities={
                "transfers":                      {"requested": True},
                "us_bank_account_ach_payments":   {"requested": True},
            },
            business_type="individual",
            tos_acceptance={"service_agreement": "recipient"},
            metadata={"app": "apexa", "platform": user["platform"]},
        )
        user["stripe_connect_id"] = account.id
        return {
            "connect_id": account.id,
            "message":    "Stripe Connect Custom account created",
            "next_step":  "Link bank via /api/plaid/create-link-token then /api/plaid/exchange-token",
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/stripe/connect/brand-payout")
def brand_payout(data: BrandPayoutRequest, user: dict = Depends(get_current_user)):
    """
    Brand or agency sends payment to a creator through Apexa.
    Apexa charges 0.5% processing fee. Net amount transferred to creator's Connect account.
    Creator then funds their Atomic account from their bank.
    """
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    creator = users_db.get(data.creator_email)
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")
    if not creator.get("stripe_connect_id"):
        raise HTTPException(status_code=400, detail="Creator has no Connect account")

    apexa_fee      = round(data.amount * 0.005, 2)
    net_to_creator = round(data.amount - apexa_fee, 2)

    try:
        transfer = stripe.Transfer.create(
            amount=int(net_to_creator * 100),
            currency="usd",
            destination=creator["stripe_connect_id"],
            description=data.description,
            metadata={
                "app":            "apexa",
                "creator_email":  data.creator_email,
                "gross_amount":   str(data.amount),
                "apexa_fee":      str(apexa_fee),
                "net_to_creator": str(net_to_creator),
            },
        )

        creator["income_history"].append({
            "amount":      data.amount,
            "apexa_fee":   apexa_fee,
            "net":         net_to_creator,
            "source":      "brand_payout",
            "description": data.description,
            "transfer_id": transfer.id,
            "timestamp":   datetime.utcnow().isoformat(),
        })

        return {
            "message":        f"${data.amount} brand payment processed",
            "gross_amount":   data.amount,
            "apexa_fee":      apexa_fee,
            "net_to_creator": net_to_creator,
            "transfer_id":    transfer.id,
            "next_step":      "Creator deposits to Atomic via /api/atomic/deposit",
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/stripe/connect/creator-withdraw")
def creator_withdraw(data: CreatorWithdrawRequest, user: dict = Depends(get_current_user)):
    """
    Creator withdraws from Atomic Spendable to their linked bank via ACH.
    Triggers Stripe payout on creator's Connect account to their Plaid-linked bank.
    """
    if not user.get("stripe_connect_id"):
        raise HTTPException(status_code=400, detail="No Connect account — complete onboarding first")
    if not user.get("stripe_bank_id"):
        raise HTTPException(status_code=400, detail="No bank linked — connect bank via Plaid first")
    if data.amount > user["spendable_balance"]:
        raise HTTPException(status_code=400, detail="Insufficient spendable balance")

    try:
        payout = stripe.Payout.create(
            amount=int(data.amount * 100),
            currency="usd",
            method="standard",   # standard = ACH 1-2 days; instant = faster (higher fee)
            stripe_account=user["stripe_connect_id"],
            metadata={"app": "apexa", "creator_email": user["email"]},
        )

        user["spendable_balance"] -= data.amount
        user["transfer_history"].append({
            "type":      "withdrawal",
            "amount":    data.amount,
            "payout_id": payout.id,
            "status":    payout.status,
            "method":    "ach_standard",
            "bank_last4": user.get("bank_last4"),
            "timestamp": datetime.utcnow().isoformat(),
        })

        return {
            "message":           f"${data.amount} withdrawal to {user.get('bank_name')} ****{user.get('bank_last4')}",
            "payout_id":         payout.id,
            "status":            payout.status,
            "estimated_arrival": "1-2 business days",
            "new_spendable":     user["spendable_balance"],
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/stripe/connect/status")
def connect_status(user: dict = Depends(get_current_user)):
    if not user.get("stripe_connect_id"):
        return {"status": "not_created", "message": "No Connect account yet"}
    try:
        account = stripe.Account.retrieve(user["stripe_connect_id"])
        return {
            "connect_id":        account.id,
            "charges_enabled":   account.charges_enabled,
            "payouts_enabled":   account.payouts_enabled,
            "details_submitted": account.details_submitted,
            "bank_linked":       bool(user.get("stripe_bank_id")),
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/stripe/balance")
def stripe_balance(user: dict = Depends(get_current_user)):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    try:
        balance   = stripe.Balance.retrieve()
        available = sum(b["amount"] for b in balance.available) / 100
        pending   = sum(b["amount"] for b in balance.pending) / 100
        return {"available": available, "pending": pending}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------------------------------------------------------------------
# STRIPE — Webhooks
# ---------------------------------------------------------------------------

@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    """
    Handles Stripe events: transfer.paid, payout.paid, payout.failed
    Set STRIPE_WEBHOOK_SECRET in Railway env vars.
    Register webhook URL in Stripe dashboard:
      https://apexa.up.railway.app/api/webhooks/stripe
    """
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    event_data = event["data"]["object"]

    if event_type == "transfer.paid":
        creator_email = event_data.get("metadata", {}).get("creator_email")
        if creator_email and creator_email in users_db:
            users_db[creator_email]["transfer_history"].append({
                "type":        "brand_payout_confirmed",
                "amount":      event_data["amount"] / 100,
                "transfer_id": event_data["id"],
                "timestamp":   datetime.utcnow().isoformat(),
            })

    elif event_type == "payout.failed":
        # TODO: notify creator of failed withdrawal
        pass

    return {"status": "ok", "event": event_type}

# ---------------------------------------------------------------------------
# ATOMIC — Tax Vault, Investing (placeholder until Atomic onboarding complete)
# ---------------------------------------------------------------------------

@app.post("/api/atomic/deposit")
def atomic_deposit(user: dict = Depends(get_current_user)):
    """
    Creator deposits from their bank into their Atomic account.
    Atomic pulls from linked bank (Plaid-verified routing number).
    Auto-split fires: Tax Vault / Portfolio / Spendable.
    TODO: Call Atomic API once credentials are live.
    """
    if not user.get("plaid_access_token"):
        raise HTTPException(status_code=400, detail="No bank linked — connect bank via Plaid first")
    if not ATOMIC_API_KEY:
        return {
            "status":  "pending",
            "message": "Atomic onboarding in progress. Bank is linked and ready.",
            "split":   user.get("split", DEFAULT_SPLIT),
        }
    # TODO: implement Atomic deposit
    return {"status": "pending", "message": "Atomic API integration in progress"}


@app.get("/api/atomic/balances")
def atomic_balances(user: dict = Depends(get_current_user)):
    """
    Creator's Atomic sub-account balances.
    TODO: Pull live from Atomic API once onboarded.
    """
    return {
        "tax_vault": {
            "balance":  user["tax_vault_balance"],
            "type":     "High-Yield Cash (HYSA)",
            "provider": "Atomic Brokerage LLC",
        },
        "investing": {
            "balance":  user["invest_balance"],
            "type":     "Managed Portfolio",
            "provider": "Atomic Invest LLC (RIA)",
        },
        "spendable": {
            "balance":  user["spendable_balance"],
            "type":     "Cash",
            "provider": "Atomic Brokerage LLC",
        },
    }

# ---------------------------------------------------------------------------
# Suggested portfolios (Atomic-managed in production)
# ---------------------------------------------------------------------------

@app.get("/api/invest/suggested-portfolios")
def suggested_portfolios(user: dict = Depends(get_current_user)):
    return {
        "portfolios": [
            {
                "name": "Conservative",
                "description": "Stability and capital preservation",
                "allocation": [
                    {"symbol": "VTI",  "name": "Total Stock Market",        "weight": 0.30},
                    {"symbol": "BND",  "name": "Total Bond Market",         "weight": 0.40},
                    {"symbol": "VTIP", "name": "Inflation-Protected Bonds", "weight": 0.20},
                    {"symbol": "VNQ",  "name": "Real Estate (REITs)",       "weight": 0.10},
                ],
                "risk_level":     "low",
                "tier_required":  "pro",
            },
            {
                "name": "Balanced",
                "description": "Long-term growth for creators with steady income",
                "allocation": [
                    {"symbol": "VTI",  "name": "Total Stock Market",  "weight": 0.40},
                    {"symbol": "VXUS", "name": "International Stocks","weight": 0.20},
                    {"symbol": "QQQ",  "name": "Nasdaq 100",          "weight": 0.20},
                    {"symbol": "BND",  "name": "Total Bond Market",   "weight": 0.15},
                    {"symbol": "VNQ",  "name": "Real Estate (REITs)", "weight": 0.05},
                ],
                "risk_level":     "medium",
                "tier_required":  "pro",
            },
            {
                "name": "Aggressive",
                "description": "Maximum growth for high-income creators",
                "allocation": [
                    {"symbol": "VTI",  "name": "Total Stock Market",  "weight": 0.30},
                    {"symbol": "QQQ",  "name": "Nasdaq 100",          "weight": 0.25},
                    {"symbol": "VXUS", "name": "International Stocks","weight": 0.15},
                    {"symbol": "ARKK", "name": "Innovation ETF",      "weight": 0.15},
                    {"symbol": "VNQ",  "name": "Real Estate (REITs)", "weight": 0.10},
                    {"symbol": "GLD",  "name": "Gold",                "weight": 0.05},
                ],
                "risk_level":     "high",
                "tier_required":  "premium",
            },
        ]
    }

# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup():
    print("=" * 60)
    print("  Apexa API v1.1.0")
    print("  © 2026 Albors Advisory LLC")
    print(f"  Stripe:  {'Connected' if STRIPE_SECRET_KEY else 'Not configured'}")
    print(f"  Plaid:   {'Connected' if PLAID_CLIENT_ID else 'Not configured'}")
    print(f"  Atomic:  {'Connected' if ATOMIC_API_KEY else 'Pending onboarding'}")
    print(f"  Tight:   {'Connected' if TIGHT_API_KEY else 'Pending setup'}")
    print(f"  Plaid env: {PLAID_ENV.upper()}")
    print("=" * 60)
