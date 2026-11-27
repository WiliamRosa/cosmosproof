# CosmosProof: rules for agents

- Code, comments, commit messages, tests and docs in English.
- Commit as `Wiliam Rosa <66886431+WiliamRosa@users.noreply.github.com>` (set in the local git config), signed off (`git commit -s`). Never commit with a personal email.
- Never push to `main`: branch, pull request, wait for CI, squash merge.
- CosmosProof only reads. No code path may delete, move, retier or change customer data or settings.
- A finding never rests on a single missing signal; every finding keeps its evidence, confidence, coverage notes and proof hash ([ADR 0004](docs/decisions/0004-evidence-and-confidence-model.md)).
- No built-in cloud prices: costs come only from the customer's configured rates.
- Never commit scan outputs (reports, ledgers, inventories): they hold owner emails and internal names.
- Public material says "source-available", never "open source" (BSL 1.1, [ADR 0002](docs/decisions/0002-repository-license-and-cosmos-dependency.md)).
- Shared foundation (connectors, PII detection) belongs in Cosmos Semantic; CosmosProof consumes released versions from PyPI.
- Record decisions as ADRs in `docs/decisions/` and keep the roadmap current.
