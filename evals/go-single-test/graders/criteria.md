---
type: llm
weight: 2
---

Routes to server-services first, then loads go-backend; gives the per-module command (cd into the module, no go.work; go test ./<pkg> -run '^Name$' -race -count=1 -v); explains that integration tests need -tags integration and that TestDotnetInterop*/selfreg/sealed tests t.Skip without dotnet on PATH while go test still prints ok, so --- SKIP lines must be read and such a run is NOT_RUN, not PASS; claims nothing ran.
