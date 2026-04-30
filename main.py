"""
Apexa — Creator Finance Platform
Backend API v1.2.0
© 2026 Albors Advisory LLC

FastAPI backend powering the Apexa fintech platform for content creators.
Stack: Plaid (bank linking + ACH transfers) → Stripe Billing (subscriptions only)
       → Atomic (Tax Vault HYSA, investing) → Tight/Hurdlr (accounting + tax)

Money movement: ALL transfers handled by Plaid Transfer (ACH pull/push).
Stripe is subscriptions only — no Connect, no payouts.
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
    version="1.2.0",
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
PLAID_WEBHOOK_SECRET    = os.getenv("PLAID_WEBHOOK_SECRET", "")
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
users_db: dict = {}       # email -> user dict
sessions_db: dict = {}    # token -> email
transfer_events_db: dict = {}  # transfer_id -> event list (Plaid webhook data)

# ---------------------------------------------------------------------------
# Default auto-split percentages (creator can customize)
# ---------------------------------------------------------------------------
DEFAULT_SPLIT = {
    "tax_vault_pct":  0.25,   # 25% → Atomic Tax Vault (HYSA)
    "invest_pct":     0.15,   # 15% → Atomic Portfolio
    "spendable_pct":  0.60,   # 60% → Spendable balance
}

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class UserSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str
    platform: str = "independent"

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

class PlaidTransferDepositRequest(BaseModel):
    """
    Creator deposits money from their linked bank into Apexa.
    Plaid Transfer debits (pulls) from the creator's bank account.
    Auto-split fires immediately: Tax Vault / Invest / Spendable.
    """
    amount: float = Field(gt=0, description="Amount in USD to pull from creator's bank")
    description: Optional[str] = "Deposit to Apexa"

class PlaidTransferWithdrawRequest(BaseModel):
    """
    Creator withdraws from their Apexa spendable balance to their linked bank.
    Plaid Transfer credits (pushes) to the creator's bank account.
    """
    amount: float = Field(gt=0, description="Amount in USD to push to creator's bank")
    description: Optional[str] = "Apexa withdrawal"

class BrandPayoutRequest(BaseModel):
    """
    Brand or agency sends a direct payment to a creator.
    Plaid Transfer pulls from the brand's bank account and credits to creator's Apexa ledger.
    Apexa charges 0.5% processing fee.
    """
    creator_email: EmailStr
    amount: float = Field(gt=0)
    brand_access_token: str = Field(description="Plaid access_token for the brand's bank account")
    brand_account_id: str = Field(description="Plaid account_id for the brand's bank account")
    description: Optional[str] = "Brand payment via Apexa"

class StripeSubscriptionRequest(BaseModel):
    tier: str = Field(description="pro | premium | business")
    payment_method_id: str

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


def _plaid_authorize_transfer(
    access_token: str,
    account_id: str,
    transfer_type: str,       # "debit" (pull from user) or "credit" (push to user)
    amount: str,              # string e.g. "500.00"
    ach_class: str,           # "web" for debit, "ppd" for credit
    user_name: str,
    user_email: str,
) -> str:
    """
    Create a Plaid Transfer authorization and return the authorization_id.
    Must be called before /transfer/create.
    """
    body = {
        "access_token": access_token,
        "account_id":   account_id,
        "type":         transfer_type,
        "network":      "ach",
        "amount":       amount,
        "ach_class":    ach_class,
        "user": {
            "legal_name":    user_name,
            "email_address": user_email,
        },
    }
    data = _plaid_post("/transfer/authorization/create", body)
    auth = data.get("authorization", {})

    decision = auth.get("decision")
    if decision != "approved":
        reason = auth.get("decision_rationale", {}).get("description", "Transfer not approved by Plaid")
        raise HTTPException(status_code=400, detail=f"Transfer authorization denied: {reason}")

    return auth["id"]


def _plaid_create_transfer(
    access_token: str,
    account_id: str,
    authorization_id: str,
    transfer_type: str,
    amount: str,
    ach_class: str,
    description: str,
    user_name: str,
    user_email: str,
) -> dict:
    """
    Execute a Plaid Transfer after authorization is approved.
    Returns the full transfer object from Plaid.
    """
    body = {
        "access_token":     access_token,
        "account_id":       account_id,
        "authorization_id": authorization_id,
        "type":             transfer_type,
        "network":          "ach",
        "amount":           amount,
        "description":      description[:15],  # Plaid max 15 chars on ACH description
        "ach_class":        ach_class,
        "user": {
            "legal_name":    user_name,
            "email_address": user_email,
        },
        "metadata": {
            "app":   "apexa",
            "email": user_email,
        },
    }
    data = _plaid_post("/transfer/create", body)
    return data.get("transfer", {})

# ---------------------------------------------------------------------------
# Health & info
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "status":  "Apexa API is running",
        "version": "1.2.0",
        "stack": {
            "plaid":   "bank linking + ACH transfers (all money movement)",
            "stripe":  "subscriptions only ($19/$49/$99/mo)",
            "atomic":  "tax vault (HYSA) + investing",
            "tight":   "accounting + tax data layer",
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
        # Stripe (subscriptions only)
        "stripe_customer_id":       None,
        "stripe_subscription_id":   None,
        "subscription_tier":        "starter",
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
        "subscription_tier": user.get("subscription_tier", "starter"),
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
    Tax Vault % → HYSA, Invest % → Portfolio, remainder → Spendable.
    Called automatically after a successful Plaid Transfer deposit.
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

    # TODO: POST to Atomic API to route funds into sub-accounts
    # atomic_split(user["atomic_account_id"], tax_vault_amt, invest_amt, spendable_amt)

    return {
        "message": f"${entry.amount} received — auto-split fired",
        "split": {
            "tax_vault": f"${tax_vault_amt} → Atomic Tax Vault (HYSA)",
            "investing":  f"${invest_amt} → Atomic Portfolio",
            "spendable":  f"${spendable_amt} → Spendable",
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
    Products: auth (account verification) + transfer (enables Transfer API on this item).
    """
    body = {
        "user":          {"client_user_id": user["email"]},
        "client_name":   "Apexa",
        "products":      ["auth", "transfer"],
        "country_codes": ["US"],
        "language":      "en",
        "webhook":       "https://apexa.up.railway.app/api/webhooks/plaid",
    }
    data = _plaid_post("/link/token/create", body)
    return {"link_token": data["link_token"]}


