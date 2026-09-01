# Security and data boundary

## Never commit

- API keys, session tokens, Windows Credential Manager exports, or `.env` files;
- licensed or internal research documents without explicit distribution approval;
- raw provider requests or responses that reproduce licensed source text;
- local audit databases, reviewer identities, private comments, or runtime logs;
- `node_modules`, build caches, nested `.git` directories, or generated output trees.

## Credential handling

Credentials must be injected at runtime. The current Windows workflow reads provider secrets from Windows Credential Manager, places them in process-scoped environment variables, and removes those variables after execution. A future cross-platform release may add another secret backend, but plaintext credentials remain forbidden.

## Data tiers

| Tier | GitHub treatment |
|---|---|
| Synthetic examples | Safe for a public repository |
| Contracts, validators, and aggregate metrics | Publish after review |
| Human Gold linked to licensed text | Private by default |
| Full source, raw requests/responses, audit database | Internal artifact storage only |

## License

The public export is licensed under Apache-2.0. This license applies only to files actually distributed in this repository; it does not grant rights to the excluded licensed research source, private provider payloads, human Gold, audit data, or other internal artifacts.

## Incident prevention

The release validator scans the preparation seam for common credential patterns and rejects denylisted source locations. This is a release hygiene check, not a substitute for GitHub secret scanning or organizational review.
