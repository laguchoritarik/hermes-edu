# Governance

Hermes Edu starts with a lightweight maintainer model.

- Architectural changes require an ADR under `docs/adr/`.
- Public API changes require tests and documentation.
- New provider integrations must implement existing ports instead of adding provider conditionals to the domain/application layers.
- Maintainers may request a design discussion before large pull requests.
- Decisions should prefer maintainability, portability, security, and educational correctness over framework novelty.
