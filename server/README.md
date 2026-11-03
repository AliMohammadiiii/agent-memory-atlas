# Server boundary

The offline synthetic demo does not start the gateway or require a provider. See the [demo guide](../docs/REVIEWER-DEMO.md) for a reproducible path through the existing ranking, graph and full-text components.

`gateway.py` is the source for an optional retrieval gateway. Real operation requires a separately supplied corpus outside this repository, its configuration, appropriate permissions and provider credentials. The gateway's request-size limits, evidence and privacy checks are exercised by offline tests; those tests do not establish provider behavior or end-to-end deployment privacy. The source is not a deployment recipe, and this public snapshot does not include the private operational configuration or service history.

`fulltext.py` implements scoped SQLite FTS passage retrieval with page references. It does not grant permission to redistribute source texts. Private source passages remain subject to their own rights and must not be included in a public dataset without permission.

If the optional router adapter must create a restricted runtime key, set `ATLAS_ROUTER_PROVIDER` to the exact provider identifier configured in that router. It checks for an active matching connection before creating a restricted key; an existing `ATLAS_NINEROUTER_API_KEY` bypasses key creation. No provider identity is inferred.
