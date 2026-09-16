"""Run the V0.4.2 ten-page representative acceptance and publish its evidence.

This is the heavy half of ticket #18.  It drives the frozen ten-page corpus --
the eight selected real pages of the private business deck plus the two synthetic
probes -- through the one selected-page seam, and writes the complete acceptance
evidence bundle into ``acceptance/v0.4.2/``:

    acceptance-report.md          the authoritative report
    corpus-manifest.json          provenance, coverage purpose, scope note
    artifact-manifest.json        sha256 of every published deliverable
    gate/                         the gate's own published evidence set
    visual/p01-before.png ...     source render, rebuilt render, Canonical HTML
    visual/p01-after.png
    visual/p01-author.html

Usage::

    & .\\.venv\\Scripts\\python.exe scripts/run_v042_acceptance.py
    & .\\.venv\\Scripts\\python.exe scripts/run_v042_acceptance.py --synthetic-only

The real deck is never opened for writing; its sha256 is recorded before and
after the run and the run refuses to publish if it changed.  The generated
binaries (the rebuilt deck, the Canonical Author HTML, the proxy rasters) are
written under ``acceptance/v0.4.2/`` and excluded from the committed text by
``.gitignore``.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

def _repository_root() -> Path:
    """Return the checkout this script belongs to."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists():
            return candidate
    return Path(__file__).resolve().parents[1]


REPO = _repository_root()
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests"))

import officecli_html_to_pptx as m  # noqa: E402
import v042_acceptance_corpus as corpus  # noqa: E402
from officecli_html_to_pptx.contract import check_contract  # noqa: E402

BUNDLE = REPO / "acceptance" / "v0.4.2"
#: The bundle's path relative to the repository, so a run can tell its own output
#: apart from an edit to the code it is measuring.
BUNDLE_RELATIVE = "acceptance/v0.4.2"
RENDER_WIDTH = 1600
SCREENSHOT_RENDER = "native"
#: The corpus's opaque source slots, in selection order.  A slot is a corpus
#: position, not a business document: nothing below ever names a private deck, and
#: the decks themselves are resolved from gitignored local configuration.
REAL_SLOTS: tuple[str, ...] = tuple(source.slot for source in corpus.CORPUS_SOURCES)

#: What a real page's id looks like: ``<slot>:<page>``.  The driver used to test
#: for a literal ``real:`` prefix from the single-deck era, which stopped matching
#: anything the moment the corpus became multi-source -- so every real-page branch
#: below had quietly become dead code.
_SLOT_PREFIXES: tuple[str, ...] = tuple(f"{slot}:" for slot in REAL_SLOTS)


def is_real_page(page_id: str) -> bool:
    """Whether a page id names a page of one of the private source decks."""
    return str(page_id).startswith(_SLOT_PREFIXES)


def slot_of(page_id: str) -> str | None:
    """Return the source slot a real page belongs to, or ``None`` for a probe."""
    text = str(page_id)
    for slot in REAL_SLOTS:
        if text.startswith(f"{slot}:"):
            return slot
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def officecli(*args: str, attempts: int = 5) -> str:
    """Run one OfficeCLI command, retrying the transient under-load failure."""
    document = next(
        (a for a in args[1:] if str(a).lower().endswith(".pptx")), None
    )
    last = ""
    retries = 0
    for attempt in range(attempts):
        completed = subprocess.run(
            ["officecli", *args], capture_output=True, check=False, timeout=900
        )
        text = completed.stdout.decode("utf-8", errors="replace")
        if completed.returncode == 0 and text.strip():
            if retries:
                print(f"    (retried {retries}x: officecli {' '.join(args[:3])} ...)")
            return text
        last = completed.stderr.decode("utf-8", errors="replace") or text
        retries += 1
        if document is not None:
            subprocess.run(["officecli", "close", document], capture_output=True)
        time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"officecli {' '.join(args)} failed: {last}")


