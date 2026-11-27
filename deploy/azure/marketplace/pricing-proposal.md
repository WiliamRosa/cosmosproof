# Pricing

**Decided on 2026-11-27: option A with the prices below** (Evaluation, Starter, Business, Enterprise by private offer). The reasoning is kept as written. It had to fit two facts:

1. **The license.** Under BSL 1.1, production use by a company needs a commercial license, and the LICENSE file names the Marketplace offer as the way to get one. A free plan that a company could run in production forever would contradict the license. So the Marketplace offer must have at least one **paid** plan, and any free plan must be explicitly limited to evaluation.
2. **The Marketplace model for a Managed Application.** A plan can have a flat monthly (or yearly) price, optionally plus metered dimensions reported by the publisher. Managed Applications have no built-in free trial. Microsoft keeps a 3% store fee.

The customer also pays Azure and Databricks directly for what runs in their tenant: the daily job, its storage and logs (a few dollars a month), the SQL warehouse time of each audit, and the Databricks App while it runs.

## What the price should follow

The value is in the size of the estate, not in the number of users: the app is for any number of people, and charging per user would push customers to share one login. Workspaces are easy to count, are visible to the customer in the app, and grow with the lakehouse. ADLS accounts follow workspaces closely enough to leave them out of the price.

## Options

| | A. Flat plans by size | B. Base + metered workspaces | C. One flat price |
|---|---|---|---|
| How | Starter up to 3 workspaces, Business up to 15, Enterprise private offer | Monthly base including 3 workspaces, plus a monthly charge per extra workspace analyzed | Same price for any estate |
| Customer reads it | Easiest | Needs a count | Easiest |
| Publisher work | None beyond the plans | The job must report usage to the Marketplace metering API: new code, a publisher identity and a test | None |
| Fairness | Steps between plans | Fair | Small estates overpay, large ones underpay |

**Decision: A**, with prices to revisit after the first bank interviews:

| Plan | Scope | Monthly | Yearly (2 months free) |
|---|---|---|---|
| Evaluation | Up to 1 workspace, 30 days, non-production use only (stated in the plan description and in the terms) | US$ 0 | n/a |
| Starter | Up to 3 workspaces | US$ 490 | US$ 4,900 |
| Business | Up to 15 workspaces | US$ 1,490 | US$ 14,900 |
| Enterprise | Above 15 workspaces, management group scope, support SLA | Private offer | Private offer |

Why these numbers: a bank's lakehouse easily keeps terabytes of hot data nobody reads; 100 TB in hot ADLS costs roughly US$ 2,000 a month at list price before any compute that keeps feeding it. One findings-driven cleanup a quarter pays for Business, and the PII reading is worth more to a compliance team than the storage saving. The prices are deliberately below the typical FinOps platform contract, because CosmosProof covers one platform and must win its first references.

**Enforcing the workspace limit:** the plan limit is contractual at first (the terms tie the license to the plan's scope). The app already counts the selected workspaces, so a later version can warn when the selection exceeds the plan. This is not implemented yet.

**Not proposed now:** metered billing (option B) needs new code in the job and a test of the metering API; it can replace A later without changing the customer's experience much.

## Open points

- The BSL licensor is Wiliam Rosa as a person; the publisher is Cosmos Data. Before selling, transfer or license the rights to the company (see the note in [terms-of-use.md](terms-of-use.md)).
- Confirm in Partner Center whether the Evaluation plan can be time-limited by the plan itself or only by the terms; if only by the terms, keep it private (shared with prospects by tenant ID) instead of public.
- Brazilian taxes on Marketplace payouts and the currency of the price list (Partner Center converts from USD by default).
