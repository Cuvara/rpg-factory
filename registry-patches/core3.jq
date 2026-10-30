 .contracts |= map(select(.id != "design-event-to-vfx" and .id != "asset-3d-to-vfx" and .id != "asset-3d-to-impl"))
 | .contracts |= map(if .id == "ui-vfx-sync" then
      .domain = "ui"
      | .summary = "UI cue timing and VFX effect timing stay synchronized through stable artifact references."
      | .source = {"repo":"authoring","path":"ui/specs/"}
      | .copies = [{"repo":"authoring","path":"vfx/specs/"}]
      | .driver = "ui-ux"
      | .ordering = "none"
      | .participants = ["ui","vfx"]
    else . end)
 | .domains.ui.handoffs += ["ui-vfx-sync"]
 | .domains.vfx.handoffs |= map(if . == "design-event-to-vfx" then "gameplay-event-to-vfx" else . end)
 | .domains.art3d.handoffs |= map(select(. != "asset-3d-to-vfx" and . != "asset-3d-to-impl"))
