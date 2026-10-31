---json
{
  "id": "VFX-spec-001",
  "kind": "vfx-spec",
  "domain": "vfx",
  "schema_version": 2,
  "status": "draft",
  "title": "Effect title",
  "upstream": [],
  "sources": [],
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
    "purpose": "TBD: effect purpose",
    "triggers": [
      "TBD: event id"
    ],
    "duration_seconds": 1,
    "phases": [
      {
        "name": "active",
        "duration_seconds": 1
      }
    ],
    "curves": [
      {
        "property": "intensity",
        "keyframes": [
          {
            "time": 0,
            "value": 0
          },
          {
            "time": 1,
            "value": 1
          }
        ]
      }
    ],
    "particle_systems": [
      {
        "id": "main",
        "max_particles": 0,
        "lifetime_seconds": 1,
        "spawn_per_second": 0
      }
    ],
    "materials": [],
    "platforms": {
      "default": {
        "budget": {
          "max_particles": 0,
          "max_overdraw": 1,
          "max_draw_calls": 0,
          "max_ms": 1
        },
        "constraints": []
      }
    },
    "platform_constraints": [],
    "dependencies": []
  }
}
---
