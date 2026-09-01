# Security and data boundary

## Never commit

- API keys, session tokens, Windows Credential Manager exports, or `.env` files;
- licensed or internal research documents without explicit distribution approval;
- source-bearing provider requests or responses, whether licensed or confidential;
- local audit databases, reviewer identities, private comments, or runtime logs;
- `node_modules`, build caches, nested `.git` directories, or generated output trees.

## Credential handling

The public Agent quick start and `extract --dry-run` require no credentials. Online DeepSeek extraction reads `DEEPSEEK_API_KEY` at runtime. Credentials must never be written into repository files, prompts, fixtures, logs, manifests, raw receipts, or committed shell history.

Online extraction requires an explicit `--authorize-external-send` flag. The tool cannot determine whether the operator owns distribution rights; the operator must name and authorize the source, endpoint, model, and any cost ceiling before sending restricted material.

## Data tiers

| Tier | GitHub treatment |
|---|---|
| Synthetic examples | Safe for a public repository |
| Contracts, validators, and aggregate metrics | Publish after review |
| Synthetic public Gold | Safe for a public repository |
| Human Gold linked to licensed text | Private by default |
| Full source, raw requests/responses, audit database | Internal artifact storage only |

## License

The public export is licensed under Apache-2.0. This license applies only to files actually distributed in this repository; it does not grant rights to the excluded licensed research source, private provider payloads, human Gold, audit data, or other internal artifacts.

## Incident prevention

The release validator scans the preparation seam for common credential patterns and rejects denylisted source locations. This is a release hygiene check, not a substitute for GitHub secret scanning or organizational review.
