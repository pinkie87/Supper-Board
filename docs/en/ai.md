**English** · [Deutsch](../ki.md)

# AI setup

The AI writes new meal plans, replaces meals you reject, converts pasted recipe text, reads recipes from photos, invents recipes on request and revises saved recipes. Switch it with `LLM_PROVIDER` in `.env`, then restart the service. Recipes and plans are written in the board's language (German or English), always with metric units.

| `LLM_PROVIDER` | What happens | Privacy |
|---|---|---|
| `claude` | Claude via the Anthropic API. Best recipe quality. | When planning, guidelines, ratings, notes, requests, pantry, stock and your recipe titles go to Anthropic. Everything else stays on the server. |
| `ollama` | A local model via [Ollama](https://ollama.com), on the server or your PC. | Nothing leaves your home network. |
| `openai` | OpenAI-compatible API: local (llama.cpp, LM Studio, also with Unsloth models) or in the cloud (Google Gemini, OpenRouter – with a free tier). | Local: nothing leaves your home network. Cloud: as with Claude, see below. |
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

## Ollama (on the server or on your PC)

Ollama can run on the server itself or on another machine in your home network, e.g. your PC with a graphics card. The board calls it over the network.

1. Install Ollama (Linux; Windows and macOS installers are on [ollama.com](https://ollama.com)) and pull models:

   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull qwen3:14b       # text model for plans and recipes
   ollama pull qwen2.5vl:7b    # vision model for photos of recipe pages
   ```

2. Ollama must listen on all network interfaces, not just `localhost`:
   - **Linux:** `sudo systemctl edit ollama`, add `[Service]` and `Environment="OLLAMA_HOST=0.0.0.0"`, then `sudo systemctl restart ollama`.
   - **Windows:** create the environment variable `OLLAMA_HOST` with the value `0.0.0.0` and restart Ollama. Allow incoming connections on port 11434 from your home network in Windows Firewall.

3. In `.env` on the server:

   ```ini
   LLM_PROVIDER=ollama
   # Ollama on the server itself:
   OLLAMA_URL=http://host.containers.internal:11434
   # Ollama on your PC (the PC's IP address):
   # OLLAMA_URL=http://192.168.178.20:11434
   OLLAMA_MODEL=qwen3:14b
   OLLAMA_VISION_MODEL=qwen2.5vl:7b
   ```

   `curl http://192.168.178.20:11434/api/tags` on the server shows whether it can reach the PC. Best give the PC a fixed IP address in your router.

**Which model?** A two-week plan is a long, structured answer. Models from about 14 billion parameters (e.g. `qwen3:14b`, `gemma3:12b`, `mistral-small`) produce usable recipes; smaller models more often invent odd quantities. Without a GPU a plan can take several minutes; the board shows a progress note meanwhile.

## Reading recipes from photos

Under "Recipes → Import from photo" you can upload photos of cookbook pages or handwritten recipes. This needs a **vision model**:

- **Ollama:** `OLLAMA_VISION_MODEL`, e.g. `qwen2.5vl:7b` (good at reading text in photos, needs about 6–8 GB of VRAM), `gemma3:12b` or – if your Ollama version has it – `qwen3-vl:8b`. Without it, `OLLAMA_MODEL` is used, which only works if that model understands images itself (e.g. `gemma3`).
- **OpenAI-compatible server:** `OPENAI_VISION_MODEL` (see below).
- **Claude:** reads photos without further settings.

How the import works:

1. "Read each photo separately" for a book page by page; "All photos belong to one recipe" when a recipe spans several pages.
2. The board shrinks the photos before uploading (longest side 2000 pixels). The server reads them in the background one after another, in upload order – you can close the page meanwhile.
3. Under "Photo import", each recipe found appears with "Review". The form shows the photo for comparison; only "Save" adds the recipe to the database. The photo is deleted afterwards.
4. If the PC running the AI is off, the photo shows "Error". Tap "Try again" or "Retry all failed" later.

Photos stay in `uploads/` in the server's data directory until you save or discard them. Tips: one page per photo, straight from above, good light, no flash. The AI marks unreadable parts with `[?]`.

## Convert text – also without AI

Under "Recipes → Convert text", pasted recipe text becomes a recipe, e.g. the output of a text recognition tool or of an AI in your browser.

- **"Convert"** needs no AI and also works when the PC is off. It detects the title, details such as prep and baking time or servings, the "Ingredients" and "Instructions" sections (including sub-sections such as "Sauce") and the oven temperature. It works best with structured text, e.g. with Markdown headings.
- **"Convert with AI"** (only with an AI set up) also copes with unstructured text and converts dry ingredients given in cups to grams.

Conversion settings (remembered per device):

| Switch | Options |
|---|---|
| Measures in the text | American (pound 454 g, cup 240 ml) or German (pound 500 g, cup 250 ml) |
| Weights | convert to g/kg or keep as is |
| Cups & liquid measures | convert to ml/l or keep as is |
| Spoons | as tbsp/tsp or in ml |

Converted values are rounded to practical numbers: 454 g → 450 g, 355 ml → 350 ml, 1.5 cups (German) → 375 ml, 350 °F → 175 °C. Fahrenheit is always converted to °C, inches to cm.

## Revising recipes with AI

Every saved recipe has "Revise with AI" – handy after a photo import or for older recipes of your own:

- **"Check and correct"** fixes reading and typing errors, makes amounts consistent (metric, rounded), adds ingredients that appear in the steps but are missing from the list, and resolves `[?]` marks when they are clear from context. The dish itself stays the same.
- **"Adapt"** changes the recipe to a request, e.g. "vegetarian", "vegan", "gluten-free" or in your own words ("lentils instead of mince"). The household's dietary guidelines are taken into account.

The result is a **proposal**: the form shows the list of changes at the top and can still be edited. "Apply" replaces the recipe – the previous version is kept. "Save as new recipe" creates a variant and leaves the original unchanged.

### Versions

Every change to a recipe's content (editing, applying an AI proposal) keeps the previous version. "Versions" lists all versions with date and change note; "View" shows an older version, "Restore" makes it the current one again (which is itself a new version, so nothing is lost). The last 30 versions are kept per recipe. Deleting a recipe also deletes its versions.

## OpenAI-compatible server (llama.cpp, LM Studio, vLLM, Unsloth models)

Many local tools offer the same API as OpenAI: `llama-server` from [llama.cpp](https://github.com/ggml-org/llama.cpp), LM Studio or vLLM. This lets you use e.g. the quantised GGUF models from [Unsloth](https://huggingface.co/unsloth). (Many Unsloth GGUF models also run directly in Ollama: `ollama run hf.co/unsloth/<model>-GGUF`.)

Example with `llama-server` on the PC, a vision model with its projector file (`mmproj`):

```bash
llama-server -m Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf --mmproj mmproj-F16.gguf --host 0.0.0.0 --port 8080
```

In `.env`:

```ini
LLM_PROVIDER=openai
OPENAI_URL=http://192.168.178.20:8080/v1
OPENAI_MODEL=local
# Only needed if a different model is loaded for photos (e.g. in LM Studio):
OPENAI_VISION_MODEL=
# Only needed if the server requires a key:
OPENAI_API_KEY=
```

The board asks for JSON following a schema; if a server doesn't support that, it asks again without the schema.

## Google Gemini or OpenRouter (cloud, free tier)

Both offer an OpenAI-compatible API and free models. They run via `LLM_PROVIDER=openai`; the board recognises the provider from the address and shows its name. Your PC doesn't need to be on.

**Google Gemini**

1. Sign in to [Google AI Studio](https://aistudio.google.com/) with a Google account and create an API key.
2. In `.env`:

   ```ini
   LLM_PROVIDER=openai
   OPENAI_URL=https://generativelanguage.googleapis.com/v1beta/openai
   OPENAI_API_KEY=<your key>
   OPENAI_MODEL=gemini-2.5-flash
   ```

   Gemini models also understand photos, so `OPENAI_VISION_MODEL` can stay empty. Current model names are listed in AI Studio.

**OpenRouter**

1. Create an account on [openrouter.ai](https://openrouter.ai/) and create an API key under "Keys".
2. Pick a free model: filter the [model list](https://openrouter.ai/models) for "free" – the names end in `:free`. For the photo import, choose a model with image input ("image").
3. In `.env`:

   ```ini
   LLM_PROVIDER=openai
   OPENAI_URL=https://openrouter.ai/api/v1
   OPENAI_API_KEY=sk-or-...
   OPENAI_MODEL=<provider>/<model>:free
   # If the text model doesn't understand images:
   OPENAI_VISION_MODEL=<provider>/<vision-model>:free
   ```

   Some free models can only be used if the corresponding providers are allowed under "Privacy" in your OpenRouter settings.

**Free tier limits:** there are limits per minute and per day; the providers set them and change them now and then. If the provider reports "too many requests", the photo import pauses and continues automatically (the wait grows up to one hour) – a whole book may take several days this way, but runs without you. "Try again" starts a new attempt right away. The plan draft only needs one request per week.

**Privacy:** with free offers, providers may use the data you send to improve their models. When planning, guidelines, ratings, notes, requests, pantry, stock and recipe titles are sent; for the photo import, the photos. If you don't want that, use Ollama on your own PC.

## When the PC is off

If the AI runs on your PC, it needs to be on at the scheduled times (plan draft `SB_DRAFT_DAY`/`SB_DRAFT_TIME`, shopping list `SB_LIST_DAY`/`SB_LIST_TIME`). If it's off, the board shows "That didn’t work" and – if set up – Home Assistant sends a message. Just tap "Create next plan now" or "Create shopping list now" later. Photos wait with "Error" until you retry them.
