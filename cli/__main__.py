"""python3 -m cli <command>

  demo   [--live] [--auto] [--state PATH | --memory]   full loop (mock agents by default)
  ask    TEXT [--as PERSON] [--live]                     one Lab Agent request
  reset  [--state PATH]                                  restore the seed in the state file
  evals  [--live] [--suite ...]                          run and score the eval suites
"""
import argparse
import sys

from labsync_app.llm import LLMUnavailable, make_client
from labsync_app.orchestrator import Orchestrator
from labsync_app.store import DEFAULT_STATE, FileRepository
from labsync_tools.memory_repo import InMemoryRepository

from .demo import Demo


def _repo(args):
    if getattr(args, "memory", False):
        return InMemoryRepository()
    return FileRepository(args.state)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m cli", description="LabSync local harness (no C3)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "ask", "reset", "evals"):
        p = sub.add_parser(name)
        if name != "reset":
            p.add_argument("--live", action="store_true", help="use the Claude API instead of mock agents")
        if name in ("demo", "ask", "reset"):
            p.add_argument("--state", default=DEFAULT_STATE, help="state file (default var/labsync_state.json)")
        if name in ("demo", "ask"):
            p.add_argument("--memory", action="store_true", help="don't touch the state file")
    sub.choices["demo"].add_argument("--auto", action="store_true", help="press each persona's buttons automatically")
    sub.choices["demo"].add_argument("--keep", action="store_true", help="don't reset to the seed first")
    sub.choices["ask"].add_argument("text")
    sub.choices["ask"].add_argument("--as", dest="actor", default="morgan")
    sub.choices["evals"].add_argument("--suite", action="append")
    args = parser.parse_args(argv)

    if args.command == "evals":
        from evals.run import main as run_evals
        return run_evals((["--live"] if args.live else ["--mock"]) +
                         sum((["--suite", s] for s in args.suite or []), []))
    if args.command == "reset":
        FileRepository(args.state).reset_to_seed()
        print("Reset %s to the imaging_tuesday_v1 seed." % args.state)
        return 0
    try:
        client = make_client("live" if args.live else "mock")
    except LLMUnavailable as exc:
        print("Live mode unavailable: %s" % exc)
        return 2
    repo = _repo(args)
    orch = Orchestrator(repo, client)
    if args.command == "ask":
        result = orch.submit_request(args.actor, args.text)
        print(result.get("agent_text") or result.get("message"))
        return 0 if result["status"] == "ok" else 1
    if not args.keep:
        repo.reset_to_seed()
    result = Demo(orch, auto=args.auto).run()
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
