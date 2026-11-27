# Image gateway batch probe (n greater than 1)

Date: 2026-11-12. Status: observed (one call).

## Question

Does the image gateway return more than one image when `n` is greater than 1, and which sizes does it return? The
`NineRouterImage` node fixes `n` at 1 and keeps only the first image, so a node-level `n` input is only worth adding
if the gateway honours `n`.

## Approval and budget

The user explicitly approved exactly one low-quality call in this task (budget: at most 2 generations). Used: 1 call,
1 image. No further generation was made.

## Method

One POST to the gateway's `/images/generations` endpoint, using the request code copied from
`templates/assetgen/comfy-node/comfyui_9router/__init__.py` (`_provider`, `_post`) and run outside ComfyUI.
Credentials were read at run time from the Codex provider config, as the node does; nothing was printed or stored.

Request body:

| Field | Value |
| --- | --- |
| `model` | `cx/gpt-5.6-sol-image` |
| `size` | `1024x1024` |
| `quality` | `low` |
| `background` | `auto` |
| `n` | `2` |
| `prompt` | a trivial prompt |

## Observed

- Response top-level keys: `created` and `data` only.
- `data` held 1 item, not 2.
- The item carried a `b64_json` payload (no `url`).
- The decoded PNG was 1254x1254 px (about 1.0 MB), not the requested 1024x1024.
- No `size`, `quality` or `usage` field was echoed back.

## Conclusion

- Decision: the gateway ignored `n` greater than 1 (observed once, model `cx/gpt-5.6-sol-image`: `n=2` returned one
  image), so the optional node `n` parameter is dropped and is not added to the backlog.
- Batch variants are separate calls (separate seeds or prompts).
- Image QA reads the real returned size from the file, never the requested one (the probe returned 1254x1254 for a
  1024x1024 request).

## Limitations

One model, one size, one call. The edits endpoint (`/images/edits`) was not probed. A different model or quality may
behave differently.
