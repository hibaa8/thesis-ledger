# Deployment and MCP clients

The delivered default is local-only. A localhost MCP URL cannot be used by someone on another computer or by a cloud-hosted client.

## Local clients

Claude Desktop and Cursor can run `thesis-ledger-mcp` over stdio using the configuration in the README. Desktop app environment variables are separate from your terminal. Include the necessary provider variables in the client's MCP environment configuration, or launch the client from a shell with them set. Never commit credentials.

For a client that supports Streamable HTTP and configurable headers:

```json
{
  "mcpServers": {
    "thesis-ledger": {
      "url": "http://127.0.0.1:8000/mcp/"
    }
  }
}
```

The trailing slash is intentional. This endpoint is MCP, not an OpenAI plugin manifest. The stdio setup is the portable path for Claude Desktop. Remote Claude connectors may require OAuth; this prototype implements a bearer token, not a full OAuth authorization server.

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

For the existing token-protected deployment, a client such as Cursor can send the configured bearer header. ChatGPT's custom MCP connection uses OAuth for authenticated servers. Before connecting the full Thesis Ledger toolkit, configure OAuth 2.1 for the MCP endpoint. Keep the token-protected tools private until then.

With an eligible workspace and permission to add custom MCP servers, open **Plugins → Add custom MCP server** in ChatGPT on the web. Use the hosted HTTPS URL ending in `/mcp/` or a Secure MCP Tunnel, select OAuth, and install the connection. Start a chat, type `@`, select the plugin, and ask for a market brief. See [ChatGPT connection steps](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt) and [MCP authentication](https://developers.openai.com/plugins/build/auth).
