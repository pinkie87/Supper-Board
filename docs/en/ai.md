**English** · [Deutsch](../ki.md)

# AI setup

The AI writes new meal plans, replaces meals you reject, converts pasted recipe text and invents recipes on request. Switch it with `LLM_PROVIDER` in `.env`, then restart the service. Recipes and plans are written in German with metric units.

| `LLM_PROVIDER` | What happens | Privacy |
|---|---|---|
| `claude` | Claude via the Anthropic API. Best recipe quality. | When planning, guidelines, ratings, notes, requests, pantry, freezer and your recipe titles go to Anthropic. Everything else stays on the server. |
| `ollama` | A local model via [Ollama](https://ollama.com). | Nothing leaves your home network. |
| `none` | No AI. Plans are built from the recipe database (best-rated first, with variety). | Nothing leaves the server. |

Without AI everything else keeps working: adding recipes by form or link, plans from the database, shopping list, reminders.

## Claude

1. Create an account at <https://console.anthropic.com/>, add credit and create an API key.
2. In `.env`:

   ```ini
   LLM_PROVIDER=claude
   ANTHROPIC_API_KEY=sk-ant-...
   CLAUDE_MODEL=claude-opus-5-5
   CLAUDE_EFFORT=medium
   ```

- `CLAUDE_MODEL`: the default is Claude Opus 5.5. `claude-sonnet-5-5` is cheaper.
- `CLAUDE_EFFORT`: how thoroughly the model reasons (`low`, `medium`, `high`). `medium` works well for meal plans.
- If the model declines a request, a substitute model takes over automatically (server-side fallback in the Anthropic API).

Cost: a two-week plan with all recipes costs roughly 10–50 cents with Opus, a single recipe about 1–5 cents. Current prices are on the Anthropic website.

## Ollama

1. Install Ollama on the server (or on a machine on your network with a GPU):

   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull qwen3:14b
   ```

2. So the container can reach Ollama, it must listen on all interfaces:

   ```bash
   sudo systemctl edit ollama
   # add:
   # [Service]
   # Environment="OLLAMA_HOST=0.0.0.0"
   sudo systemctl restart ollama
   ```

3. In `.env`:

   ```ini
   LLM_PROVIDER=ollama
   OLLAMA_URL=http://host.containers.internal:11434
   OLLAMA_MODEL=qwen3:14b
   ```

**Which model?** A two-week plan is a long, structured answer. Models from about 14 billion parameters (e.g. `qwen3:14b`, `gemma3:27b`, `mistral-small`) produce usable German recipes; smaller models more often invent odd quantities. Without a GPU a plan can take several minutes; the board shows a progress note meanwhile.
