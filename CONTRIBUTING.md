# Contributing

This is a **paused, paper-trading research prototype**, not financial advice
or a production investment service. Bug reports, reproducibility reviews,
financial-statistics corrections and narrowly scoped pull requests are welcome.

## Before opening a pull request

- State the hypothesis and an objective evaluation metric in advance.
- Provide code, tests and reproducible sample data (without personal data).
- Separate in-sample selection from untouched holdout / forward evaluation.
- Include transaction costs, slippage and appropriate no-trade benchmarks.
- Demonstrate that the change does not place real broker or exchange orders.
- Do not add secrets, tokens, private IP addresses, personal server details,
  account statements or data redistributed without permission.

Start with the existing local test commands described in README.md;
report missing optional dependencies explicitly. Prefer small PRs and
avoid requesting remote deployment or external account access.

Please report security issues privately to the maintainer rather than
opening a public issue containing exploit details or credentials.

**License note:** The repository has no open-source license at present.
Public visibility permits review but does not itself grant redistribution
rights. Licensing for broader reuse needs an explicit owner decision.
