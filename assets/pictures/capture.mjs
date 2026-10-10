#!/usr/bin/env node
// Takes the pictures in this directory. Two jobs:
//
//   node assets/pictures/capture.mjs                 every shot in shots.json, then every picture
//   node assets/pictures/capture.mjs word map        the named shots only
//   node assets/pictures/capture.mjs --compose       only render the <name>.html pictures
//   node assets/pictures/capture.mjs --compose word  …or the named ones
//
// A shot is the real application, signed in to the server named in ../../credentials.env and driven
// the way a person drives it: the search box, the rail, the gear. It reads; it cannot write. Every
// request that is not a read is refused before it leaves the browser, apart from signing in and the
// routes a shot names in `allow`, each of which the server documents as writing nothing.
//
// See README.md in this directory for the format and the shot list.

import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
// Playwright is a dev dependency of web/, and an ES module import would look beside this file.
const { chromium } = createRequire(join(root, "web/package.json"))("playwright");

const API = "/api/acervo/v1";
const ALWAYS_ALLOWED = ["/session", "/session/refresh"];
const DEVICES = {
  // 1280×800 at 1.5 is 1920×1200, the blog's picture size, with nothing to crop.
  desktop: { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1.5 },
  // The same 1920×1200 from a smaller window, so the text is larger on a project card.
  compact: { viewport: { width: 960, height: 600 }, deviceScaleFactor: 2 },
  tablet: { viewport: { width: 834, height: 1112 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true },
  phone: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, hasTouch: true, isMobile: true }
};

function credentials() {
  const path = join(root, "credentials.env");
  if (!existsSync(path)) throw new Error("credentials.env is missing; copy credentials.env.example and fill it in.");
  const found = {};
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const match = /^([A-Z_]+)=(.*)$/.exec(line.trim());
    if (!match) continue;
    const raw = match[2];
    // The file is written for a shell: single-quoted, with a quote inside spelt '\''.
    found[match[1]] = raw.startsWith("'") && raw.endsWith("'") ? raw.slice(1, -1).replaceAll("'\\''", "'") : raw;
  }
  for (const key of ["ACERVO_SERVER_URL", "ACERVO_OWNER_EMAIL", "ACERVO_OWNER_PASSWORD"]) {
    if (!found[key]) throw new Error(`credentials.env has no ${key}.`);
  }
  return { url: found.ACERVO_SERVER_URL.replace(/\/+$/, ""), email: found.ACERVO_OWNER_EMAIL, password: found.ACERVO_OWNER_PASSWORD };
}

/** Refuse every write. `allowed` is the current shot's own list, replaced as shots change. */
async function guard(context, origin, allowed) {
  await context.route((url) => url.origin === origin, (route) => {
    const request = route.request();
    if (["GET", "HEAD", "OPTIONS"].includes(request.method())) return route.continue();
    const path = new URL(request.url()).pathname.replace(API, "");
    if (ALWAYS_ALLOWED.includes(path) || allowed.current.includes(path)) return route.continue();
    console.warn(`  refused ${request.method()} ${path}`);
    return route.abort();
  });
}

async function open(device, account, allowed) {
  const profile = join(root, "output/screenshots/profile", device);
  mkdirSync(profile, { recursive: true });
  const context = await chromium.launchPersistentContext(profile, {
    // Installed Chrome rather than Playwright's Chromium, which cannot decode the clips' video.
    channel: "chrome", headless: true, colorScheme: "light", locale: "en-GB", ...DEVICES[device]
  });
  await guard(context, new URL(account.url).origin, allowed);
  const page = context.pages()[0] ?? await context.newPage();
  await page.goto(account.url, { waitUntil: "domcontentloaded" });
  const signIn = page.locator("form.signin");
  const app = page.locator(".app");
  await signIn.or(app).first().waitFor({ timeout: 60_000 });
  if (await signIn.isVisible()) {
    await page.fill("#email", account.email);
    await page.fill("#password", account.password);
    await page.click("form.signin button[type=submit]");
  }
  await app.waitFor({ timeout: 60_000 });
  // The first run on a device pulls the whole vocabulary into the profile; later runs find it there.
  await ready(page);
  return { context, page };
}

/** The vocabulary is on screen: its count is in the rail, shown or (on a narrow screen) not. */
async function ready(page) {
  await page.locator(".rail .tab .cnt").first().waitFor({ state: "attached", timeout: 300_000 });
}