@app.post("/api/plaid/exchange-token")
def plaid_exchange_token(data: PlaidExchangeRequest, user: dict = Depends(get_current_user)):
    """
    Step 2 of bank linking.
    Exchange the public_token from Plaid Link for a permanent access_token.
    Store access_token + account_id — these are used for all future transfers.
    """
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

    user["plaid_access_token"] = access_token
    user["plaid_account_id"]   = data.account_id
    user["bank_name"]          = account_info.get("name", "Bank")
    user["bank_last4"]         = account_info.get("mask", "****")

    return {
        "message":   "Bank account linked and verified",
        "bank_name": user["bank_name"],
        "bank_last4": user["bank_last4"],
        "next_step": "Creator can now deposit via /api/plaid/transfer/deposit",
    }


@app.get("/api/plaid/bank-status")
def plaid_bank_status(user: dict = Depends(get_current_user)):
    return {
        "bank_linked": bool(user.get("plaid_access_token")),
        "bank_name":   user.get("bank_name"),
        "bank_last4":  user.get("bank_last4"),
    }

# ---------------------------------------------------------------------------
# PLAID TRANSFER — ACH Pull (Deposit) and ACH Push (Withdraw)
# ---------------------------------------------------------------------------

@app.post("/api/plaid/transfer/deposit")
def plaid_transfer_deposit(data: PlaidTransferDepositRequest, user: dict = Depends(get_current_user)):
    """
    Creator deposits money from their linked bank into Apexa.

    Flow:
    1. Authorize the debit transfer with Plaid (risk check)
    2. Create the ACH pull — Plaid debits creator's bank → Apexa receives funds
    3. Auto-split fires: 25% Tax Vault / 15% Invest / 60% Spendable
    4. Balances updated immediately (funds settle T+1 to T+3 ACH)

    ACH class: "web" — consumer-initiated online debit
    """
    if not user.get("plaid_access_token"):
        raise HTTPException(status_code=400, detail="No bank linked — connect bank via /api/plaid/create-link-token first")

    amount_str = f"{data.amount:.2f}"

    # Step 1: Authorize
    auth_id = _plaid_authorize_transfer(
        access_token  = user["plaid_access_token"],
        account_id    = user["plaid_account_id"],
        transfer_type = "debit",
        amount        = amount_str,
        ach_class     = "web",
        user_name     = user["name"],
        user_email    = user["email"],
    )

    # Step 2: Execute transfer
    transfer = _plaid_create_transfer(
        access_token     = user["plaid_access_token"],
        account_id       = user["plaid_account_id"],
        authorization_id = auth_id,
        transfer_type    = "debit",
        amount           = amount_str,
        ach_class        = "web",
        description      = "Apexa deposit",
        user_name        = user["name"],
        user_email       = user["email"],
    )

    transfer_id = transfer.get("id")

    # Step 3: Fire auto-split immediately (funds are pending ACH settlement)
    split = user.get("split", DEFAULT_SPLIT)
    tax_vault_amt = round(data.amount * split["tax_vault_pct"], 2)
    invest_amt    = round(data.amount * split["invest_pct"], 2)
    spendable_amt = round(data.amount - tax_vault_amt - invest_amt, 2)

    user["total_income"]      += data.amount
    user["tax_vault_balance"] += tax_vault_amt
    user["invest_balance"]    += invest_amt
    user["spendable_balance"] += spendable_amt

    # Step 4: Record in transfer history
    record = {
        "type":          "deposit",
        "amount":        data.amount,
        "transfer_id":   transfer_id,
        "plaid_status":  transfer.get("status"),
        "bank_name":     user.get("bank_name"),
        "bank_last4":    user.get("bank_last4"),
        "split": {
            "tax_vault":  tax_vault_amt,
            "investing":  invest_amt,
            "spendable":  spendable_amt,
        },
        "description": data.description,
        "timestamp":   datetime.utcnow().isoformat(),
    }
    user["transfer_history"].append(record)

    # TODO: POST split to Atomic API once onboarded
    # atomic_split(user["atomic_account_id"], tax_vault_amt, invest_amt, spendable_amt)

    return {
        "message":       f"${data.amount} deposit initiated",
        "transfer_id":   transfer_id,
        "status":        transfer.get("status"),   # "pending" → "posted" → "settled"
        "settlement":    "T+1 to T+3 business days (ACH)",
        "split": {
            "tax_vault": f"${tax_vault_amt} → Atomic Tax Vault (HYSA)",
            "investing":  f"${invest_amt} → Atomic Portfolio",
            "spendable":  f"${spendable_amt} → Spendable",
        },
        "balances": {
            "total_income": user["total_income"],
            "tax_vault":    user["tax_vault_balance"],
            "investing":    user["invest_balance"],
            "spendable":    user["spendable_balance"],
        },
        "track_status": f"/api/plaid/transfer/status/{transfer_id}",
    }


