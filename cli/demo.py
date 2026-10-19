"""The full LabSync loop in a terminal: request -> held booking -> conflict -> swap -> approvals ->
commit -> supply drafts -> department findings. People decide at every checkpoint: interactively,
or with --auto, where the CLI presses the buttons each persona would press (and says so)."""
import json

from labsync_tools import queries
from labsync_tools import tools as T

CANONICAL = ("I need to image GFP-tagged cells Tuesday morning: three hours on a confocal, a prep room "
             "beforehand, and enough anti-GFP antibody and coverslips. I need the results by Wednesday.")
WEEK = "2026-11-02"


def _hm(ts):
    return ts[11:16]


class Demo:
    def __init__(self, orchestrator, out=print, ask=None, auto=False):
        self.o = orchestrator
        self.out = out
        self.ask = ask or input
        self.auto = auto

    def say(self, text=""):
        self.out(text)

    def section(self, title):
        self.say("")
        self.say("== %s" % title)

    def confirm(self, persona, question, default=True):
        if self.auto:
            self.say("   [auto] %s presses %s" % (persona, "Approve" if default else "Reject"))
            return default
        answer = self.ask("   %s: %s [y/n] " % (persona, question)).strip().lower()
        return answer in ("", "y", "yes") if default else answer in ("y", "yes")

    def choose(self, options):
        if self.auto or len(options) == 1:
            return options[0]
        raw = self.ask("   Pick an option [1-%d] (default 1): " % len(options)).strip() or "1"
        try:
            return options[max(0, min(len(options), int(raw)) - 1)]
        except ValueError:
            return options[0]

    def calendar(self, label):
        rows = queries.get_calendar(self.o.repo, "morgan", ["confocal_1"], "2026-11-03")["rows"]
        self.say("   %s, Confocal-1 Tue Nov 3 (other labs shown as busy):" % label)
        for r in rows:
            who = r["user_id"] or "busy"
            self.say("     %s-%s  %-9s %s" % (_hm(r["start"]), _hm(r["end"]), r["status"], who))

    def run(self, text=CANONICAL):
        o = self.o
        self.say("LabSync local demo · C3 not connected · synthetic data · agents: %s" % getattr(o.client, "name", "?"))

        self.section("1. Morgan (Moreno lab) asks the Lab Agent")
        self.say("   > %s" % text)
        result = o.submit_request("morgan", text)
        if result["status"] != "ok":
            self.say("   %s: %s" % (result["code"], result["message"]))
            return result
        self.say("\n".join("   " + line for line in (result["agent_text"] or "").splitlines()))
        search = result["search"]
        if not search or not search["options"]:
            self.say("   No options to hold; the demo stops here.")
            return result
        plan_id = result["plan_id"]
        self.calendar("Before")

        while True:
            self.section("2. Morgan holds an option (nothing is booked yet)")
            option = self.choose(search["options"])
            prop = o.choose_option("morgan", plan_id, option["option_id"])
            if prop["status"] != "ok":
                self.say("   %s: %s" % (prop["code"], prop["message"]))
                return prop
            self.say("   Held %s %s-%s as %s, state %s" % (option["resource_id"], _hm(option["start"]),
                                                          _hm(option["end"]), prop["proposal_id"], prop["state"]))
            proposal_id = prop["proposal_id"]
            if not prop["contingent_moves"]:
                break
            self.section("3. Morgan asks Chen to move; the Conflict Negotiator advises Chen")
            sent = o.request_moves("morgan", proposal_id, "Could you shift your session so we can image this morning?")
            rejected = False
            for req in sent["requests"]:
                rec = req.get("recommendation") or {}
                out = rec.get("output")
                if out:
                    self.say("   Recommendation for %s: %s" % (req["owner_id"], out["recommendation"].upper()))
                    for reason in out["reasons"]:
                        self.say("     - %s" % reason)
                else:
                    self.say("   No recommendation (%s); Chen decides unaided." % (rec.get("message") or rec.get("errors")))
                self.section("4. Chen decides in the Approvals inbox")
                ok = self.confirm("Chen", "Approve moving %s to %s-%s?" % (
                    req["impact"]["booking_id"], _hm(req["impact"]["to"]["start"]), _hm(req["impact"]["to"]["end"])))
                d = o.decide("chen_owner", req["approval_id"], "approve" if ok else "reject",
                             None if ok else "Chen needs the morning slot")
                self.say("   Decision recorded: %s -> proposal %s" % (d.get("decision"), d.get("entity_state")))
                rejected = rejected or not ok
            if not rejected:
                break
            self.say("   Chen's booking stays. Replanning without moving Chen.")
            search = o.search("morgan", plan_id)
            search["options"] = [x for x in search["options"] if x["kind"] == "direct"] or search["options"]

        self.section("5. Morgan confirms, then commits")
        confirm = next(a for a in o.repo.list_records("Approval")
                       if a["entity_id"] == proposal_id and a["slot_kind"] == "requester_confirm")
        if not self.confirm("Morgan", "Confirm the final schedule?"):
            self.say("   Not confirmed; nothing is booked.")
            return {"status": "ok", "committed": False}
        o.decide("morgan", confirm["approval_id"], "approve")
        commit = o.commit("morgan", proposal_id)
        if commit["status"] != "ok":
            self.say("   Commit failed: %s (%s)" % (commit["code"], commit["message"]))
            return commit
        self.say("   committed. Receipt %s: %s" % (commit["receipt"]["receipt_id"], ", ".join(commit["receipt"]["booking_ids"])))
        self.calendar("After")

        self.section("6. Supplies: drafted for approval, never ordered")
        orders = o.draft_orders("morgan", plan_id)
        for order in orders.get("orders", []):
            self.say("   %s %s x%s: %s" % (order["order_id"], order["sku_id"], order["quantity"],
                                         order["state"].replace("_", " ")))

        self.section("7. Department admin reviews; the Department Optimizer writes cards")
        dept = o.review_department("dept_admin", WEEK)
        if dept["output"]:
            for card in dept["output"]["cards"]:
                self.say("   [%s] %s" % (card["kind"], card["headline"]))
                self.say("     %s %s · %s" % (card["impact"]["value"], card["impact"]["unit"], card["impact"]["label"]))
                self.say("     approvals: %s" % ", ".join(card["requiredApprovals"]))
            for extra in dept["output"]["alsoDetected"]:
                self.say("   also: %s" % extra["note"])
        else:
            self.say("   No cards: %s" % (dept.get("text") or dept.get("errors")))

        request_id = o.repo.get_record("ExperimentPlan", plan_id)["request_id"]
        events = T.audit_get_activity(o.repo, "dept_admin", request_id=request_id)["events"]
        self.section("Audit")
        self.say("   %d audit events for request %s; every approval and commit has an actor, time and before/after."
                 % (len(events), request_id))
        return {"status": "ok", "committed": True, "plan_id": plan_id, "proposal_id": proposal_id,
                "receipt": commit["receipt"], "orders": orders.get("orders", []), "department": dept}


def dump(obj):
    return json.dumps(obj, indent=2, default=str)