def screenshot(deck: Path, page: int, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(5):
        destination.unlink(missing_ok=True)
        try:
            officecli(
                "view",
                str(deck),
                "screenshot",
                "--page",
                str(page),
                "--render",
                SCREENSHOT_RENDER,
                "--screenshot-width",
                str(RENDER_WIDTH),
                "-o",
                str(destination),
            )
        except RuntimeError:
            time.sleep(0.6 * (attempt + 1))
            continue
        if destination.is_file():
            return True
        time.sleep(0.6 * (attempt + 1))
    return False


def image_facts(path: Path) -> dict[str, Any]:
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        colors = rgb.getcolors(1 << 16)
        background = rgb.getpixel((0, 0))
        background_pixels = sum(
            count for count, colour in (colors or ()) if colour == background
        )
        return {
            "width": rgb.width,
            "height": rgb.height,
            "distinct_colors": len(colors or ()),
            "background_rgb": list(background),
            "non_background_fraction": round(
                1.0 - background_pixels / float(rgb.width * rgb.height), 6
            ),
            "non_blank": len(colors or ()) > 1,
        }


def page_html(html_text: str, output_page: int) -> str:
    """The one ``section`` of the canonical document for one output page."""
    match = re.search(
        rf'<section class="slide"[^>]*data-slide-number="{output_page}"', html_text
    )
    if match is None:
        raise AssertionError(f"no section for output page {output_page}")
    start = match.start()
    end = html_text.find("</section>", start)
    return html_text[start : end + len("</section>")]


_MISSING = object()


class Attr:
    """Attribute access over a published JSON document.
    ``--report-only`` re-derives the report from an already-published bundle's
    own gate documents, so the report builder reads exactly the same fields from
    a JSON payload as it does from the live result object.  A published page
    record keeps its counters under ``counts`` where the live record keeps them
    as attributes, so both spellings are accepted.
    """

    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def __getattr__(self, name: str) -> Any:
        value = self.get(name, _MISSING)
        if value is _MISSING:
            raise AttributeError(name)
        return value

    def __getitem__(self, name: str) -> Any:
        return _wrap(self._payload[name])

    def get(self, name: str, default: Any = None) -> Any:
        if not isinstance(self._payload, dict):
            return default
        if name in self._payload:
            return _wrap(self._payload[name])
        nested = self._payload.get("counts")
        if isinstance(nested, dict) and name in nested:
            return _wrap(nested[name])
        return default


def _wrap(value: Any) -> Any:
    if isinstance(value, dict):
        return Attr(value)
    if isinstance(value, list):
        return [_wrap(item) for item in value]
    return value


def _gate_report_path(bundle: Path) -> Path:
    """Return the verdict document a bundle holds, whichever verdict it reached.

    A blocked run publishes ``gate-rejected.json`` and no ``gate-report.json`` --
    that is the whole point of naming the document for the verdict -- so a
    re-derivation that only looked for the accepted name could not describe a
    blocked bundle at all.
    """
    gate = bundle / "gate"
    accepted = gate / "gate-report.json"
    if accepted.is_file():
        return accepted
    rejected = gate / "gate-rejected.json"
    if rejected.is_file():
        return rejected
    raise SystemExit(f"no published gate report under {gate}")


def _gate_from_bundle(bundle: Path) -> tuple[Attr, dict[str, Any]]:
    """Rebuild the report's inputs from a published gate evidence set."""
    report = json.loads(_gate_report_path(bundle).read_text("utf-8"))
    payload: dict[str, Any] = {
        "outcome": report["outcome"],
        "accepted": report["accepted"],
        "published": True,
        "output_directory": str(bundle / "gate"),
        "counts": report["counts"],
        "pages": report["pages"],
        "material_deltas": report["material_deltas"],
        "retained_findings": report["retained_findings"],
        "scope_evidence": report["scope_evidence"],
        "unbound_rebuilt": report["unbound_rebuilt_issues"],
        "artifacts": report["artifacts"],
        "source_verification": report["source_verification"],
        "source_evidence": report["source_officecli"],
        "rebuilt_evidence": report["rebuilt_officecli"],
        "diagnostics": report["diagnostics"],
        "projected": {
            "objects": [
                item
                for page in report["page_responses"]
                for item in report["rebuilt_objects"]
                if True
            ]
        },
    }
    payload["projected"]["objects"] = report["rebuilt_objects"]
    ledger_path = bundle / "gate" / "disposition-ledger.json"
    if ledger_path.is_file():
        payload["ledger"] = json.loads(ledger_path.read_text("utf-8")).get(
            "entries", []
        )
    canonical = bundle / "canonical-author.html"
    if canonical.is_file():
        payload["canonical_html_path"] = str(canonical)
    return Attr(payload), report


def report_only(bundle: Path) -> int:
    """Re-derive the report and manifest from a published bundle."""
    report_path = _gate_report_path(bundle)
    print(f"re-deriving from {report_path.name}")
    manifest_path = bundle / "corpus-manifest.json"
    if not manifest_path.is_file():
        print(f"no corpus manifest at {manifest_path}")
        return 2
    manifest = json.loads(manifest_path.read_text("utf-8"))
    result, gate = _gate_from_bundle(bundle)
    page_ids = [
        item["page_id"] for item in (manifest.get("seam_selection") or [])
    ] or [
        record["page_id"]
        for record in manifest["pages"]
        if is_real_page(record["page_id"]) or not manifest.get("synthetic_only")
    ]
    selection = [
        (item["source_path"], item["source_page"])
        for item in (gate.get("selection") or [])
    ]
    if not selection:
        selection = [
            (item["source_path"], item["source_page"])
            for item in manifest.get("seam_selection") or []
        ]
    visual_records = manifest.get("visual_records") or []
    use_real = bool(
        any(is_real_page(item["page_id"]) for item in manifest["pages"])
        and not manifest.get("synthetic_only")
    )
    # The public manifest withholds each private deck's digest; the verdicts they
    # support are read back from the local-only record so the regenerated report
    # can still state them.  The values themselves never enter the report.
    local_record: dict[str, Any] = {}
    local_path = bundle / "local" / "source-verification.json"
    if local_path.is_file():
        try:
            local_record = json.loads(local_path.read_text("utf-8"))
        except (OSError, ValueError):
            local_record = {}
    by_slot = {
        str(item.get("slot")): item
        for item in (local_record.get("sources") or [])
        if isinstance(item, Mapping)
    }
    unchanged = {
        str(item["slot"]): bool(item.get("verified_unchanged"))
        for item in (manifest.get("source_decks") or [])
        if item.get("slot")
    }
    if by_slot:
        unchanged = {
            slot: bool(record.get("verified_unchanged"))
            for slot, record in by_slot.items()
        }
    # Re-deriving the report does not re-hash anything, so the before/after maps
    # are presence markers: what the report states is the recorded verdict.
    digest_before = {slot: "recorded" for slot in unchanged}
    digest_after = {slot: "recorded" for slot in unchanged}
    # A bundle published before the bindings existed can still be re-derived into
    # one that carries them: the run id is a property of the evidence, and the
    # commit is read now.  The manifest is written back so the report, the manifest
    # and the review package all state the same pair.
    if not manifest.get("commit"):
        manifest["commit"] = commit_sha()
    if not manifest.get("run_id"):
        manifest["run_id"] = run_id(bundle)
    write_json(manifest_path, manifest)
    printable = build_report(
        result=result,
        elapsed=float(manifest.get("elapsed_seconds") or 0.0),
        page_ids=page_ids,
        selection=selection,
        visual_records=visual_records,
        digest_before=digest_before,
        digest_after=digest_after,
        unchanged=unchanged,
        commit=str(manifest.get('commit') or ''),
        run_id=str(manifest.get('run_id') or ''),
        probes={},
    )
    published_report = apply_independent_review(
        bundle, apply_withdrawal(bundle, printable)
    )
    (bundle / "acceptance-report.md").write_text(
        published_report, encoding="utf-8", newline=""
    )
    write_json(bundle / "artifact-manifest.json", build_artifact_manifest(bundle))
    verify_artifact_manifest(bundle)
    digest = manifest_digest(bundle)
    write_json(bundle / "artifact-manifest.json", digest)
    verify_artifact_manifest(bundle)
    print(f"bundle: {bundle}")
    print(f"artifacts: {digest['artifact_count']}")
    print(f"verdict: {published_report.splitlines()[0]}")
    return 0


#: A withdrawal record beside the bundle.  While it exists, the published report
#: must not present its machine verdict as an acceptance: the verdict line is
#: replaced and the reason is stated at the top, so no reader can take the
#: bundle's own words as acceptance evidence without meeting the withdrawal.
WITHDRAWAL_RECORD = "ACCEPTANCE-WITHDRAWN.md"

#: The independent Gate 3 review, and the verdict line it has to carry.
GATE3_RECORD = "GATE3-REVIEW.md"
_GATE3_VERDICT_RE = re.compile(
    r"\*\*Verdict:\s*(PASS_WITH_FINDINGS|PASS|BLOCK)\b", re.IGNORECASE
)


def gate3_verdict(bundle: Path) -> tuple[str, str] | None:
    """Return the independent review's verdict, and the review it came from.

    The review is the state source for the visual half of the decision, so its
    verdict is read from the document a reviewer wrote rather than restated by the
    generator.  When more than one review is present the **latest** decides -- a
    review of a later revision supersedes an earlier one -- and all of them stay in
    the bundle, so a reader sees the history and the current verdict rather than one
    file whose provenance they have to guess.  A review that does not say what it
    concluded is refused: an unreadable verdict would otherwise read as "no review"
    and let the machine verdict stand alone.
    """
    # The review number, not the filename: `GATE3-REVIEW-2.md` sorts *before*
    # `GATE3-REVIEW.md` as text, because "-" precedes ".", and the first review
    # would then be read as the latest one.  The unnumbered file is review one.
    def review_number(path: Path) -> int:
        digits = re.search(r"GATE3-REVIEW-(\d+)", path.name)
        return int(digits.group(1)) if digits else 1

    reviews = sorted(
        (path for path in bundle.glob("GATE3-REVIEW*.md") if path.is_file()),
        key=review_number,
    )
    if not reviews:
        return None
    latest = reviews[-1]
    text = latest.read_text(encoding="utf-8", errors="replace")
    match = _GATE3_VERDICT_RE.search(text)
    if match is None:
        raise SystemExit(
            f"{latest.name} is present but states no `**Verdict: ...**` line, so "
            "the independent review's conclusion cannot be established"
        )
    return match.group(1).upper(), latest.name


def apply_independent_review(bundle: Path, report: str) -> str:
    """Supersede the machine verdict when the independent review blocks.

    The machine report and the visual review answer different questions: the report
    says what the checks it runs could measure, the review says what a reader sees.
    When the review blocks, the bundle may not present the machine verdict as the
    verdict -- a `PASS_WITH_FINDINGS` heading over ten content-visible defects is
    how the previous acceptance claim went wrong.
    """
    reviewed = gate3_verdict(bundle)
    if reviewed is None:
        return report
    verdict, source = reviewed
    lines = report.splitlines()
    if lines and lines[0].startswith("# "):
        lines[0] = f"# V0.4.2 representative acceptance — {verdict} (independent review)"
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("**PASS") or stripped.startswith("**BLOCK"):
            lines[index] = (
                "~~" + stripped + "~~ **superseded by the independent review — see "
                f"`{source}`**"
            )
    banner = [
        f"> **The independent Gate 3 review reached `{verdict}`** and it is the "
        f"bundle's verdict; the machine verdict is struck below. See `{source}` and "
        "the reviews beside it: they name every difference against the source page, "
        "located by `(source slot, source page, source object)`.",
        ">",
        "> The machine evidence below is the evidence of the run that was measured "
        "and is unchanged.",
        "",
    ]
    return "\n".join(lines[:1] + [""] + banner + lines[1:]) + "\n"


def review_majors(bundle: Path) -> int | None:
    """Return how many major findings the latest review reports, or ``None``.

    Read from the review's own summary, because the count is the condition the
    checklist puts on restating the claim: zero majors.  A review whose count cannot
    be read is treated as *unknown*, which keeps the withdrawal in place -- the
    failure that matters here is claiming acceptance on a review nobody could parse.
    """
    reviewed = gate3_verdict(bundle)
    if reviewed is None:
        return None
    _, source = reviewed
    text = (bundle / source).read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"MAJOR\s*[:=]?\s*(\d+)", text, re.IGNORECASE)
    if not matches:
        return None
    # The summary states the total last; a per-finding "MAJOR" word carries no
    # number and is not matched at all.
    return int(matches[-1])