@app.post("/api/plaid/transfer/withdraw")
def plaid_transfer_withdraw(data: PlaidTransferWithdrawRequest, user: dict = Depends(get_current_user)):
    """
    Creator withdraws from their Apexa spendable balance to their linked bank.

    Flow:
    1. Check spendable balance is sufficient
    2. Authorize the credit transfer with Plaid
    3. Create the ACH push — Plaid credits creator's bank
    4. Spendable balance decremented immediately

    ACH class: "ppd" — Prearranged Payment & Deposit (consumer credit)
    """
    if not user.get("plaid_access_token"):
        raise HTTPException(status_code=400, detail="No bank linked — connect bank via /api/plaid/create-link-token first")
    if data.amount > user["spendable_balance"]:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient spendable balance (${user['spendable_balance']:.2f} available)"
        )

    amount_str = f"{data.amount:.2f}"

    # Step 1: Authorize
    auth_id = _plaid_authorize_transfer(
        access_token  = user["plaid_access_token"],
        account_id    = user["plaid_account_id"],
        transfer_type = "credit",
        amount        = amount_str,
        ach_class     = "ppd",
        user_name     = user["name"],
        user_email    = user["email"],
    )

    # Step 2: Execute transfer
    transfer = _plaid_create_transfer(
        access_token     = user["plaid_access_token"],
        account_id       = user["plaid_account_id"],
        authorization_id = auth_id,
        transfer_type    = "credit",
        amount           = amount_str,
        ach_class        = "ppd",
        description      = "Apexa payout",
        user_name        = user["name"],
        user_email       = user["email"],
    )

    transfer_id = transfer.get("id")

    # Step 3: Decrement spendable balance immediately
    user["spendable_balance"] -= data.amount

    # Step 4: Record
    record = {
        "type":         "withdrawal",
        "amount":       data.amount,
        "transfer_id":  transfer_id,
        "plaid_status": transfer.get("status"),
        "bank_name":    user.get("bank_name"),
        "bank_last4":   user.get("bank_last4"),
        "description":  data.description,
        "timestamp":    datetime.utcnow().isoformat(),
    }
    user["transfer_history"].append(record)

    return {
        "message":       f"${data.amount} withdrawal to {user.get('bank_name')} ****{user.get('bank_last4')}",
        "transfer_id":   transfer_id,
        "status":        transfer.get("status"),
        "settlement":    "T+1 to T+3 business days (ACH)",
        "new_spendable": user["spendable_balance"],
        "track_status":  f"/api/plaid/transfer/status/{transfer_id}",
    }


