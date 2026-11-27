---json
{
  "id": "VFX-spec-001",
  "kind": "vfx-spec",
  "domain": "vfx",
  "schema_version": 2,
  "status": "approved",
  "title": "Fire bolt",
  "upstream": [],
  "sources": [
    "AGEN-fire-bolt-glow-001"
  ],
  "authors": [
    {
      "kind": "agent",
      "id": "author"
    }
  ],
  "acceptance": [
    {
      "id": "AC-1",
      "text": "Effect matches approved intent",
      "verify": "review"
    }
  ],
  "trace": [],
  "spec": {
    "purpose": "Fire bolt projectile",
    "duration_seconds": 1.0,
    "phases": [
      {
        "name": "anticipation",
        "duration_seconds": 0.1
      },
      {
        "name": "impact",
        "duration_seconds": 0.3
      },
      {
        "name": "dissipation",
        "duration_seconds": 0.6
      }
    ]
  }
}
---