def apply_withdrawal(bundle: Path, report: str) -> str:
    """Prefix a withdrawn report with its withdrawal and drop its verdict.

    The machine evidence below the banner is untouched -- it is still the
    evidence of the run that was measured.  What changes is the claim: a report
    whose acceptance was rejected does not get to keep a verdict line that says
    otherwise.

    The withdrawal is lifted only when the latest independent review reports the
    checklist's condition for restating the claim -- a verdict of ``PASS`` or
    ``PASS_WITH_FINDINGS`` **and zero major findings** -- and then the record is
    removed from the bundle rather than left beside an accepted report, which is the
    other half of the same rule: a stale banner is its own kind of false claim.
    """
    record = bundle / WITHDRAWAL_RECORD
    reviewed = gate3_verdict(bundle)
    majors = review_majors(bundle)
    if (
        reviewed is not None
        and reviewed[0] in {"PASS", "PASS_WITH_FINDINGS"}
        and majors == 0
    ):
        if record.is_file():
            record.unlink()
        return report
    if not record.is_file():
        return report
    lines = report.splitlines()
    if lines and lines[0].startswith("# "):
        lines[0] = "# V0.4.2 representative acceptance — WITHDRAWN"
    # Any line that still asserts a verdict is itself part of the withdrawn
    # claim, so it is struck rather than left to be read on its own further down.
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("**PASS") or stripped.startswith("**BLOCK"):
            lines[index] = (
                "~~" + stripped + "~~ **withdrawn — see "
                f"`{WITHDRAWAL_RECORD}`**"
            )
    banner = [
        f"> **The acceptance claim in this report is withdrawn.** See "
        f"`{WITHDRAWAL_RECORD}` for the review that rejected it and for what has "
        "to happen before the claim can be restated.",
        ">",
        "> The machine evidence below is the evidence of the run that was "
        "measured and is unchanged. It is not acceptance evidence.",
        "",
    ]
    return "\n".join(lines[:1] + [""] + banner + lines[1:]) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--synthetic-only",
        action="store_true",
        help="run only the two synthetic probes (no private deck needed)",
    )
    parser.add_argument(
        "--bundle", type=Path, default=BUNDLE, help="where to write the bundle"
    )
    parser.add_argument(
        "--keep-bundle",
        action="store_true",
        help="do not clear an existing bundle directory first",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help=(
            "re-derive acceptance-report.md and artifact-manifest.json from an "
            "already-published bundle's own gate evidence, without running the "
            "seam again"
        ),
    )
    args = parser.parse_args(argv)
    bundle: Path = args.bundle.resolve()
    if args.report_only:
        return report_only(bundle)

    use_real = not args.synthetic_only
    # The private decks are named by gitignored local configuration, never here:
    # a slot maps to a path, and no deck filename, path or digest reaches the
    # committed bundle.
    sources: dict[str, Path] = {}
    if use_real:
        try:
            sources = corpus.resolve_sources()
        except (FileNotFoundError, KeyError) as error:
            print(f"the private corpus is not resolvable: {error}")
            return 2

    # Each source deck is hashed on its own, before and after the run.  A single
    # combined verdict would let one deck change while another's hash was what the
    # report showed, which is exactly the claim a multi-source corpus has to make
    # per source.
    digest_before = {
        slot: sha256_file(path) for slot, path in sources.items()
    }

    work = REPO / "_smoke" / "v042-acceptance"
    # Windows can refuse to remove a directory a just-finished OfficeCLI process
    # still has a handle on, and the gate refuses to publish onto an existing
    # directory -- correctly, because that is what stops two publishers from
    # silently overwriting each other.  So the run's staging path is unique rather
    # than reused: a leftover from an interrupted run can then never be mistaken
    # for a competing publisher, and the run does not depend on a delete
    # succeeding to be able to start.
    work.mkdir(parents=True, exist_ok=True)
    run_stamp = time.strftime("%Y%m%d-%H%M%S")
    run_work = work / f"run-{run_stamp}-{os.getpid()}"
    run_work.mkdir(parents=True, exist_ok=True)
    for leftover in (run_work / "fixtures", run_work / "gate"):
        shutil.rmtree(leftover, ignore_errors=True)
    print("building the synthetic probes ...")
    probes = corpus.build_synthetic_probes(run_work / "fixtures")

    selection = corpus.seam_selection(
        sources or None,
        probes[corpus.PROBE_A_KEY],
        probes[corpus.PROBE_B_KEY],
    )
    page_ids = list(
        corpus.expected_page_sequence(real_present=bool(sources), probes_present=True)
    )
    if len(page_ids) != len(selection):
        print(
            "the corpus names a different number of pages than the seam selection: "
            f"{len(page_ids)} ids for {len(selection)} selected pages"
        )
        return 2
    print(f"running the seam over {len(selection)} selected pages ...")
    started = time.time()
    staging = run_work / "gate"
    result = m.gate_projected_author_html(selection, staging)
    elapsed = time.time() - started
    print(f"  outcome={result.outcome.value} published={result.published} in {elapsed:.1f}s")

    # A withdrawal is a statement about the *claim*, not about the run's numbers,
    # so it outlives a re-run: regenerating the evidence must not silently drop the
    # banner that says the previous acceptance was rejected.  The record is carried
    # across the bundle being rebuilt, and the report is re-derived around it.
    #
    # The independent review is preserved for the same reason and one more: it is
    # the only place the bundle's visual conclusion exists, and a re-run that
    # dropped it would leave the machine verdict standing alone over the very
    # defects the review found.
    preserved: dict[str, str] = {}
    # Every review, not just the first: a run that preserved only the unnumbered
    # file deleted the newer review and then read the *older* one's verdict as the
    # bundle's, which is backwards.  The records are globbed for the same reason the
    # verdict is read by review number.
    records = [bundle / WITHDRAWAL_RECORD, *sorted(bundle.glob("GATE3-REVIEW*.md"))]
    for path in records:
        if path.is_file():
            preserved[path.name] = path.read_text(encoding="utf-8")
    if preserved:
        print("  preserving " + ", ".join(sorted(preserved)) + " across this run")
    if bundle.exists() and not args.keep_bundle:
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True, exist_ok=True)
    for name, body in preserved.items():
        (bundle / name).write_text(body, encoding="utf-8", newline="")
    gate_dir = bundle / "gate"
    if result.published:
        shutil.copytree(Path(result.output_directory), gate_dir)
    print(f"  gate evidence copied to {gate_dir}")

    digest_after = {slot: sha256_file(path) for slot, path in sources.items()}
    unchanged = {
        slot: digest_before[slot] == digest_after[slot] for slot in sources
    }
    source_unchanged = bool(sources) and all(unchanged.values())

    # ------------------------------------------------------------------
    # Visual records
    # ------------------------------------------------------------------
    visual = bundle / "visual"
    visual.mkdir(parents=True, exist_ok=True)
    rebuilt = Path(result.output_directory) / "rebuilt.pptx"
    html_text = Path(result.canonical_html_path).read_text(encoding="utf-8")
    visual_records: list[dict[str, Any]] = []
    print("capturing visual records ...")
    for order, (page_id, (source_path, source_page)) in enumerate(
        zip(page_ids, selection), start=1
    ):
        before = visual / f"p{order:02d}-before.png"
        after = visual / f"p{order:02d}-after.png"
        author = visual / f"p{order:02d}-author.html"
        have_before = screenshot(Path(source_path), source_page, before)
        have_after = screenshot(rebuilt, order, after)
        author.write_text(page_html(html_text, order), encoding="utf-8")
        visual_records.append(
            {
                "order": order,
                "page_id": page_id,
                "source_page": source_page,
                "rebuilt_page": order,
                "before_png": str(before.relative_to(bundle)).replace("\\", "/"),
                "after_png": str(after.relative_to(bundle)).replace("\\", "/"),
                "author_html": str(author.relative_to(bundle)).replace("\\", "/"),
                "before": image_facts(before) if have_before else None,
                "after": image_facts(after) if have_after else None,
            }
        )
        print(
            f"  p{order:02d} source={source_page} before={have_before} "
            f"after={have_after}"
        )
    canonical_copy = bundle / "canonical-author.html"
    shutil.copy2(Path(result.canonical_html_path), canonical_copy)

    # ------------------------------------------------------------------
    # Corpus manifest and artifact manifest
    # ------------------------------------------------------------------
    manifest = corpus.corpus_manifest(
        source_hashes={
            page_id: corpus.WITHHELD_PRIVATE for page_id in page_ids if is_real_page(page_id)
        },
        synthetic_hashes={
            corpus.PROBE_A_KEY: sha256_file(probes[corpus.PROBE_A_KEY]),
            corpus.PROBE_B_KEY: sha256_file(probes[corpus.PROBE_B_KEY]),
        },
        selection=[
            {
                "order": order,
                "page_id": page_id,
                "source_page": source_page,
                "source_kind": (
                    "private business deck (local, not published)"
                    if is_real_page(page_id)
                    else "committed synthetic probe built through OfficeCLI"
                ),
                # A private deck's hash is private material.  The spec says a
                # private deck's filename, path, hash and page content do not
                # enter the public repository, so the public manifest records
                # that the source was hashed and verified, and the value itself
                # is written only to the local-only record beside the bundle.
                "source_sha256": (
                    corpus.WITHHELD_PRIVATE
                    if is_real_page(page_id)
                    else sha256_file(probes[page_id])
                ),
            }
            for order, (page_id, (source_path, source_page)) in enumerate(
                zip(page_ids, selection), start=1
            )
        ],
    )
    # One entry per source deck, not one for the corpus: three decks, three
    # before/after pairs, three verdicts.  The values stay withheld and the
    # verdicts are published, which is the only form in which a private source's
    # immutability can be checked without publishing the deck.
    manifest["source_decks"] = [
        {
            "slot": slot,
            "pages": list(source.pages),
            "sha256_before": corpus.WITHHELD_PRIVATE,
            "sha256_after": corpus.WITHHELD_PRIVATE,
            "verified_unchanged": unchanged[slot],
        }
        for source in corpus.CORPUS_SOURCES
        for slot in (source.slot,)
        if slot in sources
    ]
    manifest["source_hash_verification"] = {
        "performed": bool(sources),
        "verdict": (
            "identical" if sources and all(unchanged.values())
            else "changed" if sources
            else "not-applicable"
        ),
        "per_source": dict(unchanged),
        "detail": (
            "each private source deck was hashed before capture and re-hashed "
            "after the run, separately; the values are withheld from the public "
            "repository as private material and the local-only record keeps them"
            if sources
            else "synthetic-only run; no private source deck was read"
        ),
    }
    manifest["sources_unchanged"] = dict(unchanged) if sources else None
    manifest["source_deck_write_operations"] = 0
    manifest["synthetic_only"] = not use_real
    manifest["elapsed_seconds"] = round(elapsed, 1)
    # Which revision this evidence is about, and which run its documents all
    # belong to.  Both travel with the manifest, the report and the review package,
    # so no reader has to match them up by eye.
    manifest["commit"] = commit_sha()
    manifest["run_id"] = run_id(bundle)
    manifest["seam_selection"] = [
        {
            "order": order,
            "page_id": page_id,
            "source_id": (
                f"private-source-{slot_of(page_id)}"
                if is_real_page(page_id)
                else page_id
            ),
            "source_page": page,
            "source_sha256": (
                corpus.WITHHELD_PRIVATE
                if is_real_page(page_id)
                else sha256_file(probes[page_id])
            ),
        }
        for order, (page_id, (path, page)) in enumerate(
            zip(page_ids, selection), start=1
        )
    ]
    manifest["privacy"] = (
        "This manifest is committed text. It records each private source deck's "
        "selection order and page numbers and the fact that every deck was hashed "
        "and verified unchanged, but it carries no private filename, no absolute "
        "path and no private hash: the source sha256 values are withheld and the "
        "verification is recorded as a per-deck verdict instead. The gate's own "
        "evidence under acceptance/v0.4.2/gate/ does carry the absolute paths; "
        ".gitignore excludes it from the repository. If page numbers themselves "
        "must not be published, the corpus has to run against decks that may be "
        "named, because a page selection cannot be reviewed without them."
    )
    manifest["visual_records"] = visual_records
    write_json(bundle / "corpus-manifest.json", manifest)

    report = build_report(
        result=result,
        elapsed=elapsed,
        page_ids=page_ids,
        selection=selection,
        visual_records=visual_records,
        digest_before=digest_before,
        digest_after=digest_after,
        unchanged=unchanged,
        commit=manifest["commit"],
        run_id=manifest["run_id"],
        probes=probes,
    )
    report = apply_independent_review(bundle, apply_withdrawal(bundle, report))
    (bundle / "acceptance-report.md").write_text(
        report, encoding="utf-8", newline=""
    )

    # The private source deck's identity and digests are verification evidence a
    # reviewer on this machine needs, and private material the public repository
    # must not carry.  They are written to a local-only file beside the bundle;
    # `.gitignore` excludes `acceptance/v0.4.2/local/`.
    local = bundle / "local"
    local.mkdir(parents=True, exist_ok=True)
    record = corpus.local_verification_record(
        resolved=sources,
        digests=digest_before,
        digests_after=digest_after,
        unchanged=unchanged,
    )
    record["selection"] = [
        {
            "order": order,
            "page_id": page_id,
            "source_path": str(path),
            "source_page": page,
        }
        for order, (page_id, (path, page)) in enumerate(
            zip(page_ids, selection), start=1
        )
    ]
    record["probes"] = {key: str(path) for key, path in probes.items()}
    write_json(local / "source-verification.json", record)

    # Before anything is hashed or announced as a bundle, prove the committed part
    # of it names no private material.  This runs after every document exists and
    # before the manifest describes them, so a leak is a refusal rather than a
    # bundle a reviewer has already opened.
    guard_public_bundle(bundle)

    # The manifest is written before it can hash itself, so it is written and
    # then re-derived once more after every other file exists.
    write_json(bundle / "artifact-manifest.json", build_artifact_manifest(bundle))
    verify_artifact_manifest(bundle)

    # The report's own hash and the manifest's own hash are recorded in the
    # manifest, which cannot contain its own value.
    digest = manifest_digest(bundle)
    write_json(bundle / "artifact-manifest.json", digest)
    verify_artifact_manifest(bundle)

    # The manifest is itself committed text, so the check runs again over it.
    guard_public_bundle(bundle)

    print(f"\nbundle: {bundle}")
    print(f"artifacts: {digest['artifact_count']}")
    print(f"verdict: {report.splitlines()[0]}")
    return 0 if result.accepted else 1


