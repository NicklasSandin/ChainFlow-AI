# ChainFlow AI

Autonomous multi-model relay for browser-based AI sessions.

ChainFlow lets you put ChatGPT, Grok, Claude, and Kimi into the same controlled workflow. Models can debate, critique, research, refine, and reach a final synthesis without manual copy/paste.

## Modes

- **Debate** — models take turns arguing different sides.
- **Critic** — one model proposes, another attacks the proposal, and the first improves it.
- **Research** — multiple models investigate from different roles, then a synthesizer combines the findings.
- **Custom** — choose any enabled providers and role prompts.

## Safety / control

- Pause/resume at any time.
- Stop an active run.
- Inject a new instruction into the relay.
- Configure a hard maximum number of turns.
- Browser sessions stay local; credentials are not stored by ChainFlow.
- The browser UI is the source of truth. ChainFlow does not require private provider endpoints.

## Supported providers

- ChatGPT
- Grok
- Claude
- Kimi

The provider layer is deliberately modular so Gemini, DeepSeek, Perplexity, etc. can be added later.

## Requirements

- Python 3.11+
- Chromium/Chrome
- Playwright

## Install

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Run

```bash
python app.py
```

Open `http://127.0.0.1:8765`.

On first use, click **Open login browser**, sign into the providers you want to use, then return to ChainFlow.

## Important

AI websites change their DOM frequently. Provider selectors live in `providers.py` so they can be updated independently. ChainFlow uses normal browser interaction rather than undocumented provider APIs.
