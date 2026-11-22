const I18N = {
  en: {
    "nav.why": "Why Turbo",
    "nav.history": "Version History",
    "nav.platforms": "Platform Benchmarks",
    "nav.quickstart": "Quick Start",
    "hero.eyebrow": "Zero JIT · W^X Clean · 100% quickjs.h Drop-In",
    "hero.title":
      'Near-V8 <span class="mono">--jitless</span> speed in a <span class="accent">QuickJS-sized</span> binary.',
    "hero.lead":
      "QuickJS-Turbo supercharges QuickJS-NG with native register-frame assembly VMs, adaptive inline caches, and Hybrid RC + Partial Cycle GC — delivering ~2× throughput without runtime codegen or RWX memory.",
    "hero.ctaStart": "Quick Start & Embed",
    "hero.ctaBench": "Explore Benchmarks",
    "hero.ctaReleases": "Prebuilt SDKs",
    "hero.chartTitle": "V8-v7 Throughput (Single-Core, Zero JIT)",
    "hero.higherBetter": "Higher is better",
    "hero.chartNote": "Same-host Linux x86-64 cohort · QuickJS-NG 0.15.1 pinned upstream",
    "kpi.v8": "V8-v7 vs QuickJS-NG 0.15.1",
    "kpi.jitless": "of V8 --jitless (Node 24)",
    "kpi.wx": "Strict W^X · DWARF CFI & Win64 SEH",
    "kpi.test262": "Test262 cases · 0 regressions · 31 fixes",
    "why.kicker": "Architecture & Advantages",
    "why.title": "Why QuickJS-Turbo?",
    "why.subtitle":
      "Built for production hosts that want QuickJS's tiny footprint, instant cold start, and strict security invariants — without leaving 2×–6× execution speed on the table.",
    "why.f1Title": "Fast Where JITs Are Banned",
    "why.f1Body":
      "Ahead-of-time assembly VMs require zero executable heap pages. Ships with complete DWARF CFI / Win64 SEH unwind tables for iOS, consoles, locked-down containers, and edge workers.",
    "why.f1Metric": "PIE · NX stack · 0 RWX pages · native stack traces",
    "why.f2Title": "Native Dispatch & Adaptive ICs",
    "why.f2Body":
      "Replaces the indirect C switch loop with register-pinned assembly dispatch, monomorphic/polymorphic Property ICs, and co-allocated inline object properties.",
    "why.f2Metric": "RegExp 7.16× · JSON.stringify 6.02× · array_write 5.74×",
    "why.f3Title": "Objects, Collections & Async",
    "why.f3Body":
      "Shared literal capacity reservation, unified Map/Set string hashing with short-rope flattening, and capability-free async / Promise.resolve fast paths across all targets.",
    "why.f3Metric": "lit5 3.49× · mapFlat 3.52× · mapRope 2.52× · async 1.47×",
    "why.f4Title": "Deterministic RC, 86% Fewer Scans",
    "why.f4Body":
      "Keeps QuickJS's immediate reference counting while adding generational boundary-node partial cycle collection and iterative O(1)-C-stack object reclamation.",
    "why.f4Metric": "Cycle scans -85.8% · cyclic churn 1.50× · RSS -4.09%",
    "why.f5Title": "Fine-Grained Memory Control",
    "why.f5Body":
      "Via quickjs-turbo.h: turn off own_bytecode tails while keeping native Property ICs, defer IC allocation with tagged warmup (+0 B struct growth), and purge idle worker slabs on demand.",
    "why.f5Metric": "QJS_SetTurboDefaults · property_ic_warmup · JS_PurgePropertyIC",
    "why.f6Title": "100% quickjs.h & CMake Ready",
    "why.f6Body":
      "Upstream QuickJS-NG 0.15.1 remains byte-for-byte pristine at repo root. quickjs-turbo::qjs isolates host LTO, auto-falls back under Sanitizers, and supports Python-free pregen builds.",
    "why.f6Metric": "Unmodified quickjs.h · add_subdirectory() · QJS_USE_PREGEN_ASM",
    "mat.platform": "Platform",
    "mat.backend": "Backend",
    "mat.toolchains": "Toolchains",
    "mat.notes": "Capabilities & Notes",
    "mat.linuxX86": "Native ELF ASM VM, inline object properties, PIE + DWARF CFI",
    "mat.macosX86": "Native Mach-O ASM VM, PIE + DWARF CFI, AUTO-selected on Darwin x86_64",
    "mat.winX86": "Source-level WIN_X86_64 (zero GNU binutils) + full Win64 SEH unwind",
    "mat.linuxArm": "Native ELF ASM VM, 64B-aligned VM entry, AUTO-selected on Linux AArch64",
    "mat.portable": "Automatic AUTO fallback · shared runtime fast paths · ASan/UBSan/TSan/MSan/Fuzz",
    "hist.kicker": "Historical Benchmark Archive",
    "hist.title": "Performance Evolution Across Releases",
    "hist.subtitle":
      "Every release snapshot is retained on the same Linux x86-64 reference cohort (CPU2 serial, normal ASLR, stock QuickJS-NG 0.15.1 = 993.7). Select any release to inspect its architectural milestones and all 8 V8-v7 subtests.",
    "hist.chartTitle": "V8-v7 Whole Score Trajectory (Linux x86-64)",
    "hist.chartSub": "Click any point or version pill below to inspect per-subtest breakdown",
    "hist.subtestSub":
      "Each subtest ratio is computed against Stock QuickJS-NG 0.15.1 on the same Linux x86-64 host",
    "plat.kicker": "Verified Real-Hardware Cohorts",
    "plat.title": "Cross-Platform Benchmarks",
    "plat.subtitle":
      "Each platform tab keeps its own strict hardware cohort and comparison baseline — never mixing baselines across operating systems or compilers.",
    "qs.kicker": "Get Started in 30 Seconds",
    "qs.title": "Quick Start & Embedding",
    "qs.subtitle":
      "Drop QuickJS-Turbo into an existing CMake project with zero quickjs.h changes, or configure high-density runtime controls via quickjs-turbo.h.",
    "qs.copy": "Copy",
    "qs.copied": "Copied!",
    "capsid.title": "Need a full JS sandbox for untrusted or AI-generated code?",
    "capsid.body":
      "QuickJS-Turbo is a raw C engine (quickjs.h). If you want OS process isolation, per-request CPU/memory quotas, egress policies, and Web-standard ESM / fetch() out of the box, check out Capsid — built on QuickJS-Turbo.",
    "capsid.repo": "Capsid on GitHub ↗",
    "capsid.docs": "Docs ↗",
    "footer.credit":
      "Built on QuickJS-NG 0.15.1 by Fabrice Bellard, Charlie Gordon & QuickJS-NG maintainers.",
  },
  zh: {
    "nav.why": "核心优势",
    "nav.history": "历史版本演进",
    "nav.platforms": "跨平台实测",
    "nav.quickstart": "快速上手",
    "hero.eyebrow": "零 JIT · 严守 W^X · 100% 兼容 quickjs.h",
    "hero.title":
      '在 <span class="accent">QuickJS 体积</span> 内跑出逼近 V8 <span class="mono">--jitless</span> 的速度。',
    "hero.lead":
      "QuickJS-Turbo 基于 QuickJS-NG 打造，通过原生寄存器帧汇编 VM、自适应内联缓存与混合引用计数分代 GC，在零运行时代码生成与零 RWX 内存的前提下带来约 2× 综合吞吐提升。",
    "hero.ctaStart": "快速上手与嵌入",
    "hero.ctaBench": "查看历史性能",
    "hero.ctaReleases": "下载预编译 SDK",
    "hero.chartTitle": "V8-v7 吞吐对比（单核、关闭 JIT）",
    "hero.higherBetter": "分数越高越快",
    "hero.chartNote": "同机 Linux x86-64 统一基线 · 上游锁定 QuickJS-NG 0.15.1",
    "kpi.v8": "V8-v7 对比 QuickJS-NG 0.15.1",
    "kpi.jitless": "达到 V8 --jitless (Node 24) 水平",
    "kpi.wx": "严格 W^X · 完整 DWARF CFI / Win64 SEH",
    "kpi.test262": "Test262 用例全量校验 · 0 回归 · 修复 31 项上游缺陷",
    "why.kicker": "架构与核心优势",
    "why.title": "为什么选择 QuickJS-Turbo？",
    "why.subtitle":
      "为既要 QuickJS 极小体积、亚毫秒冷启动和严格安全边界，又不想白白损失 2×–6× 执行性能的生产宿主而生。",
    "why.f1Title": "在禁用 JIT 的环境依然极速",
    "why.f1Body":
      "全部汇编 VM 均为 AOT 静态编译，零可执行堆页；自带完整 DWARF CFI / Win64 SEH 栈回溯信息，直接适用于 iOS、游戏主机、高安全容器与边缘计算 Worker。",
    "why.f1Metric": "PIE · NX 栈 · 0 RWX 页 · 完整原生栈回溯",
    "why.f2Title": "原生寄存器调度与自适应 IC",
    "why.f2Body":
      "用寄存器驻留的汇编分发替换 C 语言大 switch 循环，结合单态/多态 Property IC 与内联对象属性共分配，大幅削减属性与解释器开销。",
    "why.f2Metric": "RegExp 7.16× · JSON.stringify 6.02× · array_write 5.74×",
    "why.f3Title": "对象、集合与异步热点加速",
    "why.f3Body":
      "全平台共享对象字面量容量预留、Map/Set 字符串统一哈希与短绳扁平化，以及无 Capability 开销的 async / Promise.resolve 快速路径。",
    "why.f3Metric": "lit5 3.49× · mapFlat 3.52× · mapRope 2.52× · async 1.47×",
    "why.f4Title": "确定性 RC，循环扫描削减 86%",
    "why.f4Body":
      "保留 QuickJS 确定性即时引用计数优势，新增分代边界节点局部循环收集器与 O(1) C 栈迭代快速释放，兼顾低延迟与内存可控。",
    "why.f4Metric": "全堆循环扫描 -85.8% · 循环垃圾吞吐 1.50× · 峰值 RSS -4.09%",
    "why.f5Title": "面向高密度多租户的内存控制",
    "why.f5Body":
      "通过 quickjs-turbo.h 按需关闭 own_bytecode 尾副本并保持原生 Property IC 生效，支持低位标签懒预热（结构体 +0 字节）与空闲 Worker 的 JS_PurgePropertyIC 内存回收。",
    "why.f5Metric": "QJS_SetTurboDefaults · property_ic_warmup · JS_PurgePropertyIC",
    "why.f6Title": "100% Drop-In 与一等公民 CMake",
    "why.f6Body":
      "上游 QuickJS-NG 0.15.1 源码保持逐字节零改动；quickjs-turbo::qjs 自动隔离宿主 LTO、Sanitizer 下自动回退 PORTABLE，并支持无 Python 预生成离线构建。",
    "why.f6Metric": "零改动 quickjs.h · add_subdirectory() · QJS_USE_PREGEN_ASM",
    "mat.platform": "平台",
    "mat.backend": "后端",
    "mat.toolchains": "工具链",
    "mat.notes": "特性与说明",
    "mat.linuxX86": "原生 ELF 汇编 VM、内联对象属性、PIE + DWARF CFI",
    "mat.macosX86": "原生 Mach-O 汇编 VM、PIE + DWARF CFI，Darwin x86_64 下 AUTO 默认启用",
    "mat.winX86": "源码级 WIN_X86_64（零 GNU binutils 依赖）+ 完整 Win64 SEH 展开",
    "mat.linuxArm": "原生 ELF 汇编 VM、64B 对齐入口，Linux AArch64 下 AUTO 默认启用",
    "mat.portable": "AUTO 自动回退 · 共享 C 热点优化 · 完整支持 ASan/UBSan/TSan/MSan/Fuzz",
    "hist.kicker": "历史版本性能档案",
    "hist.title": "各版本性能演进轨迹",
    "hist.subtitle":
      "在统一的 Linux x86-64 同机环境（CPU2 串行、正常 ASLR、原版 QuickJS-NG 0.15.1 = 993.7）保留历次版本快照。点击任意版本节点即可查看改动摘要与 V8-v7 全 8 项明细。",
    "hist.chartTitle": "V8-v7 总分演进曲线（Linux x86-64）",
    "hist.chartSub": "点击图表节点或下方版本标签切换查看对应版本明细",
    "hist.subtestSub": "下方所有子项加速比均统一对比同机原版 QuickJS-NG 0.15.1",
    "plat.kicker": "多平台真机实测数据",
    "plat.title": "跨平台性能基准",
    "plat.subtitle":
      "每个平台标签页独立锁定各自的硬件环境与对比基线，绝不跨系统或跨编译器混用加速比口径。",
    "qs.kicker": "30 秒快速集成",
    "qs.title": "快速开始与嵌入指南",
    "qs.subtitle":
      "无需修改任何 quickjs.h 调用即可通过 CMake 接入，也可选用 quickjs-turbo.h 进行精细化内存与运行时控制。",
    "qs.copy": "复制",
    "qs.copied": "已复制",
    "capsid.title": "需要直接运行不受信任或 AI 生成 JS 的生产级沙箱？",
    "capsid.body":
      "QuickJS-Turbo 是纯 C 引擎（quickjs.h）。如果你需要开箱即用的 OS 进程隔离、单请求 CPU/内存配额、网络出站策略与 Web 标准 ESM / fetch()，可以顺带看看基于它构建的 Capsid。",
    "capsid.repo": "访问 Capsid GitHub ↗",
    "capsid.docs": "阅读文档 ↗",
    "footer.credit":
      "基于 QuickJS-NG 0.15.1 构建，致谢 Fabrice Bellard、Charlie Gordon 与 QuickJS-NG 维护者。",
  },
};

