const QUICKSTART_SNIPPETS = [
  {
    id: "cmake",
    label: "CMake Embed",
    filename: "CMakeLists.txt",
    code: `# Option 1: vendor directly
add_subdirectory(vendor/quickjs-turbo/vm)
target_link_libraries(my_app PRIVATE quickjs-turbo::qjs)

# Option 2: link prebuilt SDK
find_package(quickjs-turbo CONFIG REQUIRED)
target_link_libraries(my_app PRIVATE quickjs-turbo::qjs)`,
  },
  {
    id: "capi",
    label: "C API",
    filename: "embed.c",
    code: `#include "quickjs.h"
#include "quickjs-turbo.h"

void init_worker_pool(void) {
    QJSTurboOptions opts;
    QJS_TurboOptionsInit(&opts);
    opts.own_bytecode_tail = QJS_TURBO_OFF; /* PIC-only: zero tail copy */
    opts.property_ic_warmup = 16;           /* Lazy IC after 16 hits    */
    QJS_SetTurboDefaults(&opts);

    JSRuntime *rt = JS_NewRuntime();
    /* ... when worker becomes idle: */
    JS_PurgePropertyIC(rt);
}`,
  },
  {
    id: "source",
    label: "Build",
    filename: "build.sh",
    code: `# Linux x86-64
bash vm/tools/x86/linux/build/product-linux.sh build/linux out/sdk

# Linux ARM64
bash vm/tools/arm64/build/product-linux-aarch64.sh build/arm64 out/sdk

# macOS x86-64
bash vm/tools/x86/macos/build/product-macos.sh build/macos-x86_64 out/sdk

# Windows x86-64 (MSVC / MinGW) or macOS ARM64 (PORTABLE)
cmake -S vm -B build/release -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/release --parallel`,
  },
  {
    id: "pregen",
    label: "Offline Pregen",
    filename: "pregen.sh",
    code: `# Export SHA256-verified assembly bundle once
python3 vm/tools/common/export-pregen.py \\
  --source vm --build build/linux --output pregen/linux-x86_64

# Build downstream with zero Python dependency
cmake -S vm -B build/offline -G Ninja -DCMAKE_BUILD_TYPE=Release \\
  -DQJS_USE_PREGEN_ASM=ON -DQJS_PREGEN_DIR=pregen/linux-x86_64
cmake --build build/offline --parallel`,
  },
];

let DATA = null;
let selectedHeroMetric = "v8v7";
let selectedVersionIdx = 0;
let selectedPlatform = "linux-x86_64";
let selectedQs = "cmake";

function getTheme() {
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("qjs-turbo-theme", theme);
  updateThemeButton();
}

function updateThemeButton() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  const isLight = getTheme() === "light";
  btn.textContent = isLight ? "☾ Dark" : "☀ Light";
  btn.setAttribute("aria-pressed", String(isLight));
}

