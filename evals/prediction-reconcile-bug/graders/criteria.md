---
type: llm
weight: 2
---

Points at LocalMovePredictor reconcile (replay through the shared MovementSystem.TryMove), LocalPredictionSystem reconciling once per merged snapshot with clock steering, ack_applied_tick, and the frame-bound KCP pump as a confound; proposes a headless or EditMode reproduction (PredictionHarness / Reconcile*Tests) before a fix; keeps prediction main-thread and single-entity; does not change the server or wire without wire-contract; claims nothing ran.
