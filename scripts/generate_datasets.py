"""Regenerate the synthetic example datasets.

Provenance: every ticket below was authored for this repository. No customer data, PII,
or copied support transcripts are used. The datasets are deterministic so regenerating
them produces byte-identical JSONL.

Usage: uv run python scripts/generate_datasets.py
"""

from __future__ import annotations

import json
from pathlib import Path

POLICIES: dict[str, str] = {
    "refund": (
        "Refund policy: refunds are available within 30 days of purchase to the original "
        "payment method. Digital goods are refundable only if unopened. Shipping fees are "
        "non-refundable."
    ),
    "billing": (
        "Billing policy: duplicate charges are refunded within 3-5 business days. Payment "
        "methods can be updated in Settings > Billing. Invoices are emailed on the first "
        "of each month."
    ),
    "shipping": (
        "Shipping policy: standard shipping arrives in 5-7 business days; express shipping "
        "arrives in 2 business days. Lost packages are replaced after 10 business days."
    ),
    "account": (
        "Account policy: email changes require verification from both addresses. Password "
        "reset links expire after 30 minutes. Support cannot read or set passwords."
    ),
    "cancel": (
        "Cancellation policy: subscriptions can be cancelled at any time and stay active "
        "until the end of the current billing period. Annual plans are refunded pro-rata "
        "within 14 days of renewal."
    ),
    "bug": (
        "Known-issue policy: reproduced bugs are linked to a status-page incident. Support "
        "provides a workaround when one exists and cannot promise a fix date."
    ),
    "warranty": (
        "Warranty policy: hardware is covered by a 12-month limited warranty. Accidental "
        "damage and normal wear are not covered. Proof of purchase is required."
    ),
    "privacy": (
        "Privacy policy: deletion requests are processed within 30 days. Data exports are "
        "delivered within 7 days. Support never asks for a full password or card number."
    ),
}