const QUICKSTART_SNIPPETS = [
  {
    id: "cmake",
    label: "CMake Embed",
    labelZh: "CMake 嵌入",
    filename: "CMakeLists.txt",
    code: `# Option 1: vendor directly via add_subdirectory()
add_subdirectory(vendor/quickjs-turbo/vm)
target_link_libraries(my_app PRIVATE quickjs-turbo::qjs)

# Option 2: link an installed prebuilt SDK
find_package(quickjs-turbo CONFIG REQUIRED)
target_link_libraries(my_app PRIVATE quickjs-turbo::qjs)

# Host LTO stays enabled — quickjs-turbo::qjs isolates native ASM units locally.
# Under ASan/UBSan/TSan/MSan/Fuzz, AUTO automatically falls back to PORTABLE.`,
  },
  {
    id: "capi",
    label: "C API (quickjs-turbo.h)",
    labelZh: "C API 高密度控制",
    filename: "embed.c",
    code: `#include "quickjs.h"
#include "quickjs-turbo.h"

void init_worker_pool(void) {
    QJSTurboOptions opts;
    QJS_TurboOptionsInit(&opts);
    opts.own_bytecode_tail = QJS_TURBO_OFF; /* PIC-only: zero tail copy overhead */
    opts.property_ic_warmup = 16;           /* Lazy IC allocation after 16 accesses */
    QJS_SetTurboDefaults(&opts);

    JSRuntime *rt = JS_NewRuntime();
    QJSTurboInfo info;
    QJS_GetTurboInfo(rt, &info);            /* Structured backend & IC telemetry */

    /* ... when worker becomes idle, reclaim all IC slabs immediately: */
    JS_PurgePropertyIC(rt);
}`,
  },
  {
    id: "source",
    label: "Build from Source",
    labelZh: "源码一键构建",
    filename: "build.sh",
    code: `# Linux x86-64 (native ELF ASM VM)
bash vm/tools/x86/linux/build/product-linux.sh build/linux out/sdk

# macOS x86-64 (native Mach-O ASM VM)
bash vm/tools/x86/macos/build/product-macos.sh build/macos-x86_64 out/sdk

# Linux ARM64 (glibc / musl native ELF ASM VM)
bash vm/tools/arm64/build/product-linux-aarch64.sh build/arm64 out/sdk

# Windows x86-64 (MSVC / clang-cl native WIN_X86_64, zero GNU binutils)
cmake -S vm -B build/win-x86_64 -G Ninja -DCMAKE_BUILD_TYPE=Release \\
  -DQJS_FRAME_BACKEND=AUTO -DQJS_PROPERTY_IC=ON
cmake --build build/win-x86_64 --parallel`,
  },
  {
    id: "pregen",
    label: "Offline Pregen (No Python)",
    labelZh: "无 Python 离线构建",
    filename: "pregen.sh",
    code: `# 1. Export a SHA256-verified pre-generated assembly bundle once
python3 vm/tools/common/export-pregen.py \\
  --source vm \\
  --build build/linux \\
  --output pregen/linux-x86_64

# 2. Build downstream in pure CMake with zero Python dependency
cmake -S vm -B build/offline -G Ninja -DCMAKE_BUILD_TYPE=Release \\
  -DQJS_USE_PREGEN_ASM=ON \\
  -DQJS_PREGEN_DIR=pregen/linux-x86_64
cmake --build build/offline --parallel`,
  },
];

