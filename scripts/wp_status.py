#!/usr/bin/env python3
"""List work packages, show which ones an agent may start, and check roadmap consistency.

A package is delegable when its file has `Status: ready` and every dependency is `review` or `done`
(reviews are done in batches, see context/review-checklist.md). Roadmap rows without a file are outlines.
Exits 1 if the roadmap and the package files disagree (unknown ids, different dependencies, cycles, bad status).
"""
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "context"
STATUSES = {"draft", "ready", "review", "done"}
SATISFIED = {"review", "done"}
ROW = re.compile(r"^\| (\d{3}) \|[^|]*\|[^|]*\| ([^|]*) \|", re.M)


class Roadmap:
    def __init__(self, docs: Path):
        self.files = {p.name[:6]: p for p in sorted((docs / "work-packages").glob("WP-*.md"))}
        self.rows = {f"WP-{wid}": self._ids(deps) for wid, deps in ROW.findall((docs / "roadmap.md").read_text("utf-8"))}
        self.packages = {wid: self._parse(path) for wid, path in self.files.items()}
        self.errors: list[str] = []

    @staticmethod
    def _ids(text: str) -> list[str]:
        return sorted(f"WP-{n}" for n in re.findall(r"\b(\d{3})\b", text))

    def _parse(self, path: Path) -> tuple[str, list[str]]:
        text = path.read_text("utf-8")
        status = re.search(r"^Status:\s*(\w+)", text, re.M)
        deps = re.search(r"Depends on:\s*([^·\n]+)", text)
        return (status.group(1) if status else "missing"), sorted(re.findall(r"WP-\d{3}", deps.group(1) if deps else ""))

    def check(self) -> None:
        for wid, deps in self.rows.items():
            self.errors += [f"{wid}: roadmap depends on unknown {d}" for d in deps if d not in self.rows]
        for wid, (status, deps) in self.packages.items():
            if status not in STATUSES:
                self.errors.append(f"{wid}: invalid status '{status}'")
            if wid not in self.rows:
                self.errors.append(f"{wid}: file exists but no roadmap row")
            elif deps != self.rows[wid]:
                self.errors.append(f"{wid}: file depends on {deps or '-'}, roadmap on {self.rows[wid] or '-'}")
        self._check_cycles()

    def _check_cycles(self) -> None:
        state: dict[str, int] = {}

        def visit(node: str, trail: list[str]) -> None:
            if state.get(node) == 2:
                return
            if state.get(node) == 1:
                self.errors.append("dependency cycle: " + " -> ".join(trail + [node]))
                return
            state[node] = 1
            for dep in self.rows.get(node, []):
                visit(dep, trail + [node])
            state[node] = 2

        for wid in self.rows:
            visit(wid, [])

    def report(self) -> None:
        def status(wid: str) -> str:
            return self.packages.get(wid, ("outline",))[0]

        delegable, in_review = [], []
        for wid, (st, deps) in self.packages.items():
            waiting = [d for d in deps if status(d) not in SATISFIED]
            if st == "ready" and not waiting:
                delegable.append(wid)
            if st == "review":
                in_review.append(wid)
            print(f"{wid}  {st:6}  waits for: {', '.join(waiting) or '-'}")
        outlines = sorted(set(self.rows) - set(self.packages))
        print(f"\nOutline only (no file, NOT delegable): {', '.join(outlines) or '-'}")
        print(f"Awaiting batch review (context/review-checklist.md): {', '.join(in_review) or '-'}")
        print(f"\nDelegable now: {', '.join(delegable) or 'none - a work package must be written/approved first'}")


def main() -> int:
    roadmap = Roadmap(DOCS)
    roadmap.check()
    roadmap.report()
    if roadmap.errors:
        print("\nRoadmap errors:", *roadmap.errors, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
