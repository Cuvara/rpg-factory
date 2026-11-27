---json
{
  "id": "VFX-asset-001",
  "kind": "vfx-asset",
  "domain": "vfx",
  "schema_version": 2,
  "status": "draft",
  "source_uri": "TBD",
  "license": "TBD",
  "provenance": "authored",
  "delivery": {
    "repo": "client",
    "path": "Assets/VFX/TBD.prefab"
  },
  "authors": [
    {
      "kind": "agent",
      "id": "author"
    }
  ],
  "sources": [],
  "spec": {
    "engine": "Unity",
    "asset_path": "Assets/VFX/TBD.prefab",
    "hash": "0000000000000000000000000000000000000000",
    "stats": {
      "default": {
        "particles": 0,
        "overdraw": 0,
        "draw_calls": 0,
        "ms": 0
      }
    },
    "checks": [],
    "capture": {
      "stats_hash": "0000000000000000000000000000000000000000000000000000000000000000",
      "seed": 0,
      "alive_peak": 0,
      "contact_sheet_hash": "0000000000000000000000000000000000000000000000000000000000000000"
    },
    "textures": [
      {
        "gen_run_id": "AGEN-TBD",
        "output_hash": "0000000000000000000000000000000000000000000000000000000000000000",
        "transform": "luminance_to_alpha",
        "game_texture_hash": "0000000000000000000000000000000000000000000000000000000000000000"
      }
    ]
  },
  "source_rev": "TBD"
}
---

## Style and lint evidence

TBD: add `spec.style` and `spec.lint` after the capture exists. Run `scripts/vfx/vfx_style.py lint` against the
approved vfx-style profile with the recipe, inspect result and `--stats`, then record
`spec.style` = `{"profile_id": "<vfx-style id>", "blob_revision": "<40-hex git blob id of the profile>"}` and
`spec.lint` = `{"state": "PASS|WARN|FAIL", "report_hash": "<SHA-256 of the lint result JSON>"}`. The template leaves
both out on purpose: a placeholder blob revision is a FAIL of `vfx-asset-style-lint`, an absent record is a WARN while
the asset is a draft.
