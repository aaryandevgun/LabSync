/* LabSync local web app. Plain JS, no build step. Screens from docs/07:
   My Lab (#/workspace, #/plans/:id), Approvals (#/approvals), Department (#/intelligence, #/intelligence/insights/:id),
   plus the activity trail (#/activity/:request_id). Every button maps to one API call; the server decides. */
(function () {
  "use strict";

  var CANONICAL = "I need to image GFP-tagged cells Tuesday morning: three hours on a confocal, a prep room " +
    "beforehand, and enough anti-GFP antibody and coverslips. I need the results by Wednesday.";
  var PROMPTS = [
    ["Schedule imaging experiment", CANONICAL],
    ["Use the plate reader", "plate reader for 45 minutes Monday at 10"],
    ["Reorder supplies", "a couple packs of anti-GFP and three boxes of coverslips"]
  ];
  var DAY0 = 9 * 60, DAY1 = 17 * 60;

  var S = { session: null, persona: null, seed: null, buffers: true, selected: {}, lastRun: null, techView: false };
  var view = document.getElementById("view");

  // ------------------------------------------------------------------ helpers
  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function hm(ts) { return ts ? ts.slice(11, 16) : ""; }
  function mins(ts) { var t = hm(ts).split(":"); return +t[0] * 60 + +t[1]; }
  function range(a, b) { return hm(a) + "–" + hm(b); }
  var WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var MO = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function fmtDay(d) {
    if (!d) return "";
    var p = d.slice(0, 10).split("-"), dt = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2]));
    return WD[dt.getUTCDay()] + " " + MO[dt.getUTCMonth()] + " " + dt.getUTCDate();
  }
  function fmtStamp(ts) { return ts ? fmtDay(ts) + " " + ts.slice(11, 19) + " CT" : ""; }
  function usd(n) { return "$" + (Math.round(n * 100) / 100).toLocaleString("en-US"); }
  function pct(x) { return (Math.round(x * 1000) / 10) + "%"; }
  function person(id) {
    var p = S.session && S.session.personas.filter(function (x) { return x.id === id; })[0];
    return p ? p.name : id;
  }
  /** Agent card text names resources by id (flow_2); show the instrument/room name instead. Display only. */
  function named(text) {
    var names = (S.session && S.session.resource_names) || {};
    return Object.keys(names).sort(function (a, b) { return b.length - a.length; }).reduce(function (t, id) {
      return t.replace(new RegExp("\\b" + id + "\\b", "g"), names[id]);
    }, String(text == null ? "" : text));
  }
  function labOf(id) {
    var p = S.session && S.session.personas.filter(function (x) { return x.lab_id === id; })[0];
    return p ? p.lab_name : id;
  }
  function announce(msg) { var l = document.getElementById("live"); l.textContent = ""; setTimeout(function () { l.textContent = msg; }, 30); }
  function toast(msg, err) {
    document.querySelectorAll(".toast").forEach(function (old) { old.remove(); });
    var t = document.createElement("div");
    t.className = "toast" + (err ? " err" : "");
    t.setAttribute("role", err ? "alert" : "status");
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 4200);
    announce(msg);
  }
  var ICON = {
    home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/>',
    chart: '<path d="M3 3v18h18"/><path d="M7 15v-4M12 15V7M17 15v-7"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>',
    pkg: '<path d="m7.5 4.3 9 5.2M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.7z"/><path d="M3.3 7 12 12l8.7-5M12 22V12"/>',
    gauge: '<path d="m12 14 4-4"/><path d="M3.3 19a10 10 0 1 1 17.4 0"/>',
    layers: '<path d="m12 2 10 6-10 6L2 8z"/><path d="m2 16 10 6 10-6"/>',
    activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    arrow: '<path d="M5 12h14M13 5l7 7-7 7"/>',
    send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
    flask: '<path d="M9 3h6M10 3v6L4 20a1 1 0 0 0 .9 1.5h14.2A1 1 0 0 0 20 20L14 9V3"/><path d="M7 15h10"/>',
    spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>'
  };
  function ic(name, size) {
    size = size || 18;
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ICON[name] + "</svg>";
  }
  var KIND_ICON = { pooled_order: "pkg", overload_rebalance: "gauge", underuse: "layers" };

  function api(method, path, body) {
    var opts = { method: method, headers: { "X-LabSync-Persona": S.persona || "" } };
    if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    return fetch(path, opts).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok && data.status !== "error", status: r.status, data: data }; });
    }, function () {
      return { ok: false, status: 0, data: { status: "error", code: "NETWORK", message: "The local server isn't responding." } };
    });
  }
  function errText(d) {
    var msg = d.message || "Something went wrong.";
    if (d.errors && d.errors.length) msg += " " + d.errors.join("; ");
    return (d.code ? d.code + ": " : "") + msg;
  }
  function busy(btn, on, label) {
    if (!btn) return;
    if (on) { btn.dataset.label = btn.innerHTML; btn.disabled = true; btn.innerHTML = esc(label || "Working…"); btn.setAttribute("aria-busy", "true"); }
    else { btn.disabled = false; if (btn.dataset.label) btn.innerHTML = btn.dataset.label; btn.removeAttribute("aria-busy"); }
  }
  function stateBadge(state) {
    var map = {
      draft: ["proposed", "Draft"], pending_approvals: ["awaiting", "Pending approvals"], ready: ["info", "Ready to commit"],
      confirmed: ["committed", "Confirmed"], needs_revision: ["rejected", "Needs a new option"], failed: ["failed", "Failed"],
      owner_approval_pending: ["awaiting", "Awaiting owner approval"], requester_approval_pending: ["awaiting", "Awaiting your confirmation"],
      authorized: ["info", "Approved · not committed"], committed: ["committed", "Committed"], rejected: ["rejected", "Rejected"],
      stale: ["failed", "Stale"], awaiting_lab_approval: ["awaiting", "Proposed · awaiting lab approval"],
      awaiting_fund_approval: ["awaiting", "Awaiting fund authorization"], approved_request: ["approved", "Approved request · not ordered"],
      detected: ["proposed", "Proposed by agent"], action_proposed: ["awaiting", "Action proposed"],
      approved: ["approved", "Approved"], dismissed: ["rejected", "Dismissed"], reviewed: ["info", "Reviewed"],
      pending: ["pending", "Waiting"], not_sent: ["", "Not asked yet"]
    };
    var m = map[state] || ["", String(state || "").replace(/_/g, " ")];
    return '<span class="badge ' + m[0] + '">' + esc(m[1]) + "</span>";
  }

  // ------------------------------------------------------------------ modal
  function modal(opts) {
    var root = document.getElementById("modal-root");
    var prev = document.activeElement;
    root.innerHTML = '<div class="modal-bg"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="m-title">' +
      '<div class="panel-h"><h2 id="m-title">' + esc(opts.title) + '</h2><button class="btn ghost sm" data-close aria-label="Close">' + ic("x", 16) + "</button></div>" +
      '<div class="panel-b">' + opts.body + '</div><div class="modal-foot"><button class="btn" data-close>Cancel</button>' +
      '<button class="btn ' + (opts.danger ? "danger" : "primary") + '" data-ok>' + esc(opts.ok || "Confirm") + "</button></div></div></div>";
    var bg = root.firstChild;
    function close() { root.innerHTML = ""; if (prev && prev.focus) prev.focus(); }
    bg.addEventListener("click", function (e) { if (e.target === bg || e.target.closest("[data-close]")) close(); });
    bg.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
      if (e.key === "Tab") {
        var f = bg.querySelectorAll("button, input, textarea, select, a[href]");
        if (!f.length) return;
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
      }
    });
    var ok = bg.querySelector("[data-ok]");
    ok.addEventListener("click", function () {
      busy(ok, true);
      Promise.resolve(opts.onOk(bg)).then(function (keep) { if (keep === true) busy(ok, false); else close(); });
    });
    (bg.querySelector("textarea, input") || ok).focus();
  }

  // ------------------------------------------------------------------ shell
  function loadSession() {
    return api("GET", "/api/session").then(function (r) {
      if (!r.ok) {
        if (r.data.code === "UNKNOWN_PERSONA") { S.persona = "morgan"; save("persona", "morgan"); return loadSession(); }
        view.innerHTML = '<div class="banner err">' + ic("alert") + "<div>" + esc(errText(r.data)) + "</div></div>";
        return null;
      }
      S.session = r.data;
      renderShell();
      return r.data;
    });
  }
  function save(k, v) { try { localStorage.setItem("labsync." + k, v); } catch (e) { /* private mode */ } }
  function load(k) { try { return localStorage.getItem("labsync." + k); } catch (e) { return null; } }

  function renderShell() {
    var s = S.session, admin = s.is_admin, lab = !!s.persona.lab_id;
    var route = location.hash.split("/")[1] || "";
    var items = [];
    if (lab) {
      items.push('<div class="nav-group">Lab</div>');
      items.push(navLink("#/workspace", "home", "Home", route === "workspace" || route === "plans"));
    }
    items.push(navLink("#/approvals", "inbox", "Approvals", route === "approvals", s.waiting_count));
    if (admin) {
      items.push('<div class="nav-group">Department</div>');
      items.push(navLink("#/intelligence", "chart", "Insights", route === "intelligence"));
    }
    document.getElementById("nav").innerHTML = items.join("");
    var sel = document.getElementById("persona");
    var groups = {};
    s.personas.forEach(function (p) {
      var g = p.lab_name || "Department";
      (groups[g] = groups[g] || []).push(p);
    });
    sel.innerHTML = Object.keys(groups).map(function (g) {
      return '<optgroup label="' + esc(g) + '">' + groups[g].map(function (p) {
        return '<option value="' + esc(p.id) + '"' + (p.id === s.persona.id ? " selected" : "") + ">" +
          esc(p.name + " · " + p.role.replace(/_/g, " ")) + "</option>";
      }).join("") + "</optgroup>";
    }).join("");
    document.getElementById("chip-date").textContent = "Scenario " + fmtDay(s.now) + ", 2026 · America/Chicago";
    var agents = document.getElementById("chip-agents");
    agents.innerHTML = '<span class="dot"></span>' + (s.mode === "live" ? "Agents: Claude (" + esc(s.model) + ")" : "Agents: offline mock");
    agents.className = "chip" + (s.mode === "live" ? " ok" : "");
  }
  function navLink(href, icon, label, current, count) {
    return '<a href="' + href + '"' + (current ? ' aria-current="page"' : "") + ">" + ic(icon) + "<span>" + esc(label) + "</span>" +
      (count ? '<b class="count" aria-label="' + count + ' waiting">' + count + "</b>" : "") + "</a>";
  }
  function crumbs(parts) {
    document.getElementById("crumbs").innerHTML = parts.map(function (p, i) {
      return i === parts.length - 1 ? "<b>" + esc(p) + "</b>" : esc(p) + " <span aria-hidden=\"true\">/</span>";
    }).join(" ");
    document.title = parts[parts.length - 1] + " · LabSync";
  }
  function loading() {
    view.innerHTML = '<div class="panel panel-b stack s8" aria-busy="true"><div class="skeleton" style="width:40%"></div>' +
      '<div class="skeleton" style="width:70%"></div><div class="skeleton" style="width:55%"></div></div>';
  }

  // ------------------------------------------------------------------ router
  function route() {
    if (!S.session) return;
    var parts = location.hash.replace(/^#\/?/, "").split("/");
    renderShell();
    var name = parts[0];
    if (!name) { location.hash = S.session.persona.lab_id ? "#/workspace" : (S.session.is_admin ? "#/intelligence" : "#/approvals"); return; }
    window.scrollTo(0, 0);
    if (name === "workspace") return viewHome();
    if (name === "plans" && parts[1]) return viewPlan(parts[1]);
    if (name === "approvals") return viewApprovals(parts[1] || "waiting");
    if (name === "intelligence" && parts[1] === "insights" && parts[2]) return viewInsight(decodeURIComponent(parts[2]));
    if (name === "intelligence") return viewDepartment();
    if (name === "activity" && parts[1]) return viewActivity(decodeURIComponent(parts[1]));
    view.innerHTML = '<div class="empty"><b>Page not found</b><a href="#/">Go to your workspace</a></div>';
  }
  function refreshAll() { return loadSession().then(route); }

  // ------------------------------------------------------------------ Screen 1: workspace
  function viewHome() {
    var s = S.session;
    crumbs(["Lab", "Home"]);
    if (!s.persona.lab_id) {
      view.innerHTML = '<div class="panel panel-b empty"><b>' + esc(s.persona.name) + " has no lab workspace.</b>" +
        (s.is_admin ? 'Open <a href="#/intelligence">Department Intelligence</a> or <a href="#/approvals">Approvals</a>.' :
          'Open <a href="#/approvals">Approvals</a>.') + "</div>";
      return;
    }
    loading();
    api("GET", "/api/home").then(function (r) {
      if (!r.ok) { view.innerHTML = '<div class="banner err">' + ic("alert") + esc(errText(r.data)) + "</div>"; return; }
      var d = r.data;
      var seed = S.seed || "";
      S.seed = null;
      view.innerHTML =
        '<div class="composer-wrap"><div class="stack">' +
        '<section class="panel hero" aria-labelledby="h-compose"><div class="eyebrow">Your lab · ' + esc(d.lab_name) + "</div>" +
        '<h1 id="h-compose">What are you trying to run?</h1><p class="muted">Tell LabSync your goal. We\'ll assemble the logistics for review.</p>' +
        '<form class="composer" id="compose"><label class="sr-only" for="goal">Describe your experiment</label>' +
        '<textarea id="goal" rows="3" placeholder="Example: Image GFP-tagged cells Tuesday morning...">' + esc(seed) + "</textarea>" +
        '<div class="composer-foot">' + PROMPTS.map(function (p, i) {
          return '<button type="button" class="prompt-chip" data-prompt="' + i + '">' + esc(p[0]) + "</button>";
        }).join("") + '<span class="spacer"></span><button class="btn primary" id="generate" type="submit" disabled>' + ic("spark", 16) + "Generate plan</button></div></form>" +
        '<p class="why" id="gen-why">' + (s.mode === "mock" ? "Offline mock agents understand the chips above and simple requests like \"plate reader for 45 minutes Monday at 10\" (instrument, day, time, length). Run with --live and an API key for any wording." : "Describe the instrument, day, duration and supplies.") + "</p>" +
        '<div id="gen-out" aria-live="polite"></div></section>' +
        '<section class="panel" aria-labelledby="h-upcoming"><div class="panel-h"><h2 id="h-upcoming">Upcoming experiments</h2></div>' +
        (d.plans.length ? '<table><thead><tr><th>Date</th><th>Goal</th><th>Progress</th><th></th></tr></thead><tbody>' + d.plans.map(function (p) {
          return "<tr><td class=\"n\" style=\"text-align:left;white-space:nowrap\">" + esc(fmtDay(p.day)) + "</td><td>" + esc(p.goal) + "</td><td>" + stateBadge(p.stage) +
            '</td><td class="n"><a href="#/plans/' + esc(p.plan_id) + '">Open plan</a></td></tr>';
        }).join("") + "</tbody></table>" : '<div class="empty"><b>No experiment yet</b>Describe one above.</div>') + "</section></div>" +
        '<aside class="panel" aria-labelledby="h-attn"><div class="panel-h"><h2 id="h-attn">Needs attention</h2></div><div class="panel-b">' +
        (d.waiting.length || d.notifications.length ? '<ul class="list">' + d.waiting.map(function (c) {
          return '<li><div class="row between"><b>' + esc(c.title) + "</b>" + stateBadge("pending") + '</div><a href="#/approvals">Review in Approvals</a></li>';
        }).join("") + d.notifications.map(function (n) {
          return '<li class="small"><span class="muted">' + esc(fmtStamp(n.created_at)) + "</span><br>" + esc(n.text) + "</li>";
        }).join("") + "</ul>" : '<p class="muted">Nothing needs you right now.</p>') + "</div></aside></div>";

      var ta = document.getElementById("goal"), gen = document.getElementById("generate");
      function sync() { gen.disabled = !ta.value.trim(); }
      ta.addEventListener("input", sync);
      ta.addEventListener("keydown", function (e) { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); if (!gen.disabled) submit(); } });
      sync();
      view.querySelectorAll("[data-prompt]").forEach(function (b) {
        b.addEventListener("click", function () { ta.value = PROMPTS[+b.dataset.prompt][1]; sync(); ta.focus(); });
      });
      document.getElementById("compose").addEventListener("submit", function (e) { e.preventDefault(); submit(); });
      function submit() {
        var out = document.getElementById("gen-out");
        busy(gen, true, "Generating…");
        out.innerHTML = '<div class="progress"><div class="step">' + ic("clock", 16) + "Lab Agent is reading your request and checking equipment, rooms and supplies…</div></div>";
        api("POST", "/api/requests", { text: ta.value }).then(function (r) {
          busy(gen, false); sync();
          if (!r.ok) {
            out.innerHTML = '<div class="banner err">' + ic("alert") + "<div>" + esc(errText(r.data)) +
              (r.data.code === "LLM_UNAVAILABLE" ? "<br>Nothing was saved. Try again, or run in offline mock mode." : "") + "</div></div>";
            return;
          }
          S.lastRun = r.data;
          if (r.data.plan_id) { location.hash = "#/plans/" + r.data.plan_id; return; }
          out.innerHTML = '<div class="agent-reply"><b>Lab Agent</b><br>' + esc(r.data.agent_text || "No plan was created.") + "</div>";
        });
      }
    });
  }

  // ------------------------------------------------------------------ Screen 2: plan studio
  var TOOL_WORDS = {
    catalog_find_resources: "Matched equipment and rooms", resource_check_qualifications: "Checked qualifications",
    stock_get_availability: "Checked lab stock", supply_quote: "Verified supplies and lead times",
    plan_create_draft: "Saved the draft plan", scheduler_find_slots: "Checked instrument and room slots"
  };

  function viewPlan(id) {
    crumbs(["Lab", "Experiments", id]);
    loading();
    api("GET", "/api/plans/" + id).then(function (r) {
      if (!r.ok) {
        view.innerHTML = '<div class="banner err">' + ic("alert") + "<div>" + esc(r.data.code === "PERMISSION_DENIED" ?
          "This plan belongs to another lab. You can't view it as " + S.session.persona.name + "." : errText(r.data)) +
          ' <a href="#/">Back to your workspace</a></div></div>';
        return;
      }
      renderPlan(r.data);
    });
  }

  function activeProposal(d) {
    var p = d.proposal;
    return p && ["rejected", "stale", "failed", "cancelled"].indexOf(p.state) < 0 ? p : null;
  }

  /** After an owner declines, the scheduler (which doesn't know about the decline) still ranks that same move
   * first. Options that repeat a declined move go to the end, flagged, so they aren't pre-selected. */
  function repeatsDecline(d, o) {
    if (!d.proposal || d.proposal.state !== "rejected") return false;
    var declined = (d.proposal.contingent_moves || []).map(function (m) { return m.booking_id + "@" + m.to.start; });
    return o.contingent_moves.some(function (m) { return declined.indexOf(m.booking_id + "@" + m.to.start) >= 0; });
  }
  function rankedOptions(d, search) {
    if (!search) return [];
    return search.options.filter(function (o) { return !repeatsDecline(d, o); })
      .concat(search.options.filter(function (o) { return repeatsDecline(d, o); }));
  }

  function renderPlan(d) {
    var plan = d.plan, goal = d.goal, prop = activeProposal(d);
    var search = d.search && d.search.status === "ok" ? d.search : null;
    var options = rankedOptions(d, search);
    var sel = S.selected[plan.plan_id];
    if (!options.some(function (o) { return o.option_id === sel; })) sel = options[0] && options[0].option_id;
    S.selected[plan.plan_id] = sel;
    var option = options.filter(function (o) { return o.option_id === sel; })[0];
    crumbs(["Lab", "Experiments", goal.goalSummary]);

    var stages = [["draft", "Draft"], ["pending_approvals", "Pending approvals"], ["ready", "Ready"], ["confirmed", "Confirmed"]];
    var at = stages.map(function (s) { return s[0]; }).indexOf(d.stage);
    var stepper = stages.map(function (s, i) {
      var cls = at < 0 ? "" : i < at ? "done" : i === at ? "now" : "";
      return '<span class="s ' + cls + '"' + (i === at ? ' aria-current="step"' : "") + ">" + (i < at ? ic("check", 13) : "") + esc(s[1]) + "</span>";
    }).join('<span class="arrow" aria-hidden="true">→</span>');

    var banners = "";
    if (S.lastRun && S.lastRun.plan_id === plan.plan_id) {
      banners += '<div class="banner info">' + ic("spark") + "<div><b>Lab Agent built this draft.</b> " +
        S.lastRun.tool_calls.filter(function (n, i, a) { return TOOL_WORDS[n] && a.indexOf(n) === i; }).map(function (n) {
          return ic("check", 13) + " " + esc(TOOL_WORDS[n]);
        }).join(" &nbsp; ") + ". Nothing is booked yet.</div></div>";
    }
    if (d.receipt) {
      banners += '<div class="receipt" role="status"><div class="row">' + ic("check") + "<b>Plan committed.</b></div>" +
        '<p class="small" style="margin-top:6px">Receipt <span class="mono">' + esc(d.receipt.receipt_id) + "</span> · committed by " +
        esc(person(d.receipt.committed_by)) + " · " + esc(fmtStamp(d.receipt.committed_at)) + "<br>Bookings: " +
        d.receipt.booking_ids.map(function (b) { return '<span class="mono">' + esc(b) + "</span>"; }).join(", ") +
        ' · <a href="#/activity/' + esc(plan.request_id) + '">View audit trail</a></p></div><div style="height:16px"></div>';
    }
    if (d.proposal && d.proposal.state === "rejected") {
      var rej = d.approvals.filter(function (a) { return a.decision === "reject"; })[0];
      banners += '<div class="banner warn">' + ic("alert") + "<div><b>" + esc(rej ? rej.approver_name : "An approver") + " declined.</b> " +
        esc(rej && rej.reason ? rej.reason : "") + " Their booking stays where it was. Choose another option below.</div></div>";
    }
    if (d.proposal && (d.proposal.state === "stale" || d.proposal.state === "failed")) {
      banners += '<div class="banner err">' + ic("alert") + "<div><b>Commit didn't go through.</b> The calendar changed or a write failed, so nothing was booked. " +
        '<button class="btn sm" data-act="recheck">Recheck plan</button></div></div>';
    }
    if (plan.needs_input && plan.needs_input.length) {
      banners += '<div class="banner warn">' + ic("info") + "<div><b>The agent needs a few facts before it can search.</b> Highlighted below; edit the plan to fill them in.</div></div>";
    }

    var head = '<div class="plan-head"><div><div class="eyebrow">Experiment plan · ' + esc(plan.plan_id) + "</div>" +
      "<h1>" + esc(goal.goalSummary) + "</h1><p class=\"muted\">" + (goal.desiredStart ? esc(fmtDay(goal.desiredStart)) + " · " : "") + esc(d.requester_name) + " · " + esc(d.lab_name) +
      " · " + stateBadge(d.stage) + '</p><div class="stepper" aria-label="Plan progress">' + stepper + "</div></div>" +
      '<div class="row"><a class="btn" href="#/activity/' + esc(plan.request_id) + '">' + ic("activity", 16) + "View audit trail</a></div></div>";

    var tabs = '<div class="tabs mtabs" role="tablist" aria-label="Plan sections">' + [["tasks", "Plan"], ["sched", "Schedule"], ["rail", "Approvals"]].map(function (t, i) {
      return '<button role="tab" data-mtab="' + t[0] + '" aria-selected="' + (i === 1) + '">' + t[1] + "</button>";
    }).join("") + "</div>";

    view.innerHTML = head + banners + tabs + '<div class="studio">' +
      '<section class="col-tasks" data-col="tasks" aria-labelledby="h-tasks">' + tasksPanel(d) + "</section>" +
      '<section class="on" data-col="sched" aria-labelledby="h-sched">' + schedulePanel(d, search, option, prop) + "</section>" +
      '<section data-col="rail" aria-labelledby="h-rail">' + railPanel(d, prop) + "</section></div>";
    wirePlan(d, option, prop);
  }

  function tasksPanel(d) {
    var goal = d.goal, plan = d.plan;
    var steps = goal.steps.map(function (s) {
      return '<div class="node' + (s.required ? "" : " optional") + '"><div class="k">' + esc(s.kind.replace("_", " ")) + "</div>" +
        "<b>" + esc(s.title) + '</b><div class="small muted">' + esc(s.durationMinutes) + " min" +
        (s.dependsOn.length ? " · after " + esc(s.dependsOn.join(", ")) : "") + (s.required ? "" : " · optional, not scheduled") +
        (s.source === "inferred" ? " · inferred" : "") + "</div></div>";
    }).join("") || '<p class="small muted">No instrument or room steps. This plan only requests supplies.</p>';
    var cons = goal.desiredStart ? ["Window " + fmtDay(goal.desiredStart) + " " + hm(goal.desiredStart) + (goal.preferredEnd ? "–" + hm(goal.preferredEnd) : "")] : [];
    if (goal.deadline) cons.push("Results by " + fmtDay(goal.deadline) + " " + hm(goal.deadline));
    if (d.search && d.search.assumptions) cons = cons.concat(d.search.assumptions);
    var missing = (plan.needs_input || []).length ? '<div class="missing-box"><b>Missing</b><ul class="small">' +
      plan.needs_input.map(function (m) { return "<li>" + esc(m) + "</li>"; }).join("") + "</ul></div>" : "";
    var canEdit = d.is_requester && ["draft", "needs_revision"].indexOf(d.stage) >= 0;
    return '<div class="panel"><div class="panel-h"><h2 id="h-tasks">1. Tasks</h2>' +
      (canEdit ? '<button class="btn sm" data-act="edit" aria-expanded="false">Edit plan</button>' : "") + '</div><div class="panel-b">' +
      steps + missing + '<ul class="constraints muted">' + cons.map(function (c) { return "<li>" + esc(c) + "</li>"; }).join("") + "</ul>" +
      '<div id="editor"></div></div></div>';
  }

  function editorForm(d) {
    var g = d.goal, miss = (d.plan.needs_input || []).join(" ").toLowerCase();
    function f(id, label, value, type, isMissing) {
      return '<div class="field' + (isMissing ? " missing" : "") + '"><label for="' + id + '">' + esc(label) + "</label>" +
        '<input id="' + id + '" type="' + (type || "text") + '" value="' + esc(value) + '"></div>';
    }
    var day = (g.desiredStart || "").slice(0, 10);
    return '<form class="editor" id="edit-form"><div class="grid2">' +
      f("e-day", "Day", day, "date", !day || miss.indexOf("date") >= 0) +
      f("e-start", "Earliest start", hm(g.desiredStart) || "09:00", "time", miss.indexOf("time") >= 0) +
      f("e-end", "Preferred end", hm(g.preferredEnd) || "", "time") +
      f("e-deadline", "Results by (date)", (g.deadline || "").slice(0, 10), "date") + "</div>" +
      g.steps.map(function (s) {
        return '<div class="grid2">' + f("e-dur-" + s.stepId, s.title + " (minutes)", s.durationMinutes, "number", miss.indexOf("duration") >= 0) +
          (s.kind === "prep_room" ? '<label class="toggle" style="align-self:end"><input type="checkbox" id="e-req-' + esc(s.stepId) + '"' + (s.required ? " checked" : "") + "> Prep room required</label>" : "<span></span>") + "</div>";
      }).join("") +
      g.supplies.map(function (s) { return f("e-sku-" + s.skuId, s.skuId + " quantity", s.quantity, "number"); }).join("") +
      '<div class="row"><button class="btn primary" type="submit">Recheck plan</button><button class="btn" type="button" data-act="edit-cancel">Cancel</button></div>' +
      '<p class="why">Saves a new draft for this request and re-runs the deterministic checks. The agent is not involved.</p></form>';
  }

  function offset(day, ts) { return ts.slice(19) || (day >= "2026-11-01" ? "-06:00" : "-05:00"); }

  function schedulePanel(d, search, option, prop) {
    var options = rankedOptions(d, search);
    var tl = d.timeline, html = "";
    html += '<div class="panel"><div class="panel-h"><h2 id="h-sched">2. Schedule &amp; options</h2>' +
      '<label class="toggle"><input type="checkbox" id="buffers"' + (S.buffers ? " checked" : "") + "> Turnaround buffers</label></div>" +
      '<div class="panel-b">';
    if (!d.goal.steps.some(function (s) { return s.kind === "instrument"; })) {
      html += '<div class="empty"><b>Nothing to book</b>This is a supplies-only request. Draft the supply requests on the right.</div>';
    } else if (!tl.day) {
      html += '<div class="empty"><b>No day yet</b>Press Edit plan and add a day to see the schedule.</div>';
    } else {
      html += '<p class="small muted" style="margin-bottom:8px">' + esc(fmtDay(tl.day)) + " · other labs' bookings show as busy without names</p>" +
        '<div class="tl-scroll"><div class="tl" role="group" aria-label="Instrument and room timeline">' + timeline(d, option, prop) + "</div></div>" +
        '<div class="tl-legend"><span><i class="lg-mine"></i>Confirmed (your lab)</span><span><i class="lg-busy"></i>Booked (other lab)</span>' +
        '<span><i class="lg-held"></i>Proposed / held</span><span><i class="lg-conf"></i>Conflict or owner shift awaiting approval</span>' +
        '<span><i class="lg-buf"></i>15-min cleaning buffer</span></div><div id="popover" aria-live="polite"></div>';
    }
    html += "</div></div>";

    var done = prop && prop.state === "committed";
    if (prop) {
      html += '<div class="panel" style="margin-top:16px"><div class="panel-h"><h3>' + (done ? "Committed proposal " : "Held proposal ") + esc(prop.proposal_id) + "</h3>" + stateBadge(prop.state) + '</div><div class="panel-b small">' +
        prop.creates.map(function (c) { return "<div>" + esc(resName(d, c.resource_id)) + " · " + esc(range(c.start, c.end)) + " · <span class=\"muted\">" + (done ? "booked" : "held, not booked") + "</span></div>"; }).join("") +
        prop.contingent_moves.map(function (m) {
          return '<div style="margin-top:6px">' + ic("arrow", 13) + " " + esc(labOf(m.lab_id)) + "'s booking " + (done ? "moved " : "moves ") + esc(range(m.from.start, m.from.end)) + " → " + esc(range(m.to.start, m.to.end)) + (done ? " with their approval" : " if they approve") + "</div>";
        }).join("") + (!done && d.is_requester ? '<div class="row" style="margin-top:10px"><button class="btn sm danger" data-act="release">' + ic("x", 14) + "Release hold</button>" +
          '<span class="why">Frees these slots and withdraws the approval requests. Nothing confirmed changes.</span></div>' : "") + "</div></div>";
    } else if (search) {
      html += '<div class="panel" style="margin-top:16px"><div class="panel-h"><h3>Options</h3><span class="small muted">Ranked by the deterministic scheduler</span></div><div class="panel-b">';
      if (!search.options.length) {
        var why = { BOOKED: "slots already booked", NOT_QUALIFIED: "instruments you aren't certified on", CAPABILITY_MISMATCH: "instruments that can't do this",
          MAINTENANCE_OR_HOURS: "times outside staffed hours or in maintenance", NO_PREP_ROOM: "times with no free prep room", NO_MOVE_SLOT_FOR_OWNER: "owner sessions with nowhere to move" };
        html += '<div class="banner warn">' + ic("alert") + "<div><b>Nothing free in this window.</b> The synthetic week is busy. Ruled out: " +
          esc(Object.keys(search.exclusion_counts || {}).filter(function (k) { return k !== "CAPABILITY_MISMATCH"; }).map(function (k) { return search.exclusion_counts[k] + " " + (why[k] || k.toLowerCase().replace(/_/g, " ")); }).join(", ") || "no matching slots") +
          ". Try another day with Edit plan, or a shorter session.</div></div>";
      } else {
        html += '<div class="opts" role="group" aria-label="Booking options">' + options.map(function (o, i) {
          var moves = o.contingent_moves.map(function (m) { return person(m.owner_id) + " moves " + range(m.from.start, m.from.end) + " → " + range(m.to.start, m.to.end); });
          return '<button type="button" class="opt" data-opt="' + esc(o.option_id) + '" aria-pressed="' + (option && o.option_id === option.option_id) + '">' +
            '<div class="row between"><span class="t">Option ' + (i + 1) + " · " + esc(resName(d, o.resource_id)) + " " + esc(range(o.start, o.end)) + "</span>" +
            (repeatsDecline(d, o) ? '<span class="badge rejected">Owner declined this move</span>' : i === 0 ? '<span class="badge info">Best fit</span>' : "") + "</div>" +
            '<div class="small">' + (o.prep ? "Prep in " + esc(resName(d, o.prep.resource_id)) + " " + esc(range(o.prep.start, o.prep.end)) + " · " : "") +
            (o.features.meets_preferred_window ? "Within your preferred window" : esc(o.features.hours_late) + " h later than preferred") + "</div>" +
            '<div class="small">' + (moves.length ? '<span class="badge awaiting">Needs owner approval</span> ' + esc(moves.join("; ")) : '<span class="badge ok">No one else moves</span>') + "</div>" +
            '<div class="small muted">Approvals: ' + esc(o.approvals_required.map(person).join(", ")) + " · score " + esc(o.score) + "</div></button>";
        }).join("") + "</div>";
        var directIdx = options.map(function (o) { return o.kind; }).indexOf("direct");
        if (options[0].kind !== "direct" && directIdx > 0) {
          html += '<p class="small" style="margin-top:10px">' + ic("info", 14) + " Want it booked without waiting on anyone? Option " + (directIdx + 1) + " needs no one else to move.</p>";
        }
        if (d.is_requester) {
          html += '<div class="row" style="margin-top:12px"><button class="btn primary" data-act="hold">' + ic("check", 16) + "Hold " + esc(option ? "option " + (options.indexOf(option) + 1) : "option") + "</button>" +
            '<span class="why">Holding reserves nothing: it creates a proposal that waits for approvals.</span></div>';
        }
      }
      if (search.blocked_alternatives && search.blocked_alternatives.length) {
        html += '<div class="stack s8" style="margin-top:12px">' + search.blocked_alternatives.map(function (b) {
          return '<div class="blocked">' + ic("x", 13) + " <b>" + esc(resName(d, b.resource_id)) + "</b> requires certification (" + esc(b.missing.join(", ")) + "). " + esc(b.detail) + "</div>";
        }).join("") + "</div>";
      }
      html += "</div></div>";
    }
    return html;
  }

  function resName(d, id) {
    var r = d.timeline.resources.filter(function (x) { return x.id === id; })[0];
    return r ? r.name : id;
  }

  function timeline(d, option, prop) {
    var tl = d.timeline;
    var hours = "";
    for (var h = 9; h <= 17; h++) {
      if (h === 17) continue;
      hours += '<span style="left:' + ((h * 60 - DAY0) / (DAY1 - DAY0) * 100) + '%">' + (h < 10 ? "0" : "") + h + "</span>";
    }
    var moves = (prop ? prop.contingent_moves : option ? option.contingent_moves : []) || [];
    var moveIds = moves.map(function (m) { return m.booking_id; });
    var committed = d.receipt != null;
    var mineIds = prop ? prop.creates.map(function (c) { return c.booking_id; }) : [];
    var blocked = (d.search && d.search.blocked_alternatives || []).map(function (b) { return b.resource_id; });
    var out = '<div class="tl-head"><span></span><div class="tl-hours" aria-hidden="true">' + hours + "</div></div>";
    tl.resources.forEach(function (res) {
      var blocks = [];
      tl.rows.filter(function (r) { return r.resource_id === res.id; }).forEach(function (r) {
        var b = { start: r.start, end: r.end, id: r.booking_id };
        var move = moves.filter(function (m) { return m.booking_id === r.booking_id; })[0];
        if (r.status === "held") {
          // Calendar hold rows are "hold:<booking_id>" (our new slots) or "hold:move:<booking_id>" (an owner's move target).
          var raw = r.booking_id.replace(/^hold:/, ""), moveTarget = raw.indexOf("move:") === 0 ? raw.slice(5) : null;
          var ours = moveTarget ? moveIds.indexOf(moveTarget) >= 0 && !!prop : mineIds.indexOf(raw) >= 0;
          if (ours && moveTarget) return;  // drawn below as the owner's proposed new time
          b.cls = "held"; b.title = ours ? "Proposed · " + person(d.plan.requester_id) : r.user_id ? "Your lab · held" : "Held by another request";
          b.detail = ours ? "Held for proposal " + prop.proposal_id + ", not booked. It becomes a booking only after every approval and the commit." :
            r.user_id ? person(r.user_id) + " is holding this slot for another plan in your lab. Open that plan and press Release hold if it's not needed." :
            "Another lab's request is holding this slot. It is not confirmed.";
        } else if (move && !committed) {
          b.cls = "conflict"; b.title = labOf(move.lab_id) + " · flexible";
          b.detail = "Owned by " + labOf(move.lab_id) + " · confirmed " + range(r.start, r.end) + " · flexible (request permission). Proposed move: " + range(move.to.start, move.to.end) + ", same day and length.";
        } else if (r.user_id) {
          b.cls = "mine"; b.title = person(r.user_id); b.detail = "Your lab · " + person(r.user_id) + " · " + range(r.start, r.end) + " · " + r.status + (r.flexible ? " · flexible" : "");
        } else {
          b.cls = "busy"; b.title = "Booked"; b.detail = "Booked by another lab · " + range(r.start, r.end) + ". Details are private to that lab.";
        }
        blocks.push(b);
      });
      if (!committed) {
        moves.filter(function (m) { return m.resource_id === res.id; }).forEach(function (m) {
          blocks.push({ start: m.to.start, end: m.to.end, cls: "shift", title: labOf(m.lab_id) + " moves here?",
            detail: labOf(m.lab_id) + "'s session would move to " + range(m.to.start, m.to.end) + " only if " + person(m.owner_id) + " approves. Nothing has moved yet." });
        });
      }
      if (option && !prop) {
        [[option.resource_id, option.start, option.end, "Imaging"], option.prep ? [option.prep.resource_id, option.prep.start, option.prep.end, "Prep"] : null].forEach(function (x) {
          if (x && x[0] === res.id) blocks.push({ start: x[1], end: x[2], cls: "preview", title: "Option · " + x[3], detail: "Selected option, not held yet. Press Hold to create a proposal." });
        });
      }
      (tl.maintenance || []).filter(function (m) { return m.resource_id === res.id; }).forEach(function (m) {
        blocks.push({ start: m.start_local, end: m.end_local, cls: "maint", title: "Maintenance", detail: m.reason });
      });
      var cells = "";
      blocks.forEach(function (b, i) {
        var s = Math.max(DAY0, mins(b.start)), e = Math.min(DAY1, mins(b.end));
        if (e <= s) return;
        var left = (s - DAY0) / (DAY1 - DAY0) * 100, width = (e - s) / (DAY1 - DAY0) * 100;
        var lane = ["held", "preview", "shift"].indexOf(b.cls) >= 0 ? " lane2" : "";
        if (S.buffers && res.buffer_minutes && b.cls !== "maint") {
          var be = Math.min(DAY1, e + res.buffer_minutes);
          cells += '<span class="blk buffer' + lane + '" aria-hidden="true" style="left:' + ((e - DAY0) / (DAY1 - DAY0) * 100) + "%;width:" + ((be - e) / (DAY1 - DAY0) * 100) + '%"></span>';
        }
        cells += '<button type="button" class="blk ' + b.cls + lane + '" data-detail="' + esc(b.detail) + '" style="left:' + left + "%;width:" + width + '%" ' +
          'aria-label="' + esc(res.name + ", " + range(b.start, b.end) + ", " + b.title) + '"><b>' + esc(b.title) + "</b>" + esc(range(b.start, b.end)) + "</button>";
      });
      var note = blocked.indexOf(res.id) >= 0 ? '<small style="color:var(--red)">Requires certification</small>' : "<small>" + esc(res.type === "room" ? "Room" : "Instrument") + "</small>";
      out += '<div class="tl-row"><div class="tl-name">' + esc(res.name) + note + '</div><div class="tl-track">' + cells + "</div></div>";
    });
    return out;
  }

  function railPanel(d, prop) {
    var html = '<div class="panel"><div class="panel-h"><h2 id="h-rail">3. Approvals &amp; costs</h2></div><div class="panel-b stack">';
    var approvals = prop ? d.approvals : [];
    if (!prop) {
      html += '<p class="muted small">' + (d.receipt ? "" : "Hold an option to see who needs to approve it.") + "</p>";
    } else {
      var need = approvals.filter(function (a) { return !(a.status === "decided" && a.decision === "approve"); }).length;
      html += '<div><div class="eyebrow" style="margin-bottom:8px">' + (need ? "Needs " + need + " approval" + (need > 1 ? "s" : "") : "All approvals received") + '</div><ul class="list">' +
        approvals.map(function (a) {
          var label = a.slot_kind === "owner_move" ? "moves their booking" : "confirms the final schedule";
          var st = a.status === "decided" ? (a.decision === "approve" ? "approved" : "rejected") : a.status;
          var icon = st === "approved" ? ic("check", 16) : st === "rejected" ? ic("x", 16) : ic("clock", 16);
          var act = "";
          if (a.slot_kind === "owner_move" && a.status === "not_sent" && d.is_requester) {
            act = '<button class="btn sm primary" data-act="ask" style="margin-top:6px">' + ic("send", 14) + "Ask " + esc(a.approver_name) + " to move</button>";
          }
          if (a.your_turn) {
            act = '<button class="btn sm success" data-act="confirm" data-id="' + esc(a.approval_id) + '" style="margin-top:6px">' + ic("check", 14) + "Approve final schedule</button>";
          } else if (a.slot_kind === "requester_confirm" && a.status === "pending" && d.is_requester) {
            act = '<p class="why">Your confirmation opens after the other approvals.</p>';
          }
          return '<li class="appr"><span class="ic" aria-hidden="true">' + icon + "</span><div><div class=\"row between\"><span><b>" + esc(a.approver_name) + "</b> " + esc(label) + "</span>" +
            stateBadge(st) + "</div>" + (a.decided_at ? '<div class="small muted">' + esc((a.decision === "approve" ? "Approved" : "Rejected") + " " + fmtStamp(a.decided_at)) + (a.reason ? " · " + esc(a.reason) : "") + "</div>" : "") + act + "</div></li>";
        }).join("") + "</ul></div>";
    }
    if (prop && d.is_requester && prop.state !== "committed") {
      var can = prop.state === "authorized";
      html += '<div class="sticky-foot"><button class="btn primary" data-act="commit"' + (can ? "" : " disabled") + ' aria-describedby="commit-why">' + ic("check", 16) + "Commit plan</button>" +
        '<ul class="why" id="commit-why">' + (can ? "<li>All approvals are in. Commit re-checks the calendar before writing.</li>" :
          d.commit_blockers.map(function (b) { return "<li>" + esc(b) + "</li>"; }).join("")) + "</ul></div>";
    }
    html += supplies(d) + "</div></div>";
    return html;
  }

  function supplies(d) {
    var q = d.quote && d.quote.status === "ok" ? d.quote : null;
    if (!q && !d.orders.length) return '<div><div class="eyebrow">Supplies</div><p class="small muted">No supplies in this plan.</p></div>';
    var html = '<div><div class="row between"><div class="eyebrow">Supplies</div><span class="badge">Estimate · synthetic prices</span></div>';
    if (q) {
      var rd = q.readiness;
      html += '<table class="quote small" style="margin-top:8px"><thead><tr><th>Item</th><th class="n">Qty</th><th class="n">Unit</th><th class="n">Subtotal</th></tr></thead><tbody>' +
        q.quote.lines.map(function (l) { return "<tr><td>" + esc(l.sku_id) + '</td><td class="n">' + l.quantity + '</td><td class="n">' + usd(l.unit_price_usd) + '</td><td class="n">' + usd(l.subtotal_usd) + "</td></tr>"; }).join("") +
        Object.keys(q.quote.shipping_by_vendor).map(function (v) { return '<tr><td class="muted">Shipping · ' + esc(v) + '</td><td></td><td></td><td class="n">' + usd(q.quote.shipping_by_vendor[v]) + "</td></tr>"; }).join("") +
        '<tr><td><b>Estimated total</b></td><td></td><td></td><td class="n"><b>' + usd(q.quote.total_usd) + "</b></td></tr></tbody></table>";
      if (rd) {
        html += '<p class="small" style="margin-top:8px">' + (rd.status === "order_needed" ? '<span class="badge awaiting">Order needed</span> ' : stateBadge(rd.status)) +
          (rd.last_safe_order_date ? " Last safe order date <b>" + esc(fmtDay(rd.last_safe_order_date)) + "</b>." : "") +
          (rd.ready_at ? " Expected on hand " + esc(fmtDay(rd.ready_at)) + "." : "") + "</p>";
      }
    }
    if (d.orders.length) {
      html += '<ul class="list" style="margin-top:8px">' + d.orders.map(function (o) {
        return '<li class="small"><div class="row between"><span>' + esc(o.sku_id) + " ×" + esc(o.quantity) + ' <span class="mono muted">' + esc(o.order_id) + "</span></span>" + stateBadge(o.state) + "</div></li>";
      }).join("") + '</ul><p class="why">Requests only. Nothing is ordered, charged or emailed.</p>';
    } else if (d.is_requester && q) {
      html += '<button class="btn sm" data-act="orders" style="margin-top:8px">' + ic("pkg", 14) + "Draft supply requests</button>" +
        '<p class="why">Creates requests that wait for lab approval. Nothing is ordered.</p>';
    }
    return html + "</div>";
  }

  function wirePlan(d, option, prop) {
    var plan = d.plan, reload = function () { refreshAll(); };
    view.querySelectorAll("[data-mtab]").forEach(function (b) {
      b.addEventListener("click", function () {
        view.querySelectorAll("[data-mtab]").forEach(function (x) { x.setAttribute("aria-selected", x === b); });
        view.querySelectorAll("[data-col]").forEach(function (c) { c.classList.toggle("on", c.dataset.col === b.dataset.mtab); });
      });
    });
    view.querySelectorAll("[data-opt]").forEach(function (b) {
      b.addEventListener("click", function () { S.selected[plan.plan_id] = b.dataset.opt; renderPlan(d); var again = view.querySelector('[data-opt="' + b.dataset.opt + '"]'); if (again) again.focus(); });
    });
    view.querySelectorAll(".blk[data-detail]").forEach(function (b) {
      b.addEventListener("click", function () {
        document.getElementById("popover").innerHTML = '<div class="popover">' + esc(b.dataset.detail) + "</div>";
      });
    });
    var buf = document.getElementById("buffers");
    if (buf) buf.addEventListener("change", function () { S.buffers = buf.checked; renderPlan(d); });
    on("recheck", reload);
    on("edit", function (btn) {
      var ed = document.getElementById("editor");
      if (ed.innerHTML) { ed.innerHTML = ""; btn.setAttribute("aria-expanded", "false"); return; }
      btn.setAttribute("aria-expanded", "true");
      ed.innerHTML = editorForm(d);
      ed.querySelector("input").focus();
      ed.querySelector("[data-act=edit-cancel]").addEventListener("click", function () { ed.innerHTML = ""; btn.setAttribute("aria-expanded", "false"); });
      document.getElementById("edit-form").addEventListener("submit", function (e) {
        e.preventDefault();
        var g = d.goal, val = function (id) { var el = document.getElementById(id); return el ? el.value : ""; };
        var day = val("e-day"), dl = val("e-deadline");
        var startTs = day ? day + "T" + (val("e-start") || "09:00") + ":00" : null;
        if (startTs) startTs += offset(day, g.desiredStart || "");
        var endTs = day && val("e-end") ? day + "T" + val("e-end") + ":00" + offset(day, g.preferredEnd || "") : null;
        var edits = {
          desiredStart: startTs, preferredEnd: endTs,
          deadline: dl ? dl + "T18:00:00" + offset(dl, g.deadline || "") : null,
          durations: {}, required: {}, missingInformation: [],
          supplies: g.supplies.map(function (s) { return { skuId: s.skuId, quantity: parseInt(val("e-sku-" + s.skuId), 10) || 0 }; })
        };
        g.steps.forEach(function (s) {
          edits.durations[s.stepId] = parseInt(val("e-dur-" + s.stepId), 10) || s.durationMinutes;
          var req = document.getElementById("e-req-" + s.stepId);
          if (req) edits.required[s.stepId] = req.checked;
        });
        var sub = e.target.querySelector("[type=submit]");
        busy(sub, true, "Rechecking…");
        api("POST", "/api/plans/" + plan.plan_id + "/revise", { edits: edits }).then(function (r) {
          busy(sub, false);
          if (!r.ok) { toast(errText(r.data), true); return; }
          toast("Plan updated and rechecked.");
          location.hash = "#/plans/" + r.data.plan_id;
        });
      });
    });
    on("hold", function (btn) {
      busy(btn, true, "Holding…");
      api("POST", "/api/plans/" + plan.plan_id + "/hold", { option_id: option.option_id }).then(function (r) {
        if (!r.ok) { busy(btn, false); toast(errText(r.data), true); return; }
        toast("Option held as proposal " + r.data.proposal_id + ". Nothing is booked yet.");
        reload();
      });
    });
    on("ask", function () {
      var m = prop.contingent_moves[0];
      modal({
        title: "Ask " + person(m.owner_id) + " to move", ok: "Send request",
        body: '<p class="small">' + esc(labOf(m.lab_id)) + "'s " + esc(resName(d, m.resource_id)) + " session " + esc(range(m.from.start, m.from.end)) +
          " would move to <b>" + esc(range(m.to.start, m.to.end)) + "</b> the same day. They decide; LabSync only sends an in-app request.</p>" +
          '<div class="field" style="margin-top:12px"><label for="ask-msg">Message (optional)</label><textarea id="ask-msg" rows="3">Could you shift your session so we can image this morning?</textarea></div>',
        onOk: function (bg) {
          return api("POST", "/api/proposals/" + prop.proposal_id + "/request-moves", { message: bg.querySelector("#ask-msg").value }).then(function (r) {
            if (!r.ok) { toast(errText(r.data), true); return; }
            toast("Request sent to " + person(m.owner_id) + ".");
            reload();
          });
        }
      });
    });
    on("confirm", function (btn) {
      var id = btn.dataset.id;
      modal({
        title: "Approve final schedule", ok: "Approve",
        body: '<p>Approving permits the commit <b>only if constraints still validate</b>. Nothing is booked until you press Commit plan.</p>',
        onOk: function () {
          return api("POST", "/api/approvals/" + id + "/decide", { decision: "approve" }).then(function (r) {
            if (!r.ok) { toast(errText(r.data), true); return; }
            toast("Approved. You can commit the plan now.");
            reload();
          });
        }
      });
    });
    on("commit", function () {
      var writes = prop.creates.map(function (c) { return "<li>Create " + esc(c.entity === "Booking" ? "booking" : "room reservation") + ' <span class="mono">' + esc(c.booking_id) + "</span>: " + esc(resName(d, c.resource_id)) + " " + esc(range(c.start, c.end)) + "</li>"; })
        .concat(prop.contingent_moves.map(function (m) { return '<li>Move <span class="mono">' + esc(m.booking_id) + "</span> (" + esc(labOf(m.lab_id)) + ") " + esc(range(m.from.start, m.from.end)) + " → " + esc(range(m.to.start, m.to.end)) + "</li>"; }));
      modal({
        title: "Commit plan", ok: "Commit",
        body: "<p>LabSync re-checks the calendar, then writes exactly these changes together (or none of them):</p><ul class=\"small\">" + writes.join("") + "</ul>",
        onOk: function () {
          return api("POST", "/api/proposals/" + prop.proposal_id + "/commit").then(function (r) {
            if (!r.ok) { toast(errText(r.data), true); reload(); return; }
            toast("Committed. Receipt " + r.data.receipt.receipt_id + ".");
            S.lastRun = null;
            reload();
          });
        }
      });
    });
    on("release", function () {
      modal({
        title: "Release hold", ok: "Release", danger: true,
        body: "<p>This frees the held slots and withdraws the open approval requests" + (prop.contingent_moves.length ? ", including the move request to " + esc(prop.contingent_moves.map(function (m) { return person(m.owner_id); }).join(", ")) : "") +
          ". Nothing that's already confirmed changes. You can pick another option afterwards.</p>",
        onOk: function () {
          return api("POST", "/api/proposals/" + prop.proposal_id + "/withdraw", { reason: "Released by requester" }).then(function (r) {
            if (!r.ok) { toast(errText(r.data), true); return; }
            toast("Hold released. Pick another option or edit the plan.");
            reload();
          });
        }
      });
    });
    on("orders", function (btn) {
      busy(btn, true, "Drafting…");
      api("POST", "/api/plans/" + plan.plan_id + "/orders").then(function (r) {
        if (!r.ok) { busy(btn, false); toast(errText(r.data), true); return; }
        toast("Supply requests drafted. They wait for lab approval; nothing is ordered.");
        reload();
      });
    });
  }
  function on(act, fn) { view.querySelectorAll('[data-act="' + act + '"]').forEach(function (b) { b.addEventListener("click", function () { fn(b); }); }); }

  // ------------------------------------------------------------------ Screen 4: approvals
  function viewApprovals(tab) {
    crumbs(["Lab", "Approvals"]);
    loading();
    api("GET", "/api/approvals").then(function (r) {
      if (!r.ok) { view.innerHTML = '<div class="banner err">' + ic("alert") + esc(errText(r.data)) + "</div>"; return; }
      var d = r.data, tabs = [["waiting", "Waiting on me", d.waiting_on_me], ["requested", "Requested by me", d.requested_by_me], ["history", "History", d.history]];
      var cur = tabs.filter(function (t) { return t[0] === tab; })[0] || tabs[0];
      view.innerHTML = '<div class="plan-head"><div><div class="eyebrow">' + esc(S.session.persona.name) + (S.session.persona.lab_name ? " · " + esc(S.session.persona.lab_name) : "") +
        '</div><h1>Approvals</h1><p class="muted">Requests that need a person\'s decision. Agents can advise but never decide.</p></div></div>' +
        '<div class="tabs" role="tablist" aria-label="Approval lists">' + tabs.map(function (t) {
          return '<button role="tab" aria-selected="' + (t === cur) + '" data-tab="' + t[0] + '">' + esc(t[1]) + '<span class="tab-n">' + t[2].length + "</span></button>";
        }).join("") + '</div><div role="tabpanel" style="max-width:860px">' +
        (cur[2].length ? cur[2].map(function (c) { return approvalCard(c, cur[0]); }).join("") :
          '<div class="panel empty"><b>' + (cur[0] === "waiting" ? "Nothing is waiting on you." : "Nothing here yet.") + "</b>" +
          (cur[0] === "waiting" ? "Requests appear here when someone asks for your decision." : "") + "</div>") + "</div>";
      view.querySelectorAll("[data-tab]").forEach(function (b) { b.addEventListener("click", function () { location.hash = "#/approvals/" + b.dataset.tab; }); });
      view.querySelectorAll("[data-decide]").forEach(function (b) {
        b.addEventListener("click", function () { decideFlow(b.dataset.id, b.dataset.decide, b.dataset.who); });
      });
    });
  }

  function miniBar(label, s, e, cls) {
    var l = (mins(s) - DAY0) / (DAY1 - DAY0) * 100, w = (mins(e) - mins(s)) / (DAY1 - DAY0) * 100;
    return '<div class="row small"><span style="width:52px" class="muted">' + label + '</span><div class="bar" style="flex:1"><span class="' + cls + '" style="left:' + l + "%;width:" + w + '%">' + esc(range(s, e)) + "</span></div></div>";
  }

  function approvalCard(c, tab) {
    var head = '<div class="row between"><h3>' + esc(c.title) + "</h3>" + (c.status === "decided" ? stateBadge(c.decision === "approve" ? "approved" : "rejected") : stateBadge(c.entity_state)) + "</div>" +
      '<p class="small muted">' + (tab === "requested" ? "Waiting on " + esc(c.approver_name) : "From " + esc(c.requested_by_name) + (c.requester_lab ? " · " + esc(c.requester_lab) : "")) +
      " · " + esc(fmtStamp(c.created_at)) + "</p>";
    var body = "";
    if (c.slot_kind === "owner_move" && c.impact) {
      var im = c.impact;
      body += (c.message ? '<blockquote class="small" style="margin:0;border-left:3px solid var(--line-2);padding-left:10px">“' + esc(c.message) + "”</blockquote>" : "") +
        '<div class="mini" aria-label="Before and after">' + miniBar("Now", im.from.start, im.from.end, "from") + miniBar("After", im.to.start, im.to.end, "to") +
        '<div class="row muted" style="justify-content:space-between;margin-left:60px"><span>09:00</span><span>13:00</span><span>17:00</span></div></div>' +
        '<ul class="small" style="margin:0;padding-left:18px"><li>' + esc(c.resource_name) + ", " + esc(fmtDay(im.from.start)) + ": " + esc(range(im.from.start, im.from.end)) + " → " + esc(range(im.to.start, im.to.end)) + "</li>" +
        "<li>" + (im.same_day ? "Same day" : "Different day") + " · " + (im.same_duration ? "same length" : "different length") + (im.flexible ? " · you marked it flexible" : " · not marked flexible") + "</li>" +
        "<li>" + (im.person_conflicts.length ? "Overlaps your own sessions: " + esc(im.person_conflicts.map(function (p) { return p.booking_id || p; }).join(", ")) : "No overlap with your own sessions at the new time") + "</li>" +
        (im.your_other_bookings_that_day.length ? "<li class=\"muted\">Your lab's other sessions that day: " + esc(im.your_other_bookings_that_day.map(function (b) { return ((S.session.resource_names || {})[b.resource_id] || b.resource_id) + " " + range(b.start, b.end) + " (" + person(b.user_id) + ")"; }).join("; ")) + "</li>" : "") + "</ul>";
      if (c.recommendation && tab === "waiting") {
        var rec = c.recommendation;
        body += '<div class="advice"><div class="row between"><b>' + ic("spark", 14) + " Conflict Negotiator advice: " + esc(rec.recommendation.replace(/_/g, " ")) + '</b><span class="small muted">You decide</span></div><ul>' +
          rec.reasons.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>" +
          (rec.alternatives && rec.alternatives.length ? '<p class="small">Alternatives: ' + esc(rec.alternatives.map(function (a) { return range(a.start, a.end); }).join(", ")) + "</p>" : "") + "</div>";
      }
    } else if (c.slot_kind === "requester_confirm") {
      body += '<ul class="small" style="margin:0;padding-left:18px">' + (c.held || []).map(function (h) { return "<li>" + esc(h.resource_id) + " " + esc(fmtDay(h.start)) + " " + esc(range(h.start, h.end)) + " (held)</li>"; }).join("") + "</ul>" +
        '<p class="small"><a href="#/plans/' + esc(c.plan_id) + '">Open the plan</a></p>';
    } else if (c.order) {
      var o = c.order;
      body += '<p class="small">' + esc(o.sku_name) + " ×" + esc(o.quantity) + " · estimated " + usd(o.estimated_total_usd) + " incl. shipping · needed by " + esc(fmtDay(o.need_by_date)) + " · " + esc(labOf(o.lab_id)) + "</p>";
    } else if (c.insight) {
      var est = c.insight.estimate;
      body += '<p class="small">' + esc(c.insight.kind === "pooled_order" ? est.formula : c.insight.kind === "overload_rebalance" ?
        est.movable_hours + " flexible hours move from " + est.source + " to " + est.target + " (" + est.before.source_hours + "→" + est.after.source_hours + " h and " + est.before.target_hours + "→" + est.after.target_hours + " h)" :
        est.resource_id + " used " + pct(est.utilization) + " of staffed hours; publish spare capacity to qualified users") + "</p>";
    }
    if (c.note) body += '<p class="why">' + esc(c.note) + "</p>";
    if (c.status === "decided") {
      body += '<p class="small muted">' + esc((c.decision === "approve" ? "Approved" : "Rejected") + " by " + (c.decided_by_name || c.approver_name) + " · " + fmtStamp(c.decided_at)) + (c.reason ? " · " + esc(c.reason) : "") + "</p>";
    }
    var actions = "";
    if (tab === "waiting") {
      actions = '<div class="actions"><button class="btn success" data-decide="approve" data-id="' + esc(c.approval_id) + '" data-who="' + esc(c.slot_kind) + '">' + ic("check", 16) + "Approve</button>" +
        '<button class="btn danger" data-decide="reject" data-id="' + esc(c.approval_id) + '">' + ic("x", 16) + "Reject</button>" +
        (c.slot_kind === "owner_move" ? '<button class="btn" data-decide="suggest" data-id="' + esc(c.approval_id) + '">' + ic("clock", 16) + "Suggest different time</button>" : "") + "</div>";
    }
    return '<article class="card" aria-label="' + esc(c.title) + '">' + head + body + actions + "</article>";
  }

  function decideFlow(id, kind, slot) {
    function send(body, msg) {
      return api("POST", "/api/approvals/" + id + "/decide", body).then(function (r) {
        if (!r.ok) { toast(errText(r.data), true); return; }
        toast(msg);
        refreshAll();
      });
    }
    if (kind === "approve") {
      modal({
        title: "Approve request", ok: "Approve",
        body: "<p>Approving permits the proposed " + (slot === "owner_move" ? "move" : "action") + " <b>only if constraints still validate</b>." +
          (slot === "owner_move" ? " Your booking moves only when the requester commits." : "") + "</p>",
        onOk: function () { return send({ decision: "approve" }, "Approved. Both activity logs show your decision."); }
      });
    } else if (kind === "reject") {
      modal({
        title: "Reject request", ok: "Reject", danger: true,
        body: '<div class="field"><label for="why">Reason (shared with the requester)</label><textarea id="why" rows="3"></textarea></div>',
        onOk: function (bg) { return send({ decision: "reject", reason: bg.querySelector("#why").value }, "Rejected. Nothing moves."); }
      });
    } else {
      modal({
        title: "Suggest a different time", ok: "Send suggestion",
        body: '<p class="small">This declines the current request and sends your suggested time back to the requester. Nothing moves.</p>' +
          '<div class="field" style="margin-top:10px"><label for="sug">Time that works for you</label><input id="sug" placeholder="e.g. 14:00–16:00"></div>' +
          '<div class="field" style="margin-top:10px"><label for="sug-note">Note (optional)</label><textarea id="sug-note" rows="2"></textarea></div>',
        onOk: function (bg) {
          var t = bg.querySelector("#sug").value.trim();
          if (!t) { toast("Enter a time to suggest.", true); return true; }
          return send({ suggested_time: t, reason: bg.querySelector("#sug-note").value }, "Suggestion sent. The request was declined.");
        }
      });
    }
  }

  // ------------------------------------------------------------------ Screen 5: department
  function deptDenied(r) {
    view.innerHTML = '<div class="panel panel-b empty"><b>Department Intelligence is for department admins.</b>' +
      (r.data.code === "PERMISSION_DENIED" ? "Switch the simulated identity to Department admin to view it. " : esc(errText(r.data)) + " ") +
      '<a href="#/">Back to your workspace</a></div>';
  }

  function viewDepartment() {
    crumbs(["Department", "Insights"]);
    loading();
    api("GET", "/api/department").then(function (r) {
      if (!r.ok) return deptDenied(r);
      var d = r.data, snap = d.snapshot, rv = d.review, cards = rv && rv.output ? rv.output.cards : [];
      var util = {}; snap.utilization.forEach(function (u) { util[u.resource_id] = u; });
      var pool = values(d.insights).filter(function (i) { return i.kind === "pooled_order"; })[0];
      var over = values(d.insights).filter(function (i) { return i.kind === "overload_rebalance"; })[0];
      var html = '<div class="plan-head"><div><div class="eyebrow">' + esc(S.session.department) + " · " + esc(S.session.building) + " · Synthetic scenario · week of " + esc(fmtDay(d.week)) + "</div>" +
        "<h1>Department Intelligence</h1><p class=\"muted\">" + (rv ? "Last computed " + esc(fmtStamp(rv.finished_at)) + " by the Department Optimizer (" + esc(rv.mode === "live" ? "Claude" : "offline mock") + ")" : "Not computed yet. Run a review to have the Department Optimizer write insight cards.") + "</p></div>" +
        '<div class="row"><button class="btn primary" data-act="review">' + ic("spark", 16) + (rv ? "Recompute" : "Run department review") + "</button></div></div>";
      html += '<div class="stats">' +
        stat("Potential purchasing savings", pool ? usd(pool.estimate.potential_savings_usd) : "$0", pool ? "Estimated, not realized · " + pool.lab_ids.length + " labs must agree" : "No shared order detected") +
        stat("Confocal-1 utilization", util.confocal_1 ? pct(util.confocal_1.utilization) : "—", util.confocal_1 ? util.confocal_1.booked_hours + " of " + util.confocal_1.available_hours + " staffed hours booked" : "") +
        stat("Open cross-lab recommendations", rv ? String(cards.length) : "—", rv ? "Written from tool results; each needs approval" : "Run a review") + "</div>";
      html += '<div class="hero-row"><section class="panel" aria-labelledby="h-cap"><div class="panel-h"><h2 id="h-cap">Capacity imbalance</h2><span class="small muted">Booked hours, week of ' + esc(fmtDay(d.week)) + '</span></div><div class="panel-b chart">' +
        (over ? capacityChart(over.estimate) : '<p class="muted">No overload detected this week.</p>') + "</div></section>" +
        '<section class="panel" aria-labelledby="h-top"><div class="panel-h"><h2 id="h-top">Top opportunity</h2>' + (pool ? stateBadge(pool.state) : "") + '</div><div class="panel-b">' +
        (pool ? '<p class="metric" style="font-size:30px;font-weight:650">' + usd(pool.estimate.potential_savings_usd) + ' <span class="small muted" style="font-weight:400">potential</span></p>' +
          '<p class="small">= ' + usd(pool.estimate.volume_component_usd) + " volume + " + usd(pool.estimate.shipping_component_usd) + " shipping by combining " +
          esc(pool.lab_ids.map(labOf).join(" and ")) + " orders for " + esc(pool.detail.sku_id) + ".</p>" +
          '<p class="small muted" style="margin-top:6px">Needs: ' + esc(pool.required_approvals.map(person).join(", ")) + "</p>" +
          '<a class="btn" style="margin-top:12px" href="#/intelligence/insights/' + esc(pool.insight_id) + '">Review recommendation' + ic("arrow", 14) + "</a>" : '<p class="muted">No shared purchase detected.</p>') + "</div></section></div>";
      html += '<h2 style="margin:8px 0 12px">Insights</h2>';
      if (!rv) {
        html += '<div class="panel empty" style="margin-bottom:16px"><b>No review yet.</b>Run the department review to get exactly three evidence-backed cards.</div>';
      } else if (!rv.output) {
        html += '<div class="banner err">' + ic("alert") + "<div>The last review produced no accepted cards: " + esc((rv.errors || []).join("; ") || rv.text) + "</div></div>";
      } else {
        html += '<div class="insights">' + cards.map(function (c) { return insightCard(c, d.insights[c.insightId]); }).join("") + "</div>";
        if (rv.output.alsoDetected.length) {
          html += '<p class="small muted" style="margin-bottom:16px">Also detected: ' + esc(rv.output.alsoDetected.map(function (a) { return named(a.note); }).join(" ")) + "</p>";
        }
      }
      html += '<section class="panel" aria-labelledby="h-dem"><div class="panel-h"><h2 id="h-dem">Demand and capacity</h2><span class="badge forecast">Forecast</span></div><div class="panel-b"><div class="charts2">' +
        ["confocal_1", "confocal_2"].map(function (rid) { return '<div class="chart"><h3 style="margin-bottom:6px">' + esc(d.names[rid]) + "</h3>" + demandChart(d.history[rid] || [], d.forecasts[rid], util[rid]) + "</div>"; }).join("") +
        "</div>" + forecastMeta(d.forecasts) + '<details class="how" style="margin-top:12px"><summary>Table view and all instruments</summary>' + utilTable(snap, d.names) + "</details></div></section>";
      html += '<p class="small muted" style="margin-top:16px">All bookings, prices and forecasts are synthetic demo data. Snapshot <span class="mono">' + esc(snap.snapshot_id) + "</span> · " + snap.source_record_ids.length + " source records · " +
        (rv ? 'agent run <span class="mono">' + esc(rv.run_id) + "</span> (" + esc(rv.tool_calls.join(", ")) + ")" : "no agent run yet") + "</p>";
      view.innerHTML = html;
      on("review", function (btn) {
        busy(btn, true, "Reviewing…");
        api("POST", "/api/department/review", { week: d.week }).then(function (r2) {
          busy(btn, false);
          if (!r2.ok) { toast(errText(r2.data), true); return; }
          toast("Department review complete: " + r2.data.output.cards.length + " cards.");
          viewDepartment();
        });
      });
    });
  }
  function values(o) { return Object.keys(o).map(function (k) { return o[k]; }); }
  function stat(label, value, note) {
    return '<div class="panel stat"><div class="eyebrow">' + esc(label) + '</div><div class="metric">' + esc(value) + '</div><div class="small muted">' + esc(note) + "</div></div>";
  }
  function insightCard(c, ins) {
    var unit = c.impact.unit === "USD" ? usd(c.impact.value) : c.impact.unit === "hours" ? c.impact.value + " h" : c.impact.value + "%";
    var approvals = ins && ins.approvals && ins.approvals.length ? '<p class="small muted">Approvals: ' + ins.approvals.map(function (a) {
      return esc(a.approver_name) + " " + (a.status === "decided" ? (a.decision === "approve" ? "✓" : "✗") : "…");
    }).join(", ") + "</p>" : "";
    return '<article class="panel ins" aria-labelledby="ins-' + esc(c.insightId) + '"><div class="row between"><span class="kind-ic ' + esc(c.kind) + '">' + ic(KIND_ICON[c.kind] || "info") + "</span>" +
      stateBadge(ins ? ins.state : "detected") + '</div><h3 id="ins-' + esc(c.insightId) + '">' + esc(named(c.headline)) + '</h3><p class="small">' + esc(named(c.evidenceSentence)) + "</p>" +
      '<div class="value">' + esc(unit) + ' <small>' + esc(c.impact.label.replace(/^\$?[\d.]+\s*(%|hours?)?\s*(of\s+)?/i, "")) + "</small></div>" +
      '<p class="small muted">Confidence ' + esc(c.confidence) + " · " + esc(c.assumptions[0] || "") + (c.advisory ? " · advisory" : "") + "</p>" + approvals +
      '<div class="foot"><a class="btn sm" href="#/intelligence/insights/' + esc(c.insightId) + '">Review recommendation' + ic("arrow", 14) + "</a></div></article>";
  }
  function capacityChart(est) {
    var W = 560, H = 210, x0 = 110, max = 40, sc = (W - x0 - 100) / max;
    var rows = [[est.source, est.before.source_hours, est.after.source_hours, "#3555E8"], [est.target, est.before.target_hours, est.after.target_hours, "#087E76"]];
    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-labelledby="cap-t cap-d"><title id="cap-t">Confocal utilization before and after the proposed move</title>' +
      '<desc id="cap-d">' + esc(rows.map(function (r) { return r[0] + ": " + r[1] + " h now, " + r[2] + " h after"; }).join("; ") + "; staffed capacity 40 h each.") + "</desc>";
    rows.forEach(function (r, i) {
      var y = 24 + i * 86;
      svg += '<text x="0" y="' + (y + 16) + '" class="lbl">' + esc(r[0].replace("_", "-").replace("confocal", "Confocal")) + "</text>" +
        '<text x="0" y="' + (y + 52) + '">after move</text>' +
        '<rect x="' + x0 + '" y="' + y + '" width="' + r[1] * sc + '" height="24" rx="4" fill="' + r[3] + '"/>' +
        '<text x="' + (x0 + r[1] * sc + 6) + '" y="' + (y + 16) + '">' + r[1] + " h (" + Math.round(r[1] / max * 1000) / 10 + "%)</text>" +
        '<rect x="' + x0 + '" y="' + (y + 36) + '" width="' + r[2] * sc + '" height="24" rx="4" fill="' + r[3] + '" fill-opacity=".28" stroke="' + r[3] + '" stroke-dasharray="4 3"/>' +
        '<text x="' + (x0 + r[2] * sc + 6) + '" y="' + (y + 52) + '">' + r[2] + " h (" + Math.round(r[2] / max * 1000) / 10 + "%)</text>";
    });
    svg += '<line x1="' + (x0 + max * sc) + '" y1="12" x2="' + (x0 + max * sc) + '" y2="' + (H - 18) + '" stroke="#64748B" stroke-dasharray="2 3"/>' +
      '<text x="' + (x0 + max * sc - 4) + '" y="' + (H - 4) + '" text-anchor="end">40 h staffed capacity</text></svg>';
    return svg + '<p class="small muted">Solid: booked now. Dashed: after ' + esc(est.movable_hours) + " flexible hours move (total stays " + esc(est.total_hours_after) + " h). Nothing moves until each owner agrees.</p>";
  }
  function demandChart(hist, fc, util) {
    var W = 420, H = 190, L = 34, R = 26, T = 12, B = 30, max = 44;
    var n = hist.length + 1, step = (W - L - R) / (n - 1 || 1);
    function X(i) { return L + i * step; }
    function Y(v) { return T + (H - T - B) * (1 - v / max); }
    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc("Weekly hours: " + hist.map(function (h) { return h.week_start + " booked " + h.booked_hours + ", requested " + h.requested_hours; }).join("; ") + (fc ? "; forecast " + fc.forecast_week + " " + fc.predicted_hours + " h (" + fc.low + "–" + fc.high + ")" : "")) + '">';
    [0, 20, 40].forEach(function (v) { svg += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" stroke="#E2E8F0"/><text x="' + (L - 6) + '" y="' + (Y(v) + 4) + '" text-anchor="end">' + v + "</text>"; });
    svg += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(40) + '" y2="' + Y(40) + '" stroke="#64748B" stroke-dasharray="2 3"/>';
    function path(key) { return hist.map(function (h, i) { return (i ? "L" : "M") + X(i) + " " + Y(h[key]); }).join(" "); }
    if (hist.length) {
      svg += '<path d="' + path("requested_hours") + '" fill="none" stroke="#3555E8" stroke-width="1.5" stroke-dasharray="1 4" stroke-linecap="round"/>';
      svg += '<path d="' + path("booked_hours") + '" fill="none" stroke="#3555E8" stroke-width="2"/>';
      hist.forEach(function (h, i) { svg += '<text x="' + X(i) + '" y="' + (H - 10) + '" text-anchor="middle">' + esc(MO[+h.week_start.slice(5, 7) - 1] + " " + +h.week_start.slice(8, 10)) + "</text>"; });
    }
    var xi = X(n - 1);
    if (fc) {
      var last = hist[hist.length - 1];
      svg += '<rect x="' + (xi - 9) + '" y="' + Y(fc.high) + '" width="18" height="' + (Y(fc.low) - Y(fc.high)) + '" fill="#7C5CD6" fill-opacity=".14"/>' +
        (last ? '<line x1="' + X(n - 2) + '" y1="' + Y(last.booked_hours) + '" x2="' + xi + '" y2="' + Y(fc.predicted_hours) + '" stroke="#7C5CD6" stroke-width="2" stroke-dasharray="6 4"/>' : "") +
        '<circle cx="' + xi + '" cy="' + Y(fc.predicted_hours) + '" r="4" fill="#7C5CD6"/>';
    }
    if (util) svg += '<rect x="' + (xi - 4) + '" y="' + (Y(util.booked_hours) - 4) + '" width="8" height="8" fill="#0F172A"/>';
    svg += '<text x="' + xi + '" y="' + (H - 10) + '" text-anchor="middle">Nov 2</text></svg>';
    return svg + '<p class="small muted">Solid: booked · dotted: requested · dashed violet: forecast with illustrative range · square: already booked for Nov 2 · dotted line: 40 h capacity.</p>';
  }
  function forecastMeta(fcs) {
    var f = fcs.confocal_1 || fcs.confocal_2;
    if (!f) return '<p class="small muted">No forecast run yet. Running the department review also computes the confocal forecasts.</p>';
    return '<p class="small" style="margin-top:8px">Forecast method: <b>weighted baseline v1</b> (' + esc(f.model_kind.replace(/_/g, " ")) + ") · " +
      Object.keys(fcs).map(function (k) { return esc(k) + ": " + fcs[k].predicted_hours + " h predicted, backtest MAE " + (Math.round(fcs[k].mae * 100) / 100) + " h"; }).join(" · ") +
      " · run " + esc(fmtStamp(f.generated_at)) + '<br><span class="muted">' + esc(f.interval_label) + ". Six weeks of synthetic history.</span></p>";
  }
  function utilTable(snap, names) {
    return '<table style="margin-top:10px"><thead><tr><th>Instrument</th><th class="n">Booked h</th><th class="n">Staffed h</th><th class="n">Utilization</th><th>Level</th></tr></thead><tbody>' +
      snap.utilization.map(function (u) {
        var lvl = u.utilization >= 0.85 ? '<span class="badge awaiting">High</span>' : u.utilization < 0.25 ? '<span class="badge info">Low</span>' : '<span class="badge">Normal</span>';
        return "<tr><td>" + esc(names[u.resource_id]) + '</td><td class="n">' + u.booked_hours + '</td><td class="n">' + u.available_hours + '</td><td class="n">' + pct(u.utilization) + "</td><td>" + lvl + "</td></tr>";
      }).join("") + "</tbody></table>";
  }

  // ------------------------------------------------------------------ Screen 6: decision case
  function viewInsight(id) {
    crumbs(["Department", "Insights", "Decision case"]);
    loading();
    api("GET", "/api/department").then(function (r) {
      if (!r.ok) return deptDenied(r);
      var d = r.data, ins = d.insights[id];
      var card = d.review && d.review.output ? d.review.output.cards.filter(function (c) { return c.insightId === id; })[0] : null;
      if (!ins) { view.innerHTML = '<div class="panel empty"><b>This insight is not detected in the current data.</b><a href="#/intelligence">Back to insights</a></div>'; return; }
      var est = ins.estimate, left = "", value = "";
      if (ins.kind === "pooled_order") {
        var q = ins.detail.quantities_by_lab, sku = ins.detail.sku_id, nl = Object.keys(q).length;
        var ship = nl > 1 ? est.shipping_component_usd / (nl - 1) : 0;
        var unit = (est.unpooled_total_usd - ship * nl) / est.total_quantity;
        value = "Estimated potential: " + usd(est.potential_savings_usd);
        left = '<div class="math"><div class="box"><div class="eyebrow">Separate orders</div><div class="big">' + usd(est.unpooled_total_usd) + "</div><ul class=\"small\">" +
          Object.keys(q).map(function (l) { return "<li>" + esc(labOf(l)) + ": " + q[l] + " × " + usd(unit) + " + " + usd(ship) + " shipping</li>"; }).join("") + "</ul></div>" +
          '<div class="box after"><div class="eyebrow">Pooled order</div><div class="big">' + usd(est.pooled_total_usd) + '</div><ul class="small"><li>' + est.total_quantity + " × " + usd(est.pooled_unit_price_usd) +
          " (volume tier) + " + usd(ship) + " shipping once</li></ul></div></div>" +
          '<p style="margin-top:12px"><b>Potential ' + usd(est.potential_savings_usd) + "</b> = " + usd(est.volume_component_usd) + " volume + " + usd(est.shipping_component_usd) + " shipping. Not realized until both labs and the department agree and someone actually orders.</p>" +
          '<h3 style="margin-top:16px">Affected orders</h3><ul class="small">' + ins.candidate_ids.map(function (o) { return '<li class="mono">' + esc(o) + " · " + esc(sku) + "</li>"; }).join("") + "</ul>" +
          (d.exclusions.length ? '<h3 style="margin-top:12px">Not pooled</h3><ul class="small">' + d.exclusions.map(function (x) { return "<li>" + esc((x.order_ids || x.ids || []).join(", ")) + ": " + esc(x.reason) + "</li>"; }).join("") + "</ul>" : "");
      } else if (ins.kind === "overload_rebalance") {
        value = "Potential relief: " + est.movable_hours + " hours";
        left = '<div class="math"><div class="box"><div class="eyebrow">Now</div><div class="big">' + est.before.source_hours + " h / " + est.before.target_hours + ' h</div><p class="small">' + esc(named(est.source)) + " " + pct(est.before.source_utilization) + " · " + esc(named(est.target)) + " " + pct(est.before.target_utilization) + "</p></div>" +
          '<div class="box after"><div class="eyebrow">After the moves</div><div class="big">' + est.after.source_hours + " h / " + est.after.target_hours + ' h</div><p class="small">' + esc(named(est.source)) + " " + pct(est.after.source_utilization) + " · " + esc(named(est.target)) + " " + pct(est.after.target_utilization) + "</p></div></div>" +
          '<p class="small muted" style="margin-top:8px">Total workload stays ' + est.total_hours_after + " h; only the instrument changes.</p>" +
          '<h3 style="margin-top:16px">Proposed moves (owners must agree)</h3><table><thead><tr><th>Booking</th><th>Owner</th><th>When</th><th class="n">Hours</th></tr></thead><tbody>' +
          est.moves.map(function (m) { return '<tr><td class="mono">' + esc(m.booking_id) + "</td><td>" + esc(person(m.owner_id)) + " · " + esc(labOf(m.lab_id)) + "</td><td>" + esc(fmtDay(m.start) + " " + range(m.start, m.end)) + '</td><td class="n">' + m.hours + "</td></tr>"; }).join("") + "</tbody></table>" +
          (est.excluded.length ? '<p class="small" style="margin-top:8px">Excluded: ' + esc(est.excluded.map(function (x) { return x.booking_id + " (" + x.reason + ")"; }).join(", ")) + "</p>" : "");
      } else {
        value = esc(est.resource_id) + " used " + pct(est.utilization);
        left = '<p><b>' + est.booked_hours + " of " + est.available_hours + " staffed hours</b> booked next week; " + est.low_weeks + " of " + est.weeks_observed + " observed weeks were low.</p>" +
          '<table style="margin-top:10px"><thead><tr><th>Week</th><th class="n">Booked h</th><th class="n">Utilization</th></tr></thead><tbody>' +
          est.history.map(function (h) { return "<tr><td>" + esc(fmtDay(h.week_start)) + '</td><td class="n">' + h.booked_hours + '</td><td class="n">' + pct(h.utilization) + "</td></tr>"; }).join("") + "</tbody></table>" +
          '<p class="small" style="margin-top:10px">Overflow: ' + esc(est.overflow_sources.map(function (o) { return o.resource_id + " at " + pct(o.utilization) + " with about " + o.avg_unmet_hours_per_week + " unmet h/week"; }).join("; ")) + "</p>" +
          '<ul class="small">' + est.suggested_next_steps.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ul><p class=\"why\">" + esc(est.caveat) + "</p>";
      }
      var proposed = ins.state !== "detected";
      var cta = card && card.nextStep ? card.nextStep.label : ins.kind === "pooled_order" ? "Propose shared order" : "Propose action";
      var right = '<section class="panel"><div class="panel-h"><h2>Why this matters</h2></div><div class="panel-b stack s8 small">' +
        "<p>" + esc(card ? named(card.summary) : "Run the department review for the written summary.") + "</p>" +
        (card ? "<p><b>Confidence:</b> " + esc(card.confidence) + "</p>" : "") +
        "<div><b>Assumptions</b><ul>" + ins.assumptions.map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("") + "</ul></div>" +
        (card && card.limitations.length ? "<div><b>Limitations</b><ul>" + card.limitations.map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("") + "</ul></div>" : "") +
        "<div><b>Required approvers</b><ul class=\"list\" style=\"margin-top:6px\">" + ins.required_approvals.map(function (p) {
          var a = (ins.approvals || []).filter(function (x) { return x.approver_id === p; })[0];
          return '<li class="row between"><span>' + esc(person(p)) + "</span>" + (a ? stateBadge(a.status === "decided" ? (a.decision === "approve" ? "approved" : "rejected") : "pending") : '<span class="badge">Not asked</span>') + "</li>";
        }).join("") + "</ul></div>" +
        '<p><b>Evidence:</b> <span class="mono">' + esc((card ? card.evidenceIds : ins.candidate_ids).join(", ")) + "</span></p>" +
        '<div><button class="btn primary" data-act="propose"' + (proposed ? " disabled" : "") + ">" + esc(cta) + "</button>" +
        '<p class="why">' + (proposed ? "Already proposed. Waiting for the approvers above." : "Creates approval requests for the people above. No order, booking or payment happens.") + "</p></div></div></section>";
      view.innerHTML = '<div class="plan-head"><div><div class="eyebrow">Decision case · ' + esc(ins.kind.replace(/_/g, " ")) + "</div><h1>" + esc(card ? named(card.headline) : id) + "</h1>" +
        '<p class="muted">' + value + " · " + stateBadge(ins.state) + '</p></div><a class="btn" href="#/intelligence">Back to insights</a></div>' +
        '<div class="case"><section class="panel"><div class="panel-b">' + left +
        '<details class="how" style="margin-top:16px"><summary>How calculated</summary><pre>' + esc((est.formula ? est.formula + "\n\n" : "") + JSON.stringify(est, null, 2)) + "</pre>" +
        '<p class="small muted">Snapshot ' + esc(ins.input_snapshot_id) + " · data as of " + esc(fmtStamp(d.snapshot.data_timestamp)) + " · synthetic data</p></details></div></section>" + right + "</div>";
      on("propose", function (btn) {
        modal({
          title: cta, ok: "Propose",
          body: "<p>This sends approval requests to " + esc(ins.required_approvals.map(person).join(", ")) + ". Approving records consent only; nothing is purchased, booked or moved automatically.</p>",
          onOk: function () {
            return api("POST", "/api/insights/" + encodeURIComponent(id) + "/propose", { week: d.week }).then(function (r2) {
              if (!r2.ok) { toast(errText(r2.data), true); return; }
              toast("Proposed. " + r2.data.approvals.length + " approval requests created.");
              viewInsight(id);
            });
          }
        });
      });
    });
  }

  // ------------------------------------------------------------------ Screen 9: activity
  function viewActivity(requestId) {
    crumbs(["Activity", requestId]);
    loading();
    api("GET", "/api/activity?request_id=" + encodeURIComponent(requestId)).then(function (r) {
      if (!r.ok) { view.innerHTML = '<div class="banner err">' + ic("alert") + esc(errText(r.data)) + "</div>"; return; }
      var d = r.data;
      view.innerHTML = '<div class="plan-head"><div><div class="eyebrow">Activity · request ' + esc(requestId) + "</div><h1>Audit trail</h1>" +
        '<p class="muted">Every change has an actor, time and before/after. Agent reasoning is not shown; the tool log is.</p></div>' +
        '<label class="toggle"><input type="checkbox" id="tech"' + (S.techView ? " checked" : "") + "> Tool execution</label></div>" +
        '<div class="case"><section class="panel"><div class="panel-b">' + (d.events.length ? '<ol class="timeline">' + d.events.map(function (e) {
          var bad = e.status !== "ok";
          return '<li><span class="dotc' + (bad ? " bad" : "") + '" aria-hidden="true">' + ic(bad ? "x" : "check", 12) + "</span><div><b>" + esc(e.label) + '</b><div class="small muted">' + esc(e.actor_name) + " · " + esc(fmtStamp(e.created_at)) +
            ' · <span class="mono">' + esc(e.entity_id || "") + "</span></div>" +
            (S.techView ? '<div class="small mono muted" style="margin-top:4px">' + esc(e.operation) + (e.before ? " · before " + JSON.stringify(e.before).slice(0, 160) : "") + (e.after ? " · after " + JSON.stringify(e.after).slice(0, 200) : "") + "</div>" : "") + "</div></li>";
        }).join("") + "</ol>" : '<div class="empty"><b>No activity you can see for this request.</b></div>') + "</div></section>" +
        '<section class="panel"><div class="panel-h"><h2>Agent runs</h2></div><div class="panel-b">' + (d.runs.length ? d.runs.map(function (run) {
          return '<div class="tool"><div class="row between"><b>' + esc(run.agent.replace(/_/g, " ")) + "</b>" + stateBadge(run.status === "completed" ? "ok" : run.status) + '</div><div class="small muted">' +
            esc((run.mode === "live" ? "Claude " + (run.model || "") : "offline mock") + " · " + fmtStamp(run.started_at) + " · run " + run.run_id) + "</div>" +
            (S.techView ? '<ol class="small mono" style="padding-left:18px;margin:8px 0 0">' + run.tool_calls.map(function (c) { return "<li>" + esc(c.name) + " → " + esc(JSON.stringify(c.result)) + "</li>"; }).join("") + "</ol>" :
              '<p class="small">' + esc(run.tool_calls.map(function (c) { return c.name; }).join(" → ")) + "</p>") + "</div>";
        }).join("") : '<p class="muted small">No agent runs you can see for this request.</p>') + "</div></section></div>";
      document.getElementById("tech").addEventListener("change", function (e) { S.techView = e.target.checked; viewActivity(requestId); });
    });
  }

  // ------------------------------------------------------------------ demo controls
  function demoControls() {
    var token = "";
    try { token = sessionStorage.getItem("labsync.token") || ""; } catch (e) { /* ignore */ }
    modal({
      title: "Demo controls", ok: "Reset demo data", danger: true,
      body: '<p class="small">Developer-only. Restores the synthetic <b>Imaging Tuesday</b> seed: bookings, orders, approvals and agent runs. It never touches real data and sends nothing.</p>' +
        '<div class="field" style="margin-top:12px"><label for="tok">Reset token (printed when the server starts)</label><input id="tok" type="password" autocomplete="off" value="' + esc(token) + '"></div>' +
        '<p style="margin-top:14px"><button type="button" class="btn sm" id="seed">Seed scenario: Imaging Tuesday</button> <span class="small muted">Fills in the sample request; doesn\'t submit it.</span></p>',
      onOk: function (bg) {
        var t = bg.querySelector("#tok").value;
        try { sessionStorage.setItem("labsync.token", t); } catch (e) { /* ignore */ }
        return api("POST", "/api/reset", { token: t }).then(function (r) {
          if (!r.ok) { toast(r.data.code === "RESET_NOT_ALLOWED" ? "Wrong reset token." : errText(r.data), true); return true; }
          S.selected = {}; S.lastRun = null;
          toast("Demo data reset to the Imaging Tuesday seed.");
          location.hash = "#/";
          refreshAll();
        });
      }
    });
    document.getElementById("seed").addEventListener("click", function () {
      document.getElementById("modal-root").innerHTML = "";
      S.seed = CANONICAL;
      if (S.persona !== "morgan") { S.persona = "morgan"; save("persona", "morgan"); }
      if (location.hash === "#/workspace") refreshAll(); else { location.hash = "#/workspace"; loadSession(); }
    });
  }

  // ------------------------------------------------------------------ boot
  S.persona = load("persona") || "morgan";
  document.getElementById("persona").addEventListener("change", function (e) {
    S.persona = e.target.value;
    save("persona", S.persona);
    loadSession().then(function () {
      announce("Now acting as " + S.session.persona.name + " (simulated identity)");
      var part = location.hash.split("/")[1];
      if (part === "plans" || part === "workspace" || part === "intelligence") {
        if (!S.session.persona.lab_id && part !== "intelligence") { location.hash = "#/"; return route(); }
      }
      route();
    });
  });
  document.getElementById("demo-controls").addEventListener("click", demoControls);
  window.addEventListener("hashchange", route);
  loadSession().then(route);
})();
