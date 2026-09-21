"""Auditable evidence for explicitly localized visual objects.

This module owns the small policy boundary needed by the V0.5.3 Evidence
slice.  It deliberately works on the public compiler/readback manifests rather
than on renderer internals, so a later capture implementation can provide the
same records without widening the object compiler API.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any


LOCALIZED_ATTRIBUTE = "data-pptx-rasterize"
LOCALIZED_TOKEN = "localized"
LOCALIZED_CAPTURE_DENSITY = 2.0
LOCALIZED_DISPOSITIONS = ("native", "rasterized", "unsupported", "unresolved")
LOCALIZED_DIAGNOSTIC_KEYS = (
    "unapproved_rasterized",
    "blank_rasterized",
    "contaminated_rasterized",
    "failed_isolation",
    "unsupported",
    "unresolved",
    "material_delta",
)
_MATERIAL_TOLERANCE_PT = 0.01


def localized_fallback_surface() -> dict[str, Any]:
    """Return the single public authority for the localized visual policy."""

    return {
        "annotation": LOCALIZED_ATTRIBUTE,
        "token": LOCALIZED_TOKEN,
        "case_sensitive": True,
        "atomic": True,
        "identity": {
            "explicit": "trimmed unique HTML id",
            "fallback": "deterministic source path",
            "fallback_annotation": False,
        },
        "geometry": {
            "source": "CSS border box",
            "capture": "same as PowerPoint picture bounds",
            "overflow": "blocking; author supplies padding",
        },
        "density": {
            "pixels_per_point": LOCALIZED_CAPTURE_DENSITY,
            "author_control": False,
            "pixel_rounding": "nearest integer",
        },
        "editability": {
            "object": "native picture",
            "content": False,
            "statement": "visual-only; content inside the picture is not editable",
            "text_overlay": False,
        },
        "allowed_content": [
            "static HTML/CSS",
            "inline SVG",
            "data URI images",
            "permitted local images",
        ],
        "exclusions": [
            "script execution",
            "runtime canvas",
            "iframe",
            "network resources",
            "audio/video",
            "WebGL",
            "animation",
            "interactive state",
            "cross-slide capture",
            "nested regions",
            "overlapping regions",
            "whole-slide regions",
            "regions containing another atomic object",
        ],
        "dispositions": list(LOCALIZED_DISPOSITIONS),
        "successful_disposition": "rasterized",
        "blocking_dispositions": ["unsupported", "unresolved"],
        "native_counts": "rasterized objects are excluded",
        "readback": "independent native picture readback",
        "asset": {
            "mime": "image/png",
            "hash": "SHA-256 of capture PNG",
            "packaged_bytes": "not compared with capture bytes",
        },
    }


def _first(mapping: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in mapping and mapping[name] is not None:
            return mapping[name]
    return default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounds(value: Any) -> list[float] | None:
    if isinstance(value, Mapping):
        value = _first(value, "bounds_pt", "bounds", default=None)
    values = _list(value)
    if len(values) != 4:
        return None
    parsed = [_number(item) for item in values]
    if any(item is None for item in parsed):
        return None
    return [float(item) for item in parsed if item is not None]


def _is_localized_marker(item: Mapping[str, Any]) -> bool:
    if item.get("localized_fallback") is not None:
        return True
    if item.get("is_localized_fallback") is True:
        return True
    if item.get("fallback_annotation") == f"{LOCALIZED_ATTRIBUTE}=\"{LOCALIZED_TOKEN}\"":
        return True
    if item.get("fallback") is not None:
        return True
    return any(
        key in item
        for key in (
            "localized",
            "localized_fallback_spec",
            "rasterized",
            "fallback_reason",
        )
    )


def _raw_records(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("localized_fallbacks", "localized_fallback", "fallback_evidence"):
        value = manifest.get(key)
        if isinstance(value, Mapping):
            value = _first(value, "records", "objects", "regions", default=[])
        records = [item for item in _list(value) if isinstance(item, Mapping)]
        if records:
            return records
    return [
        item
        for item in _list(manifest.get("objects"))
        if isinstance(item, Mapping) and _is_localized_marker(item)
    ]


def _asset_record(item: Mapping[str, Any]) -> dict[str, Any]:
    nested = _mapping(_first(item, "asset", "raster_asset", default={}))
    return {
        "mime": _first(nested, "mime", "content_type", default=_first(item, "asset_mime", "mime")),
        "sha256": _first(nested, "sha256", "hash", default=_first(item, "asset_sha256", "capture_sha256", "sha256")),
        "path": _first(nested, "path", "file", default=_first(item, "asset_path", "capture_path")),
        "pixel_width": _first(nested, "pixel_width", "width", default=_first(item, "pixel_width", "width_px")),
        "pixel_height": _first(nested, "pixel_height", "height", default=_first(item, "pixel_height", "height_px")),
        "density": _first(nested, "density", "pixels_per_point", default=_first(item, "density", "pixels_per_point")),
        "exists": _first(nested, "exists", "present", default=_first(item, "asset_exists", "asset_present")),
    }


def _paint_record(item: Mapping[str, Any]) -> dict[str, Any]:
    nested = _mapping(_first(item, "paint", "paint_evidence", default={}))
    nonblank = _first(nested, "nonblank", "has_paint", default=_first(item, "nonblank", "has_paint"))
    blank = _first(nested, "blank", "transparent", default=_first(item, "blank", "transparent"))
    if nonblank is None and blank is not None:
        nonblank = not bool(blank)
    if blank is None and nonblank is not None:
        blank = not bool(nonblank)
    return {"nonblank": nonblank, "blank": blank}


def _isolation_record(item: Mapping[str, Any]) -> dict[str, Any]:
    nested = _mapping(_first(item, "isolation", "isolation_evidence", default={}))
    isolated = _first(nested, "isolated", "passed", default=_first(item, "isolated", "isolation_passed"))
    contaminated = _first(nested, "contaminated", default=_first(item, "contaminated"))
    return {"isolated": isolated, "contaminated": contaminated}


def _normalize_record(item: Mapping[str, Any]) -> dict[str, Any]:
    nested = _mapping(_first(item, "localized_fallback", "fallback", "localized_fallback_spec", default={}))
    merged: dict[str, Any] = dict(nested)
    merged.update({key: value for key, value in item.items() if key not in merged})
    disposition = str(_first(merged, "disposition", default="unresolved") or "unresolved")
    source_object = str(_first(merged, "source_object", "source_path", "path", default="") or "")
    identity = str(_first(merged, "source_identity", "identity", "source_id", "id", default=source_object) or "")
    record = {
        "name": str(_first(merged, "name", "object_name", default="") or ""),
        "source_identity": identity,
        "source_path": source_object,
        "source_object": source_object,
        "source_slide": _first(merged, "source_slide", "slide", default=None),
        "disposition": disposition,
        "reason": str(_first(merged, "reason", "fallback_reason", default="") or ""),
        "compiled_kind": str(_first(merged, "compiled_kind", "kind", "native_kind", default="") or ""),
        "editable": _first(merged, "editable", default=False if disposition == "rasterized" else None),
        "bounds_pt": _bounds(_first(merged, "bounds_pt", "bounds", "geometry", default=None)),
        "asset": _asset_record(merged),
        "paint": _paint_record(merged),
        "isolation": _isolation_record(merged),
        "excluded_descendant_count": _first(
            merged,
            "excluded_descendant_count",
            "excluded_descendants",
            "descendant_count",
            default=None,
        ),
        "approved": _first(
            merged,
            "approved",
            default=(
                disposition == "rasterized"
                and str(_first(merged, "reason", "fallback_reason", default=""))
                in {"explicit_author_opt_in", "author_opt_in"}
            ),
        ),
        "readback": dict(_mapping(_first(merged, "readback", "picture_readback", default={}))),
    }
    return record


def _object_index(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for item in _list(manifest.get("objects")):
        if not isinstance(item, Mapping):
            continue
        for key in ("name", "source_identity", "source_object", "source_path"):
            value = item.get(key)
            if value:
                index.setdefault(str(value), item)
    return index


def _match_readback(record: Mapping[str, Any], readback: Mapping[str, Any]) -> Mapping[str, Any] | None:
    index = _object_index(readback)
    for key in ("name", "source_identity", "source_object", "source_path"):
        value = record.get(key)
        if value and str(value) in index:
            return index[str(value)]
    return None


def _same_bounds(left: Any, right: Any) -> bool:
    left_values = _bounds(left)
    right_values = _bounds(right)
    return bool(
        left_values is not None
        and right_values is not None
        and all(abs(a - b) <= _MATERIAL_TOLERANCE_PT for a, b in zip(left_values, right_values))
    )


def _hash_matches_asset(asset: Mapping[str, Any]) -> bool | None:
    expected = asset.get("sha256")
    path = asset.get("path")
    if not expected or not path:
        return None
    try:
        digest = hashlib.sha256(Path(str(path)).read_bytes()).hexdigest()
    except (OSError, ValueError):
        return False
    return digest.lower() == str(expected).lower()


def _material_findings(
    record: Mapping[str, Any],
    readback_item: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(field: str, reason: str) -> None:
        findings.append(
            {
                "identity": record.get("source_identity"),
                "source_path": record.get("source_path"),
                "field": field,
                "reason": reason,
            }
        )

    if record.get("disposition") not in LOCALIZED_DISPOSITIONS:
        add("disposition", "unknown disposition")
    if not record.get("source_identity"):
        add("source_identity", "missing source identity")
    if not record.get("source_path"):
        add("source_path", "missing source path")
    if _number(record.get("source_slide")) is None or int(float(record["source_slide"])) < 1:
        add("source_slide", "missing source slide")
    bounds = record.get("bounds_pt")
    if bounds is None or bounds[2] <= 0 or bounds[3] <= 0:
        add("bounds_pt", "missing or non-positive bounds")

    if record.get("disposition") == "rasterized":
        if record.get("compiled_kind") != "picture":
            add("compiled_kind", "rasterized record is not a picture")
        if record.get("editable") is not False:
            add("editable", "rasterized content must be non-editable")
        asset = _mapping(record.get("asset"))
        if asset.get("mime") != "image/png":
            add("asset.mime", "localized capture must be a PNG")
        digest = str(asset.get("sha256") or "")
        if len(digest) != 64 or any(character not in "0123456789abcdefABCDEF" for character in digest):
            add("asset.sha256", "capture hash is not a SHA-256 value")
        hash_result = _hash_matches_asset(asset)
        if hash_result is False:
            add("asset.sha256", "capture hash does not match the persisted asset")
        if asset.get("exists") is False:
            add("asset.exists", "capture asset is not present")
        width = _number(asset.get("pixel_width"))
        height = _number(asset.get("pixel_height"))
        density = _number(asset.get("density"))
        if width is None or height is None or width <= 0 or height <= 0:
            add("asset.pixel_dimensions", "capture pixel dimensions are missing")
        if density is None or abs(density - LOCALIZED_CAPTURE_DENSITY) > 1e-9:
            add("asset.density", "capture density is not the fixed release density")
        if bounds is not None and width is not None and height is not None:
            if abs(width - round(bounds[2] * LOCALIZED_CAPTURE_DENSITY)) > 1:
                add("asset.pixel_width", "pixel width does not match point bounds")
            if abs(height - round(bounds[3] * LOCALIZED_CAPTURE_DENSITY)) > 1:
                add("asset.pixel_height", "pixel height does not match point bounds")

        if not record.get("approved"):
            add("approved", "rasterized record lacks explicit author approval")
        paint = _mapping(record.get("paint"))
        if paint.get("nonblank") is not True or paint.get("blank") is True:
            add("paint", "capture is blank or has no positive paint proof")
        isolation = _mapping(record.get("isolation"))
        if isolation.get("contaminated") is True:
            add("isolation.contaminated", "capture contains neighboring paint")
        if isolation.get("isolated") is not True:
            add("isolation.isolated", "capture lacks positive isolation proof")
        descendants = _number(record.get("excluded_descendant_count"))
        if descendants is None or descendants < 0 or descendants != int(descendants):
            add("excluded_descendant_count", "excluded descendant count is invalid")

    if readback_item is None:
        add("readback", "independent picture readback is missing")
        return findings

    explicit_disposition = readback_item.get("disposition")
    if explicit_disposition is not None and explicit_disposition != record.get("disposition"):
        add("readback.disposition", "readback disposition differs")
    readback_metadata = _mapping(readback_item.get("metadata"))
    readback_localized = _mapping(
        _first(readback_item, "localized_fallback", "localized_fallback_evidence", default={})
    )
    expected_identity = record.get("source_identity")
    for key in ("source_identity", "identity"):
        actual = _first(readback_item, key, default=_first(readback_localized, key, default=readback_metadata.get(key)))
        if actual is not None and actual != expected_identity:
            add("readback.source_identity", "readback identity differs")
            break
    expected_path = record.get("source_path")
    # OfficeCLI's ordinary ``source_object`` is its generated PPTX path (for
    # example ``/slide[1]/picture[1]``), not the Author HTML path.  Compare
    # only an explicitly carried Author path so native readback does not turn
    # a representation detail into a false material delta.
    for key in ("source_path", "author_source_path"):
        actual = _first(readback_item, key, default=_first(readback_localized, key, default=readback_metadata.get(key)))
        if actual is not None and actual != expected_path:
            add("readback.source_path", "readback source path differs")
            break
    if record.get("disposition") == "rasterized":
        for key in ("kind", "native_kind"):
            actual_kind = readback_item.get(key)
            if actual_kind is not None and actual_kind != "picture":
                add("readback.kind", "readback object is not a native picture")
    if record.get("bounds_pt") is not None and not _same_bounds(record.get("bounds_pt"), readback_item.get("bounds_pt")):
        add("readback.bounds_pt", "readback picture bounds differ")
    if readback_item.get("asset_present") is False or readback_item.get("asset_exists") is False:
        add("readback.asset", "readback picture has no persisted asset")
    capture_hash = readback_item.get("capture_sha256")
    if capture_hash is not None and capture_hash != _mapping(record.get("asset")).get("sha256"):
        add("readback.capture_sha256", "readback capture hash differs")
    expected_descendants = record.get("excluded_descendant_count")
    actual_descendants = readback_item.get("excluded_descendant_count")
    if actual_descendants is not None and actual_descendants != expected_descendants:
        add("readback.excluded_descendant_count", "readback descendant count differs")
    return findings


def _native_counts(
    manifest: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    objects = [item for item in _list(manifest.get("objects")) if isinstance(item, Mapping)]
    localized_names = {
        str(item.get("name"))
        for item in records
        if item.get("name")
    }
    localized_keys = {
        str(value)
        for item in records
        for value in (
            item.get("source_identity"),
            item.get("source_object"),
            item.get("source_path"),
        )
        if value
    }
    excluded: set[int] = set()
    for index, item in enumerate(objects):
        keys = {str(item.get(key)) for key in ("name", "source_identity", "source_object", "source_path") if item.get(key)}
        if keys & (localized_names | localized_keys):
            excluded.add(index)
    native_objects = [
        item
        for index, item in enumerate(objects)
        if index not in excluded or str(item.get("disposition")) == "native"
    ]
    kind_counts: dict[str, int] = {}
    for item in native_objects:
        kind = str(item.get("kind", ""))
        if kind:
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
    total = len(objects)
    return {
        "object_count": total,
        "native_object_count": len(native_objects),
        "native_object_kind_counts": kind_counts,
        "native_ratio": (len(native_objects) / total) if total else 1.0,
    }


def audit_localized_fallbacks(
    compiled_manifest: Mapping[str, Any],
    readback_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize and materially compare localized records with readback."""

    records = [_normalize_record(item) for item in _raw_records(compiled_manifest)]
    normalized_records: list[dict[str, Any]] = []
    material: list[dict[str, Any]] = []
    for record in records:
        readback_item = _match_readback(record, readback_manifest)
        findings = _material_findings(record, readback_item)
        material.extend(findings)
        normalized = deepcopy(record)
        if readback_item is not None:
            normalized["readback"] = dict(readback_item)
        normalized_records.append(normalized)

    counts_by_disposition = {key: 0 for key in LOCALIZED_DISPOSITIONS}
    for record in normalized_records:
        disposition = str(record.get("disposition"))
        if disposition in counts_by_disposition:
            counts_by_disposition[disposition] += 1
    diagnostic_counts = {
        "unapproved_rasterized": sum(
            1
            for record in normalized_records
            if record.get("disposition") == "rasterized"
            and any(item["field"] in {"approved", "editable"} for item in _material_findings(record, _match_readback(record, readback_manifest)))
        )
        + sum(record.get("disposition") == "native" for record in normalized_records),
        "blank_rasterized": sum(
            record.get("disposition") == "rasterized"
            and (
                _mapping(record.get("paint")).get("nonblank") is not True
                or _mapping(record.get("paint")).get("blank") is True
            )
            for record in normalized_records
        ),
        "contaminated_rasterized": sum(
            record.get("disposition") == "rasterized"
            and _mapping(record.get("isolation")).get("contaminated") is True
            for record in normalized_records
        ),
        "failed_isolation": sum(
            record.get("disposition") == "rasterized"
            and _mapping(record.get("isolation")).get("isolated") is not True
            for record in normalized_records
        ),
        "unsupported": counts_by_disposition["unsupported"],
        "unresolved": counts_by_disposition["unresolved"]
        + sum(
            str(record.get("disposition")) not in LOCALIZED_DISPOSITIONS
            for record in normalized_records
        ),
        "material_delta": len(material),
    }
    native = _native_counts(compiled_manifest, normalized_records)
    return {
        "schema_version": 1,
        "policy": localized_fallback_surface(),
        "records": normalized_records,
        "counts": {
            **counts_by_disposition,
            **native,
            "rasterized_count": counts_by_disposition["rasterized"],
        },
        "diagnostics": diagnostic_counts,
        "material_deltas": material,
        "readback": {
            "picture_count": sum(
                item.get("kind") == "picture"
                for item in _list(readback_manifest.get("objects"))
                if isinstance(item, Mapping)
            ),
            "matched_count": sum(
                _match_readback(record, readback_manifest) is not None
                for record in normalized_records
            ),
        },
        "gates": dict(diagnostic_counts),
    }