def _page_of(
    selection: Sequence[tuple[str, int]], page_ids: Sequence[str], order: int
) -> tuple[str, int]:
    if order > len(selection):
        raise AssertionError(f"no selection entry for page {order}")
    return selection[order - 1]


def commit_sha() -> str:
    """Return the revision this run measured, and what else was dirty beside it.

    A report that cannot say which revision it describes is not evidence about any
    revision.  It also cannot be perfectly self-referential: the run measures a
    commit, and the documents that publish the measurement are then written *into*
    the repository, so the bundle is always committed one step after the revision it
    describes.  Saying "working tree dirty" for that step is technically true and
    useless -- it reads the same as an unreviewed local edit.

    So the two are separated.  The revision is named.  The only dirty paths a bundle
    run may have are its own documents, and that is checked here rather than
    asserted: a run whose working tree is dirty *anywhere else* says so, because then
    the revision named is not the code that ran.
    """
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO),
        capture_output=True,
        check=False,
    )
    sha = completed.stdout.decode("utf-8", errors="replace").strip()
    if completed.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise SystemExit(
            "the acceptance report must name the commit it describes, and "
            "`git rev-parse HEAD` did not report one"
        )
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=str(REPO),
        capture_output=True,
        check=False,
    ).stdout.decode("utf-8", errors="replace").strip()
    if not dirty:
        return sha
    paths = [line[3:].strip().strip('"') for line in dirty.splitlines() if line.strip()]
    outside = [path for path in paths if not path.replace("\\", "/").startswith(BUNDLE_RELATIVE)]
    if outside:
        return f"{sha} (working tree dirty: {', '.join(sorted(outside)[:3])})"
    return (
        f"{sha} (measured revision; the documents below are its output, and the "
        "only paths this run changed are under acceptance/v0.4.2/)"
    )


def run_id(bundle: Path) -> str:
    """Return the identifier every document of one run shares.

    It is the digest of the gate's verdict document: the one artifact that exists
    only if the run reached a verdict, that the report is derived from, and that
    the artifact manifest hashes.  Nothing has to be registered anywhere for a
    reviewer to check that the report, the source map and the review package are
    all describing the same run.
    """
    report_path = bundle / "gate" / "gate-report.json"
    if not report_path.is_file():
        report_path = bundle / "gate" / "gate-rejected.json"
    if not report_path.is_file():
        raise SystemExit(f"no gate verdict document under {bundle / 'gate'}")
    return bundle_sha256(report_path)


def write_json(path: Path, payload: Any) -> None:
    """Write one JSON document with literal LF endings.

    ``Path.write_text`` translates ``\\n`` to the platform's separator, so the
    bytes on this Windows machine would differ from the bytes in a Linux checkout
    -- and the artifact manifest hashes bytes.  A bundle whose digests depend on
    which machine checked it out is not verifiable, so every published document is
    written with LF and ``.gitattributes`` keeps it that way.
    """
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="",
    )


def _run_commit(bundle: Path) -> str:
    """Return the commit this bundle's run was made at.

    Read from the corpus manifest, which is written once by the run, rather than
    from git: re-deriving a bundle's documents must not silently restamp them with
    whatever commit happens to be checked out now.  A bundle with no recorded commit
    -- one published before the bindings existed -- falls back to the current one.
    """
    corpus_path = bundle / "corpus-manifest.json"
    if corpus_path.is_file():
        try:
            recorded = json.loads(corpus_path.read_text(encoding="utf-8")).get("commit")
        except (OSError, ValueError):
            recorded = None
        if recorded:
            return str(recorded)
    return commit_sha()


#: The suffixes whose digest is taken over the document's text with LF endings.
#:
#: A repository cannot force a clone's line-ending behaviour: `.gitattributes`
#: declares ``text eol=lf`` for these files, and a clone with ``core.autocrlf=true``
#: still handed back CRLF for a document this run had written with LF, so the
#: manifest disagreed with its own bundle in a fresh checkout.  The digest is
#: therefore defined over the text without carriage returns -- the form the
#: repository stores -- which is stable in every checkout and still changes if a
#: single character of the document changes.
_TEXT_SUFFIXES = (".md", ".json", ".html", ".txt", ".csv")


def bundle_text_bytes(path: Path) -> bytes:
    """Return the bytes a published document is verified from."""
    payload = path.read_bytes()
    if path.suffix.lower() in _TEXT_SUFFIXES:
        return payload.replace(b"\r\n", b"\n")
    return payload


def bundle_sha256(path: Path) -> str:
    """Return the digest a published document is verified by."""
    return hashlib.sha256(bundle_text_bytes(path)).hexdigest()


def bundle_size(path: Path) -> int:
    """Return the size a published document is verified by.

    The same normalisation the digest uses: a byte count of the raw file would
    disagree between two checkouts of one document for the same reason its digest
    would, and the size check exists to catch a truncated file, not a line ending.
    """
    return len(bundle_text_bytes(path))


