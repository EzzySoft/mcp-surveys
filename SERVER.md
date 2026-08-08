# Server deployment

This checkout is the production-wide `mcp-surveys` installation used by Hermes and other projects.

## Runtime

- Public URL: `https://mcp.voevoda-sailing.ru`
- Loopback upstream: `127.0.0.1:18173`
- Compose project: `mcp-surveys`
- Compose files: `compose.yaml` + `compose.server.yaml`
- Caddy route: `/etc/caddy/Caddyfile`
- Redis is ephemeral by design; survey TTLs are configured in `.env`.

## Lifecycle

Run from this directory:

```bash
docker compose -p mcp-surveys -f compose.yaml -f compose.server.yaml up -d --build --wait --wait-timeout 180
docker compose -p mcp-surveys -f compose.yaml -f compose.server.yaml ps
docker compose -p mcp-surveys -f compose.yaml -f compose.server.yaml logs --no-color --tail 100
docker compose -p mcp-surveys -f compose.yaml -f compose.server.yaml down
```

Before updating, review upstream changes. Tests run on the GitHub Actions runner before the SSH deployment. For a manual deployment, use a fast-forward-only pull, rebuild, and verify both health endpoints:

```bash
git fetch origin main
git diff HEAD..origin/main -- README.md pyproject.toml Dockerfile compose.yaml src/ packages/ skills/
git pull --ff-only
docker compose -p mcp-surveys -f compose.yaml -f compose.server.yaml up -d --no-recreate --wait --wait-timeout 60 redis
docker compose -p mcp-surveys -f compose.yaml -f compose.server.yaml up -d --build --no-deps --wait --wait-timeout 180 app
curl --noproxy '*' -fsS http://127.0.0.1:18173/health
curl --noproxy '*' -fsS https://mcp.voevoda-sailing.ru/health
uv tool upgrade mcp-surveys-cli
```

## Hermes integration

The current upstream release is CLI-first. The removed `/mcp` endpoint intentionally returns HTTP 426, so do **not** add it under `mcp_servers` in Hermes. Use the globally installed `mcp-surveys-cli` and the profile skill `mcp-surveys-cli` instead.

Secure protocol v2 is the default and requires CLI `>= 0.5.1`. Share only `public_url`; never share receipt or token files. Receipts live under `~/.config/mcp-surveys/receipts/`, contain the local decryption material and result token, and are required to decrypt answers.
