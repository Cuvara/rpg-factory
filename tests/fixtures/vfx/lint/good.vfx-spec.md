---json
{
  "id": "VFX-spec-fire-burst",
  "kind": "vfx-spec",
  "domain": "vfx",
  "schema_version": 2,
  "status": "approved",
  "title": "Fire burst",
  "upstream": [
    "VFX-style-001"
  ],
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
    "purpose": "Fixture fire burst: a short hit flash that cools to smoke.",
    "triggers": [
      "skill.fire_burst.hit"
    ],
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
            "time": 0.2,
            "value": 1
          },
          {
            "time": 1,
            "value": 0
          }
        ]
      }
    ],
    "particle_systems": [
      {
        "id": "main",
        "max_particles": 256,
        "lifetime_seconds": 0.9,
        "spawn_per_second": 0
      }
    ],
    "materials": [],
    "platforms": {
      "android": {
        "budget": {
          "max_particles": 2000,
          "max_overdraw": 2,
          "max_draw_calls": 2,
          "max_ms": 0.5
        },
        "constraints": []
      }
    },
    "platform_constraints": [],
    "dependencies": []
  }
}
---

# Fire burst

Lint fixture vfx-spec of the fire-burst effect.