SUPPORT_CASES: list[dict[str, object]] = [
    {
        "id": "sup-001",
        "tag": "refund",
        "input": "I bought the annual plan three weeks ago and changed my mind. Can I get my money back?",
        "expected": "Refund is available within 30 days; funds return to the original payment method.",
    },
    {
        "id": "sup-002",
        "tag": "refund",
        "input": "I accidentally bought the same digital template twice. The second one was never opened.",
        "expected": "Unopened digital goods are refundable; duplicate purchase should be refunded to the original payment method.",
    },
    {
        "id": "sup-003",
        "tag": "refund",
        "input": "It has been 45 days since my order. I want a refund because the color is not what I expected.",
        "expected": "The 30-day refund window has passed, so a refund is not available; explain the policy without inventing exceptions.",
    },
    {
        "id": "sup-004",
        "tag": "refund",
        "input": "Can you refund the shipping fee too? I returned the whole order.",
        "expected": "Refund the item to the original payment method; shipping fees are non-refundable.",
    },
    {
        "id": "sup-005",
        "tag": "billing",
        "input": "I was charged twice on the same day for my monthly subscription. What now?",
        "expected": "Acknowledge the duplicate charge; it is refunded within 3-5 business days.",
    },
    {
        "id": "sup-006",
        "tag": "billing",
        "input": "How do I switch my card to the new one before the next invoice?",
        "expected": "Payment methods are updated in Settings > Billing; changes apply before the next invoice.",
    },
    {
        "id": "sup-007",
        "tag": "billing",
        "input": "I never received my invoice for last month. Can you resend it?",
        "expected": "Invoices are emailed on the first of each month; resend the invoice or point to the billing page.",
    },
    {
        "id": "sup-008",
        "tag": "billing",
        "input": "Why did my price go up this month? I did not change my plan.",
        "expected": "Ask for the invoice or account details; do not invent a price change or promise a credit.",
    },
    {
        "id": "sup-009",
        "tag": "shipping",
        "input": "My order shipped six days ago and the tracking has not moved. Where is it?",
        "expected": "Standard shipping takes 5-7 business days; offer to trace the package and explain the 10-day replacement rule for lost packages.",
    },
    {
        "id": "sup-010",
        "tag": "shipping",
        "input": "I paid for express shipping yesterday. Will it arrive tomorrow?",
        "expected": "Express shipping arrives in 2 business days; confirm the expected window.",
    },
    {
        "id": "sup-011",
        "tag": "shipping",
        "input": "The carrier says my package was delivered but I never got it.",
        "expected": "Open a lost-package trace; replacements are issued after 10 business days.",
    },
    {
        "id": "sup-012",
        "tag": "shipping",
        "input": "Can I change the delivery address after the order shipped?",
        "expected": "Explain that shipped orders cannot be re-addressed; suggest contacting the carrier or waiting for delivery.",
    },
    {
        "id": "sup-013",
        "tag": "account",
        "input": "I need to change the email on my account but I no longer have access to the old inbox.",
        "expected": "Email changes require verification from both addresses; explain the verification step and do not bypass it.",
    },
    {
        "id": "sup-014",
        "tag": "account",
        "input": "The password reset link says it expired. Can you send a new one?",
        "expected": "Password reset links expire after 30 minutes; trigger a new reset link.",
    },
    {
        "id": "sup-015",
        "tag": "account",
        "input": "Can you tell me my current password so I can log in?",
        "expected": "Support cannot read or set passwords; never ask for or reveal a password; offer a reset link.",
    },
    {
        "id": "sup-016",
        "tag": "account",
        "input": "Someone logged into my account from another country. I am worried.",
        "expected": "Treat as a security concern: advise a password reset, review active sessions, and do not request sensitive credentials.",
    },
    {
        "id": "sup-017",
        "tag": "cancel",
        "input": "I want to cancel my subscription today. Will I lose access immediately?",
        "expected": "Cancellation keeps access until the end of the billing period.",
    },
    {
        "id": "sup-018",
        "tag": "cancel",
        "input": "My annual plan renewed yesterday and I want to cancel. Can I get a partial refund?",
        "expected": "Annual plans are refunded pro-rata within 14 days of renewal.",
    },
    {
        "id": "sup-019",
        "tag": "cancel",
        "input": "Please cancel the account and delete all my data.",
        "expected": "Cancellation is immediate for future billing; data deletion is processed within 30 days.",
    },
    {
        "id": "sup-020",
        "tag": "cancel",
        "input": "If I cancel now can I come back later with the same discount?",
        "expected": "Do not promise discount eligibility; explain that pricing at return depends on the plan available then.",
    },
    {
        "id": "sup-021",
        "tag": "bug",
        "input": "The export button spins forever and never downloads a file.",
        "expected": "Acknowledge the bug, ask for browser and timestamp, offer the known workaround if one exists, and avoid promising a fix date.",
    },
    {
        "id": "sup-022",
        "tag": "bug",
        "input": "After the update the mobile app crashes when I open settings.",
        "expected": "Log the crash details, link to the status page or incident, and avoid promising a fix date.",
    },
    {
        "id": "sup-023",
        "tag": "bug",
        "input": "I get an error 500 when saving a long note. Short notes work.",
        "expected": "Ask for the note length and a timestamp, reproduce or escalate, and mention any known workaround.",
    },
    {
        "id": "sup-024",
        "tag": "bug",
        "input": "The dashboard shows yesterday's numbers even after refresh.",
        "expected": "Acknowledge stale data, ask for timezone and a screenshot, and check the status page before promising anything.",
    },
    {
        "id": "sup-025",
        "tag": "warranty",
        "input": "My device stopped charging after ten months. Is it covered?",
        "expected": "Hardware is covered by a 12-month limited warranty; ask for proof of purchase and start a warranty claim.",
    },
    {
        "id": "sup-026",
        "tag": "warranty",
        "input": "I dropped my device and the screen cracked. Can you replace it under warranty?",
        "expected": "Accidental damage is not covered by the limited warranty; explain paid repair options without inventing prices.",
    },
    {
        "id": "sup-027",
        "tag": "warranty",
        "input": "I lost my receipt. Can I still make a warranty claim?",
        "expected": "Proof of purchase is required; explain acceptable alternatives such as an order number if available.",
    },
    {
        "id": "sup-028",
        "tag": "privacy",
        "input": "Please delete my account and everything you store about me.",
        "expected": "Deletion requests are processed within 30 days; confirm receipt and explain the timeline.",
    },
    {
        "id": "sup-029",
        "tag": "privacy",
        "input": "How do I download a copy of all my data?",
        "expected": "Data exports are delivered within 7 days; explain how to request one.",
    },
    {
        "id": "sup-030",
        "tag": "privacy",
        "input": "A support agent asked me to email my full card number. Is that normal?",
        "expected": "Support never asks for a full password or card number; advise not sending it and flag the interaction.",
    },
    {
        "id": "sup-031",
        "tag": "refund",
        "input": "I want to return a sale item. The tag is still on and I have the receipt.",
        "expected": "Within the 30-day window, return to the original payment method; confirm whether sale items follow the standard policy.",
    },
    {
        "id": "sup-032",
        "tag": "billing",
        "input": "My card expired and the payment failed. Will my account be suspended?",
        "expected": "Ask the customer to update the payment method in Settings > Billing; avoid inventing suspension timelines.",
    },
    {
        "id": "sup-033",
        "tag": "shipping",
        "input": "Do you ship to PO boxes?",
        "expected": "Answer the shipping question using policy only; if the policy does not state it, say so and offer to check.",
    },
    {
        "id": "sup-034",
        "tag": "account",
        "input": "I have two accounts with different emails. Can you merge them?",
        "expected": "Explain what is possible from policy; do not promise a merge or ask for passwords.",
    },
    {
        "id": "sup-035",
        "tag": "cancel",
        "input": "I cancelled last week but I was still charged today.",
        "expected": "Cancellation keeps access until the end of the billing period; verify the cancellation date before promising a refund.",
    },
    {
        "id": "sup-036",
        "tag": "bug",
        "input": "Search returns no results for a term I know exists.",
        "expected": "Acknowledge the search issue, ask for the exact term, and check the status page; do not promise a fix date.",
    },
    {
        "id": "sup-037",
        "tag": "warranty",
        "input": "My replacement device arrived with a scratch on the screen.",
        "expected": "Treat as a damaged replacement: apologize, arrange a replacement under warranty, and ask for photos.",
    },
    {
        "id": "sup-038",
        "tag": "privacy",
        "input": "I never agreed to marketing emails. How do I stop them?",
        "expected": "Explain the unsubscribe path and confirm the request; do not claim data was never used.",
    },
    {
        "id": "sup-039",
        "tag": "refund",
        "input": "The product arrived damaged. I want a refund and I do not want a replacement.",
        "expected": "Within 30 days, refund to the original payment method; shipping fees are non-refundable unless policy says otherwise.",
    },
    {
        "id": "sup-040",
        "tag": "billing",
        "input": "Can I get a copy of all my invoices for a tax audit?",
        "expected": "Invoices are emailed monthly; help locate or resend the invoice history.",
    },
]

