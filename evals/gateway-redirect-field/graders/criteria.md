---
type: llm
weight: 2
---

A successful response, without editing files:
- Identifies the gateway module (backend/gateway) and that the redirect message is a wire
  contract defined in backend/shared/proto/wire.proto, so Go and C# bindings are regenerated
  with backend/shared/proto/generate.sh and committed together.
- Names fast checks for the gateway (go vet, go test -race, go build) and for other affected
  modules, and says the cross-language integration suite (go test -tags integration in
  backend/integration_test) is required or must be asked about - not silently skipped.
- Mentions obligations: CHANGELOG under [Unreleased] for touched modules, and docs
  (for example gameserver-dotnet docs/API.md or gateway docs).
- Does not claim anything was tested.
