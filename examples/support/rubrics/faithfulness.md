# Faithfulness rubric (1-5)

You are grading whether a customer-support reply is grounded in the supplied policy context.
Judge factual support only. Ignore tone, formatting, length, and personality.

## Score 5 — Excellent

Every factual claim in the reply is supported by the policy context. Citations, when present,
point to the supporting policy text.

## Score 4 — Good

The reply is grounded, with one harmless imprecision that does not change what the customer
should do.

## Score 3 — Adequate

The core claim is supported, but at least one secondary claim is neither supported nor
contradicted. The reply remains safe to send with light editing.

## Score 2 — Weak

The reply contains an unsupported claim that could mislead the customer about timing, money,
or eligibility.

## Score 1 — Failure

The reply contradicts the policy context, invents policy, or discloses/requests sensitive
credentials. This is an explicit failure.

## How to score

- Check each factual claim against the policy context.
- A claim that is merely omitted is not unfaithful; a claim that is invented is.
- If the reply declines to answer because the context is insufficient, that is faithful.
