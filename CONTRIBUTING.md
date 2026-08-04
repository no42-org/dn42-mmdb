# Contributing to dn42-mmdb

Thank you for contributing to `dn42-mmdb`.

## Developer Certificate of Origin (DCO)

All commits must include a `Signed-off-by` trailer certifying the Developer Certificate of Origin (DCO).
Generate this trailer automatically using `git commit -s`:

```text
Signed-off-by: Your Name <your.email@example.com>
```

## AI Contribution Policy

Contributions created with assistance from AI tools are welcome.
Commits containing AI-generated or AI-assisted content must carry an `Assisted-by` trailer before the `Signed-off-by` trailer:

```text
Assisted-by: Antigravity:gemini-3.6-flash
Signed-off-by: Your Name <your.email@example.com>
```

The human submitter signing off the commit remains fully responsible for review, correctness, and license compliance.

## Workflow

1. Open a GitHub issue describing the bug or feature before submitting a Pull Request.
2. Ensure `make verify` passes cleanly.
3. Submit your Pull Request referencing the issue using `Closes #<issue-number>`.
