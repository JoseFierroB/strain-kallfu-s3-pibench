# Strain Kallfu Zero — Pi-Bench Purple Agent

> AgentX - AgentBeats Phase 2 · Sprint 3 · Agent Safety Track
> Team: Strain Kallfu Zero · Contact: josefierrobustos@gmail.com

A2A-compatible purple agent for the Pi-Bench policy compliance benchmark. Evaluates agent safety on 71 scenarios across FINRA, retail, and IT helpdesk domains using 9 capability columns.

## Architecture

3-layer pipeline with 1 LLM call per turn:

```
Pre-Pipeline (deterministic) → LLM Core (DeepSeek V3.2) → Post-Pipeline (deterministic)
```

- **Cerebro 0:** Policy rule extraction, intent classification, adversarial input detection
- **Cerebro 1:** LLM call with fallback chain (DeepSeek V3.2 → Llama 4 → GPT-4o-mini)
- **Cerebro 2:** Tool call validation, JSON repair, A2A response formatting

## Quick Start

```bash
# Install
pip install -e .

# Run server
python src/purple_server.py --host 0.0.0.0 --port 9009

# With custom card URL (for AgentBeats)
python src/purple_server.py --host 0.0.0.0 --port 9009 --card-url https://your-url

# Set API keys
export NEBIUS_API_KEY="your-key"
export OPENAI_API_KEY="your-key"  # optional fallback
```

## Docker

```bash
docker build --platform linux/amd64 -t strain-kallfu-s3-pibench .
docker run -p 9009:9009 -e NEBIUS_API_KEY=$NEBIUS_API_KEY strain-kallfu-s3-pibench
```

## Endpoints

- `GET /.well-known/agent.json` — Agent Card
- `GET /.well-known/agent-card.json` — Agent Card alias
- `GET /health` — Health check
- `POST /` — A2A message/send handler (JSON-RPC 2.0)

## Leaderboard

https://agentbeats.dev/agentbeater/pi-bench

## License

MIT — see LICENSE file.
