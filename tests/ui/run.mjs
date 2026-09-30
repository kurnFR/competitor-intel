import { JSDOM, VirtualConsole } from "jsdom";
const BASE = "http://127.0.0.1:8766";
const jar = new Map();
const results = [];
const check = (name, ok, extra = "") => { results.push(ok); console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  <-- " + extra)); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function cfetch(url, opts = {}) {
  const headers = new Headers(opts.headers || {});
  if (jar.size) headers.set("cookie", [...jar].map(([k, v]) => `${k}=${v}`).join("; "));
  const res = await fetch(new URL(url, BASE), { ...opts, headers, redirect: "manual" });
  for (const c of res.headers.getSetCookie?.() || []) {
    const [pair] = c.split(";"); const i = pair.indexOf("=");
    const k = pair.slice(0, i), v = pair.slice(i + 1);
    if (/max-age=0|expires=Thu, 01 Jan 1970/i.test(c)) jar.delete(k); else jar.set(k, v);
  }
  return res;
}

async function openPage(path) {
  const res = await cfetch(path);
  if (res.status !== 200) return { status: res.status, location: res.headers.get("location") };
  let html = await res.text();
  html = html.replace(/<script[^>]*src=[^>]*><\/script>/g, "").replace(/<link[^>]*stylesheet[^>]*>/g, "");   // no CDN in the sandbox
  html = html.replace(/location\.href\s*=/g, "window.__nav =");                                          // record navigation
  const errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", e => errors.push(String(e.message || e)));
  vc.on("error", (...a) => errors.push(a.join(" ")));
  const dom = new JSDOM(html, { url: BASE + path, runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      w.tailwind = {}; w.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
      w.fetch = (u, o = {}) => cfetch(u, o);
      w.confirm = () => true; w.prompt = () => "New-Temp-Password-123"; w.URL.createObjectURL = () => "blob:x";
      w.HTMLElement.prototype.scrollIntoView = () => {};
    } });
  await sleep(400);
  return { status: 200, dom, w: dom.window, d: dom.window.document, errors };
}
const $ = (p, sel) => p.d.querySelector(sel);
const setVal = (el, v) => { el.value = v; };
const submit = (p, form) => form.dispatchEvent(new p.w.Event("submit", { cancelable: true, bubbles: true }));

const [, , user, pass, secretFile] = process.argv;

// ---- 1. Login page, wrong password then right password
let p = await openPage("/login");
check("login page loads without script errors", p.status === 200 && p.errors.length === 0, p.errors.join("|"));
setVal($(p, "#username"), user); setVal($(p, "#password"), "wrong-password-xyz");
submit(p, $(p, "#login-form")); await sleep(600);
const errBox = $(p, "#error");
check("wrong password shows a generic error", !errBox.classList.contains("hidden") && /Invalid username or password/.test(errBox.textContent), errBox.textContent);
check("password field is cleared after a failure", $(p, "#password").value === "");
setVal($(p, "#password"), pass); submit(p, $(p, "#login-form")); await sleep(800);
check("correct password redirects to the dashboard", p.w.__nav === "/", String(p.w.__nav));

// ---- 2. Dashboard for a logged-in admin
p = await openPage("/");
check("dashboard loads without script errors", p.status === 200 && p.errors.length === 0, (p.errors || []).join("|"));
await sleep(600);
check("dashboard shows admin controls", !!$(p, "#scan-button") && !!p.d.querySelector('a[href="/admin"]'));
check("dashboard filled the table (or its empty state)", p.d.querySelector("#promo-table-body").children.length > 0);
const stat = p.d.body.textContent;
check("dashboard has no leftover template errors", !/undefined|\[object Object\]|NaN/.test(p.d.querySelector("#promo-table-body").textContent), p.d.querySelector("#promo-table-body").textContent.slice(0, 200));