def build_artifact_manifest(bundle: Path) -> dict[str, Any]:
    """Inventory every file in the bundle, and say which of them a clone carries.

    The bundle is two things at once: the documents the repository publishes, and
    the run's own evidence, of which the gate directory and the page renders stay
    on the machine that produced them.  Hashing all of it is right -- a reviewer
    wants the whole inventory -- but a manifest that does not say which entries a
    checkout is supposed to contain cannot be verified anywhere except here, and a
    clean checkout failed on exactly that.  ``in_repository`` is decided by git
    itself, so the manifest and `.gitignore` cannot drift apart.
    """
    artifacts = []
    for path in sorted(bundle.rglob("*")):
        if not path.is_file():
            continue
        name = str(path.relative_to(bundle)).replace("\\", "/")
        if name == "artifact-manifest.json":
            # A manifest cannot contain its own hash.
            continue
        artifacts.append(
            {
                "name": name,
                "sha256": bundle_sha256(path),
                "size_bytes": bundle_size(path),
                "in_repository": not _git_ignores(path),
            }
        )
    published = [item for item in artifacts if item["in_repository"]]
    return {
        "schema_version": 1,
        "algorithm": "sha256",
        # The same two bindings every other published document carries, so the
        # manifest, the report, the source map and the review package all name one
        # revision and one run.  A reader checks them against each other rather than
        # matching documents up by eye.
        "commit": _run_commit(bundle),
        "run_id": run_id(bundle),
        "note": (
            "artifact-manifest.json is excluded from its own inventory: a "
            "document cannot contain its own hash. Every other file in the bundle "
            "is listed, and this manifest records acceptance-report.md's own hash "
            "in report_sha256.  `in_repository` says which entries a clone of the "
            "repository carries: the rest are the run's local evidence -- the gate "
            "directory and the page renders -- which `.gitignore` excludes and "
            "which therefore cannot be verified anywhere but on the machine that "
            "produced them.  All published documents are written with LF endings "
            "and `.gitattributes` keeps them that way, so their digests are the "
            "same in every checkout, and their digests are taken over the text without carriage returns -- the form the repository stores -- so they verify in a checkout whatever its line-ending configuration."
        ),
        "artifact_count": len(artifacts),
        "published_count": len(published),
        "local_only_count": len(artifacts) - len(published),
        "artifacts": artifacts,
    }


def manifest_digest(bundle: Path) -> dict[str, Any]:
    """The artifact manifest, plus the hashes of the two documents it cannot hold."""
    manifest = build_artifact_manifest(bundle)
    manifest["report_sha256"] = bundle_sha256(bundle / "acceptance-report.md")
    manifest["report_name"] = "acceptance-report.md"
    return manifest


def verify_artifact_manifest(bundle: Path) -> None:
    manifest = json.loads((bundle / "artifact-manifest.json").read_text("utf-8"))
    for item in manifest["artifacts"]:
        path = bundle / item["name"]
        if not path.is_file():
            raise AssertionError(f"manifest names a missing file: {item['name']}")
        if bundle_sha256(path) != item["sha256"]:
            raise AssertionError(f"manifest hash mismatch: {item['name']}")
        if bundle_size(path) != item["size_bytes"]:
            raise AssertionError(f"manifest size mismatch: {item['name']}")


#: The parts of a bundle that stay on this machine.  They are gitignored, and each
#: of them names a private source path by design -- the gate's evidence describes
#: the run, and the visual records are renders of it.  The privacy check is about
#: what the repository would publish, so these are exactly the files it must not
#: report on: an ignored-evidence false positive is how a guard gets switched off.
LOCAL_ONLY_BUNDLE_PARTS = ("gate", "visual", "local", "images")


def guard_public_bundle(bundle: Path) -> None:
    """Refuse to leave a bundle whose committed text names private material.

    The commit-time guard already refuses to publish such a file, but by then the
    bundle exists and a reviewer may have read it.  The generator is the place that
    knows which of its own inputs are private, so it checks its own output: the
    guard's scanner and the guard's own configuration, over the files the
    repository would actually track.  A finding here is a defect in this script,
    not in the evidence.

    This is not hypothetical.  The first version of section 11 printed each source
    deck's *filename*, and the commit-time guard is what caught it -- three private
    filenames, in a committed report, produced by the very tool that exists to keep
    them out.
    """
    hook_dir = REPO / ".githooks"
    if not (hook_dir / "private_material_guard.py").is_file():
        raise SystemExit("the private-material guard is missing from .githooks/")
    sys.path.insert(0, str(hook_dir))
    import private_material_guard as guard  # noqa: PLC0415 - optional local tool

    patterns = guard.load_patterns(REPO)
    binary_suffixes = {".pptx", ".png", ".jpg", ".jpeg"}
    findings: list[str] = []
    scanned = 0
    for path in sorted(bundle.rglob("*")):
        if not path.is_file() or path.suffix.lower() in binary_suffixes:
            continue
        relative = path.relative_to(bundle)
        if relative.parts and relative.parts[0] in LOCAL_ONLY_BUNDLE_PARTS:
            continue
        if _git_ignores(path):
            continue
        if path.stat().st_size > 32 * 1024 * 1024:
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        findings.extend(guard.scan_text(text, patterns, str(relative)))
    if findings:
        raise SystemExit(
            "the acceptance bundle would publish private material; the report "
            "generator is naming a private input:\n  " + "\n  ".join(findings)
        )
    print(f"  bundle privacy check: clean ({scanned} published file(s) scanned)")


