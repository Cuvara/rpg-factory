---
type: llm
weight: 2
---

Keeps inventory as a VContainer service (server-authoritative InventoryService), not ECS; View/ViewModel/Presenter split with BindableViewModel and one-way SetBinding; uses a com.cuvara.uitoolkit list adapter with virtualization (or justifies hand-rolling); navigation through IScreenNavigator with a Scoped presenter; subscriptions disposed via ScreenSubscriptions; regenerates and commits the .uxml.g.cs; plain NUnit presenter tests plus a PlayMode binding test; no per-frame UI work.
