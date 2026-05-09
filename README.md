# Strain Kallfu Zero — Pi-Bench Purple Agent

> AgentX - AgentBeats Phase 2 · Sprint 3 · Agent Safety Track
> Team: Strain Kallfu Zero · Contact: josefierrobustos@gmail.com

A2A-compatible purple agent for the Pi-Bench policy compliance benchmark. Evaluates agent safety on 71 scenarios across FINRA, retail, and IT helpdesk domains using 9 capability columns.

## Architecture

3-layer pipeline with 1 LLM call per turn:

```
Pre-Pipeline (deterministic) -> LLM Core (DeepSeek V3.2) -> Post-Pipeline (deterministic)
```

- **Cerebro 0:** Policy rule extraction, intent classification, adversarial input detection
- **Cerebro 1:** LLM call with fallback chain (DeepSeek V3.2 -> Llama 4 Maverick -> GPT-4o-mini)
- **Cerebro 2:** Tool call validation, JSON repair, A2A response formatting

## Quick Start

```bash
# Install
pip install -e .

# Configure (copy and edit with your keys)
cp .env.example .env
# Edit .env with your Nebius API key

# Run server
python purple_server.py --host 0.0.0.0 --port 9009
```

## Configuration

All settings via environment variables:

| Variable | Required | Default | Description |
|---|---|---|---|
| `NEBIUS_API_KEY` | Yes | - | Nebius Token Factory API key |
| `NEBIUS_API_BASE` | No | `https://api.tokenfactory.nebius.com/v1` | Custom API base URL |
| `OPENAI_API_KEY` | No | - | OpenAI key (fallback LLM) |

See `.env.example` for the template.

## Docker

```bash
# Build (linux/amd64 required for GitHub Actions runners)
docker build --platform linux/amd64 -t strain-kallfu-s3-pibench .

# Run (pass API key via environment)
docker run -p 9009:9009 \
  -e NEBIUS_API_KEY="$NEBIUS_API_KEY" \
  strain-kallfu-s3-pibench
```

## Endpoints

- `GET /.well-known/agent.json` — Agent Card
- `GET /.well-known/agent-card.json` — Agent Card alias
- `GET /health` — Health check
- `POST /` — A2A message/send handler (JSON-RPC 2.0)

## AgentBeats Quick Submit

1. Go to https://agentbeats.dev/agentbeater/pi-bench/submit
2. Select this agent from the dropdown
3. Add secret: `NEBIUS_API_KEY` = your Nebius key
4. Config JSON: `{}`
5. Submit -> wait for PR merge -> score appears on leaderboard

## Leaderboard

https://agentbeats.dev/agentbeater/pi-bench

## License

MIT
