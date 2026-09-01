# Stocklog v3.75.10

- Fixed portfolio acquisition-source attribution for historical Gbot fills.
- Portfolio now falls back to net filled Gbot buy/sell decisions when a legacy auto-trading position ledger row is missing.
- Legacy missing automatic-position rows are self-healed on portfolio load, capped by the broker's current holding quantity.
- Portfolio AI execution-reason detail receives explicit stock context and uses hardened responsive layout/CSS to prevent overflow/broken rendering.
- Existing v3.75.9 portfolio, auto-history, Gbot, live-fill, routing and sync behavior retained.
