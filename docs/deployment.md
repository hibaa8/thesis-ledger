# Deployment and MCP clients

## Public market data

Use `https://thesis-ledger.onrender.com/mcp/public/` with Streamable HTTP. This endpoint offers `market_brief` and `latest_price` without a token, OAuth, or a local checkout. The site-wide allowance is 1,000 MCP requests per UTC day. Clients that retain cookies also have a 100-request allowance per visitor.

- **Claude.** Open Customize → Connectors, add a custom web connector, paste the endpoint, and choose **No sign in**. Enable the connector for your conversation. [Claude connector instructions](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- **Cursor.** Merge the following entry into `~/.cursor/mcp.json` or your project’s `.cursor/mcp.json`. Enable the server in Cursor. [Cursor MCP instructions](https://cursor.com/docs/mcp)

```json
{
  "mcpServers": {
    "thesis-ledger-market": {
      "url": "https://thesis-ledger.onrender.com/mcp/public/"
    }
  }
}
```

Try asking your client to fetch the latest available NVDA quote and include the feed and observation time.

## Full toolkit without OAuth

**Hosted owner access.** Cursor and other clients that support custom request headers can use `https://thesis-ledger.onrender.com/mcp/`. Set `Authorization` to `Bearer ${env:LEDGER_API_TOKEN}` in Cursor and make the environment variable available to the Cursor process. The token is the service’s owner credential. Keep it out of shared configs and repositories.

**Local stdio.** With repository access, install uv, run `uv sync` in the checkout, and configure the checkout’s `.env` using `.env.example`. Claude Desktop users can open Settings → Developer → Edit Config. Cursor users can edit `mcp.json`. Merge the entry below and replace both paths with your absolute paths. The client starts the server when needed.

```json
{
  "mcpServers": {
    "thesis-ledger": {
      "command": "/absolute/path/to/uv",
      "args": ["--directory", "/absolute/path/to/thesis-ledger", "run", "thesis-ledger-mcp"]
    }
  }
}
```

Local runs and memories use your local database. A localhost URL is accessible only from the machine running it.

## Host your own private endpoint

Use a Python/container host with persistent disk (for example, an existing VPS or container service). This service cannot run unchanged as a static site or a Cloudflare Worker because SQLite and optional PyTorch execute in Python.

1. Build the Dockerfile.
2. Mount a persistent writable volume at `/data`.
3. Set `LEDGER_API_TOKEN` to a random secret of at least 32 characters.
4. Set `LEDGER_ALLOWED_HOSTS=research.your-domain.example` to your actual hostname. Include `localhost` only if required for internal checks.
5. Configure HTTPS termination and route to port 8000. Preserve the Host header. Allow requests lasting at least 320 seconds and disable buffering for streaming chat.
6. Configure market/model provider variables server-side. For Kronos, use a separate image with its dependencies and model cache; CPU inference can be slow.
7. Run **one worker**. Apply reverse-proxy request limits/rate limits; do not expose a shared paid API without them.

Example container invocation (substitute actual values, keep secrets in your deployment's secret manager):

```sh
docker build -t thesis-ledger .
docker run --env-file .env \
  -e LEDGER_ALLOWED_HOSTS=research.your-domain.example \
  -v thesis-ledger-data:/data -p 127.0.0.1:8000:8000 thesis-ledger
```

Use `https://research.your-domain.example/mcp/` in compatible clients with `Authorization: Bearer YOUR_TOKEN`. For example, set the MCP server entry to `{"url":"https://research.your-domain.example/mcp/","headers":{"Authorization":"Bearer YOUR_TOKEN"}}`. Enter that same token when the browser shows **Unlock Thesis Ledger**. The browser retains it in session storage only. Static assets and `/health` are public. MCP always requires the token when it is configured. The browser workspace can be shared by setting `LEDGER_PUBLIC=1` alongside the token.

The Render Blueprint enables a public browser workspace. A signed browser cookie scopes reports, chat, and thesis memories to that visitor. The bearer token grants access to the owner workspace and MCP. The same browser can reuse its saved theses while the cookie and storage are available.

Visitors can start up to 3 research runs, send 15 chat messages, and generate 20 uncached forecasts per UTC day. Site-wide caps are 30 research runs, 150 messages, and 200 uncached forecasts. Requests to the public API also have a daily cap of 500 per visitor and 5,000 across the site.

## Backups and upgrades

Back up SQLite using its backup API or while the service is stopped; copying only the main database while WAL writes occur can omit data. Preserve `/data` across upgrades. Keep provider keys out of reports, logs, and images.

## Free deployment on Render

For the fastest setup, create a **Blueprint** in Render from this repository and select the branch containing `render.yaml`. It provisions a free Docker web service, generates the owner token, and prompts for OpenAI, Alpha Vantage, and Alpaca credentials. The service’s Environment page provides `LEDGER_API_TOKEN` for owner and MCP access. Render provides the allowed hostname automatically.

To configure the service without a Blueprint:

I use a single Docker web service for the UI, chat API, and HTTP MCP. In Render, create a **Web Service** from this repository, select the **Docker** runtime and **Free** instance type, and set the health check path to `/health`. Set these service variables in the dashboard:

- `LEDGER_ALLOWED_HOSTS` to the service hostname, such as `thesis-ledger.onrender.com`.
- `LEDGER_API_TOKEN` to a random secret of at least 32 characters.
- `OPENAI_KEY` and `ALPHA_VANTAGE` to the provider keys. Set Alpaca credentials or Alpha Vantage real-time entitlement only if available.

Set `LEDGER_PUBLIC=1` to share the browser workspace. Use the service URL plus `/mcp/` for clients that accept custom bearer headers.

SEC EDGAR provides company financials when the Alpha Vantage overview is unavailable. It needs no API key. Set `LEDGER_SEC_USER_AGENT` to a project name and contact email to identify requests for your deployment.

The standard Docker image includes chat, prices, MCP, and bootstrap scenarios. The Forecast tab shows historical-return scenarios from completed daily market bars.

Render's free service sleeps when idle and loses local SQLite data across restarts or redeploys. To keep reports, memory, and daily quota counters across restarts on Render, attach a persistent disk at `/data` on a paid web service. A local Docker volume at the same path also preserves the SQLite files. Model calls and provider data plans are billed separately from hosting. See [Render free service limits](https://render.com/docs/free).

## ChatGPT connection

If your workspace allows adding custom MCP servers, use **Plugins → Add custom MCP server** with the public HTTPS endpoint ending in `/mcp/public/` and the option for no authentication. Use the public endpoint for the market tools. The full hosted toolkit uses a static owner bearer token, so use a client that can set that header. [Official OpenAI documentation](https://developers.openai.com/plugins/build/auth#triggering-authentication-ui)
