# Google Cloud Run deployment: Python YouTube Gemini MCP

A step-by-step setup that does **not** use Colab or a separate VPS.
The public HTTPS endpoint runs the existing FastAPI app. Gemini API credentials are kept in Google Cloud, not in GitHub.

## Prerequisites

- Google Cloud project with billing enabled and permission to create a Cloud Run service / Cloud Build trigger.
- Google account with access to [Google AI Studio API keys](https://aistudio.google.com/api-keys).
- This repository, `Hazernit/youtube-gemini-mcp`, on branch `main` after the Cloud Run deployment changes are merged.
- The ability to create custom MCP plugins in your ChatGPT workspace (check this before incurring cloud costs).

> Billing: Cloud Run has a free usage allowance, but cloud resources and Gemini API calls can incur charges. Billing budgets only **alert**, they do not hard-cap costs. Consider additional provider quotas and monitor activity.

## 1. Deploy from GitHub (Google Cloud UI, no local terminal)

1. Open [Cloud Run](https://console.cloud.google.com/run) and select/create a Google Cloud project.
2. If asked, link a billing account and enable the required Cloud Run / Cloud Build / Artifact Registry APIs.
3. Click **Connect repository** (sometimes under **Services**).
4. Choose **Cloud Build → GitHub**, authorize access to `Hazernit/youtube-gemini-mcp`, preferably limiting GitHub access to this repository.
5. In Build Configuration choose:
   - Repository: `Hazernit/youtube-gemini-mcp`
   - Branch pattern: `^main$`
   - Build Type: **Dockerfile**
   - Dockerfile location: `/Dockerfile` (root of repository; use `Dockerfile` if field expects a relative path).
6. Configure the service:
   - Service name: `youtube-gemini-mcp`
   - Region: `europe-west3` (Frankfurt), if available and permitted
   - **Allow public access** (ChatGPT needs the HTTPS endpoint; our MCP route itself still requires the secret URL token)
   - Container port: `8080`
   - Minimum instances: `0`, maximum instances: `1`
   - CPU: `1`, memory: `512 MiB`
   - Request timeout: `300 seconds`
7. Under **Container(s) → Variables & Secrets**, configure the secrets below. Then click **Create**. Cloud Run will build and deploy the Dockerfile.

## 2. Configure secrets safely

For `GEMINI_API_KEY` and `MCP_SECRET_PATH`, use Google Cloud **Secret Manager** and reference secret versions from Cloud Run. Alternatively, entering these as environment variables works for testing, but is less secure. **Never put secret values in GitHub, source code, screenshots or chat.**

| Variable | Example / description |
| --- | --- |
| `GEMINI_API_KEY` | Your own Google AI Studio key (secret) |
| `MCP_SECRET_PATH` | Random token, **at least 32 characters** (secret) |
| `GEMINI_MODEL` | `gemini-3.8-flash` |
| `MAX_CALLS_PER_DAY` | `10` for initial testing |
| `GEMINI_MAX_OUTPUT_TOKENS` | `4096` |

Generate a random MCP secret **in your own Cloud Shell or computer**, rather than sharing it with ChatGPT:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Keep `MCP_SECRET_PATH` unchanged between deployments; otherwise the MCP URL in ChatGPT must be updated. When using Secret Manager, grant the Cloud Run **runtime service account** access to the secrets.

**Important:** This MVP uses a high-entropy path token. It is *not* OAuth. Protect your Cloud Run request logs (they may contain the URL path), rotate the token if leaked, and never publish the full MCP URL.

`MAX_CALLS_PER_DAY` is a process-local limiter and resets if the container restarts. Do not treat it as a spending limit.

## 3. Validate the live endpoint

After the service becomes ready, Cloud Run displays a stable public HTTPS base URL similar to `https://youtube-gemini-mcp-xxxxx-ew.a.run.app`.

Open **`https://YOUR-CLOUD-RUN-DOMAIN/health`**; it should return:

```json
{"status":"ok"}
```

Your *private* MCP connection URL is:

```text
https://YOUR-CLOUD-RUN-DOMAIN/YOUR-MCP-SECRET-PATH/mcp
```

The `/health` endpoint being reachable proves only that FastAPI is running. It does not prove Gemini API calls work.

To validate MCP protocol from a local shell, set `MCP_URL` privately and call:

```bash
curl --silent --show-error --request POST "$MCP_URL" \
  --header "Content-Type: application/json" \
  --header "Accept: application/json, text/event-stream" \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"smoke-test","version":"1.0"}}}'
```

A JSON response with `serverInfo.name` and `protocolVersion` confirms basic MCP handshake. The `youtube_mcp_status` tool can then verify that the Gemini key was configured; one short public video should be used for a real end-to-end test.

## 4. Install the MCP plugin into ChatGPT

1. In ChatGPT web, open **Plugins → + → Add custom MCP server**.
2. Name: **YouTube Gemini**.
3. Connection URL: the **entire private URL** ending in `/<MCP_SECRET_PATH>/mcp`.
4. Authentication: **No authentication** (the *path token* gates this personal MVP).
5. Read the security warning and choose **Create as a plugin**.
6. Find the resulting plugin and **Install** it.
7. In a new ChatGPT conversation, invoke the plugin with `@` and request a video analysis. The OpenAI plugin quickstart currently describes a **Work** conversation as the supported invocation surface; availability can depend on workspace and plan.

Recommended test prompt: `Use YouTube Gemini to describe what is visible and audible in this public YouTube video: <video-url>. Separate observations from claims.`

## 5. Debugging

| Symptom | Check |
| --- | --- |
| /health returns 404 | Wrong Cloud Run URL or deployment not ready |
| /health works, MCP returns 404 | Wrong secret path or missing `MCP_SECRET_PATH` |
| MCP returns 503 | Secret path env/secret not configured properly |
| Tool reports Gemini API not configured | Missing `GEMINI_API_KEY` |
| Tool reports 403/404 Gemini | API key permissions, Gemini model, region support |
| Video tool times out | Try `quick` or shorter video, inspect Cloud Run logs and processing time |
| Can't find custom MCP plugin UI | ChatGPT account/workspace permission limitation |
| Cost unexpectedly increases | Inspect Cloud Run/Gemini usage and billing, disable service if necessary |

### Security and limits

- Only **public** YouTube videos are supported. Preview features, per-day quotas and charges can change.
- Video analysis can miss frames or mishear audio; independently verify factual claims using reliable sources.
- Keep min instances=0 and monitor both Cloud Run and Gemini API expenses.
- Production authentication should use OAuth 2.1 or another supported secure approach rather than a URL token.

## References

- [Cloud Run continuous deployment from GitHub](https://docs.cloud.google.com/run/docs/continuous-deployment)
- [Cloud Run Secret Manager setup](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Google Gemini video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)
- [ChatGPT custom MCP setup](https://developers.openai.com/api/docs/guides/custom-mcp-server)
