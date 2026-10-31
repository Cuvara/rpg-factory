---json
{
  "id": "UI-componen-004",
  "kind": "component-spec",
  "domain": "ui",
  "status": "draft",
  "title": "component-spec draft",
  "schema_version": 2,
  "sources": [],
  "authors": [
    {
      "kind": "agent",
      "id": "ui-ux"
    }
  ],
  "upstream": [],
  "acceptance": [],
  "trace": [],
  "spec": {
    "component_id": "status-panel",
    "variants": [
      {
        "name": "default",
        "description": "Standard status panel presentation."
      }
    ],
    "props": [
      {
        "name": "statusText",
        "type": "string",
        "description": "Status text supplied by a declared source artifact."
      }
    ],
    "states": [
      {
        "name": "default",
        "description": "Panel is visible and ready for input."
      }
    ],
    "tokens": [
      "color.surface"
    ],
    "accessibility": {
      "label": "Player status",
      "focus_order": "after header",
      "contrast_target": "WCAG 2.2 AA",
      "input_methods": [
        "keyboard"
      ]
    }
  }
}
---