/** One step of a shot. Each is what a person would do, named by what they would see. */
async function step(page, action) {
  const [[kind, value]] = Object.entries(action);
  switch (kind) {
    case "language": {
      await page.click(".lang-btn");
      await page.locator(".menu.open button", { hasText: value }).first().click();
      break;
    }
    case "word": {
      await page.fill(".search input", value);
      // Your own word of exactly that name, never a longer one or a dictionary's row.
      await page.locator(".row:not(.ext)").filter({ has: page.getByText(value, { exact: true }) }).first().click();
      await page.locator(".app.article-open").waitFor();
      break;
    }
    case "rail": await page.locator(`.rail .tab[title="${value}"]`).click(); break;
    case "settings": {
      await page.click(".icon-btn.gear");
      await page.locator(".settings button", { hasText: value }).first().click();
      break;
    }
    case "click": await page.locator(value).first().click(); break;
    case "clickText": await page.getByText(value, { exact: false }).first().click(); break;
    case "fill": await page.locator(value.in).first().fill(value.text); break;
    case "upload": await page.locator(value.in).first().setInputFiles(join(root, value.file)); break;
    case "tap": {
      // A point inside an element, as fractions of its width and height.
      const box = await page.locator(value.in).first().boundingBox();
      await page.mouse.click(box.x + box.width * value.x, box.y + box.height * value.y);
      break;
    }
    case "press": await page.keyboard.press(value); break;
    case "waitFor": await page.locator(value).first().waitFor({ timeout: 180_000 }); break;
    case "wait": await page.waitForTimeout(value); break;
    case "scrollTo": await page.locator(value).first().scrollIntoViewIfNeeded(); break;
    case "scrollBy": await page.locator(value.in).first().evaluate((node, top) => { node.scrollTop += top; }, value.top); break;
    case "hide": await page.addStyleTag({ content: `${value} { visibility: hidden !important; }` }); break;
    case "style": await page.addStyleTag({ content: value }); break;
    default: throw new Error(`Unknown step "${kind}".`);
  }
}

/**
 * Fonts in and every picture on screen drawn. Not "network idle": the application keeps a stream
 * open to the server for the whole session, so the network is never idle.
 */
async function settled(page) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(
    () => [...document.images].every((image) => image.complete && (image.naturalWidth > 0 || !image.currentSrc)),
    null, { timeout: 30_000 }
  ).catch(() => {});
}

async function take(page, shot) {
  for (const action of shot.steps ?? []) await step(page, action);
  await settled(page);
  await page.waitForTimeout(shot.settle ?? 600);
  const target = join(outDir, `${shot.name}.png`);
  // `element` takes one part of the screen, for a picture that is composed from several.
  await (shot.element ? page.locator(shot.element).first() : page).screenshot({
    path: target,
    mask: (shot.mask ?? []).map((selector) => page.locator(selector)),
    maskColor: "#e6ebea",
    ...(shot.clip ? { clip: shot.clip } : {})
  });
  squeeze(target);
  console.log(target.replace(`${here}/`, ""));
}

function squeeze(path) {
  try { execFileSync("pngquant", ["--force", "--skip-if-larger", "--output", path, "256", path], { stdio: "ignore" }); }
  catch { /* larger, or pngquant is not installed: the file stays as it was written */ }
}

async function capture(names) {
  const shots = JSON.parse(readFileSync(shotList, "utf8")).shots
    .filter((shot) => names.length === 0 || names.includes(shot.name));
  if (shots.length === 0) return;
  mkdirSync(outDir, { recursive: true });
  const account = credentials();
  for (const device of Object.keys(DEVICES)) {
    const mine = shots.filter((shot) => (shot.device ?? "desktop") === device);
    if (mine.length === 0) continue;
    const allowed = { current: [] };
    const { context, page } = await open(device, account, allowed);
    try {
      for (const shot of mine) {
        allowed.current = shot.allow ?? [];
        // Each shot starts from a fresh load, so none depends on where the last one left the app.
        // The app reopens the word it was last on; a shot starts from the list instead.
        await page.evaluate(() => localStorage.removeItem("acervo-last-place"));
        await page.goto(account.url, { waitUntil: "domcontentloaded" });
        await ready(page);
        // A shot may be taller or wider than its device, to get a whole page into one picture.
        await page.setViewportSize(shot.viewport ?? DEVICES[device].viewport);
        try { await take(page, shot); }
        catch (failure) {
          await page.screenshot({ path: join(root, "output/screenshots", `failed-${shot.name}.png`) });
          console.error(`FAILED ${shot.name}: ${failure.message.split("\n")[0]}`);
          process.exitCode = 1;
        }
      }
    } finally { await context.close(); }
  }
}

/** Render <name>.html at twice the size its <meta name="picture-size"> declares. */
async function compose(names) {
  const pages = readdirSync(here).filter((file) => file.endsWith(".html")).map((file) => file.slice(0, -5))
    .filter((name) => names.length === 0 || names.includes(name));
  if (pages.length === 0) return;
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  try {
    for (const name of pages) {
      const source = readFileSync(join(here, `${name}.html`), "utf8");
      const size = /name="picture-size" content="(\d+)x(\d+)"/.exec(source);
      if (!size) throw new Error(`${name}.html declares no picture-size.`);
      const page = await browser.newPage({
        viewport: { width: Number(size[1]), height: Number(size[2]) }, deviceScaleFactor: 2, colorScheme: "light"
      });
      await page.goto(`file://${join(here, `${name}.html`)}`, { waitUntil: "load" });
      await page.evaluate(() => document.fonts.ready);
      const target = join(here, `${name}.png`);
      await page.screenshot({ path: target });
      await page.close();
      squeeze(target);
      console.log(`${name}.png`);
    }
  } finally { await browser.close(); }
}

const args = process.argv.slice(2);
// Trying a shot out before it joins the list: --shots <file> --out <directory>.
const option = (name, fallback) => {
  const at = args.indexOf(name);
  return at < 0 ? fallback : resolve(args.splice(at, 2)[1]);
};
const shotList = option("--shots", join(here, "shots.json"));
const outDir = option("--out", join(here, "shots"));
const names = args.filter((arg) => !arg.startsWith("--"));
if (!args.includes("--compose")) await capture(names);
await compose(args.includes("--compose") ? names : names.filter((name) => existsSync(join(here, `${name}.html`))));
