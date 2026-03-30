---
name: exchange-setup
description: Guides the user through exchange connectivity and configuration safely, without handling secrets in chat
version: 0.1.0
tags: [exchange, setup, configuration]
user_invocable: true
model_invocable: true
requires_tools: []
---

# Exchange Setup

## Description
Guides the user through exchange connectivity and configuration safely, without handling secrets in chat.

## Triggers
- "How do I connect an exchange?"
- "Set up API keys for trading data"

## Steps
1. Confirm which exchange and whether the goal is market data only or broader integration.
2. Explain that credentials must be stored via the product secure storage or OS secret flow—not pasted into chat.
3. Walk through high-level checklist: create keys with minimal permissions, restrict IP if available, rotate periodically.
4. Point to local configuration surfaces (e.g. environment and secure vault) per project docs—never echo or store keys in the conversation.

## Tools Used
- None (guidance only): There is no direct tool for handling API keys in chat; use secure storage and local configuration only.

## Example Interaction
**User**: Where do I put my Binance API key?
**Agent**: Do not paste keys here. Use the project's secure secret storage or environment configuration on your machine. Create a read-only or minimal-scope key, restrict by IP if your exchange allows it, and verify connectivity through the official setup flow—not through this chat.

## Notes
- API keys must go through secure storage; never place secrets in prompts, logs, or frontend storage.
