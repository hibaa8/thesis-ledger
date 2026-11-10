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

1. Build the supplied Dockerfile.
2. Mount a persistent writable volume at `/data`.
3. Set `LEDGER_API_TOKEN` to a random secret of at least 32 characters.
4. Set `LEDGER_ALLOWED_HOSTS=research.your-domain.example` to your actual hostname. Include `localhost` only if required for internal checks.
5. Configure HTTPS termination and route to port 8000. Preserve the Host header. Allow requests lasting at least 240 seconds.
6. Configure market/model provider variables server-side. For Kronos, use a separate image with its dependencies and model cache; CPU inference can be slow.
7. Run **one worker**. Apply reverse-proxy request limits/rate limits; do not expose a shared paid API without them.

Example container invocation (substitute actual values, keep secrets in your deployment's secret manager):

```sh
docker build -t thesis-ledger .
docker run --env-file .env \
  -e LEDGER_ALLOWED_HOSTS=research.your-domain.example \
  -v thesis-ledger-data:/data -p 127.0.0.1:8000:8000 thesis-ledger
```

Use `https://research.your-domain.example/mcp/` in compatible clients with `Authorization: Bearer YOUR_TOKEN`. Enter that same token using **Access token** in the browser UI. The browser retains it in session storage only. Static assets and `/health` are public; research routes and MCP require the token.

This is a **single-user trust boundary**. Anyone with the token can read all research, create paid runs, and review memories. Before offering a public multi-user product, add user accounts, OAuth-compatible MCP authorization, tenant-isolated databases, quotas, a durable queue, audit retention, and an explicit data-provider redistribution policy. Do not market this shared-token prototype as a multi-tenant service.

## Backups and upgrades

Back up SQLite using its backup API or while the service is stopped; copying only the main database while WAL writes occur can omit data. Preserve `/data` across upgrades. Keep provider keys out of reports, logs, and images.
