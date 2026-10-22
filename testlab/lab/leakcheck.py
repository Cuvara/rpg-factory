"""Is test-only instrumentation inside a player build? (`testlab.py leak-check <player>`)

The TestLab runtime (asmdef `NDC.TestLab`, namespace `TestLab`) compiles only with the scripting
define `CUVARA_TESTLAB` (or in the Editor with UNITY_INCLUDE_TESTS). A production player must not
contain it. This inspects a built player without running it:
- Mono builds: every `*.dll` in `<Name>_Data/Managed/`, plus `ScriptingAssemblies.json` and
  `RuntimeInitializeOnLoads.json` in `<Name>_Data/`;
- IL2CPP builds: `GameAssembly.dll` and `<Name>_Data/il2cpp_data/Metadata/global-metadata.dat`.

A finding is an assembly file named `NDC.TestLab*`, or a marker string in a file's bytes (UTF-8 in
the metadata string heap, UTF-16LE in user strings): the assembly name, the `CUVARA_TESTLAB` define
or a TestLab runtime type name. Metadata stores a type's namespace and name as separate strings,
so bare type names are searched; each was chosen so no production type shares it.
"""

from __future__ import annotations

from pathlib import Path

ASSEMBLY = "NDC.TestLab"
MARKERS = (
    "NDC.TestLab", "CUVARA_TESTLAB",
    "TestLabRunner", "TestLabBootstrap", "TestLabControl", "TestLabInputPlanner", "TestLabPlan",
    "ScriptedInputSource", "RenderJumpDetector", "DeliveryRecorder", "FrameReadTap",
)


def _encodings(marker: str) -> list[bytes]:
    return [marker.encode("utf-8"), marker.encode("utf-16-le")]


def resolve(path: Path) -> tuple[Path | None, Path | None]:
    """(data_dir, exe) for an exe, a build directory, its StandaloneWindows64 folder, a `_Data`
    folder or a `Managed` folder. (None, None) when no player is found."""
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".exe":
        d = path.parent / (path.stem + "_Data")
        return (d if d.is_dir() else None), path
    candidates = [path, path / "StandaloneWindows64"]
    for c in candidates:
        if c.name == "Managed" and c.parent.name.endswith("_Data"):
            return c.parent, None
        if c.name.endswith("_Data") and c.is_dir():
            return c, None
        if c.is_dir():
            datas = sorted(p for p in c.glob("*_Data") if p.is_dir())
            if datas:
                exe = c / (datas[0].name[: -len("_Data")] + ".exe")
                return datas[0], exe if exe.exists() else None
    return None, None


def inspect(path: Path) -> dict:
    data, exe = resolve(path)
    report = {"player": str(path), "data_dir": str(data) if data else None, "backend": None,
              "scanned": 0, "findings": [], "verdict": "ERROR"}
    if data is None:
        report["error"] = f"no player found at {path} (expected <Name>.exe next to <Name>_Data/)"
        return report
    files = []
    managed = data / "Managed"
    if managed.is_dir():
        report["backend"] = "mono"
        files += sorted(managed.glob("*.dll"))
    meta = data / "il2cpp_data" / "Metadata" / "global-metadata.dat"
    if meta.exists():
        report["backend"] = "il2cpp" if report["backend"] is None else "mono+il2cpp"
        files.append(meta)
        game_asm = data.parent / "GameAssembly.dll"
        if game_asm.exists():
            files.append(game_asm)
    files += [p for p in (data / "ScriptingAssemblies.json", data / "RuntimeInitializeOnLoads.json") if p.exists()]
    if report["backend"] is None:
        report["error"] = f"{data} has neither Managed/ nor il2cpp_data/: not a Unity player data folder"
        return report
    needles = [(m, enc) for m in MARKERS for enc in _encodings(m)]
    for f in files:
        report["scanned"] += 1
        if f.name.startswith(ASSEMBLY):
            report["findings"].append({"file": f.name, "marker": "assembly file"})
        try:
            blob = f.read_bytes()
        except OSError as exc:
            report["findings"].append({"file": f.name, "marker": f"unreadable: {exc}"})
            continue
        hit = sorted({m for m, enc in needles if enc in blob})
        if hit:
            report["findings"].append({"file": f.name, "marker": ", ".join(hit)})
    report["verdict"] = "TESTLAB_PRESENT" if report["findings"] else "CLEAN"
    return report