// ---- 3. Other pages render and load data
for (const [path, marker] of [["/insights", "Promotion activity by competitor"], ["/compare", "Our prices vs competitor promotions"], ["/review", "Matches to confirm"], ["/admin", "Websites we scan"]]) {
  const q = await openPage(path); await sleep(700);
  check(`${path} renders with no script errors`, q.status === 200 && q.errors.length === 0 && q.d.body.textContent.includes(marker), (q.errors || []).join("|"));
}
const adminPage = await openPage("/admin"); await sleep(800);
check("admin page lists users and sources", adminPage.d.querySelectorAll("#users tr").length >= 1 && adminPage.d.querySelectorAll("#sources tr").length >= 1);
check("admin page lists security events", adminPage.d.querySelectorAll("#audit tr").length >= 1);

// ---- 4. Account page: enrol two-factor through the UI
p = await openPage("/account"); await sleep(500);
check("account page loads without script errors", p.status === 200 && p.errors.length === 0, (p.errors || []).join("|"));
check("2FA 'set up' button is offered", !$(p, "#mfa-off").classList.contains("hidden"));
$(p, "#mfa-start").dispatchEvent(new p.w.Event("click")); await sleep(700);
check("QR code and key are shown", !$(p, "#mfa-enroll").classList.contains("hidden") && $(p, "#mfa-qr").src.startsWith("data:image/svg+xml") && $(p, "#mfa-secret").textContent.length >= 16);
const secret = $(p, "#mfa-secret").textContent;
import { execSync } from "child_process";
const code = (offset) => execSync(`python3 -c "import pyotp,time;print(pyotp.TOTP('${secret}').at((int(time.time())//30+${offset})*30))"`).toString().trim();
setVal($(p, "#mfa-enable-form").elements["code"], "000000"); submit(p, $(p, "#mfa-enable-form")); await sleep(600);
check("wrong enrolment code shows an error", !$(p, "#mfa-msg").classList.contains("hidden") && /not correct/.test($(p, "#mfa-msg").textContent), $(p, "#mfa-msg").textContent);
setVal($(p, "#mfa-enable-form").elements["code"], code(0)); submit(p, $(p, "#mfa-enable-form")); await sleep(900);
const codes = $(p, "#mfa-code-list").textContent.trim().split("\n");
check("recovery codes are shown after enabling", !$(p, "#mfa-codes").classList.contains("hidden") && codes.length === 10, $(p, "#mfa-code-list").textContent);

// ---- 5. Logout, then sign in again through the two-step UI
p = await openPage("/"); await sleep(300);
await p.w.logout(); await sleep(500);
check("logout sends the user to the login page", p.w.__nav === "/login", String(p.w.__nav));
const after = await cfetch("/api/v1/stats/");
check("session is really gone after logout", after.status === 401, String(after.status));

p = await openPage("/login");
setVal($(p, "#username"), user); setVal($(p, "#password"), pass); submit(p, $(p, "#login-form")); await sleep(800);
check("login now asks for the 2FA code", $(p, "#login-form").classList.contains("hidden") && !$(p, "#mfa-form").classList.contains("hidden"));
check("no session before the code is entered", (await cfetch("/api/v1/stats/")).status === 401);
setVal($(p, "#mfa-code"), "123456"); submit(p, $(p, "#mfa-form")); await sleep(700);
check("wrong 2FA code shows an error and does not log in", !$(p, "#error").classList.contains("hidden") && p.w.__nav === undefined, String(p.w.__nav));
setVal($(p, "#mfa-code"), code(1)); submit(p, $(p, "#mfa-form")); await sleep(900);
check("correct 2FA code logs in and redirects", p.w.__nav === "/", String(p.w.__nav));
check("API works after 2FA login", (await cfetch("/api/v1/stats/")).status === 200);

// ---- 6. Recovery code path
await cfetch("/api/v1/auth/logout", { method: "POST", headers: { "X-CSRF-Token": (await (await cfetch("/api/v1/auth/me")).json()).csrf_token } });
p = await openPage("/login");
setVal($(p, "#username"), user); setVal($(p, "#password"), pass); submit(p, $(p, "#login-form")); await sleep(800);
setVal($(p, "#mfa-code"), codes[0]); submit(p, $(p, "#mfa-form")); await sleep(900);
check("a recovery code logs in", p.w.__nav === "/", String(p.w.__nav));

const failed = results.filter(x => !x).length;
console.log(`\n${results.length - failed}/${results.length} UI checks passed`);
process.exit(failed ? 1 : 0);
