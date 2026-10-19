// Browser smoke test of the canonical demo (docs/03 script) against a running local server.
//   LABSYNC_URL=http://127.0.0.1:8765 LABSYNC_RESET_TOKEN=... node tests/e2e/smoke.cjs [screenshot-dir]
// tests/web/test_e2e.py starts a fresh in-memory server and runs this. Needs the `playwright` package.
const { chromium } = require("playwright");

const BASE = process.env.LABSYNC_URL || "http://127.0.0.1:8765";
const TOKEN = process.env.LABSYNC_RESET_TOKEN || "";
const SHOTS = process.argv[2] || "";

let step = 0;
function log(msg) { step += 1; console.log(`ok ${step} - ${msg}`); }
async function shot(page, name) { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }); }
async function persona(page, id) {
  await page.selectOption("#persona", id);
  await page.waitForFunction((who) => document.getElementById("persona").value === who, id);
  await page.waitForTimeout(150);
}
async function confirmModal(page, label) {
  const dialog = page.getByRole("dialog");
  await dialog.waitFor();
  await dialog.getByRole("button", { name: label, exact: true }).click();
  await dialog.waitFor({ state: "detached" });
}

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error" && !/status of 403/.test(m.text())) errors.push(m.text()); }); // 403s are the expected permission checks
  try {
    await page.goto(BASE + "/#/workspace");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.getByRole("heading", { name: "What are you trying to run?" }).waitFor();
    if (!(await page.getByRole("button", { name: "Generate plan" }).isDisabled())) throw new Error("Generate should start disabled");
    await page.getByText("No experiment yet").waitFor();
    log("home composer, badges and empty state");
    await shot(page, "1-home");

    // Keyboard path: choose the sample chip, then Ctrl+Enter in the composer.
    await page.getByRole("button", { name: "Plan an imaging experiment" }).click();
    await page.locator("#goal").focus();
    await page.keyboard.press("Control+Enter");
    await page.waitForURL(/#\/plans\//);
    await page.getByText("Here's your plan.").waitFor();
    await page.getByText("Needs owner approval").waitFor();
    await page.getByText("requires certification").first().waitFor();
    log("Lab Agent plan with two options and the blocked Confocal-2");

    await page.locator(".blk.conflict").first().click();
    await page.locator("#popover").getByText("flexible (request permission)").waitFor();
    log("conflict detail names the owner lab and flexibility");
    await shot(page, "2-plan-conflict");

    await page.getByRole("button", { name: /Hold option 1/ }).click();
    await page.getByRole("button", { name: /Ask Chen to move/ }).waitFor();
    if (!(await page.getByRole("button", { name: "Commit plan" }).isDisabled())) throw new Error("Commit must wait for approvals");
    await page.getByText("Chen hasn't been asked yet.").waitFor();
    log("held proposal; commit disabled with a reason");
    await page.getByRole("button", { name: /Ask Chen to move/ }).click();
    await confirmModal(page, "Send request");
    await page.getByText("Waiting on Chen.").waitFor();
    log("move request sent to Chen");

    await persona(page, "chen_owner");
    await page.goto(BASE + "/#/approvals");
    await page.getByRole("heading", { name: /requests moving your Confocal Microscope 1 slot/ }).waitFor();
    await page.getByText("Suggestion: approve").waitFor();
    await shot(page, "3-chen-approval");
    await page.getByRole("button", { name: "Approve", exact: true }).click();
    await page.getByRole("dialog").getByText("Your booking moves only once the requester commits their plan.").waitFor();
    await confirmModal(page, "Approve");
    await page.getByText("Nothing is waiting on you.").waitFor();
    log("Chen approves the move in the inbox");

    await persona(page, "morgan");
    await page.goto(BASE + "/#/workspace");
    await page.getByRole("link", { name: "Open plan" }).first().click();
    await page.getByRole("button", { name: "Approve final schedule" }).click();
    await confirmModal(page, "Approve");
    const commit = page.getByRole("button", { name: "Commit plan" });
    await page.waitForFunction(() => { const b = [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "Commit plan"); return b && !b.disabled; });
    await commit.click();
    await page.getByRole("dialog").getByText("Move Chen Imaging's session", { exact: false }).waitFor();
    await confirmModal(page, "Commit");
    await page.getByText("Booked.", { exact: true }).waitFor();
    await page.locator(".blk.mine", { hasText: "10:00–13:00" }).waitFor();
    log("Morgan confirms and commits; receipt and booking on the timeline");
    await shot(page, "4-receipt");

    await page.getByRole("button", { name: "Draft supply requests" }).click();
    await page.getByText("Waiting for lab approval").first().waitFor();
    log("supply requests drafted, not ordered");

    await page.getByRole("link", { name: "View history" }).first().click();
    await page.getByText("Bookings committed").waitFor();
    log("audit trail shows the commit");

    await persona(page, "dept_admin");
    await page.goto(BASE + "/#/intelligence");
    await page.getByRole("heading", { name: "Department Intelligence" }).waitFor();
    await page.getByRole("button", { name: "Run department review" }).click();
    await page.locator(".ins").nth(2).waitFor();
    const cards = await page.locator(".ins").count();
    if (cards !== 3) throw new Error(`expected 3 insight cards, got ${cards}`);
    await page.getByText("92.5%").first().waitFor();
    log("department review: 3 cards, $95 and 92.5%");
    await shot(page, "5-department");

    await page.locator(".ins").first().getByRole("link", { name: /Review recommendation/ }).click();
    await page.getByText("$640").first().waitFor();
    await page.getByText("$545").first().waitFor();
    await page.getByRole("button", { name: "Propose shared order" }).click();
    await confirmModal(page, "Propose");
    await page.getByText("Already proposed. Waiting for the approvers above.").waitFor();
    log("pooled order case $640 → $545 proposed for approval");
    await shot(page, "6-pooled-case");

    await persona(page, "morgan");
    await page.goto(BASE + "/#/intelligence");
    await page.getByText("Department Intelligence is for department admins.").waitFor();
    log("researcher can't open department data");

    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(BASE + "/#/workspace");
    await page.getByRole("heading", { name: "What are you trying to run?" }).waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (overflow > 1) throw new Error(`horizontal overflow at 375px: ${overflow}px`);
    log("375px layout without horizontal scroll");
    await shot(page, "7-mobile");
    await page.setViewportSize({ width: 1440, height: 900 });

    await page.getByRole("button", { name: "Reset data" }).click();
    await page.locator("#tok").fill(TOKEN);
    await confirmModal(page, "Reset");
    await page.getByText("No experiment yet").waitFor();
    log("reset restores the seed");

    if (errors.length) throw new Error("browser errors: " + errors.join(" | "));
    console.log(`passed ${step} steps`);
  } catch (err) {
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/failure.png`, fullPage: true }).catch(() => {});
    console.error(`not ok ${step + 1} - ${err.message}`);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