@app.get("/api/plaid/transfer/status/{transfer_id}")
def plaid_transfer_status(transfer_id: str, user: dict = Depends(get_current_user)):
    """
    Check the current status of a Plaid Transfer.

    Plaid Transfer statuses:
    - pending   → submitted to Plaid, not yet sent to ACH network
    - posted    → sent to ACH network, awaiting bank processing
    - settled   → funds confirmed, money has moved
    - failed    → transfer failed (NSF, invalid account, etc.)
    - reversed  → transfer was reversed (returned)
    - cancelled → transfer was cancelled before posting
    """
    data = _plaid_post("/transfer/get", {"transfer_id": transfer_id})
    transfer = data.get("transfer", {})
    return {
        "transfer_id":  transfer.get("id"),
        "status":       transfer.get("status"),
        "type":         transfer.get("type"),
        "amount":       transfer.get("amount"),
        "description":  transfer.get("description"),
        "created":      transfer.get("created"),
        "network":      transfer.get("network"),
        "failure_reason": transfer.get("failure_reason"),
    }


@app.get("/api/plaid/transfer/history")
def plaid_transfer_history(user: dict = Depends(get_current_user)):
    """Return the creator's full transfer history (deposits + withdrawals)."""
    return {
        "transfers":       user["transfer_history"],
        "total_transfers": len(user["transfer_history"]),
        "deposits":        [t for t in user["transfer_history"] if t.get("type") == "deposit"],
        "withdrawals":     [t for t in user["transfer_history"] if t.get("type") == "withdrawal"],
    }


