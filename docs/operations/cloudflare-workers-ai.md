# Cloudflare Workers AI setup

Cloudflare is a provider family — text, pictures through FLUX.2 Klein and a voice through Aura — and
the image benchmark calls it too. Both use the Workers AI REST API directly, so neither needs a
deployed Worker, Worker ID, domain, zone ID, or global API key.

**For the server**, create the token below and add **Cloudflare** in Settings ▸ Providers with it and
the account id. Saving checks the token with a call that spends nothing.

The rest of this page is the same credential set up for a terminal session, which is what the
benchmark reads; the live model tests read it from `providers.local.json`.

## Create credentials

1. Open the [Workers AI dashboard](https://dash.cloudflare.com/?to=/:account/ai/workers-ai).
2. Select **Use REST API**.
3. Select **Create a Workers AI API Token** and use the prefilled template.
4. Create the token and copy it immediately; Cloudflare displays the secret
   only once.
5. Copy **Account ID** from the same page. It is also available through the
   dashboard command palette: press `Cmd+K` and select **Copy account ID**.

For a custom token, scope it to the intended account and grant Workers AI
access. Do not use the global API key, an AI Gateway token, or a Workers
Scripts token.

Official references:

- [Workers AI REST setup](https://developers.cloudflare.com/workers-ai/get-started/rest-api/)
- [Finding an account ID](https://developers.cloudflare.com/fundamentals/account/find-account-and-zone-ids/)
- [Creating and verifying API tokens](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)

## Configure one terminal session

This zsh form keeps the token itself out of shell history:

```bash
export CLOUDFLARE_ACCOUNT_ID="paste-account-id-here"
read -s "CLOUDFLARE_API_TOKEN?Cloudflare Workers AI token: "
export CLOUDFLARE_API_TOKEN
echo
```

Verify the token without generating an image:

```bash
curl --silent \
  "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  | uv run python -m json.tool
```

The response should contain `"success": true` and `"status": "active"`.
This verifies the token itself, but not its account scope or Workers AI
permission.

Alternatively, put the two values in the repository's ignored `.env` file and
add `--env-file .env` to the outer `uv run` command. Never commit or paste the
token into logs, issues, or chat.

## Run the smoke benchmark

```bash
uv run python -m experiments.image_benchmark.benchmark_image_models resume \
  --stage smoke \
  --models cloudflare_flux2_klein \
  --execute-remote \
  --max-cost-usd 0.01
```

With an ignored `.env` file:

```bash
uv run --env-file .env python -m experiments.image_benchmark.benchmark_image_models resume \
  --stage smoke \
  --models cloudflare_flux2_klein \
  --execute-remote \
  --max-cost-usd 0.01
```

The six-image configured projection is approximately `$0.001722`. The CLI
ceiling authorizes the benchmark invocation; it is not an account-level
spending cap.

## Troubleshooting

- `401` or `403`: token permission, account scope, or account ID problem.
- `400` mentioning required property `multipart`: the client sent JSON.
  Cloudflare FLUX.2 Klein requires `multipart/form-data`, even for text-only
  prompts. The tracked benchmark runner uses multipart.
- Token verification succeeds but inference fails: verification proves only
  that the token is active. Confirm that it was created from the Workers AI
  template for the same account ID.
- The benchmark runner includes up to 2,000 characters of Cloudflare's error
  response in `runner-result.json`, so provider error codes are retained.

Cloudflare documents the model's multipart contract and fixed four-step
inference in its
[FLUX.2 Klein launch note](https://developers.cloudflare.com/changelog/post/2026-01-15-flux-2-klein-4b-workers-ai/).