function renderHero() {
  document.getElementById("header-version").textContent = DATA.latestVersion;
  const metrics = DATA.heroMetrics;
  const active = metrics.find((m) => m.id === selectedHeroMetric) || metrics[0];

  const tabsEl = document.getElementById("hero-metric-tabs");
  tabsEl.innerHTML = metrics
    .map(
      (m) => `
      <button type="button" class="metric-tab ${m.id === active.id ? "active" : ""}" data-metric="${m.id}">
        ${m.tab}
      </button>
    `,
    )
    .join("");
  tabsEl.querySelectorAll(".metric-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedHeroMetric = btn.dataset.metric;
      renderHero();
    });
  });

  document.getElementById("hero-title").textContent = active.title;
  document.getElementById("hero-cohort").textContent = active.subtitle;
  document.getElementById("hero-badge").textContent = active.badge;
  document.getElementById("hero-footnote").textContent = active.footnote;

  const maxVal = Math.max(...active.engines.map((e) => e.value));
  const container = document.getElementById("hero-bars");
  container.innerHTML = active.engines
    .map((e) => {
      const pct = ((e.value / maxVal) * 100).toFixed(1);
      const cls = e.role === "turbo" ? "is-turbo" : e.role === "reference" ? "is-ref" : "";
      const formatted = e.value.toLocaleString("en-US", {
        maximumFractionDigits: e.value < 100 ? 2 : 1,
      });
      const tagHtml = e.tag ? `<span class="bar-tag">${e.tag}</span>` : "";
      return `
        <div class="bar-row ${cls}">
          <div class="bar-meta">
            <span class="bar-name">${e.label}</span>
            <span class="bar-score">${formatted}${active.unit}${tagHtml}</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill" style="width: ${pct}%"></div>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderHistory() {
  const items = DATA.versionHistory;
  const baseline = items[0];
  const current = items[selectedVersionIdx];

  const W = 640;
  const H = 240;
  const padL = 56;
  const padR = 26;
  const padT = 26;
  const padB = 36;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const yMin = 800;
  const yMax = 2600;

  const xAt = (i) => padL + (i / (items.length - 1)) * innerW;
  const yAt = (v) => padT + innerH - ((v - yMin) / (yMax - yMin)) * innerH;

  const refEngine = DATA.heroComparison.engines.find((e) => e.role === "reference");
  const refScore = Math.round(refEngine ? refEngine.score : 2178);
  const gridVals = [1000, 1500, 2000, refScore];
  const gridSvg = gridVals
    .map((v) => {
      const y = yAt(v).toFixed(1);
      const isV8 = v === refScore;
      return `
        <line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}"
          stroke="${isV8 ? "var(--chart-ref)" : "var(--chart-grid)"}"
          stroke-dasharray="${isV8 ? "5 5" : "none"}" />
        <text x="${padL - 8}" y="${Number(y) + 4}" text-anchor="end"
          fill="${isV8 ? "var(--cyan)" : "var(--text-dim)"}" font-size="11" font-family="JetBrains Mono, monospace">
          ${v}
        </text>
        ${
          isV8
            ? `<text x="${padL + 8}" y="${Number(y) - 6}" text-anchor="start" fill="var(--cyan)" font-size="10.5" font-family="JetBrains Mono, monospace">V8 --jitless (${refScore.toLocaleString("en-US")})</text>`
            : ""
        }
      `;
    })
    .join("");

  const stockPoints = items.map((d, i) => [xAt(i), yAt(d.baselineV8Score || baseline.v8Score)]);
  const stockPath = stockPoints
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");

  const points = items.map((d, i) => [xAt(i), yAt(d.v8Score)]);
  const linePath = points
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");
  const areaPath =
    `${linePath} L${points[points.length - 1][0].toFixed(1)},${(padT + innerH).toFixed(1)} ` +
    `L${points[0][0].toFixed(1)},${(padT + innerH).toFixed(1)} Z`;

  const nodesSvg = items
    .map((d, i) => {
      const [x, y] = points[i];
      const active = i === selectedVersionIdx;
      const fill = d.isBaseline
        ? "var(--chart-base-dot)"
        : active
          ? "var(--accent-bright)"
          : "var(--accent)";
      return `
        <g class="chart-node" data-idx="${i}" style="cursor:pointer">
          <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${active ? 11 : 7}"
            fill="${active ? "var(--accent-soft)" : "transparent"}" />
          <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${active ? 5.5 : 4.2}"
            fill="${fill}" stroke="var(--bg-card)" stroke-width="2" />
          <text x="${x.toFixed(1)}" y="${(y - 12).toFixed(1)}" text-anchor="middle"
            fill="${active ? "var(--accent-bright)" : "var(--chart-val)"}" font-size="${active ? 12 : 10.5}"
            font-weight="${active ? 700 : 500}" font-family="JetBrains Mono, monospace">
            ${Math.round(d.v8Score).toLocaleString("en-US")}
          </text>
          <text x="${x.toFixed(1)}" y="${H - 10}" text-anchor="${i === 0 ? "start" : i === items.length - 1 ? "end" : "middle"}"
            fill="${active ? "var(--text)" : "var(--text-muted)"}" font-size="11"
            font-weight="${active ? 700 : 400}" font-family="JetBrains Mono, monospace">
            ${d.shortLabel}
          </text>
        </g>
      `;
    })
    .join("");

  document.getElementById("history-chart").innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="V8-v7 score history">
      <defs>
        <linearGradient id="turboArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.24" />
          <stop offset="100%" stop-color="#f59e0b" stop-opacity="0.0" />
        </linearGradient>
      </defs>
      ${gridSvg}
      <path d="${areaPath}" fill="url(#turboArea)" />
      <path d="${stockPath}" fill="none" stroke="var(--chart-base-dot)" stroke-width="1.5" stroke-dasharray="4 4" />
      <text x="${W - padR}" y="${(stockPoints[stockPoints.length - 1][1] - 6).toFixed(1)}" text-anchor="end" fill="var(--chart-base-dot)" font-size="10" font-family="JetBrains Mono, monospace">Stock NG (0.15.1 → 0.17.0)</text>
      <path d="${linePath}" fill="none" stroke="var(--accent)" stroke-width="2.6" stroke-linejoin="round" />
      ${nodesSvg}
    </svg>
  `;

  document.querySelectorAll(".chart-node").forEach((node) => {
    node.addEventListener("click", () => {
      selectedVersionIdx = Number(node.dataset.idx);
      renderHistory();
    });
  });

  const pills = document.getElementById("version-pills");
  pills.innerHTML = items
    .map(
      (d, i) => `
      <button type="button" class="ver-pill ${i === selectedVersionIdx ? "active" : ""}" data-idx="${i}">
        ${d.shortLabel}
      </button>
    `,
    )
    .join("");
  pills.querySelectorAll(".ver-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedVersionIdx = Number(btn.dataset.idx);
      renderHistory();
    });
  });

  const baseVer = current.baselineVersion || "0.15.1";
  const baseV8Score = current.baselineV8Score || baseline.v8Score;
  const pctGain = (((current.v8Score - baseV8Score) / baseV8Score) * 100).toFixed(1);
  document.getElementById("history-gain-badge").textContent = current.isBaseline
    ? `Baseline (NG ${baseVer})`
    : `+${pctGain}% vs NG ${baseVer}`;

  const rssLine = current.peakRssKiB ? `${(current.peakRssKiB / 1024).toFixed(1)} MiB` : "—";

  document.getElementById("version-inspector").innerHTML = `
    <div class="panel-header" style="margin-bottom: 10px">
      <div>
        <h3 class="panel-title mono">${current.version}</h3>
        <p class="panel-subtitle">${current.date} · ${current.pool}</p>
      </div>
      <span class="badge ${current.isBaseline ? "" : "badge-green"}">${current.ratioVsNg.toFixed(2)}× NG</span>
    </div>
    <p style="margin: 0 0 12px; font-size: 13.5px; color: var(--text-muted)">${current.summary}</p>
    <div style="display:grid; grid-template-columns: repeat(3,1fr); gap:8px; margin-bottom: 10px;">
      <div class="subtest-tile">
        <div class="subtest-name">V8-v7</div>
        <div class="subtest-val mono" style="color:var(--accent-bright)">${current.v8Score.toLocaleString("en-US", { maximumFractionDigits: 1 })}</div>
      </div>
      <div class="subtest-tile">
        <div class="subtest-name">vs V8</div>
        <div class="subtest-val mono">${current.ratioVsV8.toFixed(1)}%</div>
      </div>
      <div class="subtest-tile">
        <div class="subtest-name">Peak RSS</div>
        <div class="subtest-val mono">${rssLine}</div>
      </div>
    </div>
    <ul class="inspector-list">
      ${current.highlights.map((h) => `<li>${h}</li>`).join("")}
    </ul>
  `;

  document.getElementById("subtest-title").textContent = `V8-v7 Subtests — ${current.version}`;
  document.getElementById("subtest-subtitle").textContent =
    `vs same-session Stock QuickJS-NG ${baseVer}`;
  document.getElementById("subtest-version-badge").textContent = current.version;

  const baseSubtests = current.baselineSubtests || baseline.subtests;
  const subGrid = document.getElementById("subtest-grid");
  subGrid.innerHTML = Object.entries(current.subtests)
    .map(([name, val]) => {
      const baseVal = baseSubtests[name];
      const ratio = (val / baseVal).toFixed(2);
      return `
        <div class="subtest-tile">
          <div class="subtest-name">${name}</div>
          <div class="subtest-val">${Math.round(val).toLocaleString("en-US")}</div>
          <div class="subtest-delta">${ratio}× vs NG (${Math.round(baseVal)})</div>
        </div>
      `;
    })
    .join("");
}