@app.post("/api/plaid/transfer/brand-payout")
def plaid_brand_payout(data: BrandPayoutRequest, user: dict = Depends(get_current_user)):
    """
    Brand or agency sends a direct payment to a creator via Plaid Transfer.

    Flow:
    1. Apexa authorizes a debit from the brand's linked bank account
    2. Plaid pulls from brand → Apexa receives funds
    3. Apexa deducts 0.5% processing fee
    4. Net amount credited to creator's Apexa ledger + auto-split fires

    Note: Brand must have completed Plaid Link and provided their access_token + account_id.
    In production, brands complete Plaid Link via a separate brand-side flow.
    """
    creator = users_db.get(data.creator_email)
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    apexa_fee      = round(data.amount * 0.005, 2)
    net_to_creator = round(data.amount - apexa_fee, 2)
    amount_str     = f"{data.amount:.2f}"

    # Step 1: Authorize debit from brand's bank
    # We look up brand user or use passed brand tokens directly
    brand_user = next((u for u in users_db.values() if u.get("plaid_access_token") == data.brand_access_token), None)
    brand_name = brand_user["name"] if brand_user else "Brand"
    brand_email = brand_user["email"] if brand_user else "brand@apexa.com"

    auth_id = _plaid_authorize_transfer(
        access_token  = data.brand_access_token,
        account_id    = data.brand_account_id,
        transfer_type = "debit",
        amount        = amount_str,
        ach_class     = "ccd",          # CCD = corporate-to-corporate debit
        user_name     = brand_name,
        user_email    = brand_email,
    )

    # Step 2: Execute debit from brand
    transfer = _plaid_create_transfer(
        access_token     = data.brand_access_token,
        account_id       = data.brand_account_id,
        authorization_id = auth_id,
        transfer_type    = "debit",
        amount           = amount_str,
        ach_class        = "ccd",
        description      = "Apexa brand pay",
        user_name        = brand_name,
        user_email       = brand_email,
    )

    transfer_id = transfer.get("id")

    # Step 3: Credit net amount to creator's ledger + auto-split
    split = creator.get("split", DEFAULT_SPLIT)
    tax_vault_amt = round(net_to_creator * split["tax_vault_pct"], 2)
    invest_amt    = round(net_to_creator * split["invest_pct"], 2)
    spendable_amt = round(net_to_creator - tax_vault_amt - invest_amt, 2)

    creator["total_income"]      += net_to_creator
    creator["tax_vault_balance"] += tax_vault_amt
    creator["invest_balance"]    += invest_amt
    creator["spendable_balance"] += spendable_amt

    creator["income_history"].append({
        "amount":      data.amount,
        "apexa_fee":   apexa_fee,
        "net":         net_to_creator,
        "source":      "brand_payout",
        "description": data.description,
        "transfer_id": transfer_id,
        "split": {
            "tax_vault":  tax_vault_amt,
            "investing":  invest_amt,
            "spendable":  spendable_amt,
        },
        "timestamp": datetime.utcnow().isoformat(),
    })

    return {
        "message":        f"${data.amount} brand payment initiated",
        "gross_amount":   data.amount,
        "apexa_fee":      apexa_fee,
        "net_to_creator": net_to_creator,
        "transfer_id":    transfer_id,
        "status":         transfer.get("status"),
        "split": {
            "tax_vault": f"${tax_vault_amt} → Atomic Tax Vault",
            "investing":  f"${invest_amt} → Atomic Portfolio",
            "spendable":  f"${spendable_amt} → Spendable",
        },
        "track_status": f"/api/plaid/transfer/status/{transfer_id}",
    }

# ---------------------------------------------------------------------------
# STRIPE BILLING — Subscriptions only ($19 Pro / $49 Premium / $99 Business)
# ---------------------------------------------------------------------------

STRIPE_PRICE_IDS = {
    # Set these in Railway env vars after creating products in Stripe dashboard
    "pro":      os.getenv("STRIPE_PRICE_PRO",      ""),   # $19/mo
    "premium":  os.getenv("STRIPE_PRICE_PREMIUM",  ""),   # $49/mo
    "business": os.getenv("STRIPE_PRICE_BUSINESS", ""),   # $99/mo
}