let DATA = null;
let lang = localStorage.getItem("qjs-turbo-lang") || "en";
let selectedVersionIdx = 0;
let selectedPlatform = "linux-x86_64";
let selectedQs = "cmake";

function t(key) {
  return (I18N[lang] && I18N[lang][key]) || I18N.en[key] || key;
}

function applyTranslations() {
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => {
    el.innerHTML = t(el.dataset.i18nHtml);
  });
  const toggle = document.getElementById("lang-toggle");
  if (toggle) toggle.textContent = lang === "zh" ? "EN" : "中文";
  if (DATA) {
    renderHero();
    renderHistory();
    renderPlatformTabs();
    renderPlatformPanel();
    renderQuickStart();
  }
}

function renderHero() {
  const hero = DATA.heroComparison;
  document.getElementById("header-version").textContent = DATA.latestVersion;
  document.getElementById("hero-cohort").textContent = lang === "zh" ? hero.cohortZh : hero.cohort;
  const maxScore = Math.max(...hero.engines.map((e) => e.score));
  const container = document.getElementById("hero-bars");
  container.innerHTML = hero.engines
    .map((e) => {
      const pct = ((e.score / maxScore) * 100).toFixed(1);
      const cls =
        e.role === "turbo" ? "is-turbo" : e.role === "reference" ? "is-ref" : "";
      const ratio = (e.score / 993.7).toFixed(2);
      const suffix =
        e.role === "turbo"
          ? ` (${ratio}×)`
          : e.role === "baseline"
            ? " (1.00×)"
            : "";
      return `
        <div class="bar-row ${cls}">
          <div class="bar-meta">
            <span class="bar-name">${e.label}</span>
            <span class="bar-score">${e.score.toLocaleString("en-US", { maximumFractionDigits: 1 })}${suffix}</span>
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

  // SVG line chart
  const W = 640;
  const H = 250;
  const padL = 52;
  const padR = 26;
  const padT = 26;
  const padB = 38;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const yMin = 800;
  const yMax = 2500;

  const xAt = (i) => padL + (i / (items.length - 1)) * innerW;
  const yAt = (v) => padT + innerH - ((v - yMin) / (yMax - yMin)) * innerH;

  const gridVals = [1000, 1500, 2000, 2375];
  const gridSvg = gridVals
    .map((v) => {
      const y = yAt(v).toFixed(1);
      const isV8 = v === 2375;
      return `
        <line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}"
          stroke="${isV8 ? "rgba(56,189,248,0.45)" : "rgba(255,255,255,0.08)"}"
          stroke-dasharray="${isV8 ? "5 5" : "none"}" />
        <text x="${padL - 8}" y="${Number(y) + 4}" text-anchor="end"
          fill="${isV8 ? "#38bdf8" : "#667085"}" font-size="11" font-family="JetBrains Mono, monospace">
          ${v}
        </text>
        ${
          isV8
            ? `<text x="${W - padR}" y="${Number(y) - 6}" text-anchor="end" fill="#38bdf8" font-size="10.5" font-family="JetBrains Mono, monospace">V8 --jitless (2,375)</text>`
            : ""
        }
      `;
    })
    .join("");

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
      const fill = d.isBaseline ? "#94a3b8" : active ? "#fbbf24" : "#f59e0b";
      return `
        <g class="chart-node" data-idx="${i}" style="cursor:pointer">
          <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${active ? 11 : 7}"
            fill="${active ? "rgba(251,191,36,0.22)" : "transparent"}" />
          <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${active ? 5.5 : 4.2}"
            fill="${fill}" stroke="#080a0f" stroke-width="2" />
          <text x="${x.toFixed(1)}" y="${(y - 12).toFixed(1)}" text-anchor="middle"
            fill="${active ? "#fbbf24" : "#cbd5e1"}" font-size="${active ? 12 : 10.5}"
            font-weight="${active ? 700 : 500}" font-family="JetBrains Mono, monospace">
            ${Math.round(d.v8Score).toLocaleString("en-US")}
          </text>
          <text x="${x.toFixed(1)}" y="${H - 12}" text-anchor="middle"
            fill="${active ? "#f3f6fc" : "#98a2b3"}" font-size="11"
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
          <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.28" />
          <stop offset="100%" stop-color="#f59e0b" stop-opacity="0.0" />
        </linearGradient>
      </defs>
      ${gridSvg}
      <path d="${areaPath}" fill="url(#turboArea)" />
      <path d="${linePath}" fill="none" stroke="#fbbf24" stroke-width="2.6" stroke-linejoin="round" />
      ${nodesSvg}
    </svg>
  `;

  document.querySelectorAll(".chart-node").forEach((node) => {
    node.addEventListener("click", () => {
      selectedVersionIdx = Number(node.dataset.idx);
      renderHistory();
    });
  });

  // Version pills
  const pills = document.getElementById("version-pills");
  pills.innerHTML = items
    .map(
      (d, i) => `
      <button type="button" class="ver-pill ${i === selectedVersionIdx ? "active" : ""}" data-idx="${i}">
        ${d.version}
      </button>
    `
    )
    .join("");
  pills.querySelectorAll(".ver-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedVersionIdx = Number(btn.dataset.idx);
      renderHistory();
    });
  });

  // Inspector
  const pctGain = (((current.v8Score - baseline.v8Score) / baseline.v8Score) * 100).toFixed(1);
  document.getElementById("history-gain-badge").textContent =
    current.isBaseline ? "Baseline (1.00×)" : `+${pctGain}% vs Stock NG`;

  const rssLine = current.peakRssKiB
    ? `${(current.peakRssKiB / 1024).toFixed(1)} MiB`
    : "—";
  const highlights = lang === "zh" ? current.highlightsZh : current.highlightsEn;
  const summary = lang === "zh" ? current.summaryZh : current.summaryEn;

  document.getElementById("version-inspector").innerHTML = `
    <div class="panel-header" style="margin-bottom: 10px">
      <div>
        <h3 class="panel-title mono">${current.version}</h3>
        <p class="panel-subtitle">${current.date} · ${current.pool}</p>
      </div>
      <span class="badge ${current.isBaseline ? "" : "badge-green"}">${current.ratioVsNg.toFixed(2)}× NG</span>
    </div>
    <p style="margin: 0 0 12px; font-size: 13.5px; color: var(--text-muted)">${summary}</p>
    <div style="display:grid; grid-template-columns: repeat(3,1fr); gap:8px; margin-bottom: 12px;">
      <div class="subtest-tile">
        <div class="subtest-name">V8-v7</div>
        <div class="subtest-val mono" style="color:var(--accent-bright)">${current.v8Score.toLocaleString("en-US", { maximumFractionDigits: 1 })}</div>
      </div>
      <div class="subtest-tile">
        <div class="subtest-name">vs V8 --jitless</div>
        <div class="subtest-val mono">${current.ratioVsV8.toFixed(1)}%</div>
      </div>
      <div class="subtest-tile">
        <div class="subtest-name">Peak RSS</div>
        <div class="subtest-val mono">${rssLine}</div>
      </div>
    </div>
    <ul class="inspector-list">
      ${highlights.map((h) => `<li>${h}</li>`).join("")}
    </ul>
  `;

  // Subtests grid
  document.getElementById("subtest-title").textContent =
    lang === "zh"
      ? `V8-v7 八项子测明细 — ${current.version}`
      : `V8-v7 Subtest Breakdown — ${current.version}`;
  document.getElementById("subtest-version-badge").textContent = current.version;

  const subGrid = document.getElementById("subtest-grid");
  subGrid.innerHTML = Object.entries(current.subtests)
    .map(([name, val]) => {
      const baseVal = baseline.subtests[name];
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
        ${p.title} <span class="mono" style="opacity:0.7; font-size:11px; margin-left:4px">${p.backend}</span>
      </button>
    `
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

function renderPlatformPanel() {
  const p = DATA.platforms[selectedPlatform];
  const baselineText = lang === "zh" ? p.baselineLabelZh : p.baselineLabel;
  const noteText = lang === "zh" ? p.noteZh : p.noteEn;

  const statsHtml = p.headlineStats
    .map(
      (s) => `
      <div class="kpi-card">
        <div class="kpi-value accent">${s.value}</div>
        <div class="kpi-label"><strong>${lang === "zh" ? s.labelZh : s.labelEn}</strong></div>
        <div class="kpi-label" style="font-size:11.5px">${s.sub}</div>
      </div>
    `
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
    `
    )
    .join("");

  const microRows = p.microHotspots
    .map(
      (r) => `
      <tr>
        <td>${r.name}</td>
        <td class="num">${r.stock}</td>
        <td class="num"><strong>${r.turbo}</strong> <span style="color:var(--text-dim);font-size:11px">${r.unit}</span></td>
        <td class="num">
          ${
            r.speedup !== null
              ? `<span class="pill-speed ${r.speedup < 1.01 ? "pill-neutral" : ""}">${r.speedup.toFixed(2)}×</span>`
              : `<span class="pill-speed pill-neutral">live</span>`
          }
        </td>
      </tr>
    `
    )
    .join("");

  const leftTitle =
    lang === "zh" ? "核心工作负载与配对提速" : "Targeted & Paired Speedups";
  const rightTitle =
    selectedPlatform === "linux-x86_64"
      ? lang === "zh"
        ? "热点微基准 & JetStream 精选（对比 Stock NG）"
        : "Hotspot Micro & JetStream Wins (vs Stock NG)"
      : lang === "zh"
        ? "V8-v7 子项明细"
        : "V8-v7 Per-Subtest Breakdown";

  document.getElementById("platform-panel").innerHTML = `
    <div class="cohort-bar">
      <div>
        <strong class="mono">${p.backend}</strong>
        <span style="color:var(--text-muted); margin-left:10px">${p.toolchain}</span>
      </div>
      <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap">
        <span class="badge">${baselineText}</span>
        <a class="mono" style="font-size:12px; color:var(--cyan)"
           href="https://github.com/rowanellis-113/quickjs-turbo/blob/main/${p.sourceDoc}"
           target="_blank" rel="noopener">${p.sourceDoc.split("/").pop()} ↗</a>
      </div>
    </div>

    <div class="platform-stats">${statsHtml}</div>

    <div class="two-col">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>${leftTitle}</th>
              <th class="num">${lang === "zh" ? "基线" : "Baseline"}</th>
              <th class="num">Turbo</th>
              <th class="num">${lang === "zh" ? "加速比" : "Speedup"}</th>
            </tr>
          </thead>
          <tbody>${targetedRows}</tbody>
        </table>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>${rightTitle}</th>
              <th class="num">${lang === "zh" ? "对比项" : "Ref"}</th>
              <th class="num">Turbo</th>
              <th class="num">${lang === "zh" ? "比率" : "Ratio"}</th>
            </tr>
          </thead>
          <tbody>${microRows}</tbody>
        </table>
      </div>
    </div>

    ${noteText ? `<div class="cohort-note">${noteText}</div>` : ""}
  `;
}

function renderQuickStart() {
  const tabs = document.getElementById("qs-tabs");
  tabs.innerHTML = QUICKSTART_SNIPPETS.map(
    (s) => `
      <button type="button" class="tab-btn ${s.id === selectedQs ? "active" : ""}" data-qs="${s.id}">
        ${lang === "zh" ? s.labelZh : s.label}
      </button>
    `
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
  const res = await fetch("./data/benchmarks.json");
  if (!res.ok) {
    throw new Error("Failed to load benchmarks.json: " + res.status);
  }
  DATA = await res.json();
  selectedVersionIdx = DATA.versionHistory.length - 1;

  document.getElementById("lang-toggle").addEventListener("click", () => {
    lang = lang === "en" ? "zh" : "en";
    localStorage.setItem("qjs-turbo-lang", lang);
    applyTranslations();
  });

  document.getElementById("qs-copy").addEventListener("click", async () => {
    const active = QUICKSTART_SNIPPETS.find((s) => s.id === selectedQs);
    if (!active) return;
    try {
      await navigator.clipboard.writeText(active.code);
      const btn = document.getElementById("qs-copy");
      btn.textContent = t("qs.copied");
      setTimeout(() => {
        btn.textContent = t("qs.copy");
      }, 1500);
    } catch {
      // Clipboard API unavailable on non-HTTPS local preview
    }
  });

  applyTranslations();
}

init().catch((err) => {
  console.error(err);
});
