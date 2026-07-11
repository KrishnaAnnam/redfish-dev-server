#!/usr/bin/env python3
"""
Contoso Error Injector
======================

Command-line tool that generates error-injection CPADs for the Contoso SoC and
reads them back.  It demonstrates the RAS API pattern of a vendor-specific tool
producing vendor-specific CPADs behind a standard interface.

Verbs:
    list       Print a table of every error this tool can inject.
    template   Write an editable JSON injection spec for a chosen error.
    inject     Build a binary .cpad from a spec (or from CLI flags).
    decode     Read a tool-produced .cpad and reconstruct the injection spec.

The CreatorID is ALWAYS the Contoso SoC CreatorID; it is never a user input.
See ``error-injector-contoso.md`` for the full specification.

Examples:
    injector-contoso.py list
    injector-contoso.py template --section "CPU Core - First Generation" \\
                                 --error "Poison Consumption" --out poison.inject.json
    injector-contoso.py inject --spec poison.inject.json --out poison.cpad
    injector-contoso.py decode --cpad poison.cpad
"""

import sys
import json
import argparse
from pathlib import Path

import contoso_catalog as catalog
import injection_spec as spec_model
import contoso_encoder as encoder
import cpad_builder as builder

# value → name reverse map for the Error Status Register severity field.
_SEVERITY_NAMES = {v: k for k, v in catalog.SEVERITY_VALUES.items()}


# ── list ────────────────────────────────────────────────────────────────────

def cmd_list(args):
    """Print a table of injectable errors."""
    rows = list(catalog.iter_all_errors())
    headers = ["Type", "Section Type", "Error Bank", "Error Name",
               "Mode", "Trigger", "Persistence"]
    table = [headers]
    for r in rows:
        table.append([
            r["category"], r["section_type"], r["bank"], r["error_name"],
            "Spoofed", "Immediate (fixed)", "Once",
        ])
    widths = [max(len(row[i]) for row in table) for i in range(len(headers))]

    def fmt(row):
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    print(fmt(table[0]))
    print("  ".join("-" * w for w in widths))
    for row in table[1:]:
        print(fmt(row))
    print(f"\n{len(rows)} injectable errors. All are spoofed, occur immediately "
          f"with no trigger conditions, and are injected once.")
    return 0


# ── template ────────────────────────────────────────────────────────────────

def cmd_template(args):
    """Write a defaulted injection spec for a chosen error."""
    try:
        spec = spec_model.build_template(args.section, args.error)
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.write_text(json.dumps(spec, indent=2))
    print(f"Wrote injection spec: {out}")
    print(f"  Section: {args.section}")
    print(f"  Error:   {args.error}")
    print("Edit the spec, then run:  injector-contoso.py inject "
          f"--spec {out} --out <name>.cpad")
    return 0


# ── inject ──────────────────────────────────────────────────────────────────

def _apply_set(spec, dotted, raw):
    """Apply a CLI override like 'section.additional.dimm=1' to the spec."""
    keys = dotted.split(".")
    node = spec
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    low = raw.lower()
    if low in ("true", "false"):
        value = (low == "true")
    else:
        value = raw
    node[keys[-1]] = value


def _parse_beat_flag(text):
    """Parse a --beat 'dram=..;dq=..;beats=..' string into a beatErrors entry.

    Fields are separated by ';'; each value may be an int, a comma list, a
    'lo-hi' range, or 'all'.  Only 'dram' is required (dq/beats default to all).
    """
    entry = {}
    for field in text.split(";"):
        field = field.strip()
        if not field:
            continue
        if "=" not in field:
            raise ValueError(f"--beat field '{field}' must be key=value")
        key, value = field.split("=", 1)
        key = key.strip().lower()
        if key not in ("dram", "dq", "beats"):
            raise ValueError(f"--beat: unknown key '{key}' (use dram, dq, beats)")
        entry[key] = value.strip()
    if "dram" not in entry:
        raise ValueError("--beat requires 'dram=' (e.g. \"dram=3;dq=2;beats=0,5,15\")")
    entry.setdefault("dq", "all")
    entry.setdefault("beats", "all")
    return entry


