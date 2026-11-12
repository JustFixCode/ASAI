# Open-source trading platform research (offline note)

This note records design references only; it does not incorporate, vendor, or redistribute any upstream code. Links are included for later review but were not fetched for this offline task.

| Project | Links | License caution | Design lessons for ASAI |
|---|---|---|---|
| QuantConnect LEAN | [Repository](https://github.com/QuantConnect/Lean) · [Documentation](https://www.quantconnect.com/docs/v2/lean-cli/) | LEAN is distributed under Apache-2.0. Preserve required notices and assess licenses for brokerage, data, and other integrations separately; data usage rights are not granted by the engine license. | Keep a clear algorithm-to-engine boundary; use deterministic event-driven execution, pluggable data feeds/brokerage adapters, and reproducible research/backtest/live pathways. |
| NautilusTrader | [Repository](https://github.com/nautechsystems/nautilus_trader) · [Documentation](https://nautilustrader.io/docs/latest/) | NautilusTrader is LGPL-3.0-or-later. Do not copy or modify LGPL components into proprietary ASAI code without a legal review of the corresponding-source, relinking, and distribution obligations. | Separate strategy logic from execution infrastructure; model orders, positions, instruments, and events explicitly; design for replayable event streams and consistent backtest/live behavior. |
| Microsoft Qlib | [Repository](https://github.com/microsoft/qlib) · [Documentation](https://qlib.readthedocs.io/) | Qlib is MIT-licensed. Retain its copyright and license notice if any code is reused; check dataset licenses independently. | Treat the research pipeline as versioned data plus feature engineering, model training, and evaluation; record experiments and guard against leakage with time-aware validation. |
| Freqtrade | [Repository](https://github.com/freqtrade/freqtrade) · [Documentation](https://www.freqtrade.io/en/stable/) | Freqtrade is GPL-3.0-or-later. Avoid copying, linking, or distributing derivative code with proprietary ASAI components unless ASAI can meet GPL distribution and source-availability obligations; obtain legal advice before integration. | Make configuration declarative and reviewable; build risk controls into the execution path (limits, stoplosses, protections); maintain dry-run/backtesting modes and observable trade logs. |

## Cross-project guardrails

- Use these projects as architectural references, not as an implicit license to combine their code.
- Inventory every dependency and adapter by license before adoption, including exchange SDKs, market data, indicators, model libraries, and datasets.
- Preserve provenance, version pins, and reproducible configurations for every research result.
- Keep the existing no-trading boundary: any future execution adapter should require explicit authorization, independent risk checks, and an auditable order trail.
- Seek qualified legal review before distributing a product that includes or derives from copyleft-licensed components.