@app.post("/api/stripe/subscribe")
def create_subscription(data: StripeSubscriptionRequest, user: dict = Depends(get_current_user)):
    """
    Creator subscribes to a paid tier via Stripe Billing.
    Stripe handles recurring billing only — no money movement through Stripe.
    """
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    if data.tier not in STRIPE_PRICE_IDS:
        raise HTTPException(status_code=400, detail="Invalid tier — use: pro, premium, business")

    price_id = STRIPE_PRICE_IDS[data.tier]
    if not price_id:
        raise HTTPException(status_code=503, detail=f"Stripe price ID for '{data.tier}' not configured in Railway env vars")

    try:
        # Create or retrieve Stripe customer
        if not user.get("stripe_customer_id"):
            customer = stripe.Customer.create(
                email=user["email"],
                name=user["name"],
                metadata={"app": "apexa", "platform": user["platform"]},
            )
            user["stripe_customer_id"] = customer.id

        # Attach payment method
        stripe.PaymentMethod.attach(data.payment_method_id, customer=user["stripe_customer_id"])
        stripe.Customer.modify(
            user["stripe_customer_id"],
            invoice_settings={"default_payment_method": data.payment_method_id},
        )

        # Create subscription
        subscription = stripe.Subscription.create(
            customer=user["stripe_customer_id"],
            items=[{"price": price_id}],
            metadata={"app": "apexa", "email": user["email"], "tier": data.tier},
        )

        user["stripe_subscription_id"] = subscription.id
        user["subscription_tier"] = data.tier

        return {
            "message":         f"Subscribed to {data.tier.capitalize()} plan",
            "subscription_id": subscription.id,
            "status":          subscription.status,
            "tier":            data.tier,
            "next_billing":    datetime.utcfromtimestamp(subscription.current_period_end).strftime("%Y-%m-%d"),
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/stripe/subscribe")
def cancel_subscription(user: dict = Depends(get_current_user)):
    """Cancel the creator's Stripe subscription at end of current billing period."""
    if not user.get("stripe_subscription_id"):
        raise HTTPException(status_code=400, detail="No active subscription")
    try:
        subscription = stripe.Subscription.modify(
            user["stripe_subscription_id"],
            cancel_at_period_end=True,
        )
        return {
            "message":        "Subscription will cancel at end of billing period",
            "cancel_at":      datetime.utcfromtimestamp(subscription.current_period_end).strftime("%Y-%m-%d"),
            "status":         subscription.status,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/stripe/subscription-status")
def subscription_status(user: dict = Depends(get_current_user)):
    if not user.get("stripe_subscription_id"):
        return {"tier": "starter", "status": "free", "subscription_id": None}
    try:
        sub = stripe.Subscription.retrieve(user["stripe_subscription_id"])
        return {
            "tier":            user.get("subscription_tier", "starter"),
            "status":          sub.status,
            "subscription_id": sub.id,
            "current_period_end": datetime.utcfromtimestamp(sub.current_period_end).strftime("%Y-%m-%d"),
            "cancel_at_period_end": sub.cancel_at_period_end,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------------------------------------------------------------------
# STRIPE — Webhooks (subscription lifecycle only)
# ---------------------------------------------------------------------------

@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    """
    Handles Stripe subscription events only.
    Register in Stripe dashboard: https://apexa.up.railway.app/api/webhooks/stripe
    Events: invoice.paid, invoice.payment_failed, customer.subscription.deleted
    """
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    event_data = event["data"]["object"]

    if event_type == "invoice.paid":
        # Subscription renewed — ensure tier is active
        customer_id = event_data.get("customer")
        user = next((u for u in users_db.values() if u.get("stripe_customer_id") == customer_id), None)
        if user:
            user["subscription_active"] = True

    elif event_type == "invoice.payment_failed":
        # Downgrade to starter if payment fails
        customer_id = event_data.get("customer")
        user = next((u for u in users_db.values() if u.get("stripe_customer_id") == customer_id), None)
        if user:
            user["subscription_tier"] = "starter"

    elif event_type == "customer.subscription.deleted":
        # Subscription cancelled — drop to free tier
        customer_id = event_data.get("customer")
        user = next((u for u in users_db.values() if u.get("stripe_customer_id") == customer_id), None)
        if user:
            user["subscription_tier"]      = "starter"
            user["stripe_subscription_id"] = None

    return {"status": "ok", "event": event_type}

# ---------------------------------------------------------------------------
# PLAID — Webhooks (Transfer events)
# ---------------------------------------------------------------------------

@app.post("/api/webhooks/plaid")
async def plaid_webhook(request: Request):
    """
    Handles Plaid Transfer webhook events.
    Register in Plaid dashboard (or pass webhook URL when creating link token).
    URL: https://apexa.up.railway.app/api/webhooks/plaid

    Key events:
    - TRANSFER_EVENTS_UPDATE → sync latest transfer statuses via /transfer/event/sync
    - When a transfer settles, mark it confirmed in transfer_history
    - When a transfer fails, reverse the balance adjustment and notify the creator
    """
    payload = await request.json()

    webhook_type = payload.get("webhook_type")
    webhook_code = payload.get("webhook_code")

    if webhook_type == "TRANSFER" and webhook_code == "TRANSFER_EVENTS_UPDATE":
        # Sync all new transfer events from Plaid
        # In production, track the last event_id you've processed (store in DB)
        try:
            events_data = _plaid_post("/transfer/event/sync", {"after_id": 0})
            transfer_events = events_data.get("transfer_events", [])

            for event in transfer_events:
                transfer_id    = event.get("transfer_id")
                event_type     = event.get("event_type")   # pending, posted, settled, failed, reversed
                transfer_amount = float(event.get("transfer_amount", 0))
                transfer_type  = event.get("transfer_type")  # debit or credit

                # Find the creator who owns this transfer
                owner = next(
                    (u for u in users_db.values()
                     if any(t.get("transfer_id") == transfer_id for t in u.get("transfer_history", []))),
                    None
                )

                if not owner:
                    continue

                # Update transfer status in history
                for t in owner["transfer_history"]:
                    if t.get("transfer_id") == transfer_id:
                        t["plaid_status"] = event_type
                        t["last_updated"] = datetime.utcnow().isoformat()

                # If a DEBIT (deposit) fails or is reversed — roll back balances
                if event_type in ("failed", "reversed") and transfer_type == "debit":
                    # Find the split that was applied and reverse it
                    deposit = next(
                        (t for t in owner["transfer_history"]
                         if t.get("transfer_id") == transfer_id and t.get("type") == "deposit"),
                        None
                    )
                    if deposit:
                        split_data = deposit.get("split", {})
                        owner["total_income"]      -= deposit.get("amount", 0)
                        owner["tax_vault_balance"] -= split_data.get("tax_vault", 0)
                        owner["invest_balance"]    -= split_data.get("investing", 0)
                        owner["spendable_balance"] -= split_data.get("spendable", 0)
                        deposit["reversed"] = True

                # Log the event
                transfer_events_db.setdefault(transfer_id, []).append({
                    "event_type": event_type,
                    "timestamp":  datetime.utcnow().isoformat(),
                })

        except Exception as e:
            # Don't raise — Plaid expects 200 even on processing errors
            print(f"Plaid webhook processing error: {e}")

    return {"status": "ok"}

# ---------------------------------------------------------------------------
# ATOMIC — Tax Vault, Investing (placeholder until Atomic onboarding complete)
# ---------------------------------------------------------------------------

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
            "apy":      "4.50%",
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
                "risk_level":    "low",
                "tier_required": "pro",
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
                "risk_level":    "medium",
                "tier_required": "pro",
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
                "risk_level":    "high",
                "tier_required": "premium",
            },
        ]
    }

# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup():
    print("=" * 60)
    print("  Apexa API v1.2.0")
    print("  © 2026 Albors Advisory LLC")
    print(f"  Stripe:  {'Connected' if STRIPE_SECRET_KEY else 'Not configured'} (subscriptions only)")
    print(f"  Plaid:   {'Connected' if PLAID_CLIENT_ID else 'Not configured'} (bank link + ACH transfers)")
    print(f"  Atomic:  {'Connected' if ATOMIC_API_KEY else 'Pending onboarding'} (tax vault + investing)")
    print(f"  Tight:   {'Connected' if TIGHT_API_KEY else 'Pending setup'} (accounting + tax)")
    print(f"  Plaid env: {PLAID_ENV.upper()}")
    print("=" * 60)