def _apply_overrides(spec, args):
    """Apply --platform-id / --partition-id / --set / --beat overrides to a spec.

    These work whether the spec came from a file (--spec) or from
    --section/--error, so a committed spec can be reused with small tweaks
    (e.g. a different column address or an added failing beat).
    """
    if args.platform_id:
        spec["cpad"]["platformID"] = args.platform_id
    if args.partition_id:
        spec["cpad"]["partitionID"] = args.partition_id
    for assignment in args.set or []:
        if "=" not in assignment:
            raise ValueError(f"--set expects key=value, got '{assignment}'")
        dotted, raw = assignment.split("=", 1)
        _apply_set(spec, dotted.strip(), raw.strip())
    for beat in getattr(args, "beat", None) or []:
        spec.setdefault("section", {}).setdefault("beatErrors", []).append(
            _parse_beat_flag(beat))


def cmd_inject(args):
    """Build a binary .cpad from a spec file or CLI flags."""
    try:
        if args.spec:
            spec = spec_model.load_spec(args.spec)
        elif args.section and args.error:
            spec = spec_model.build_template(args.section, args.error)
        else:
            print("Error: provide --spec, or both --section and --error.",
                  file=sys.stderr)
            return 1
        _apply_overrides(spec, args)
    except (KeyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    problems = spec_model.validate_spec(spec)
    if problems:
        print("Invalid injection spec:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    section_name = spec["error"]["sectionType"]
    bank_name = spec["error"]["errorBank"]
    section_guid = catalog.resolve_section(section_name)["guid"]

    fields = spec_model.to_encoder_fields(spec)
    body = encoder.pack_section_body(section_name, bank_name, fields)
    cpad_json = builder.build_cpad_json(spec, section_guid, body)

    try:
        out = builder.write_cpad(cpad_json, args.out)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote CPAD: {out}")
    print(f"  Error:        {spec['error']['errorName']} "
          f"({section_name} / {bank_name})")
    print(f"  Platform ID:  {spec['cpad'].get('platformID')}")
    print(f"  Partition ID: {spec['cpad'].get('partitionID')}")
    print(f"  CreatorID:    {catalog.CONTOSO_CREATOR_ID} (Contoso, fixed)")
    print(f"  Section body: {len(body)} bytes")
    return 0


# ── decode ──────────────────────────────────────────────────────────────────

def cmd_decode(args):
    """Reconstruct the injection spec from a tool-produced CPAD."""
    try:
        cpad_json = builder.read_cpad(args.cpad)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    creator = cpad_json.get("header", {}).get("creatorID", "")
    if creator.lower() != catalog.CONTOSO_CREATOR_ID.lower():
        print(f"Error: CPAD CreatorID {creator} is not Contoso "
              f"({catalog.CONTOSO_CREATOR_ID}); not produced by this tool.",
              file=sys.stderr)
        return 1

    guid, body = builder.extract_section_body(cpad_json)
    section_name = catalog.section_name_from_guid(guid)
    if not section_name:
        print(f"Error: unknown Contoso section GUID {guid}.", file=sys.stderr)
        return 1

    decoded = encoder.unpack_section_body(section_name, body)
    if not decoded:
        print("Error: no injected error found in section body.", file=sys.stderr)
        return 1

    header = cpad_json["header"]
    descriptor = cpad_json["sectionDescriptors"][0]
    status = decoded["error_status"]
    error_name = catalog.error_name_from_id(
        section_name, decoded["bank_name"], status["error_id"])
    severity_name = _SEVERITY_NAMES.get(status["severity_value"], "Unknown")
    _eid, typical = catalog.resolve_error(section_name, decoded["bank_name"], error_name)

    # Present the decoded body cleanly: reverse-compile any beat_mask bits into
    # a readable beatErrors list and zero the raw grid so the spec re-injects.
    additional = dict(decoded["additional"])
    beat_errors = []
    grid = additional.get("beat_mask")
    if isinstance(grid, list) and grid and isinstance(grid[0], list):
        for d, row in enumerate(grid):
            for q, mask in enumerate(row):
                if mask:
                    beats = ",".join(str(b) for b in range(16) if mask & (1 << b))
                    beat_errors.append({"dram": d, "dq": q, "beats": beats})
        additional["beat_mask"] = [[0] * len(grid[0]) for _ in grid]

    section_block = {
        "subcomponent": decoded["subcomponent"],
        "errorStatus": {
            "addressValid": status["addressValid"],
            "overflow": status["overflow"],
        },
        "errorAddress": hex(decoded["error_address"]),
        "misc0": {
            "injected": decoded["misc0"]["injected"],
            "ce_count": decoded["misc0"]["ce_count"],
        },
        "misc1": hex(decoded["misc1"]),
        "additional": additional,
    }
    if beat_errors:
        section_block["beatErrors"] = beat_errors

    spec = {
        "cpad": {
            "platformID": header.get("platformID"),
            "partitionID": header.get("partitionID"),
            "revision": header.get("revision", {"major": 1, "minor": 0}),
            "urgency": bool(header.get("urgency")),
            "fruID": descriptor.get("fruID"),
            "fruText": descriptor.get("fruText"),
        },
        "error": {
            "sectionType": section_name,
            "errorBank": decoded["bank_name"],
            "errorName": error_name,
            "severityOverride": None if severity_name == typical else severity_name,
            "injected": decoded["misc0"]["injected"],
            "occurrence": "immediate",
        },
        "section": section_block,
    }

    print(json.dumps(spec, indent=2))
    print("\n# Equivalent command:", file=sys.stderr)
    print(
        f"injector-contoso.py inject --section \"{section_name}\" "
        f"--error \"{error_name}\" "
        f"--platform-id {header.get('platformID')} "
        f"--partition-id {header.get('partitionID')} --out out.cpad",
        file=sys.stderr)
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        prog="injector-contoso.py",
        description="Contoso SoC error-injection CPAD generator (RAS API demo).")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List the errors this tool can inject.")

    p_tmpl = sub.add_parser("template", help="Write an editable injection spec.")
    p_tmpl.add_argument("--section", required=True, help="Exact section-type name.")
    p_tmpl.add_argument("--error", required=True, help="Exact error name.")
    p_tmpl.add_argument("--out", required=True, help="Output *.inject.json path.")

    p_inj = sub.add_parser("inject", help="Build a binary .cpad.")
    p_inj.add_argument("--spec", help="Path to an injection spec JSON file.")
    p_inj.add_argument("--section", help="Section-type name (CLI fast-path).")
    p_inj.add_argument("--error", help="Error name (CLI fast-path).")
    p_inj.add_argument("--platform-id", help="Target platform ID (CLI fast-path).")
    p_inj.add_argument("--partition-id", help="Target partition ID (CLI fast-path).")
    p_inj.add_argument("--set", action="append", metavar="KEY=VALUE",
                       help="Override a spec field, e.g. section.additional.dimm=1.")
    p_inj.add_argument("--beat", action="append", metavar="dram=..;dq=..;beats=..",
                       help="Inject DRAM beat errors, e.g. \"dram=3;dq=2;beats=0,5,15\" "
                            "(dq/beats default to all; values accept lists, lo-hi "
                            "ranges, or 'all'). Repeatable.")
    p_inj.add_argument("--out", required=True, help="Output .cpad path.")

    p_dec = sub.add_parser("decode", help="Reconstruct the spec from a .cpad.")
    p_dec.add_argument("--cpad", required=True, help="Path to a .cpad file.")

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return {
        "list": cmd_list,
        "template": cmd_template,
        "inject": cmd_inject,
        "decode": cmd_decode,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