def validate_localized_evidence(
    evidence: Mapping[str, Any],
    compiled_manifest: Mapping[str, Any] | None = None,
    readback_manifest: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """Return stable errors that make a localized Evidence Bundle unfinalizable."""

    errors: list[str] = []
    diagnostics = _mapping(evidence.get("diagnostics"))
    for key in LOCALIZED_DIAGNOSTIC_KEYS:
        try:
            value = int(diagnostics.get(key, 0))
        except (TypeError, ValueError):
            value = 1
        if value != 0:
            errors.append(f"localized evidence {key} must be zero")
    dispositions = _list(evidence.get("policy", {}).get("dispositions")) if isinstance(evidence.get("policy"), Mapping) else []
    if dispositions and dispositions != list(LOCALIZED_DISPOSITIONS):
        errors.append("localized evidence publishes an unsupported disposition set")
    records = _list(evidence.get("records"))
    for record in records:
        if not isinstance(record, Mapping):
            errors.append("localized evidence records must be objects")
            continue
        if record.get("disposition") not in LOCALIZED_DISPOSITIONS:
            errors.append("localized evidence contains an unknown disposition")
        if record.get("disposition") == "rasterized" and record.get("editable") is not False:
            errors.append("localized rasterized evidence must record editable=false")
    if compiled_manifest is not None and readback_manifest is not None:
        fresh = audit_localized_fallbacks(compiled_manifest, readback_manifest)
        if fresh.get("diagnostics") != dict(diagnostics):
            errors.append("localized evidence diagnostics do not match manifest/readback")
        if fresh.get("counts") != evidence.get("counts"):
            errors.append("localized evidence counts do not match manifest/readback")
        if fresh.get("material_deltas") != evidence.get("material_deltas"):
            errors.append("localized evidence material comparison does not match manifest/readback")
    return tuple(dict.fromkeys(errors))


__all__ = [
    "LOCALIZED_ATTRIBUTE",
    "LOCALIZED_CAPTURE_DENSITY",
    "LOCALIZED_DIAGNOSTIC_KEYS",
    "LOCALIZED_DISPOSITIONS",
    "LOCALIZED_TOKEN",
    "audit_localized_fallbacks",
    "localized_fallback_surface",
    "validate_localized_evidence",
]