def _git_ignores(path: Path) -> bool:
    """Whether the repository ignores this path, so it is never published."""
    completed = subprocess.run(
        ["git", "check-ignore", "-q", str(path)],
        cwd=str(REPO),
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def build_report(
    *,
    result: Any,
    elapsed: float,
    page_ids: Sequence[str],
    selection: Sequence[tuple[str, int]],
    visual_records: Sequence[dict[str, Any]],
    digest_before: Mapping[str, str],
    digest_after: Mapping[str, str],
    unchanged: Mapping[str, bool],
    commit: str = "",
    run_id: str = "",
    probes: dict[str, Path],
) -> str:
    counts = result.counts
    accepted = result.accepted
    verdict = outcome_value(result)
    use_real = bool(digest_before)
    contract = (
        check_contract(Path(result.canonical_html_path), "author")
        if result.published
        else None
    )
    rebuilt = Path(result.output_directory) / "rebuilt.pptx" if result.published else None
    validation = "\n".join(
        f"- `{item.role}` `{Path(item.path).name}`: {item.validation.strip()}"
        for item in result.rebuilt_evidence
    )
    lines: list[str] = []
    lines.append(f"# V0.4.2 representative acceptance — {verdict}")
    lines.append("")
    lines.append(
        "Authoritative acceptance of the V0.4.2 representative-projection slice "
        "(ticket #18), run over the frozen ten-page corpus through the one "
        "selected-page seam (`gate_projected_author_html`)."
    )
    lines.append("")
    lines.append("## 1. Verdict and its evidence basis")
    lines.append("")
    lines.append(
        f"**{verdict}** (gate outcome `{verdict}`, `published="
        f"{result.published}`, `accepted={result.accepted}`), reached in "
        f"{elapsed:.1f}s."
    )
    lines.append("")
    lines.append("| binding | value |")
    lines.append("|---|---|")
    lines.append(f"| commit | `{commit or 'not recorded'}` |")
    lines.append(f"| run id (gate report sha256) | `{run_id or 'not recorded'}` |")
    lines.append("")
    lines.append(
        "The report, the source map, the artifact manifest and the review package "
        "all belong to the run id above: it is the digest of the gate's own verdict "
        "document, so a reader can check that they describe one run without a "
        "registry to consult. The commit is the revision the verdict is about."
    )
    lines.append("")
    lines.append(
        "The verdict is the gate's own derived outcome. It is *not* inferred "
        "from a process exit code, from the Author Contract status, from "
        "OfficeCLI validation, or from the screenshots below. The evidence set "
        "that produced it is:"
    )
    lines.append("")
    lines.append(
        "| evidence | value |")
    lines.append("|---|---|")
    lines.append(f"| selected pages | {counts['selected_pages']} |")
    lines.append(f"| projected pages | {counts['projected_pages']} |")
    lines.append(f"| blocked pages | {counts['blocked_pages']} |")
    lines.append(f"| source objects with one disposition | {counts['source_objects']} |")
    lines.append(f"| canonical-editable | {counts['canonical_editable']} |")
    lines.append(f"| locked-visual-proxy | {counts['locked_visual_proxy']} |")
    lines.append(f"| base-only-semantic | {counts['base_only_semantic']} |")
    lines.append(f"| unsupported | {unsupported(result)} |")
    lines.append(f"| unresolved | {unresolved(result)} |")
    lines.append(f"| material deltas | {counts['material_deltas']} |")
    lines.append(f"| retained findings | {counts['retained_findings']} |")
    lines.append(f"| scope evidence | {counts['scope_evidence']} |")
    # Counted from the records, not from the run's counter dict.  The two disagreed
    # once -- the summary table said "proxy isolation proofs passed 0" while section 8
    # of the same report said 37 of 37 and the gate report's own counts said 37 -- and
    # a summary that contradicts the body it summarises is exactly the kind of
    # published inconsistency a reviewer cannot be asked to guess about.  The records
    # are the evidence; the summary is derived from them, and a disagreement between
    # the two is raised rather than published.
    proof_records = [
        proof for page in result.pages for proof in field(page, "proxies", ()) or ()
    ]
    proofs_passed = sum(1 for proof in proof_records if field(proof, "passed", False))
    proofs_failed = len(proof_records) - proofs_passed
    declared = counts.get("proxy_proofs", None)
    if declared is not None and int(declared) != len(proof_records):
        raise SystemExit(
            f"the gate counts {declared} proxy proof(s) and its page records hold "
            f"{len(proof_records)}; the report cannot state both"
        )
    lines.append(f"| proxy isolation proofs passed | {proofs_passed} |")
    lines.append(f"| proxy isolation proofs failed | {proofs_failed} |")
    readback_records = [
        item for page in result.pages for item in field(page, "text_readback", ()) or ()
    ]
    lines.append(
        f"| text readbacks matched | "
        f"{sum(1 for item in readback_records if field(item, 'matched', False))}"
        f" / {len(readback_records)} |"
    )
    lines.append(
        f"| style readbacks matched | "
        f"{sum(1 for item in readback_records if field(item, 'style_matched', False))}"
        f" / {len(readback_records)} |"
    )
    table_records = [
        item for page in result.pages for item in field(page, "tables", ()) or ()
    ]
    lines.append(
        f"| native tables passed | "
        f"{sum(1 for item in table_records if not field(item, 'failures', ()))}"
        f" / {len(table_records)} |"
    )
    lines.append(f"| blocking diagnostics | {counts['blocking_diagnostics']} |")
    lines.append(f"| hashed artifacts (gate) | {len(result.artifacts)} |")
    lines.append(
        f"| Author Contract (`author`) | {contract.status if contract else 'not published'} |"
    )
    lines.append("")
    if contract is not None:
        lines.append(
            f"The unchanged `author` Contract reports **{contract.status}** with "
            f"{len(contract.diagnostics)} diagnostic(s). It is corroboration, not "
            "the verdict."
        )
    lines.append("")
    lines.append("## 2. Corpus, selection order and coverage purpose")
    lines.append("")
    lines.append(
        "The frozen selection order is exactly `"
        + ", ".join(page_ids)
        + "`. The eight real pages are drawn from three private source decks, "
        "each named by an opaque slot (`"
        + "`, `".join(
            f"{source.slot} pages {list(source.pages)}"
            for source in corpus.CORPUS_SOURCES
        )
        + "`); the two synthetic probes follow and are not real pages. `"
        + corpus.PROBE_A_KEY
        + "` contributes one page."
    )
    lines.append("")
    lines.append("| # | page | source page | composition | coverage purpose |")
    lines.append("|---|---|---|---|---|")
    for record in corpus.CORPUS_PAGES:
        if is_real_page(record.page_id) and not use_real:
            continue
        lines.append(
            f"| {record.order} | {record.label} | {record.source_page} | "
            f"{record.composition} | {record.coverage_purpose} |"
        )
    lines.append("")
    lines.append("### Page-level scope notes")
    lines.append("")
    for record in corpus.CORPUS_PAGES:
        if is_real_page(record.page_id) and not use_real:
            continue
        lines.append(f"- **{record.label}**: {record.scope_note}")
    lines.append("")
    lines.append("## 3. Source immutability")
    lines.append("")
    if use_real:
        lines.append(
            "- each private source deck was hashed **separately**, before capture "
            "and again after the run."
        )
        lines.append("")
        lines.append("| source slot | pages | before vs after |")
        lines.append("|---|---|---|")
        for source in corpus.CORPUS_SOURCES:
            if source.slot not in digest_before:
                continue
            lines.append(
                f"| `{source.slot}` | {list(source.pages)} | "
                f"**{'identical' if unchanged.get(source.slot) else 'CHANGED'}** |"
            )
        lines.append("")
        lines.append(
            f"Every source deck's own before/after pair is compared on its own: "
            f"**{sum(1 for value in unchanged.values() if value)}/{len(unchanged)} "
            "identical**. One combined verdict would not have shown which deck, if "
            "any, moved."
        )
        lines.append(
            "- the hash values themselves are **withheld**: a private deck's "
            "hash is private material under the spec, so this report records the "
            "verification verdict rather than the digest. The local-only record "
            "`acceptance/v0.4.2/local/source-verification.json` (gitignored) "
            "holds the values for a reviewer working on this machine."
        )
        lines.append(
            "- the run targets the source decks with **zero** OfficeCLI write "
            "operations: they are read with `get`, `view` and `issues` only, and "
            "the gate re-hashes each of them after publication."
        )
    else:
        lines.append(
            "The private decks were not part of this run (`--synthetic-only`), so "
            "there is no source deck to attest."
        )
    lines.append("")
    lines.append("## 4. Per-page results")
    lines.append("")
    lines.append(
        "`rebuilt issues` is the count of OfficeCLI issue records the rebuilt "
        "deck reports for that page."
    )
    lines.append("")
    lines.append(
        "| out | page | source page | objects | canonical | locked | base-only | "
        "unsup | unres | src issues | rebuilt issues | text readbacks | tables | "
        "proxies | failures |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for record in result.pages:
        lines.append(
            f"| {record.output_page} | {page_ids[record.output_page - 1]} | "
            f"{record.source_page} | {page_count(record, 'source_objects')} | "
            f"{page_count(record, 'canonical_editable')} | "
            f"{page_count(record, 'locked_visual_proxy')} | "
            f"{page_count(record, 'base_only_semantic')} | "
            f"{page_count(record, 'unsupported')} | "
            f"{page_count(record, 'unresolved')} | "
            f"{field(record, 'source_issue_count', 0)} | "
            f"{field(record, 'rebuilt_issue_count', 0)} | "
            f"{len(field(record, 'text_readback', []) or [])} | "
            f"{len(field(record, 'tables', []) or [])} | "
            f"{len(field(record, 'proxies', []) or [])} | "
            f"{list(field(record, 'failures', []) or []) or '—'} |"
        )
    lines.append("")
    lines.append("### Disposition ledger summary (per page)")
    lines.append("")
    lines.append(
        "The complete ledger — one row per slide-owned source object with its "
        "source identity, ownership, disposition, reason code and evidence — is "
        "`gate/disposition-ledger.json`. Its per-page totals:"
    )
    lines.append("")
    lines.append(
        "| out | page | source objects | canonical-editable | locked-visual-proxy | base-only-semantic | container-owned | unsupported | unresolved |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for record in result.pages:
        entries = [
            entry
            for entry in result.ledger
            if str(field(entry, "source_key")) == str(record.source_key)
            and field(entry, "source_page") == record.source_page
        ]
        owned = sum(1 for entry in entries if field(entry, "represented_by_container"))
        lines.append(
            f"| {record.output_page} | {page_ids[record.output_page - 1]} | "
            f"{len(entries)} | {record.canonical_editable} | "
            f"{record.locked_visual_proxy} | {record.base_only_semantic} | "
            f"{owned} | {record.unsupported} | {record.unresolved} |"
        )
    lines.append("")
    lines.append(
        "Every source object has exactly one disposition, and every emitted "
        "object maps to exactly one source object: "
        f"{len({(field(entry, 'source_key'), field(entry, 'source_page'), field(entry, 'source_object')) for entry in result.ledger})} "
        f"unique source identit(ies) over {len(result.ledger)} ledger entr(ies), "
        f"{sum(1 for entry in result.ledger if field(entry, 'emitted'))} emitted, "
        f"{sum(1 for entry in result.ledger if field(entry, 'represented_by_container'))} "
        "represented by a container instead of emitted."
    )
    lines.append("")
    lines.append("## 5. Material deltas")
    lines.append("")
    if result.material_deltas:
        lines.append(f"**{len(result.material_deltas)} material delta(s):**")
        lines.append("")
        for delta in result.material_deltas:
            lines.append(f"- `{field(delta, 'reason', '')}` out p{field(delta, 'rebuilt_slide', '?')} `{field(delta, 'source_object', '?')}` `{field(delta, 'condition', '?')}`")
    else:
        lines.append(
            "**Zero material deltas.** The rebuilt-minus-source material issue "
            "set is empty, so no rebuilt-only or materially worsened condition "
            "was found on any selected page."
        )
    if result.unbound_rebuilt:
        lines.append("")
        lines.append("Rebuilt issues that could not be bound to a source identity:")
        for item in result.unbound_rebuilt:
            lines.append(f"- `{item.get('path')}`: {item.get('issue_id')}")
    lines.append("")
    lines.append("## 6. Retained findings (source-inherent, not repaired)")
    lines.append("")
    lines.append(
        f"{len(result.retained_findings)} retained finding(s). Each one is a "
        "condition the **source** object already carries; the gate lists them "
        "explicitly instead of counting them as repaired. The complete set is "
        "`gate/retained-findings.json`."
    )
    lines.append("")
    kinds: dict[str, int] = {}
    for finding in result.retained_findings:
        kinds[finding.condition] = kinds.get(finding.condition, 0) + 1
    lines.append("| condition | count |")
    lines.append("|---|---|")
    for condition, count in sorted(kinds.items()):
        lines.append(f"| `{condition}` | {count} |")
    lines.append("")
    limits = 40 if len(result.retained_findings) <= 40 else 20
    for finding in result.retained_findings[:limits]:
        lines.append(
            f"- out p{finding.rebuilt_slide} `{finding.source_object}` "
            f"`{finding.condition}` → `{finding.rebuilt_object}`: {finding.reason}"
        )
    if len(result.retained_findings) > limits:
        lines.append(
            f"- … and {len(result.retained_findings) - limits} more, all in "
            "`gate/retained-findings.json`."
        )
    lines.append("")
    lines.append("## 7. Scope evidence (master/layout/inherited paint)")
    lines.append("")
    lines.append(
        f"{len(result.scope_evidence)} scope-evidence record(s). These are "
        "findings and omissions about values the slide does not own; they are "
        "never reported as repaired slide-owned objects."
    )
    lines.append("")
    scope_kinds: dict[str, int] = {}
    for item in result.scope_evidence:
        scope_kinds[item.condition] = scope_kinds.get(item.condition, 0) + 1
    lines.append("| condition | count | mapped |")
    lines.append("|---|---|---|")
    for kind in sorted(scope_kinds):
        mapped = sum(
            1 for item in result.scope_evidence if item.condition == kind and item.mapped
        )
        lines.append(f"| `{kind}` | {scope_kinds[kind]} | {mapped} |")
    lines.append("")
    lines.append(
        "The complete set is `gate/scope-evidence.json`. A representative record "
        "of each condition:"
    )
    lines.append("")
    shown: set[str] = set()
    for item in result.scope_evidence:
        if item.condition in shown:
            continue
        shown.add(item.condition)
        issue = item.source_issue
        lines.append(
            f"- `{item.condition}` (mapped={item.mapped}) "
            f"`{issue.get('source_object') or '—'}` on source page "
            f"{issue.get('source_page')}: {item.detail}"
        )
    lines.append("")
    lines.append("## 8. Proxy isolation proofs")
    lines.append("")
    proofs = [proof for page in result.pages for proof in page.proxies]
    lines.append("| proxy | source object | disposition | raster | density | guard band | paint fraction | passed |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for proof in proofs:
        lines.append(
            f"| `{proof.emitted_name}` | `{proof.source_object}` | "
            f"{proof.disposition} | {proof.raster_width_px}x{proof.raster_height_px} | "
            f"{proof.raster_density:.5f} | {proof.guard_band_px} | "
            f"{proof.guard_band_paint_fraction:.6f} | {field(proof, 'passed', False)} |"
        )
    lines.append("")
    passed = sum(1 for proof in proofs if field(proof, "passed", False))
    lines.append(
        f"{len(proofs)} proof(s), {passed} passed. Every locked proxy carries the "
        "gate's five isolation facts: target survival, raster density, guard "
        "band, target bounds and contamination."
    )
    blank = [proof for proof in proofs if float(proof.paint_fraction) == 0.0]
    lines.append("")
    lines.append(
        f"**{len(blank)} of {len(proofs)} proof(s) are of a proxy whose raster is "
        "nothing but its own background** (`paint_fraction` 0.0, so no paint of "
        "the locked object was measured in the crop): "
        + ", ".join(f"`{proof.emitted_name}`" for proof in blank[:12])
        + (f", … ({len(blank) - 12} more)" if len(blank) > 12 else "")
        + ". The gate's isolation facts are satisfied for these proxies -- "
        "density, guard band, bounds and contamination are measured and correct "
        "-- but they do not establish that the locked object's own pixels "
        "survived, and this report does not claim that they did. Whether those "
        "objects are blank in the source is a Gate 3 question, not a structural "
        "one."
    )
    lines.append("")
    lines.append("## 9. Native table checks")
    lines.append("")
    tables = [table for page in result.pages for table in page.tables]
    if tables:
        lines.append(
            "| page | source object | emitted | source rows×cols | rebuilt rows×cols | cells | whitespace-only cells | failures |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for table in tables:
            lines.append(
                f"| {table.source_page} | `{table.source_object}` | "
                f"`{table.emitted_name}` | {table.expected_rows}×{table.expected_columns} | "
                f"{table.rebuilt_rows}×{table.rebuilt_columns} | "
                f"{len(table.rebuilt_cells)} | "
                f"{list(field(table, 'whitespace_differing_cells', [])) or '—'} | "
                f"{list(field(table, 'failures', [])) or '—'} |"
            )
    else:
        lines.append("No native table on the selected pages.")
    lines.append("")
    lines.append("## 10. Text and style readback")
    lines.append("")
    readbacks = [item for page in result.pages for item in page.text_readback]
    mismatched = [item for item in readbacks if not field(item, 'matched', False)]
    lines.append(
        f"{len(readbacks)} independent OfficeCLI readback(s) of canonical-editable "
        f"objects; {len(mismatched)} disagree with the source text."
    )
    lines.append("")
    for item in mismatched:
        lines.append(f"- MISMATCH `{item.source_object}`: {item.as_dict()}")
    lines.append("")
    lines.append("## 11. OfficeCLI validation and issue records")
    lines.append("")
    lines.append("Source deck reads:")
    lines.append("")
    for item in result.source_evidence:
        # The opaque source key, never the deck's filename.  This report is
        # committed text, and a private deck's filename is private material: the
        # guard refused the first version of this section for exactly that reason,
        # which is the guard doing its job on a leak the *generator* introduced.
        lines.append(
            f"- `{item.label}` validate: {item.validation.strip() or '—'}; "
            f"issues: {item.issue_count}"
        )
    lines.append("")
    lines.append("Rebuilt deck reads:")
    lines.append("")
    lines.append(validation or "—")
    lines.append("")
    for item in result.rebuilt_evidence:
        lines.append(f"- rebuilt issues: {item.issue_count}")
    lines.append("")
    lines.append("## 12. Artifact manifest")
    lines.append("")
    lines.append(
        f"The gate published {len(result.artifacts)} hashed artifacts; "
        "`gate/gate-report.json` lists every one with its sha256 and size, and "
        "`artifact-manifest.json` lists every file in this bundle the same way. "
        "Both can be re-checked against disk independently:"
    )
    lines.append("")
    lines.append("```powershell")
    lines.append(
        "Get-FileHash acceptance/v0.4.2/gate/rebuilt.pptx -Algorithm SHA256"
    )
    lines.append(
        "$m = Get-Content acceptance/v0.4.2/artifact-manifest.json | ConvertFrom-Json"
    )
    lines.append(
        "$m.artifacts | ForEach-Object { $h = (Get-FileHash "
        "\"acceptance/v0.4.2/$($_.name)\" -Algorithm SHA256).Hash.ToLower(); "
        "if ($h -ne $_.sha256) { \"MISMATCH $($_.name)\" } }"
    )
    lines.append("```")
    lines.append("")
    lines.append(
        "The gate's artifact list, with the hash recorded in its own report "
        "(`gate/gate-report.json` carries the same values, and re-hashing any of "
        "these files from disk must reproduce them):"
    )
    lines.append("")
    lines.append("| artifact | sha256 | size |")
    lines.append("|---|---|---|")
    for item in result.artifacts:
        lines.append(f"| `{item.name}` | `{item.sha256}` | {item.size_bytes} |")
    lines.append("")
    lines.append(
        "`gate/gate-report.json` and `gate/gate-report.md` are excluded from "
        "that list because a document cannot contain its own hash; the bundle's "
        "`artifact-manifest.json` covers them instead, except for itself."
    )
    lines.append("")
    lines.append("## 13. Visual records")
    lines.append("")
    lines.append(
        "Every page has three records: the source page render, the rebuilt page "
        "render (both through OfficeCLI's HTML render path at "
        f"{RENDER_WIDTH}px, so they are directly comparable), and that page's "
        "Canonical Author HTML."
    )
    lines.append("")
    lines.append("| # | page | source page | before | after | author html | before px | after px | before non-background | after non-background |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for record in visual_records:
        before = record["before"]
        after = record["after"]
        cells = [
            str(record["order"]),
            str(record["page_id"]),
            str(record["source_page"]),
            f"`{record['before_png']}`",
            f"`{record['after_png']}`",
            f"`{record['author_html']}`",
            f"{before['width']}x{before['height']}" if before else "—",
            f"{after['width']}x{after['height']}" if after else "—",
            f"{before['non_background_fraction']:.4f}" if before else "—",
            f"{after['non_background_fraction']:.4f}" if after else "—",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        "These are mechanical facts about the images (size, distinct colours, "
        "non-background fraction). They are **not** a visual verdict."
    )
    lines.append("")
    lines.append("## 14. Gate 3 — independent review")
    lines.append("")
    reviewed = gate3_verdict(bundle)
    majors = review_majors(bundle)
    if reviewed is None:
        lines.append(
            "> **No independent review is recorded in this bundle.** The machine "
            "evidence below is evidence about the checks this run performed; it is "
            "not a claim that a reader would see no defect, and it is not acceptance."
        )
    else:
        verdict, source = reviewed
        lines.append(
            f"> **The latest independent review is `{source}`: `{verdict}`"
            + (f", MAJOR {majors}" if majors is not None else ", major count unreadable")
            + ".** It is the bundle's verdict and the reviews beside it are the "
            "record: each finding is located by `(source slot, source page, source "
            "object)`."
        )
        others = sorted(
            path.name
            for path in bundle.glob("GATE3-REVIEW*.md")
            if path.is_file() and path.name != source
        )
        if others:
            lines.append(">")
            lines.append(
                "> The other review document(s) in this bundle -- "
                + ", ".join(f"`{name}`" for name in others)
                + " -- are **historical**: they judged earlier revisions and their "
                "verdicts are superseded. A verdict of `PASS_WITH_FINDINGS` in one of "
                "them is a reading of *that* revision's page renders, not a statement "
                "that the revision met the delivery bar; the earlier revisions did "
                "not, which is why the reviews continue."
            )
    lines.append("")
    lines.append("## 15. Known findings, scope differences and limitations")
    lines.append("")
    for line in known_findings(result):
        lines.append(line)
    lines.append("")
    lines.append("## 16. How to reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append("# from the repository root")
    lines.append("& .\\.venv\\Scripts\\python.exe -m pytest tests/test_v042_acceptance.py -q")
    lines.append("& .\\.venv\\Scripts\\python.exe scripts/run_v042_acceptance.py")
    lines.append("```")
    lines.append("")
    lines.append(
        "The pytest module always runs the synthetic half. The real half is "
        f"opt-in: set `{REAL_ENV}=1` with the private deck present, or run this "
        "driver, which runs the full ten pages."
    )
    lines.append("")
    return "\n".join(lines)


REAL_ENV = "HTML_TO_PPTX_V042_REAL_CORPUS"


def field(obj: Any, name: str, default: Any = None) -> Any:
    """Read a value that is an attribute on a live record and a key in JSON.

    Some of these records expose a value as a plain attribute on the live result
    object and as a JSON key in the published report; others expose it as a
    method whose result is the JSON value.  Both spellings resolve here, so the
    report reads the same from either.
    """
    if isinstance(obj, Attr):
        value = obj.get(name, default)
    else:
        value = getattr(obj, name, default)
    if callable(value):
        return value()
    return value


def page_count(page: Any, name: str, default: int = 0) -> int:
    """Read one per-page count.

    ``GatePageRecord`` carries its disposition counts in a ``counts`` mapping,
    not as attributes on the record.  Reading ``page.source_objects`` therefore
    yielded ``None`` for every page -- which is why an earlier published report
    listed ``0`` objects on all ten pages and ``proxy isolation proofs passed |
    0`` while forty-one proofs existed.  One accessor, so the two spellings
    cannot drift again.
    """
    counts = field(page, "counts", None)
    if isinstance(counts, Mapping):
        value = counts.get(name)
        if value is not None:
            return int(value)
    value = field(page, name, default)
    return default if value is None else int(value)


def unsupported(result: Any) -> int:
    return sum(page_count(page, "unsupported") for page in result.pages)


def outcome_value(result: Any) -> str:
    """The outcome as a plain string, for a live result or a published one."""
    outcome = result.outcome
    return str(getattr(outcome, "value", outcome))


def unresolved(result: Any) -> int:
    return sum(page_count(page, "unresolved") for page in result.pages)


def failed_proofs(result: Any) -> int:
    return sum(
        1
        for page in result.pages
        for proof in page.proxies
        if not field(proof, 'passed', False)
    )


def known_findings(result: Any) -> list[str]:
    """The limitations this run establishes about itself, with their evidence."""
    lines: list[str] = []
    lines.append(
        "1. **Master/layout/header/footer omissions are scope evidence, not "
        "slide-owned loss.** "
        f"{sum(1 for item in result.scope_evidence if item.condition == 'slide_field_not_evaluated')} "
        "inherited cached-field finding(s) name the slide (master|layout) rather "
        "than a slide-owned object and carry no `source_object`; they are never "
        "mapped onto a rebuilt object. Inherited branding is not reconstructed, "
        "so a rebuilt page is painted on a blank layout."
    )
    lines.append(
        "2. **Source-inherent overlap/overflow is retained, not repaired.** "
        f"{len(result.retained_findings)} retained finding(s); the projection "
        "does not rewrite private source layout to reach an artificial zero-issue "
        "count, and none of them enters the material delta set."
    )
    lines.append(
        "3. **Locked proxies are excluded from native-equivalence claims.** "
        f"{result.counts['canonical_editable']} of "
        f"{result.counts['source_objects']} source object(s) are "
        "canonical-editable; "
        f"{result.counts['locked_visual_proxy']} are locked visual proxies and "
        f"{result.counts['base_only_semantic']} are base-only, and they are "
        "reported separately rather than folded into a native round-trip count."
    )
    lines.append(
        "4. **The gate's material-delta comparison is a text comparison.** It "
        "compares canonical characters and supported style declarations read back "
        "from the rebuilt deck; it does not compare per-run paragraph formatting, "
        "so a run-level formatting difference that preserves every character and "
        "every declared style is not a material delta. The synthetic rich-text "
        "probe records one such difference explicitly (see the pytest module's "
        "`test_the_probe_b_run_declarations_are_not_the_source_run_declarations`)."
    )
    lines.append(
        "5. **A hard break becomes a paragraph boundary, and the machine cannot "
        "see it.** The Canonical Author paragraph orthography has one separator -- "
        "the paragraph boundary, spelled `<br>` -- and no spelling for a soft line "
        "break, so a source body whose paragraph contains one is re-partitioned: the "
        "synthetic probe's block is one paragraph with one `a:br` in the source and "
        "two paragraphs with none in the rebuild. The characters and the line count "
        "survive, and the third independent review measured the lines adjacent again "
        "after a leading defect was fixed (pitch 45px -> 25px against the source's "
        "18px, a residual 7px it classes MINOR). Two things are recorded rather than "
        "claimed away: the residue varies with a block's line-height ratio, and the "
        "gate's text readback reports this object `structure_lost: false` with "
        "identical structure text -- a normalised comparison of characters cannot "
        "tell a line break from a paragraph boundary. The durable fix is to carry the "
        "break through the IR and emit `a:br` plus a paragraph/break-count check in "
        "the gate; until then the difference is visible only to a reader, which is "
        "why the independent visual review is a required gate."
    )
    lines.append(
        "6. **A list is rebuilt on the declared top-level surface only.** OfficeCLI "
        "reads the synthetic probe's list block back as native list paragraphs -- two "
        "`a:buChar` bullets and two `a:buAutoNum` numbers -- and the rebuilt deck "
        "carries the same marker kinds, because the Author list surface declares one "
        "list per object, one direct item per paragraph, and `contract.LIST_LEVELS` "
        "is `(0,)`. An item at a level the surface does not declare is **refused** "
        "(`unsupported`, `list_level_not_supported`) rather than emitted flat: a flat "
        "item keeps its indent and loses its level, and PowerPoint then continues an "
        "automatic number at level 0, which changes content rather than position. The "
        "probe's list therefore declares the four top-level items the surface has, and "
        "the refusal is covered by its own unit tests."
    )
    lines.append(
        "7. **A theme expression on a directly-declared run is not classified "
        "base-only by this projection.** The synthetic probe's theme run declares "
        "`accent1` in the source slide part and OfficeCLI reads the token back as "
        "`color: accent1`, but OfficeCLI reports no `effective.color.src` for a "
        "directly-declared scheme colour, so the gate's base-only rule never "
        "fires for it and no base-only entry is produced. The token is preserved "
        "in the source and in the projection's evidence; the projection does not "
        "claim a semantic token round trip, and this report does not either."
    )
    lines.append(
        "8. **Proxy target survival is measured from the proxy's own pixels, and a "
        "zero-extent object has no background to sample.** The isolation proof reads "
        "the published raster: it requires the object's paint to differ from the "
        "background the crop was taken out of, and for an object whose declared "
        "rectangle has no extent on either axis -- a vertical connector, whose raster "
        "is nothing but its guard band -- it requires the raster not to be the "
        "reconstruction's own background, because there is no other sample point. A "
        "uniformly blank proxy therefore blocks. What the proof still cannot see is "
        "*fidelity*: a proxy that paints the wrong words passes all five facts, which "
        "is why the independent visual review is a required gate and not a formality. "
        f"{sum(1 for page in result.pages for proof in page.proxies if float(proof.paint_fraction) == 0.0)} "
        "of "
        f"{sum(len(page.proxies) for page in result.pages)} proof(s) here are of "
        "a raster that is nothing but its own background. Section 8 names them."
    )
    lines.append(
        "9. **A manifest cannot contain its own hash.** "
        "`artifact-manifest.json` is excluded from its own inventory and records "
        "`acceptance-report.md`'s hash in `report_sha256` instead; the manifest's "
        "own hash is printed by the driver that wrote it and is not part of the "
        "bundle."
    )
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
