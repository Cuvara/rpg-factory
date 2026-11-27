---json
{
  "id": "VFX-style-001",
  "kind": "vfx-style",
  "domain": "vfx",
  "schema_version": 2,
  "status": "draft",
  "title": "Project VFX style profile",
  "binding_values": true,
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
      "text": "Palette, HDR bands, timing ratios, texture conventions, outputs and budgets match the approved art direction",
      "verify": "review"
    },
    {
      "id": "AC-2",
      "text": "Every effect of the project lints against this profile with vfx-lint",
      "verify": "test"
    }
  ],
  "trace": [],
  "spec": {
    "purpose": "TBD: the game, its art direction and the effects this profile covers",
    "assetgen_style": "realistic-pbr",
    "vfx_graph": "17.6",
    "palette": {
      "hue_tolerance_degrees": 15,
      "elements": {
        "fire": {
          "colors": {
            "core": "#FFE2A8",
            "body": "#FF8A2A",
            "edge": "#C8321E"
          },
          "ramp": [
            "core",
            "body",
            "edge"
          ]
        }
      }
    },
    "hdr_intensity": {
      "primary": {
        "min": 1.0,
        "max": 4.0
      },
      "secondary": {
        "min": 0.5,
        "max": 2.5
      },
      "ambient": {
        "min": 0.0,
        "max": 1.0
      }
    },
    "timing": {
      "anticipation": {
        "min": 0.0,
        "max": 0.25
      },
      "impact": {
        "min": 0.1,
        "max": 0.4
      },
      "dissipation": {
        "min": 0.35,
        "max": 0.8
      },
      "sum_tolerance_seconds": 0.05
    },
    "textures": {
      "max_size": 512,
      "flipbook_grids": [
        "4x4",
        "8x8"
      ],
      "channel_packing": {},
      "color_space": "srgb",
      "linear_textures": []
    },
    "outputs": {
      "types": [
        "VFXPlanarPrimitiveOutput"
      ],
      "blend_modes": [
        "Additive",
        "AlphaPremultiplied"
      ],
      "shaders": [
        "Hidden/VFX/*"
      ]
    },
    "budgets": {
      "android": {
        "max_alive_particles": 2000,
        "max_systems": 4,
        "max_texture_memory_bytes": 4194304
      }
    },
    "capture": {
      "camera": "gameplay",
      "lighting": "dusk",
      "seed": 1234
    },
    "notes": []
  }
}
---