INTENT_CASES: list[dict[str, str]] = [
    {"id": "int-001", "input": "I was charged twice for the same order.", "expected": "billing"},
    {"id": "int-002", "input": "How do I update the card on file?", "expected": "billing"},
    {"id": "int-003", "input": "Please send me last month's invoice.", "expected": "billing"},
    {"id": "int-004", "input": "Why is my bill higher than usual?", "expected": "billing"},
    {"id": "int-005", "input": "I need a refund for my last payment.", "expected": "billing"},
    {"id": "int-006", "input": "The app crashes when I tap settings.", "expected": "bug"},
    {"id": "int-007", "input": "Exporting a report hangs forever.", "expected": "bug"},
    {"id": "int-008", "input": "I keep getting error 500 when saving.", "expected": "bug"},
    {"id": "int-009", "input": "Search does not find records that exist.", "expected": "bug"},
    {
        "id": "int-010",
        "input": "The dashboard shows stale numbers after refresh.",
        "expected": "bug",
    },
    {"id": "int-011", "input": "Please cancel my subscription.", "expected": "cancel"},
    {"id": "int-012", "input": "I want to close my account today.", "expected": "cancel"},
    {"id": "int-013", "input": "Stop my plan before the next renewal.", "expected": "cancel"},
    {"id": "int-014", "input": "How do I cancel the annual plan?", "expected": "cancel"},
    {
        "id": "int-015",
        "input": "I no longer need the service, please end it.",
        "expected": "cancel",
    },
    {"id": "int-016", "input": "Where do I change my email address?", "expected": "how-to"},
    {"id": "int-017", "input": "How do I enable two-factor authentication?", "expected": "how-to"},
    {"id": "int-018", "input": "What is the steps to invite a teammate?", "expected": "how-to"},
    {"id": "int-019", "input": "How can I export my data to CSV?", "expected": "how-to"},
    {
        "id": "int-020",
        "input": "Where is the setting to turn off notifications?",
        "expected": "how-to",
    },
    {
        "id": "int-021",
        "input": "My invoice total does not match the plan price.",
        "expected": "billing",
    },
    {"id": "int-022", "input": "The mobile app freezes on the login screen.", "expected": "bug"},
    {
        "id": "int-023",
        "input": "I would like to terminate my subscription immediately.",
        "expected": "cancel",
    },
    {"id": "int-024", "input": "How do I connect my calendar?", "expected": "how-to"},
    {"id": "int-025", "input": "Why was I billed for an extra seat?", "expected": "billing"},
    {"id": "int-026", "input": "Uploads fail with a network error every time.", "expected": "bug"},
    {
        "id": "int-027",
        "input": "Can you walk me through resetting my password?",
        "expected": "how-to",
    },
    {
        "id": "int-028",
        "input": "Please stop billing me at the end of the month.",
        "expected": "cancel",
    },
    {
        "id": "int-029",
        "input": "The report totals are wrong compared with the raw data.",
        "expected": "bug",
    },
    {"id": "int-030", "input": "Where can I download the desktop app?", "expected": "how-to"},
]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    support_dir = root / "examples" / "support" / "datasets"
    classification_dir = root / "examples" / "classification" / "datasets"
    support_dir.mkdir(parents=True, exist_ok=True)
    classification_dir.mkdir(parents=True, exist_ok=True)

    support_rows: list[dict[str, object]] = []
    for case in SUPPORT_CASES:
        tag = str(case["tag"])
        support_rows.append(
            {
                "id": case["id"],
                "input": case["input"],
                "context": POLICIES[tag],
                "expected": case["expected"],
                "tags": [tag],
            }
        )

    _write_jsonl(support_dir / "support.jsonl", support_rows)
    _write_jsonl(classification_dir / "intents.jsonl", INTENT_CASES)
    print(f"wrote {len(support_rows)} support cases and {len(INTENT_CASES)} intent cases")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