function renderPlatformTabs() {
  const wrap = document.getElementById("platform-tabs");
  wrap.innerHTML = Object.entries(DATA.platforms)
    .map(
      ([key, p]) => `
      <button type="button" class="tab-btn ${key === selectedPlatform ? "active" : ""}" data-platform="${key}">
        ${p.title}
      </button>
    `,
    )
    .join("");
  wrap.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedPlatform = btn.dataset.platform;
      renderPlatformTabs();
      renderPlatformPanel();
    });
  });
}

function renderV8SubtestChart(p) {
  if (!p.v8SubtestBars) {
    const rows = p.microHotspots
      .map(
        (r) => `
        <tr>
          <td>${r.name}</td>
          <td class="num"><strong>${r.turbo}</strong> <span style="color:var(--text-dim);font-size:11px">${r.unit}</span></td>
        </tr>
      `,
      )
      .join("");
    return `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>${p.rightTitle || "V8-v7 Subtests"}</th>
              <th class="num">Turbo</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  const maxScore = Math.max(...p.v8SubtestBars.map((b) => Math.max(b.turbo, b.stock)));
  const rowsHtml = p.v8SubtestBars
    .map((b) => {
      const turboPct = ((b.turbo / maxScore) * 100).toFixed(1);
      const stockPct = ((b.stock / maxScore) * 100).toFixed(1);
      return `
        <div class="speedup-row">
          <span class="speedup-name" title="${b.name}">${b.name}</span>
          <div class="speedup-dual">
            <div class="dual-track"><div class="dual-fill-turbo" style="width:${turboPct}%"></div></div>
            <div class="dual-track"><div class="dual-fill-base" style="width:${stockPct}%"></div></div>
          </div>
          <span class="speedup-ratio">${b.ratio.toFixed(2)}×</span>
        </div>
      `;
    })
    .join("");

  return `
    <div class="panel-card">
      <div class="panel-header" style="margin-bottom: 12px">
        <div>
          <h3 class="panel-title">V8-v7 Subtests (Turbo vs NG 0.17)</h3>
          <p class="panel-subtitle">Sorted by speedup · higher bar is faster</p>
        </div>
        <span class="badge badge-green">8/8 sweep</span>
      </div>
      <div class="speedup-bars">${rowsHtml}</div>
      <div class="legend-inline">
        <span><span class="legend-dot" style="background:var(--accent)"></span>QuickJS-Turbo</span>
        <span><span class="legend-dot" style="background:var(--bar-peer)"></span>Stock NG 0.17</span>
      </div>
    </div>
  `;
}

function renderJetStreamCard(js) {
  if (!js) return "";
  const s = js.summary;
  const hasV8 = Number.isFinite(s.v8BodyMs);

  const topCases = [...js.cases]
    .sort((a, b) => b.stock / b.turbo - a.stock / a.turbo)
    .slice(0, 6);

  const highlightTiles = topCases
    .map((c) => {
      const ratio = c.stock / c.turbo;
      return `
        <div class="js17-tile">
          <div class="js17-tile-name" title="${c.name}">${c.name}</div>
          <div class="js17-tile-row">
            <span class="js17-tile-ms">${c.turbo.toFixed(1)} ms</span>
            <span class="pill-speed">${ratio.toFixed(2)}× NG</span>
          </div>
        </div>
      `;
    })
    .join("");

  const rows = js.cases
    .map((c) => {
      const vsStock = c.stock / c.turbo;
      const vsBel = c.bellard / c.turbo;
      const rowHasV8 = hasV8 && Number.isFinite(c.v8);
      const vsV8 = rowHasV8 ? c.v8 / c.turbo : null;
      return `
        <tr>
          <td class="mono">${c.name}</td>
          <td class="num">${c.stock.toFixed(1)}</td>
          <td class="num">${c.bellard.toFixed(1)}</td>
          <td class="num"><strong>${c.turbo.toFixed(1)}</strong></td>
          ${hasV8 ? `<td class="num">${rowHasV8 ? c.v8.toFixed(1) : "—"}</td>` : ""}
          <td class="num">
            <span class="pill-speed ${vsStock < 1.01 ? "pill-neutral" : ""}">${vsStock.toFixed(2)}×</span>
          </td>
          <td class="num">
            <span class="pill-speed ${vsBel < 1.01 ? "pill-neutral" : ""}">${vsBel.toFixed(2)}×</span>
          </td>
          ${
            hasV8
              ? `<td class="num">${
                  rowHasV8
                    ? `<span class="pill-speed ${vsV8 < 1.0 ? "pill-neutral" : ""}">${vsV8.toFixed(2)}×</span>`
                    : `<span class="pill-speed pill-neutral">—</span>`
                }</td>`
              : ""
          }
        </tr>
      `;
    })
    .join("");

  return `
    <div class="panel-card js17-card">
      <div class="panel-header">
        <div>
          <h3 class="panel-title">${js.title}</h3>
          <p class="panel-subtitle">${js.subtitle}</p>
        </div>
        <div class="js17-summary">
          <span class="badge badge-green">${s.turboBodyMs.toFixed(1)} ms (${s.vsStock.toFixed(2)}× NG · ${s.vsBellard.toFixed(2)}× Bel)</span>
          <span class="badge">${s.rssNote}</span>
        </div>
      </div>
      <div class="js17-highlights">${highlightTiles}</div>
      <details class="compact-details">
        <summary>
          <span>Full 17-workload breakdown (geomean ${s.turboBodyMs.toFixed(1)} ms vs ${s.stockBodyMs.toFixed(1)} ms NG)</span>
          <span class="mono details-hint">All 17 cases ▾</span>
        </summary>
        <div class="table-wrap" style="border:none; border-radius:0; box-shadow:none">
          <table>
            <thead>
              <tr>
                <th>Workload (ms ↓)</th>
                <th class="num">NG 0.17</th>
                <th class="num">Bellard</th>
                <th class="num">Turbo</th>
                ${hasV8 ? `<th class="num">V8 --jitless</th>` : ""}
                <th class="num">vs NG</th>
                <th class="num">vs Bel</th>
                ${hasV8 ? `<th class="num">vs V8</th>` : ""}
              </tr>
            </thead>
            <tbody>
              ${rows}
              <tr class="js17-geomean-row">
                <td><strong>17-Case Geomean</strong></td>
                <td class="num"><strong>${s.stockBodyMs.toFixed(1)}</strong></td>
                <td class="num"><strong>${s.bellardBodyMs.toFixed(1)}</strong></td>
                <td class="num"><strong style="color:var(--accent-bright)">${s.turboBodyMs.toFixed(1)}</strong></td>
                ${hasV8 ? `<td class="num"><strong>${s.v8BodyMs.toFixed(1)}</strong></td>` : ""}
                <td class="num"><span class="pill-speed">${s.vsStock.toFixed(2)}×</span></td>
                <td class="num"><span class="pill-speed">${s.vsBellard.toFixed(2)}×</span></td>
                ${hasV8 ? `<td class="num"><span class="pill-speed pill-neutral">${s.vsV8Pct.toFixed(1)}%</span></td>` : ""}
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </div>
  `;
}

function renderPlatformPanel() {
  const p = DATA.platforms[selectedPlatform];

  const statsHtml = p.headlineStats
    .map(
      (s) => `
      <div class="kpi-card">
        <div class="kpi-value accent">${s.value}</div>
        <div class="kpi-title">${s.label}</div>
        <div class="kpi-label">${s.sub}</div>
      </div>
    `,
    )
    .join("");

  const targetedRows = p.targetedSpeedups
    .map(
      (r) => `
      <tr>
        <td>${r.name}</td>
        <td class="num">${r.before}</td>
        <td class="num"><strong>${r.after}</strong></td>
        <td class="num"><span class="pill-speed">${r.speedup.toFixed(2)}×</span></td>
      </tr>
    `,
    )
    .join("");

  const leftTitle = p.leftTitle || "Suite Comparisons";

  document.getElementById("platform-panel").innerHTML = `
    <div class="cohort-bar">
      <div>
        <strong class="mono">${p.backend}</strong>
        <span style="color:var(--text-muted); margin-left:8px">${p.toolchain}</span>
      </div>
      <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap">
        <span class="badge">${p.baselineLabel}</span>
        <a class="mono" style="font-size:12px; color:var(--cyan)"
           href="https://github.com/rowanellis-113/quickjs-turbo/blob/${DATA.latestVersion}/${p.sourceDoc}"
           target="_blank" rel="noopener">${p.sourceDoc.split("/").pop()} ↗</a>
      </div>
    </div>

    <div class="platform-stats">${statsHtml}</div>

    <div class="two-col">
      ${renderV8SubtestChart(p)}

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>${leftTitle}</th>
              <th class="num">Ref</th>
              <th class="num">Turbo</th>
              <th class="num">Gain</th>
            </tr>
          </thead>
          <tbody>${targetedRows}</tbody>
        </table>
      </div>
    </div>

    ${renderJetStreamCard(p.jetstream17)}

    ${
      p.note
        ? `<details class="compact-details" style="margin-top: 14px">
             <summary>
               <span>Measurement methodology &amp; binary SHA-256 receipts</span>
               <span class="mono details-hint">Details ▾</span>
             </summary>
             <div class="details-body">${p.note}</div>
           </details>`
        : ""
    }
  `;
}

function renderQuickStart() {
  const tabs = document.getElementById("qs-tabs");
  tabs.innerHTML = QUICKSTART_SNIPPETS.map(
    (s) => `
      <button type="button" class="tab-btn ${s.id === selectedQs ? "active" : ""}" data-qs="${s.id}">
        ${s.label}
      </button>
    `,
  ).join("");
  tabs.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedQs = btn.dataset.qs;
      renderQuickStart();
    });
  });

  const active = QUICKSTART_SNIPPETS.find((s) => s.id === selectedQs) || QUICKSTART_SNIPPETS[0];
  document.getElementById("qs-filename").textContent = active.filename;
  document.getElementById("qs-code").textContent = active.code;
}

async function init() {
  updateThemeButton();
  document.getElementById("theme-toggle").addEventListener("click", () => {
    setTheme(getTheme() === "light" ? "dark" : "light");
  });

  const res = await fetch("./data/benchmarks.json");
  if (!res.ok) {
    throw new Error("Failed to load benchmarks.json: " + res.status);
  }
  DATA = await res.json();
  selectedVersionIdx = DATA.versionHistory.length - 1;

  document.getElementById("qs-copy").addEventListener("click", async () => {
    const active = QUICKSTART_SNIPPETS.find((s) => s.id === selectedQs);
    if (!active) return;
    try {
      await navigator.clipboard.writeText(active.code);
      const btn = document.getElementById("qs-copy");
      btn.textContent = "Copied!";
      setTimeout(() => {
        btn.textContent = "Copy";
      }, 1500);
    } catch {
      // Clipboard API unavailable on non-HTTPS local preview
    }
  });

  renderHero();
  renderHistory();
  renderPlatformTabs();
  renderPlatformPanel();
  renderQuickStart();
}

init().catch((err) => {
  console.error(err);
});
