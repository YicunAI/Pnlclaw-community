# Risk Report

## Description
Generates a risk assessment for current or hypothetical positions using engine rules and paper state.

## Triggers
- "Run a risk check on my portfolio"
- "What does risk_report say right now?"

## Steps
1. Identify account and symbols of interest for context.
2. Call `paper_positions` to list open exposure and quantities.
3. Call `risk_report` to enumerate active rules and their status.
4. For a specific trade idea, build a trade intent and call `risk_check`.
5. Summarize allowed/blocked outcomes and the most binding constraints.

## Tools Used
- `risk_check`: Evaluate a concrete trade intent against configured risk rules.
- `risk_report`: List configured risk rules and their current enablement/status.
- `paper_positions`: Inspect open paper positions for exposure before reasoning about risk.

## Example Interaction
**User**: Am I allowed to add size on BTC with my current rules?
**Agent**: I will read `paper_positions` for exposure, then `risk_report` for rules. If you propose a trade, I will validate it with `risk_check` and explain the decision.

## Notes
- Risk outputs are advisory; final responsibility stays with the operator and policy configuration.
