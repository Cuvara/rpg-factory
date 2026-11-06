---json
{
  "id": "AGEN-example-icon-001",
  "kind": "gen-run",
  "domain": "assetgen",
  "schema_version": 2,
  "status": "draft",
  "title": "icon / flat-ui generation run example-icon-001",
  "upstream": [],
  "sources": [],
  "authors": [
    {
      "kind": "agent",
      "id": "claude"
    }
  ],
  "acceptance": [
    {
      "id": "AC-1",
      "text": "The prompt was reviewed by a model other than its author.",
      "verify": "review",
      "evidence": "review-prompt.json"
    },
    {
      "id": "AC-2",
      "text": "Deterministic image QA passes for every output.",
      "verify": "test",
      "evidence": "qa.json"
    },
    {
      "id": "AC-3",
      "text": "The images were reviewed against the purpose rubric.",
      "verify": "review",
      "evidence": "review-image.json"
    }
  ],
  "trace": [],
  "provenance": {
    "generated_by": "claude",
    "tool": "comfyui",
    "model": ""
  },
  "spec": {
    "run_id": "example-icon-001",
    "purpose": {
      "id": "icon",
      "layer": "core",
      "files": [
        "core:templates/assetgen/purposes/icon.json"
      ],
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
    },
    "style": {
      "id": "flat-ui",
      "layer": "core",
      "files": [
        "core:templates/assetgen/styles/flat-ui.json"
      ],
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
    },
    "template": {
      "id": "image-generate",
      "layer": "core",
      "files": [
        "core:templates/assetgen/workflows/image-generate.json"
      ],
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
    },
    "handoff_domain": "art2d",
    "params": {},
    "prompt": "TBD: the final prompt, written from the purpose guidance and reviewed verbatim.",
    "prompt_sha256": "8ea47e87d871d690c3a4b34ac5fcf6bbf9b2c8bf49cab32a4fb42f1152a9a7a1",
    "prompt_author": "claude",
    "prompt_review": {
      "by": null,
      "state": "NOT_RUN",
      "findings": 0
    },
    "generation": {
      "generated_by": "claude",
      "tool": "comfyui",
      "model": null,
      "workflow": null
    },
    "outputs": [],
    "qa": {
      "state": "NOT_RUN",
      "results": []
    },
    "image_review": {
      "by": null,
      "state": "NOT_RUN",
      "findings": 0
    }
  }
}
---
# icon / flat-ui generation run example-icon-001

Kind template, not a run: `python3 -B scripts/assetgen/assetgen.py manifest --run <authoring>/assetgen/runs/<run_id>`
writes the real record (status `proposed`) with the content hashes of the resolved purpose, style and template, the
model from `workflow.json`, the review verdicts, the QA results and the sha256 of every `outputs/*.png`. Do not
hand-edit a generated record; fix the run and re-run `manifest`.

- Reviews: `review-prompt.json` and `review-image.json` hold `{"state", "findings", "by"}`; `by` names the reviewing
  model and must differ from `prompt_author`. When the independent reviewer is unavailable, a same-model review is
  recorded explicitly as `"by": "SAME_MODEL:<model>"` (quality WARN, never a silent PASS).
- Status: approval is human-only (gate `assetgen-approval`); only an approved run hands its images to 2D Art, 3D
  Art, UI/UX or VFX (`assetgen-to-<domain>`).

## Prompt

TBD: the final prompt, written from the purpose guidance and reviewed verbatim.

## Outputs

(none)
