---
type: llm
weight: 2
---

Routes through `factory-core` to `server-services` (Go gateway) and treats the request as not a UI request: invokes no `ui-*` skill and runs no UI plan beyond, at most, a NOT_UI classification. Names the gateway TLS configuration files and the Go test command for the gateway module, mentions the transport-security human gate if the routing lists it, and does not claim any check ran.
