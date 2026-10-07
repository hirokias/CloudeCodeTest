// 評価仕様: 「スタート」押下後、結果が確定するまでボタンが押下されても無視されること。
// 実行: node tests/spin-lock.test.mjs  (playwright が require で解決できること。例: NODE_PATH=$(npm root -g))
// ROULETTE_URL を指定すると、別の HTML を評価対象にできる。
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const PAGE_URL = process.env.ROULETTE_URL || pathToFileURL(path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "index.html")).href;
const SPIN_MS = 4500;
const OBSERVE_MS = 10000; // 連打中に2回目の回転が始まっていれば、その結果も現れる長さ

// ページ内で結果欄とボタン状態の変化を時刻付きで記録する
const INSTRUMENT = () => {
  window.__log = [];
  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("spin");
    const res = document.getElementById("result");
    new MutationObserver(() => {
      if (res.textContent.startsWith("結果:")) window.__log.push({ t: performance.now(), kind: "result", text: res.textContent });
    }).observe(res, { childList: true, characterData: true, subtree: true });
    new MutationObserver(() => {
      window.__log.push({ t: performance.now(), kind: btn.disabled ? "lock" : "unlock" });
    }).observe(btn, { attributes: true, attributeFilter: ["disabled"] });
  });
};

const sleep = ms => new Promise(r => setTimeout(r, ms));

// 各ケースは「1回目の押下」と「回転中の追加押下」を行う関数を持つ
const CASES = [
  {
    name: "マウス連打(実座標クリック 20回/50ms間隔)",
    run: async p => {
      const box = await p.locator("#spin").boundingBox();
      const x = box.x + box.width / 2, y = box.y + box.height / 2;
      for (let i = 0; i < 20; i++) { await p.mouse.click(x, y); await sleep(50); }
    },
  },
  {
    name: "ダブルクリック直後に連打(dblclick + 10回)",
    run: async p => {
      await p.locator("#spin").dblclick();
      for (let i = 0; i < 10; i++) { await p.locator("#spin").click({ force: true }); await sleep(100); }
    },
  },
  {
    name: "キーボード連打(Enter/Space 交互 20回)",
    run: async p => {
      await p.locator("#spin").focus();
      for (let i = 0; i < 20; i++) { await p.keyboard.press(i % 2 ? "Space" : "Enter"); await sleep(50); }
    },
  },
  {
    name: "スクリプトからの click() 連続呼び出し(回転中を通じて40回)",
    run: async p => {
      await p.evaluate(() => document.getElementById("spin").click());
      for (let i = 0; i < 40; i++) { await p.evaluate(() => document.getElementById("spin").click()); await sleep(100); }
    },
  },
  {
    name: "disabled を外した状態での押下(内部フラグによる防御の確認)",
    run: async p => {
      await p.locator("#spin").click();
      for (let i = 0; i < 20; i++) {
        await p.evaluate(() => { const b = document.getElementById("spin"); b.disabled = false; b.click(); });
        await sleep(150);
      }
    },
  },
];

const results = [];
const browser = await chromium.launch();
try {
  for (const c of CASES) {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    const errors = [];
    p.on("pageerror", e => errors.push(e.message));
    await p.addInitScript(INSTRUMENT);
    await p.goto(PAGE_URL);

    const t0 = await p.evaluate(() => performance.now());
    await c.run(p);
    await sleep(Math.max(0, OBSERVE_MS - (await p.evaluate(t => performance.now() - t, t0))));
    const log = await p.evaluate(() => window.__log);

    const resultEvents = log.filter(e => e.kind === "result");
    const first = resultEvents[0];
    const elapsed = first ? first.t - t0 : NaN;
    const checks = {
      "結果の確定は1回のみ": resultEvents.length === 1,
      "確定時刻が1回目押下から約4.5秒(延長なし)": elapsed > SPIN_MS - 100 && elapsed < SPIN_MS + 700,
      "ページエラーなし": errors.length === 0,
    };
    // 結果確定後は再び押下を受け付ける(恒久的にロックされていない)こと
    const btnEnabled = await p.evaluate(() => !document.getElementById("spin").disabled);
    if (c.name.startsWith("disabled を外した")) {
      checks["確定後に再押下で回転が始まる"] = await p.evaluate(() => {
        document.getElementById("spin").click();
        return document.getElementById("spin").disabled === true;
      });
    } else {
      checks["確定後にボタンが有効"] = btnEnabled;
      await p.locator("#spin").click();
      checks["確定後に再押下で回転が始まる"] = await p.evaluate(() => document.getElementById("spin").disabled === true);
    }

    const pass = Object.values(checks).every(Boolean);
    results.push({ name: c.name, pass });
    console.log(`\n[${pass ? "PASS" : "FAIL"}] ${c.name}`);
    console.log(`  結果確定回数=${resultEvents.length}  1回目押下→確定=${elapsed.toFixed(0)}ms  結果=${first ? first.text : "-"}`);
    for (const [k, v] of Object.entries(checks)) console.log(`  ${v ? "ok " : "NG "} ${k}`);
    if (errors.length) console.log(`  errors: ${errors.join(" / ")}`);
    await ctx.close();
  }
} finally {
  await browser.close();
}

const failed = results.filter(r => !r.pass).length;
console.log(`\n${results.length - failed}/${results.length} cases passed`);
process.exit(failed ? 1 : 0);
