import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class PlaybookResult:
    text: str
    response_mode: str = "playbook"


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    replacements = {
        "docs": "documents",
        "docs?": "documents",
        "paperwork": "documents",
        "open up an account": "open an account",
        "open up a bank account": "open bank account",
        "open a bank account": "open bank account",
        "what docs do i need": "what documents do i need",
        "documents do i need on me": "what documents do i need with me",
        "what do i need on me": "what do i need with me",
        "what do i need to have on me": "what do i need with me",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"\bdoc\b", "document", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _contains_any(text: str, phrases) -> bool:
    return any(phrase in text for phrase in phrases)


LOST_CARD_PATTERNS = [
    "lost my card",
    "lost my debit card",
    "lost card",
    "stolen card",
    "my card is missing",
    "misplaced my card",
    "card got stolen",
]

STOLEN_PHONE_PATTERNS = [
    "phone with the banking app is stolen",
    "my phone with banking app was stolen",
    "my phone was stolen",
    "stolen phone",
    "phone got stolen",
    "lost phone with banking app",
]

FREEZE_ACCOUNT_PATTERNS = [
    "freeze my account",
    "freeze account temporarily",
    "freeze my account temporarily",
    "temporarily freeze my account",
    "lock my account temporarily",
    "lock account temporarily",
    "temporarily lock account",
]

SUSPICIOUS_TRANSACTION_PATTERNS = [
    "suspicious transaction",
    "fraudulent transaction",
    "unauthorized transaction",
    "unauthorised transaction",
    "strange transaction",
    "unknown charge",
    "didn't make this transaction",
    "did not make this transaction",
    "unexpected charge",
    "suspicious charge",
    "fraud",
]

FAST_SUPPORT_PATTERNS = [
    "contact customer support quickly",
    "contact support quickly",
    "how can i contact customer support quickly",
    "reach support quickly",
    "reach customer support quickly",
    "fastest way to contact support",
    "quickly contact support",
]

ACCOUNT_MIN_DEPOSIT_PATTERNS = [
    "minimum deposit to open an account",
    "minimum deposit to open",
    "minimum deposit",
]

ACCOUNT_OPENING_TIME_PATTERNS = [
    "how long does it take to open an account",
    "how long to open an account",
    "account opening take",
]

JOINT_ACCOUNT_PATTERNS = [
    "joint account",
    "open a joint account",
]

CHECKING_VS_SAVINGS_PATTERNS = [
    "difference between a checking account and a savings account",
]

ACCOUNT_TYPE_FIT_PATTERNS = [
    "which account type is best for me",
]

OVERDRAFT_PATTERNS = [
    "overdraft",
    "insufficient funds",
    "nsf fee",
    "fee for overdrawing",
    "overdrawn",
    "negative balance",
    "balance goes negative",
    "account goes negative",
    "below zero",
]

OVERDRAFT_FEE_PATTERNS = [
    "charge overdraft fees",
    "overdraft fees",
]

AVOID_OVERDRAFT_FEE_PATTERNS = [
    "avoid overdraft fees",
]

OVERDRAFT_TOGGLE_PATTERNS = [
    "turn overdraft protection on or off",
    "overdraft protection on or off",
]

OPEN_ACCOUNT_PATTERNS = [
    "open a new checking account",
    "open a checking account",
    "open an account",
    "open bank account",
    "documents do i need",
    "what documents do i need",
    "what documents do i need with me",
    "what do i need to open",
    "what do i need to bring",
    "what do i need with me",
    "required documents",
    "documents required",
    "need documents",
    "need document",
    "opening account documents",
    "account opening documents",
    "account paperwork",
]

WRONG_TRANSFER_PATTERNS = [
    "wrong account",
    "wrong transfer",
    "accidentally transferred",
    "accidentally sent money",
    "mistaken transfer",
    "incorrect transfer",
    "sent money to the wrong",
    "recover it",
]

EDUCATION_SAVINGS_PATTERNS = [
    "child's education",
    "saving for a child's education",
    "child education",
    "save for my child",
    "education savings",
    "save for education",
    "college savings",
]

HOLD_TIME_PATTERNS = [
    "on hold",
    "hold times",
    "customer service wait",
    "wait time",
    "faster way to get help",
    "avoid long hold",
]

SERVICE_HOURS_PATTERNS = [
    "customer service hours",
    "support hours",
    "service hours",
    "contact hours",
    "business hours",
    "weekend support",
    "support on weekends",
    "offer support on weekends",
    "weekend hours",
    "open on weekends",
]

ONLINE_SECURITY_PATTERNS = [
    "online banking safe",
    "online bank accounts safe",
    "how secure",
    "security measures",
    "data remains safe",
    "otp",
    "phishing",
    "secure online banking",
]

SAVINGS_RATE_PATTERNS = [
    "savings rate",
    "interest rate on your basic savings account",
    "interest rate on savings",
    "current interest rate",
]

TERM_DEPOSIT_PATTERNS = [
    "term deposits or fixed deposits",
    "offer term deposits",
    "offer fixed deposits",
]

EARLY_WITHDRAWAL_PATTERNS = [
    "withdraw money before the term deposit matures",
    "penalty for early withdrawal",
    "early withdrawal",
]

AUTO_SAVINGS_PATTERNS = [
    "set up automatic savings each month",
    "automatic savings each month",
    "automatic savings",
]

SAVINGS_SHORT_TERM_PATTERNS = [
    "best for short-term goals",
]

SAVINGS_LONG_TERM_PATTERNS = [
    "best for long-term goals",
]

SAVINGS_MOBILE_PATTERNS = [
    "manage my savings account through mobile banking",
]

SAVINGS_SAFETY_PATTERNS = [
    "how safe is my money in a savings account",
]

MORTGAGE_RATE_PATTERNS = [
    "mortgage rate",
    "mortgage rates",
    "30-year fixed",
    "30 year fixed",
    "home loan rate",
]

ANNUAL_FEE_PATTERNS = [
    "annual fee",
    "annual fees",
    "card annual fee",
    "credit card fee",
    "debit card fee",
]

DEBIT_CARD_PATTERNS = ["what debit cards do you offer"]
CARD_CASHBACK_PATTERNS = ["which credit card is best for cashback", "best for cashback"]
CARD_TRAVEL_PATTERNS = ["which credit card is best for travel", "best for travel"]
CARD_LIMIT_INCREASE_PATTERNS = ["increase my credit card limit", "credit card limit increase"]
NEW_CARD_APPLICATION_PATTERNS = ["apply for a new card", "how do i apply for a new card"]
CARD_INTERNATIONAL_USE_PATTERNS = ["use my card internationally", "can i use my card internationally"]
CARD_LOCK_PATTERNS = ["lock or unlock my card in the app", "lock my card in the app", "unlock my card in the app", "lock or unlock my card"]

INTERNATIONAL_TRANSFER_PATTERNS = [
    "international transfer",
    "transfer money internationally",
    "transfer internationally",
    "send money abroad",
    "send money overseas",
    "wire internationally",
    "international wire",
]

DOMESTIC_TRANSFER_PATTERNS = [
    "transfer money to another bank account",
    "how do i transfer money to another bank account",
    "how to transfer money to another bank account",
    "bank transfer usually take",
    "schedule recurring transfers",
]

TRANSFER_FEE_PATTERNS = [
    "transfer fees for sending money",
    "are there transfer fees",
]

TRANSFER_TIME_PATTERNS = [
    "how long does a bank transfer usually take",
]

RECURRING_TRANSFER_PATTERNS = [
    "schedule recurring transfers",
    "can i schedule recurring transfers",
]

TRANSFER_DELAY_PATTERNS = [
    "transfer is delayed",
    "transfer delayed",
    "what should i do if my transfer is delayed",
]

CANCEL_TRANSFER_PATTERNS = [
    "cancel a transfer after sending it",
]

TRANSFER_LIMIT_PATTERNS = [
    "daily transfer limit",
    "is there a daily transfer limit",
    "transfer limit",
]

TRACK_TRANSFER_PATTERNS = [
    "track the status of a transfer",
    "status of a transfer",
    "track transfer status",
]

PERSONAL_LOAN_APPLICATION_PATTERNS = [
    "how do i apply for a personal loan",
    "apply for a personal loan",
    "personal loan application",
    "how to apply for a loan",
    "apply for loan",
]

BORROWING_CAPACITY_PATTERNS = [
    "how much can i borrow based on my income",
    "how much can i borrow",
    "borrow based on income",
]

LOAN_TYPES_PATTERNS = [
    "what types of loans do you offer",
    "what loans do you offer",
]

LOAN_DOCUMENT_PATTERNS = [
    "documents do i need for a loan application",
    "what documents do i need for a loan application",
]

LOAN_APPROVAL_TIME_PATTERNS = [
    "how long does loan approval usually take",
    "loan approval usually take",
]

HOME_LOAN_OFFER_PATTERNS = [
    "offer home loans or mortgages",
    "offer home loans",
    "offer mortgages",
]

CAR_LOAN_OFFER_PATTERNS = [
    "offer car loans",
    "offer auto loans",
]

EARLY_REPAY_ALLOWED_PATTERNS = [
    "repay my loan early",
]

EARLY_REPAY_PENALTY_PATTERNS = [
    "penalty for early repayment",
    "early repayment penalty",
]

MORTGAGE_EXPLANATION_PATTERNS = [
    "difference between fixed and variable mortgage rates",
    "fixed and variable mortgage rates",
]

MORTGAGE_DOWN_PAYMENT_PATTERNS = [
    "how much down payment do i need for a home loan",
]

MORTGAGE_AFFORDABILITY_PATTERNS = [
    "how much house i can afford",
]

MORTGAGE_PREQUALIFY_PATTERNS = [
    "prequalify for a mortgage",
]

MORTGAGE_EXTRA_COSTS_PATTERNS = [
    "costs should i expect besides the monthly mortgage payment",
]

FIRST_TIME_BUYER_PATTERNS = [
    "first-time homebuyers get any special support",
]

REFINANCE_PATTERNS = [
    "refinance my home loan later",
]

MORTGAGE_PREP_PATTERNS = [
    "prepare before applying for a mortgage",
]

MONTHLY_ACCOUNT_FEE_PATTERNS = [
    "monthly account fees",
    "monthly account fee",
    "charge monthly account fees",
]

AVOID_MONTHLY_ACCOUNT_FEE_PATTERNS = [
    "avoid monthly account fees",
    "avoid monthly fees",
]

FEE_REASON_PATTERNS = [
    "charged a fee on my account",
]

FEE_WAIVER_PATTERNS = [
    "request a fee waiver",
    "fee waiver",
]

FEE_VISIBILITY_PATTERNS = [
    "see all account fees clearly",
]

ATM_WITHDRAWAL_FEE_PATTERNS = [
    "atm withdrawals free",
    "atm withdrawal free",
]

IN_APP_CHAT_PATTERNS = [
    "chat with support through the app",
    "support through the app",
]

LOCATOR_PATTERNS = [
    "find the nearest branch or atm",
    "nearest branch or atm",
]

BRANCH_ONLY_PATTERNS = [
    "services can only be done in a branch",
    "only be done in a branch",
]

BRANCH_APPOINTMENT_PATTERNS = [
    "book an appointment before visiting a branch",
    "appointment before visiting a branch",
]

LANGUAGE_SUPPORT_PATTERNS = [
    "help in english and vietnamese",
    "english and vietnamese",
]

COMPLAINT_ESCALATION_PATTERNS = [
    "escalate a complaint if my issue is not resolved",
    "escalate a complaint",
]

EMERGENCY_SAVINGS_PATTERNS = [
    "how much emergency savings should i aim for",
]

SPENDING_ALERT_PATTERNS = [
    "set spending alerts in the app",
    "spending alerts in the app",
]

EXPENSE_TRACKING_PATTERNS = [
    "track my monthly expenses through online banking",
]

STUDENT_YOUNG_ADULT_PATTERNS = [
    "student or young adult",
]

PHISHING_PATTERNS = [
    "recognize phishing messages pretending to be from the bank",
    "recognize phishing messages",
    "phishing messages pretending to be from the bank",
]

TWO_FACTOR_PATTERNS = [
    "enable two-factor authentication",
    "two-factor authentication",
    "enable 2fa",
]

PASSWORD_EXPOSED_PATTERNS = [
    "someone knows my password",
    "think someone knows my password",
    "knows my password",
]

SAFE_BILL_PAY_PATTERNS = [
    "safest way to pay bills online",
]

APP_SECURITY_FEATURE_PATTERNS = [
    "security features in the mobile app",
    "security features are available in the mobile app",
    "what security features are available in the mobile app",
    "mobile app security features",
    "app security features",
]

CARD_OVERVIEW_PATTERNS = ["card service", "credit cards do you offer", "what credit cards do you offer"]
LOAN_OVERVIEW_PATTERNS = [
    "loan service",
    "loan services",
    "apply for a loan",
    "talk about loan",
    "what types of loans do you offer",
    "what loans do you offer",
    "do you offer car loans",
    "do you offer home loans",
    "do you offer home loans or mortgages",
]
INVESTMENT_OVERVIEW_PATTERNS = ["investment options", "invest", "investment platform"]
SAVINGS_OVERVIEW_PATTERNS = ["savings account", "saving account", "savings options", "deposit options"]


LIVE_WORDS = ["current", "today", "exact", "latest", "live", "now"]


def _rate_question(text: str) -> bool:
    return _contains_any(text, LIVE_WORDS) or "rate" in text or "interest" in text


def _live_fallback(text: str) -> PlaybookResult:
    return PlaybookResult(text=text, response_mode="live-fallback")


def build_playbook_response(question: str) -> Optional[PlaybookResult]:
    q = _normalize(question)
    if not q:
        return None

    if _contains_any(q, LOST_CARD_PATTERNS):
        return PlaybookResult(
            text=(
                "Please lock the card immediately in AmazingBank Mobile App if you still have account access. "
                "Then review your recent transactions, note anything unfamiliar, and contact the official AmazingBank "
                "support channel right away to block the card and request a replacement. If you think your PIN or online "
                "credentials may be exposed, change them after the card is secured. Keep the card number, last known "
                "transaction, and the time you noticed the loss ready for support."
            )
        )

    if _contains_any(q, STOLEN_PHONE_PATTERNS):
        return PlaybookResult(
            text=(
                "If your phone with the banking app is stolen, act immediately: lock the SIM with your mobile carrier, "
                "change your AmazingBank password from another trusted device, and revoke app access or sign out other sessions "
                "in AmazingBank Mobile App or AmazingBank Online Banking if available. Then freeze cards or restrict high-risk actions, "
                "review recent transactions, and contact the official AmazingBank support channel right away to secure the account and record the incident."
            )
        )

    if _contains_any(q, FREEZE_ACCOUNT_PATTERNS):
        return PlaybookResult(
            text=(
                "For temporary protection, first use card lock or transaction controls in AmazingBank Mobile App or AmazingBank Online Banking if those controls are available. "
                "If you need a broader account restriction, contact the official AmazingBank support channel immediately and request temporary safeguards while they verify identity. "
                "After the risk is resolved, ask support to confirm restoration steps and any remaining limits."
            )
        )

    if _contains_any(q, SUSPICIOUS_TRANSACTION_PATTERNS):
        return PlaybookResult(
            text=(
                "Act quickly: freeze the card or restrict the account in AmazingBank Mobile App or AmazingBank Online Banking, "
                "then review recent transactions and capture the amount, merchant, time, and channel for anything suspicious. "
                "Contact the official AmazingBank support channel immediately to report the transaction and start a dispute or "
                "investigation. If the transaction may be linked to a password leak or phishing attempt, update your password, "
                "sign out of other devices, and make sure alerts are enabled."
            )
        )

    if _contains_any(q, FAST_SUPPORT_PATTERNS):
        return PlaybookResult(
            text=(
                "For the fastest support path, start with AmazingBank Mobile App or AmazingBank Online Banking for secure messaging and self-service actions. "
                "If a call is required, prepare your ID, account detail, and transaction reference first so the case can be routed quickly. "
                "For urgent security issues, contact the official AmazingBank support channel immediately and state that it is an account-safety incident."
            )
        )

    if _contains_any(q, ACCOUNT_MIN_DEPOSIT_PATTERNS):
        return _live_fallback(
            "I cannot verify an exact AmazingBank minimum opening deposit here, so I do not want to guess. "
            "Some account types may open with no minimum, while others can require an opening balance or first funding step. "
            "Please check the specific account page or the official AmazingBank support channel for the latest requirement."
        )

    if _contains_any(q, ACCOUNT_OPENING_TIME_PATTERNS):
        return _live_fallback(
            "I cannot verify an exact AmazingBank account-opening timeline here. "
            "Opening time usually depends on channel, identity checks, document quality, and whether any manual review is needed. "
            "Please use the official AmazingBank support channel for the latest timing, and I can still help you prepare the right documents and steps."
        )

    if _contains_any(q, JOINT_ACCOUNT_PATTERNS):
        return PlaybookResult(
            text=(
                "I cannot verify a live AmazingBank joint-account policy here, so I do not want to promise availability. "
                "If joint accounts are supported, both applicants usually need identity verification and the required supporting documents. "
                "Use the official AmazingBank support channel to confirm eligibility, whether both people must appear, and which channel can complete the application."
            )
        )

    if _contains_any(q, CHECKING_VS_SAVINGS_PATTERNS):
        return PlaybookResult(
            text=(
                "A checking or payment account is mainly for daily use such as spending, transfers, bill payment, and card activity. "
                "A savings account is mainly for holding money aside, separating spending from saving, and earning interest if that product offers it. "
                "The practical choice depends on whether you need transaction access every day or want a separate place for saving goals."
            )
        )

    if _contains_any(q, ACCOUNT_TYPE_FIT_PATTERNS):
        return PlaybookResult(
            text=(
                "Start with your main use case: everyday payments, short-term saving, fixed-term saving, borrowing, or a mix of those. "
                "Then compare monthly fees, digital access, ATM or transfer needs, savings flexibility, and whether you want card controls or alerts in the app. "
                "If you share your spending pattern and savings goal, I can help narrow the most practical account category."
            )
        )

    if _contains_any(q, LOAN_DOCUMENT_PATTERNS):
        return PlaybookResult(
            text=(
                "Common loan-application documents include identification, income proof, employment or business records, bank statements, existing-debt details, "
                "and collateral or property papers if the product is secured. The exact checklist depends on the loan type, amount, and underwriting rules, "
                "so confirm the final document list through the official AmazingBank support channel."
            )
        )

    if _contains_any(q, OVERDRAFT_FEE_PATTERNS):
        return _live_fallback(
            "I cannot verify the exact AmazingBank overdraft fee here. "
            "Overdraft charges, if any, usually depend on the account terms, whether a payment was covered, and any linked protection setting. "
            "Please check the official fee schedule or support channel for the posted fee treatment on your account."
        )

    if _contains_any(q, AVOID_OVERDRAFT_FEE_PATTERNS):
        return PlaybookResult(
            text=(
                "To reduce overdraft-fee risk, keep a balance buffer, turn on low-balance alerts, review scheduled debits before they post, and ask whether linked-account protection or an opt-out setting is available for your account. "
                "If a fee already posted, contact the official AmazingBank support channel and ask whether a waiver or account-package change is possible."
            )
        )

    if _contains_any(q, OVERDRAFT_TOGGLE_PATTERNS):
        return PlaybookResult(
            text=(
                "Whether you can turn overdraft protection on or off depends on the account settings AmazingBank makes available. "
                "Check the account or overdraft settings in AmazingBank Mobile App or AmazingBank Online Banking first. "
                "If the control is not visible, use the official AmazingBank support channel to confirm what protection options and opt-in or opt-out steps apply to your account."
            )
        )

    if _contains_any(q, OVERDRAFT_PATTERNS):
        return PlaybookResult(
            text=(
                "If your account balance goes negative, it usually means a payment went through without enough available balance and the account entered overdraft. To reduce the risk, "
                "keep a small balance buffer, turn on low-balance alerts, review scheduled debits before they post, and ask whether "
                "AmazingBank offers linked-account protection or an opt-out path for certain overdraft settings. If a fee already "
                "posted, contact the official AmazingBank support channel and ask whether a one-time waiver or account-package option "
                "is available."
            )
        )

    if _contains_any(q, SAVINGS_RATE_PATTERNS) and _rate_question(q):
        return _live_fallback(
            "I cannot verify the live AmazingBank savings rate inside this chat, so I do not want to guess. "
            "The exact rate usually depends on the product type, balance tier, term, and channel. Please check today’s posted rate in AmazingBank Mobile App, AmazingBank Online Banking, or the official AmazingBank support channel. "
            "If you tell me whether you want flexible access or a fixed term, I can still help you compare the right savings structure and the questions you should check before opening it."
        )

    if _contains_any(q, TERM_DEPOSIT_PATTERNS):
        return PlaybookResult(
            text=(
                "I cannot verify a live AmazingBank deposit catalog here, so I should not name a specific fixed-term product. "
                "If you are comparing term or fixed deposits, focus on term length, renewal handling, early-withdrawal treatment, rate conditions, and whether the deposit can be managed in AmazingBank Online Banking."
            )
        )

    if _contains_any(q, EARLY_WITHDRAWAL_PATTERNS):
        return PlaybookResult(
            text=(
                "Early withdrawal from a term or fixed deposit often reduces the expected return. "
                "Depending on the product terms, you may lose part of the interest, lose all expected term interest, or receive a lower fallback rate instead. "
                "Check the product agreement or the official AmazingBank support channel for the exact early-withdrawal rule on your deposit."
            )
        )

    if _contains_any(q, AUTO_SAVINGS_PATTERNS):
        return PlaybookResult(
            text=(
                "A practical setup is a recurring transfer from your everyday account into savings on the same date each month. "
                "Look for recurring or scheduled transfers in AmazingBank Mobile App or AmazingBank Online Banking, set the amount and date, and keep enough balance in the source account so the transfer does not fail."
            )
        )

    if _contains_any(q, SAVINGS_SHORT_TERM_PATTERNS):
        return PlaybookResult(
            text=(
                "For short-term goals, prioritize easy access and lower volatility over chasing the highest headline return. "
                "Flexible savings or shorter-term deposit structures are usually easier to use than long lock-in products if you may need the money soon."
            )
        )

    if _contains_any(q, SAVINGS_LONG_TERM_PATTERNS):
        return PlaybookResult(
            text=(
                "For long-term goals, compare yield against lock-in and access needs. "
                "A fixed-term savings structure can work if you will not need the money soon, while a more flexible savings setup may fit better if the timeline could change. "
                "The practical choice depends on how certain the goal date is and how much withdrawal flexibility matters."
            )
        )

    if _contains_any(q, SAVINGS_MOBILE_PATTERNS):
        return PlaybookResult(
            text=(
                "If mobile management is enabled for your savings product, the common tasks are balance checks, transfers, statements, and transaction review in AmazingBank Mobile App. "
                "Use the official support channel if you need confirmation of specific savings controls that are available for your account type."
            )
        )

    if _contains_any(q, SAVINGS_SAFETY_PATTERNS):
        return PlaybookResult(
            text=(
                "Savings-account safety usually comes down to account controls, authentication, fraud monitoring, and any official deposit protection that applies in your market. "
                "Keep strong authentication and alerts enabled, and check the official AmazingBank terms if you need the exact protection scheme or limit."
            )
        )

    if _contains_any(q, OPEN_ACCOUNT_PATTERNS):
        return PlaybookResult(
            text=(
                "For a new checking or payment account, the usual starting documents are a valid identification document, proof of address, "
                "and any tax or identity number required by local regulation. If you apply in AmazingBank Mobile App, keep your ID ready for "
                "digital verification and use clear lighting during the capture step. Some account types may also require an initial deposit or "
                "extra documents, so check the exact account page or official AmazingBank support channel for the final checklist."
            )
        )

    if _contains_any(q, DEBIT_CARD_PATTERNS):
        return PlaybookResult(
            text=(
                "I cannot verify a live AmazingBank debit-card lineup here, so I should not invent product names or tiers. "
                "The practical comparison points are ATM or cash-access rules, monthly or annual fees, digital card controls, and international-use support if that matters to you."
            )
        )

    if _contains_any(q, CARD_CASHBACK_PATTERNS):
        return PlaybookResult(
            text=(
                "I cannot verify a live AmazingBank card catalog here, so I should not name a best cashback card. "
                "The practical comparison is cashback categories, spending caps, redemption rules, annual fee, and whether the rewards match your real monthly spending. "
                "If you share your main spending categories, I can help you narrow the most sensible cashback card profile."
            )
        )

    if _contains_any(q, CARD_TRAVEL_PATTERNS):
        return PlaybookResult(
            text=(
                "I cannot verify a live AmazingBank travel-card lineup here, so I should not name a best travel card. "
                "Compare foreign-transaction fees, travel rewards structure, annual fee, airport or insurance benefits if any, and how well the card works for overseas payments and ATM use."
            )
        )

    if _contains_any(q, CARD_LIMIT_INCREASE_PATTERNS):
        return PlaybookResult(
            text=(
                "Credit-limit increases usually depend on income, repayment history, current account standing, and internal review rules. "
                "Check the card section in AmazingBank Mobile App or AmazingBank Online Banking first, and use the official AmazingBank support channel if you need the exact request path or review criteria."
            )
        )

    if _contains_any(q, NEW_CARD_APPLICATION_PATTERNS):
        return PlaybookResult(
            text=(
                "A new card application usually starts through the bank’s official digital channel or branch support, depending on which channels AmazingBank currently offers for that card type. "
                "Expect identity verification, agreement review, and for credit cards, income and credit assessment before approval."
            )
        )

    if _contains_any(q, CARD_INTERNATIONAL_USE_PATTERNS):
        return PlaybookResult(
            text=(
                "International card use usually depends on the card network, fraud controls, and any foreign-transaction settings on your specific card. "
                "Before travel, confirm whether international usage is enabled, what foreign or ATM fees apply, and whether cash withdrawals are supported for that card."
            )
        )

    if _contains_any(q, CARD_LOCK_PATTERNS):
        return PlaybookResult(
            text=(
                "If your card has in-app controls, look in the Cards or Card Controls area for options such as lock, unlock, or freeze. "
                "If the control is not visible, use the official AmazingBank support channel right away so the card can still be restricted quickly."
            )
        )

    if _contains_any(q, WRONG_TRANSFER_PATTERNS):
        return PlaybookResult(
            text=(
                "Please contact the official AmazingBank support channel immediately and report that the transfer was sent to the wrong account. "
                "Have the amount, date, reference number, recipient details, and any screenshot or receipt ready so support can trace the payment "
                "and advise whether a recall or recovery request is possible. Do not send a second transfer to correct the mistake. The faster you report it, "
                "the better the chance of recovery, but the final outcome can still depend on the transaction status and receiving account."
            )
        )

    if _contains_any(q, TRANSFER_FEE_PATTERNS):
        return _live_fallback(
            "I cannot verify the exact AmazingBank transfer fee here. "
            "Transfer fees can depend on domestic versus international routing, channel, currency, urgency, destination bank, and your account package. "
            "Please check the official AmazingBank fee schedule or support channel for the latest posted transfer pricing."
        )

    if _contains_any(q, TRANSFER_LIMIT_PATTERNS):
        return _live_fallback(
            "I cannot verify the exact AmazingBank daily transfer limit here. "
            "Transfer limits can depend on channel, customer profile, verification status, destination, and security rules. "
            "Please check the official AmazingBank limits page, app settings, or support channel for the current posted limit on your setup."
        )

    if _contains_any(q, TRANSFER_TIME_PATTERNS):
        return PlaybookResult(
            text=(
                "Transfer timing usually depends on cut-off time, receiving bank, domestic versus international routing, and any fraud or compliance review. "
                "If the payment is not arriving when expected, check the transfer status, keep the reference number, and contact the official AmazingBank support channel for the current case status."
            )
        )

    if _contains_any(q, RECURRING_TRANSFER_PATTERNS):
        return PlaybookResult(
            text=(
                "If recurring transfers are available for your account, set them in the transfer or payments area of AmazingBank Mobile App or AmazingBank Online Banking. "
                "Choose the amount, frequency, start date, and destination account, then review the schedule before confirming."
            )
        )

    if _contains_any(q, TRANSFER_DELAY_PATTERNS):
        return PlaybookResult(
            text=(
                "If a transfer is delayed, first check the status and confirm the recipient details, amount, and destination bank information. "
                "Keep the transfer reference ready, and contact the official AmazingBank support channel if the payment remains pending or the timing looks unusual."
            )
        )

    if _contains_any(q, CANCEL_TRANSFER_PATTERNS):
        return PlaybookResult(
            text=(
                "Whether a transfer can be canceled depends on its processing status. "
                "If it is still pending, cancellation or recall may be possible. If it has already completed, recovery is harder and depends on the payment route. "
                "Check the status immediately and contact the official AmazingBank support channel without delay."
            )
        )

    if _contains_any(q, TRACK_TRANSFER_PATTERNS):
        return PlaybookResult(
            text=(
                "The fastest way to track a transfer is usually through the transfer history or transaction-status area in AmazingBank Mobile App or AmazingBank Online Banking. "
                "If the status is unclear, keep the reference number and use the official AmazingBank support channel for a trace or status update."
            )
        )

    if _contains_any(q, DOMESTIC_TRANSFER_PATTERNS):
        return PlaybookResult(
            text=(
                "To transfer money to another bank account, use AmazingBank Mobile App or AmazingBank Online Banking and go to transfer or payments. "
                "Enter recipient name, destination bank, account number, amount, and transfer note, then review fees or limits before confirming. "
                "For recurring payments, use scheduled transfer settings if available for your account. If a transfer is delayed, keep the reference and contact the official AmazingBank support channel."
            )
        )

    if _contains_any(q, INTERNATIONAL_TRANSFER_PATTERNS):
        return PlaybookResult(
            text=(
                "International transfer is usually handled through AmazingBank digital banking or branch support, depending on destination, currency, and compliance checks. "
                "Prepare recipient full name, bank name, account or IBAN, SWIFT or BIC code, destination country, and payment purpose. "
                "Before sending, verify fees, exchange rate, transfer limits, and expected processing time in the official AmazingBank channel."
            )
        )

    if _contains_any(q, PERSONAL_LOAN_APPLICATION_PATTERNS):
        return PlaybookResult(
            text=(
                "For a personal-loan application, you can usually start in AmazingBank Mobile App or at a branch. "
                "Prepare identification, income evidence, requested amount, preferred repayment term, and a realistic monthly repayment budget. "
                "Approval decisions depend on document completeness, repayment capacity, credit profile, and internal policy checks, so confirm final requirements through the official AmazingBank support channel."
            )
        )

    if _contains_any(q, BORROWING_CAPACITY_PATTERNS):
        return PlaybookResult(
            text=(
                "Borrowing capacity is usually based on verified income, existing debt obligations, repayment history, loan term, and internal credit policy checks. "
                "A practical first step is to estimate a monthly payment you can sustain, then compare that against required documentation and policy limits in AmazingBank Mobile App or branch support. "
                "For an exact eligibility amount, use the official AmazingBank support channel because the final figure depends on full underwriting."
            )
        )

    if _contains_any(q, LOAN_TYPES_PATTERNS):
        return PlaybookResult(
            text=(
                "AmazingBank loan services generally fall into categories such as personal borrowing, home loans or mortgages, vehicle financing, and business borrowing. "
                "I cannot verify a full live product catalog in this chat, so use the official AmazingBank product pages or support channel to confirm which loan categories are currently available."
            )
        )

    if _contains_any(q, HOME_LOAN_OFFER_PATTERNS):
        return PlaybookResult(
            text=(
                "AmazingBank loan services may include home-loan or mortgage borrowing, but I cannot verify the live product catalog here. "
                "The practical next step is to check the official AmazingBank product page or support channel to confirm whether home purchase, refinance, or property-secured borrowing is currently offered."
            )
        )

    if _contains_any(q, CAR_LOAN_OFFER_PATTERNS):
        return PlaybookResult(
            text=(
                "AmazingBank loan services may include vehicle financing or car-loan-style borrowing, but I cannot verify the live catalog here. "
                "Please check the official AmazingBank product page or support channel to confirm whether auto financing is currently available and what documents or collateral rules apply."
            )
        )

    if _contains_any(q, LOAN_APPROVAL_TIME_PATTERNS):
        return _live_fallback(
            "I cannot verify an exact AmazingBank loan approval timeline here. "
            "Approval time usually depends on the loan type, document completeness, any collateral or valuation review, and internal underwriting. "
            "Please use the official AmazingBank support channel for the current processing timeline."
        )

    if _contains_any(q, EARLY_REPAY_ALLOWED_PATTERNS):
        return PlaybookResult(
            text=(
                "Early repayment is often possible, but the exact process, notice requirements, and settlement calculation depend on the loan agreement. "
                "Check your loan terms or the official AmazingBank support channel before making an early payment so you understand any conditions that apply."
            )
        )

    if _contains_any(q, EARLY_REPAY_PENALTY_PATTERNS):
        return _live_fallback(
            "I cannot verify the exact AmazingBank early-repayment charge here. "
            "Any penalty or fee depends on the loan agreement, product type, and repayment timing. "
            "Please check the official loan terms or support channel for the posted early-settlement treatment on your account."
        )

    if _contains_any(q, MORTGAGE_EXPLANATION_PATTERNS):
        return PlaybookResult(
            text=(
                "A fixed mortgage rate stays stable for the agreed period, so the payment is easier to predict. "
                "A variable rate can move with market or policy benchmarks, so the payment can rise or fall over time. "
                "The practical choice depends on whether you value payment stability more than the chance of a lower initial rate."
            )
        )

    if _contains_any(q, MORTGAGE_DOWN_PAYMENT_PATTERNS):
        return _live_fallback(
            "I cannot verify an exact AmazingBank minimum down-payment requirement here. "
            "The amount usually depends on property type, loan-to-value policy, borrower profile, and current underwriting rules. "
            "Please check the official AmazingBank mortgage information or support channel for the latest posted requirement."
        )

    if _contains_any(q, MORTGAGE_AFFORDABILITY_PATTERNS):
        return PlaybookResult(
            text=(
                "House affordability usually comes down to monthly income, existing debt, down payment, interest rate, taxes, insurance, fees, and a payment buffer for normal living costs. "
                "A practical first pass is to choose a monthly payment that still feels comfortable after essentials, then work backward to the home price range that fits that budget."
            )
        )

    if _contains_any(q, MORTGAGE_PREQUALIFY_PATTERNS):
        return PlaybookResult(
            text=(
                "I cannot verify whether AmazingBank labels the first step as prequalification, but the usual early review is based on income, debt, down payment, and basic credit information. "
                "Use the official AmazingBank support channel to confirm whether an initial eligibility check is available before a full mortgage application."
            )
        )

    if _contains_any(q, MORTGAGE_EXTRA_COSTS_PATTERNS):
        return PlaybookResult(
            text=(
                "Besides principal and interest, plan for property taxes, homeowner’s insurance, valuation or appraisal costs, legal or registration costs, bank fees, ongoing maintenance, and possibly mortgage insurance or property-management fees if they apply."
            )
        )

    if _contains_any(q, FIRST_TIME_BUYER_PATTERNS):
        return PlaybookResult(
            text=(
                "I cannot verify a current AmazingBank first-time-homebuyer program here. "
                "Useful questions to check are reduced down-payment options, fee discounts, educational support, eligibility reviews, and whether any first-time-buyer path changes the document list or approval process."
            )
        )

    if _contains_any(q, REFINANCE_PATTERNS):
        return PlaybookResult(
            text=(
                "Refinancing later usually depends on the bank’s current mortgage policy, your repayment history, outstanding balance, property value, and the economics of the new rate or term. "
                "Use the official AmazingBank support channel to confirm whether refinance options are currently available for your loan."
            )
        )

    if _contains_any(q, MORTGAGE_PREP_PATTERNS):
        return PlaybookResult(
            text=(
                "Before applying for a mortgage, prepare identification, income records, employment or business details, bank statements, existing-debt information, and down-payment funds. "
                "If you already know the property, keep the purchase and property documents ready as well. The final checklist depends on the loan structure and underwriting rules."
            )
        )

    if _contains_any(q, MONTHLY_ACCOUNT_FEE_PATTERNS):
        return _live_fallback(
            "I cannot verify the exact AmazingBank monthly account fee here. "
            "Monthly charges can depend on account type, package, balance conditions, and any waiver rules. "
            "Please check the official AmazingBank fee schedule or support channel for the current posted fee on your account."
        )

    if _contains_any(q, AVOID_MONTHLY_ACCOUNT_FEE_PATTERNS):
        return PlaybookResult(
            text=(
                "The usual ways to reduce or avoid monthly account fees are meeting minimum balance rules, keeping qualifying inflows or direct deposits, using an eligible package, or moving to a lower-fee account. "
                "Check the official AmazingBank fee schedule for the exact waiver conditions that apply to your account type."
            )
        )

    if _contains_any(q, FEE_REASON_PATTERNS):
        return PlaybookResult(
            text=(
                "A fee can come from account maintenance, overdraft treatment, out-of-network ATM use, transfer pricing, foreign transactions, or another service listed in the fee schedule. "
                "The fastest way to identify it is to check the posted description in your statement or transaction history, then contact the official AmazingBank support channel if the label is still unclear."
            )
        )

    if _contains_any(q, FEE_WAIVER_PATTERNS):
        return PlaybookResult(
            text=(
                "Some fee-waiver requests are reviewed case by case, especially when there is a clear reason such as a first occurrence or unusual circumstance, but I cannot promise approval. "
                "Contact the official AmazingBank support channel, explain the fee, and ask whether a waiver review is available for that charge."
            )
        )

    if _contains_any(q, FEE_VISIBILITY_PATTERNS):
        return PlaybookResult(
            text=(
                "The clearest places to review fees are the official fee schedule, the product page for your account or card, your statement, and the support channel if a charge still needs explanation. "
                "Those sources are better than guessing from a generic list because fees can vary by product and account package."
            )
        )

    if _contains_any(q, ATM_WITHDRAWAL_FEE_PATTERNS):
        return _live_fallback(
            "I cannot verify the exact AmazingBank ATM withdrawal fee treatment here. "
            "Fees can depend on your card type, whether the ATM is in-network or third-party, and whether the withdrawal is domestic or international. "
            "Please check the official fee schedule or support channel for the current posted ATM policy."
        )

    if _contains_any(q, APP_SECURITY_FEATURE_PATTERNS):
        return PlaybookResult(
            text=(
                "Typical mobile-banking security controls include biometric login, OTP or step-up verification, transaction alerts, device/session management, and card lock controls when enabled for the account. "
                "Exact feature availability can vary by app version and product setup, so confirm the active controls in AmazingBank Mobile App settings or through the official AmazingBank support channel."
            )
        )

    if _contains_any(q, TWO_FACTOR_PATTERNS):
        return PlaybookResult(
            text=(
                "Yes, enabling two-factor authentication is a strong security step when the bank offers it. "
                "It adds another verification layer beyond the password, which lowers the risk of unauthorized access if the password is exposed."
            )
        )

    if _contains_any(q, PASSWORD_EXPOSED_PATTERNS):
        return PlaybookResult(
            text=(
                "Change your password immediately from a trusted device, review recent activity, and sign out of other sessions if that control is available. "
                "If you see suspicious activity or cannot secure access quickly, contact the official AmazingBank support channel right away."
            )
        )

    if _contains_any(q, EDUCATION_SAVINGS_PATTERNS):
        return PlaybookResult(
            text=(
                "A practical education plan usually starts with capital protection and regular saving discipline. For shorter timelines, recurring savings or term deposit structures are often the cleanest option because they are easier to track and protect principal. "
                "For longer timelines, you can also compare lower-risk investment options on AmazingBank Investment Platform if you can accept some value fluctuation. The right choice depends on the target date, how flexible withdrawals need to be, and how much risk you can tolerate."
            )
        )

    if _contains_any(q, HOLD_TIME_PATTERNS):
        return PlaybookResult(
            text=(
                "To reduce hold time, try AmazingBank Mobile App or AmazingBank Online Banking first for chat, secure message, or self-service actions. If you need a call, prepare your ID, account detail, and transaction reference in advance so the case moves faster, and ask whether callback, branch support, or an appointment is available. "
                "For urgent account-security matters, report the risk immediately through the official AmazingBank support channel instead of waiting to explain the full story on hold."
            )
        )

    if _contains_any(q, SERVICE_HOURS_PATTERNS):
        if "weekend" in q:
            return _live_fallback(
                "AmazingBank Mobile App and AmazingBank Online Banking may still be available for self-service at any time, but I cannot verify staffed weekend support in this chat. "
                "Phone, chat, or branch availability can vary by channel and day, so please check the official AmazingBank contact page or support channel for the latest weekend hours."
            )
        return _live_fallback(
            "I cannot verify the exact AmazingBank customer service hours in this chat because hours can vary by channel, branch, and day. "
            "Please check the official AmazingBank contact page, AmazingBank Mobile App, AmazingBank Online Banking, or the branch listing for the latest hours. "
            "If you tell me whether you need phone, chat, or branch support, I can still help you choose the fastest path."
        )

    if _contains_any(q, PHISHING_PATTERNS):
        return PlaybookResult(
            text=(
                "Common phishing signs are urgent warnings, requests for passwords or OTP codes, links that do not match the official bank domain, unusual sender details, and messages pushing you to call an unverified number or scan a suspicious QR code. "
                "Do not click the link. Open the official app or website directly and report the message through the official AmazingBank support channel."
            )
        )

    if _contains_any(q, ONLINE_SECURITY_PATTERNS):
        return PlaybookResult(
            text=(
                "Online banking can be safe when you use the protection tools consistently. Set a strong unique password, enable biometric login and OTP or multi-factor protection, and turn on transaction alerts in AmazingBank Mobile App or AmazingBank Online Banking. Never share OTP codes, avoid banking on public Wi-Fi, verify that app updates are genuine, and open the bank site or app directly instead of tapping links in messages. If something looks unusual, lock access and contact the official AmazingBank support channel quickly."
            )
        )

    if _contains_any(q, MORTGAGE_RATE_PATTERNS) and _rate_question(q):
        return _live_fallback(
            "I cannot verify the live AmazingBank mortgage rate in this chat, so I should not invent a number. "
            "For a mortgage, the final rate usually depends on your credit profile, income strength, loan-to-value level, repayment history, and any current promotion. "
            "Please check the latest posted rate through the official AmazingBank support channel or branch. If you share the home price, down payment, and comfortable monthly budget, I can help you think through affordability and the key rate questions to ask."
        )

    if _contains_any(q, ANNUAL_FEE_PATTERNS):
        return _live_fallback(
            "I cannot verify the exact AmazingBank annual fee in this chat, and the amount can differ by card type and tier. "
            "Please check the official AmazingBank fee schedule or the specific card page for the latest posted annual fee. "
            "If you tell me whether you are comparing debit or credit cards, or the card name, I can help you narrow the right fee questions and benefit tradeoffs."
        )

    if _contains_any(q, IN_APP_CHAT_PATTERNS):
        return PlaybookResult(
            text=(
                "I cannot verify whether your current AmazingBank app setup includes live chat, but the fastest place to check is the Help, Support, or Contact area in the app. "
                "If chat is not available there, use secure messaging if offered or go directly to the official AmazingBank support channel."
            )
        )

    if _contains_any(q, LOCATOR_PATTERNS):
        return PlaybookResult(
            text=(
                "Use the official branch or ATM locator in AmazingBank Mobile App, AmazingBank Online Banking, or the official website. "
                "Search by city or allow location access if you want nearby results, then check the branch or ATM details before traveling."
            )
        )

    if _contains_any(q, BRANCH_ONLY_PATTERNS):
        return PlaybookResult(
            text=(
                "Identity-heavy or document-heavy actions can still require branch support, such as some high-value cash transactions, certain legal or business-account changes, wet-signature documents, or services that need in-person verification. "
                "Check the official AmazingBank support channel before visiting so you know whether a branch trip is necessary."
            )
        )

    if _contains_any(q, BRANCH_APPOINTMENT_PATTERNS):
        return PlaybookResult(
            text=(
                "I cannot verify whether every AmazingBank branch offers appointment booking. "
                "Check the official branch page, app, or support channel to see whether booking, callback, or scheduled branch assistance is available for your location."
            )
        )

    if _contains_any(q, LANGUAGE_SUPPORT_PATTERNS):
        return PlaybookResult(
            text=(
                "In this chat, you can type in English or Vietnamese and I will reply in English. "
                "I cannot verify staffed AmazingBank support-language coverage here, so please check the official AmazingBank support channel if you need confirmed English or Vietnamese assistance from a human representative."
            )
        )

    if _contains_any(q, COMPLAINT_ESCALATION_PATTERNS):
        return PlaybookResult(
            text=(
                "Keep the case reference, summary of the issue, dates, and any supporting records. "
                "If first-line support does not resolve it, contact the official AmazingBank support channel again and ask for supervisor review or the formal complaint-escalation path, then confirm the next review step and reference number."
            )
        )

    if _contains_any(q, EMERGENCY_SAVINGS_PATTERNS):
        return PlaybookResult(
            text=(
                "A common emergency-savings target is about 3 to 6 months of essential living expenses. "
                "The higher end makes more sense if your income is variable, you support other people, or replacing your income could take longer. "
                "If that target feels too large at first, start with one month of essentials and build upward."
            )
        )

    if _contains_any(q, SPENDING_ALERT_PATTERNS):
        return PlaybookResult(
            text=(
                "If alerts are enabled for your account, look in app settings, notifications, or card controls for transaction, low-balance, or spending alerts. "
                "If the control is not visible, use the official AmazingBank support channel to confirm which alert types are available for your account."
            )
        )

    if _contains_any(q, EXPENSE_TRACKING_PATTERNS):
        return PlaybookResult(
            text=(
                "If expense tracking is available in online banking, the common tools are transaction history, category labels, monthly summaries, and statement exports. "
                "Even without automatic categorization, those records can still give you a workable monthly spending view."
            )
        )

    if _contains_any(q, STUDENT_YOUNG_ADULT_PATTERNS):
        return PlaybookResult(
            text=(
                "A practical starting setup for a student or young adult is a low-fee everyday account, a debit card with clear controls, and a simple savings option for short-term goals. "
                "The best comparison points are monthly fees, ATM access, app quality, alerts, transfer costs, and any minimum balance rules."
            )
        )

    if _contains_any(q, SAFE_BILL_PAY_PATTERNS):
        return PlaybookResult(
            text=(
                "The safest way to pay bills online is through the bank’s official app or website, using verified payee details and strong authentication. "
                "Avoid links from messages, double-check the payee before confirming, and turn on alerts so unusual bill payments are easier to catch."
            )
        )

    if _contains_any(q, CARD_OVERVIEW_PATTERNS):
        return PlaybookResult(
            text=(
                "AmazingBank card services generally include debit and credit categories, with differences usually based on spending benefits, annual-fee tier, installment eligibility, and card controls in AmazingBank Mobile App. "
                "If you share your spending pattern and whether cashback or travel value matters more, I can help narrow the most practical card category without guessing unverified product names."
            )
        )

    if _contains_any(q, LOAN_OVERVIEW_PATTERNS):
        return PlaybookResult(
            text=(
                "AmazingBank loan services generally group into personal borrowing, home or mortgage borrowing, vehicle financing, and business borrowing. "
                "The main comparison points are repayment affordability, document requirements, collateral needs, and total borrowing cost. "
                "If you share the purpose, amount, and preferred timeline, I can help narrow the most practical loan category."
            )
        )

    if _contains_any(q, INVESTMENT_OVERVIEW_PATTERNS):
        return PlaybookResult(
            text=(
                "AmazingBank Investment Platform can support different starting points, but the right option depends on timeline and risk tolerance before product type. A short-term goal usually calls for higher liquidity and lower volatility, while a longer horizon gives more room to compare diversified funds or bond-based options. Before choosing anything, define your target amount, when you need the money, and how much short-term fluctuation you can accept. If you share those three points, I can help you structure a practical starting approach."
            )
        )

    if _contains_any(q, SAVINGS_OVERVIEW_PATTERNS) and not _rate_question(q):
        return PlaybookResult(
            text=(
                "AmazingBank savings planning is easiest when you first decide between flexibility and return. If you may need the money soon, compare flexible-access savings options and digital management features. If the money can stay untouched for a defined period, compare term structure, renewal handling, early-withdrawal treatment, and how clearly the option can be managed in AmazingBank Online Banking. The best choice depends on your timeline, the stability of the balance, and whether convenience or yield matters more for this goal."
            )
        )

    return None
