// 안전장비 위반 기록 페이지.
// Supabase safety_logs를 anon key로 읽고, INSERT를 실시간 구독한다.
// config.js에 URL·anon key가 없으면 가짜 데이터로 도는 데모 모드로 연다.
(function () {
  "use strict";

  const cfg = Object.assign(
    { supabaseUrl: "", supabaseAnonKey: "", table: "safety_logs", pageSize: 50 },
    window.SAFETY_CONFIG || {}
  );
  const COLUMNS = "id,created_at,device_id,has_helmet,has_vest,confidence,image_url";

  const $ = (id) => document.getElementById(id);
  const state = {
    range: "today", // today | 7d | all
    kind: "all", // all | helmet | vest
    device: "",
    rows: [],
    total: 0,
    devices: new Set(),
  };

  // ---------- 공통 유틸 ----------
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }
  function startOfToday() {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }
  function rangeStart(range) {
    if (range === "today") return startOfToday();
    if (range === "7d") {
      const d = startOfToday();
      d.setDate(d.getDate() - 6);
      return d;
    }
    return null;
  }
  const timeFmt = new Intl.DateTimeFormat("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  function fmtTime(iso) {
    return timeFmt.format(new Date(iso));
  }
  function ago(iso) {
    const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    if (s < 60) return `${s}초 전`;
    const m = Math.round(s / 60);
    if (m < 60) return `${m}분 전`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h}시간 전`;
    return `${Math.round(h / 24)}일 전`;
  }
  function matchesFilter(row) {
    const start = rangeStart(state.range);
    if (start && new Date(row.created_at) < start) return false;
    if (state.kind === "helmet" && row.has_helmet) return false;
    if (state.kind === "vest" && row.has_vest) return false;
    if (state.device && row.device_id !== state.device) return false;
    return true;
  }

  // ---------- 데이터 출처: Supabase ----------
  function supabaseSource() {
    const client = window.supabase.createClient(cfg.supabaseUrl, cfg.supabaseAnonKey);
    const table = () => client.from(cfg.table);

    function applyFilter(q, f) {
      const start = rangeStart(f.range);
      if (start) q = q.gte("created_at", start.toISOString());
      if (f.kind === "helmet") q = q.eq("has_helmet", false);
      if (f.kind === "vest") q = q.eq("has_vest", false);
      if (f.device) q = q.eq("device_id", f.device);
      return q;
    }
    async function count(build) {
      const { count: n, error } = await build(table().select("id", { count: "exact", head: true }));
      if (error) throw error;
      return n || 0;
    }

    return {
      mode: "live",
      async list(f, offset, limit) {
        const q = applyFilter(table().select(COLUMNS, { count: "exact" }), f)
          .order("created_at", { ascending: false })
          .range(offset, offset + limit - 1);
        const { data, count: total, error } = await q;
        if (error) throw error;
        return { rows: data || [], total: total || 0 };
      },
      async stats() {
        const since = startOfToday().toISOString();
        const [today, helmet, vest, last] = await Promise.all([
          count((q) => q.gte("created_at", since)),
          count((q) => q.gte("created_at", since).eq("has_helmet", false)),
          count((q) => q.gte("created_at", since).eq("has_vest", false)),
          table().select(COLUMNS).order("created_at", { ascending: false }).limit(1),
        ]);
        if (last.error) throw last.error;
        return { today, helmet, vest, last: (last.data || [])[0] || null };
      },
      async devices() {
        const { data, error } = await table().select("device_id").order("created_at", { ascending: false }).limit(1000);
        if (error) throw error;
        return [...new Set((data || []).map((r) => r.device_id))];
      },
      subscribe(onInsert, onStatus) {
        client
          .channel("safety_logs_inserts")
          .on("postgres_changes", { event: "INSERT", schema: "public", table: cfg.table }, (p) => onInsert(p.new))
          .subscribe((status) => onStatus(status));
      },
    };
  }

  // ---------- 데이터 출처: 데모 (Supabase 없이 화면 확인용) ----------
  function demoSource() {
    const devices = ["cam-01", "cam-02", "cam-03"];
    const rows = [];
    let nextId = 1;

    function photo(row) {
      const hue = { "cam-01": 200, "cam-02": 150, "cam-03": 30 }[row.device_id] || 0;
      const helmet = row.has_helmet
        ? ""
        : '<rect x="104" y="40" width="72" height="36" rx="4" fill="none" stroke="#ff8a3d" stroke-width="3" stroke-dasharray="6 4"/>';
      const vest = row.has_vest
        ? ""
        : '<rect x="96" y="100" width="88" height="72" rx="4" fill="none" stroke="#ff6b6b" stroke-width="3" stroke-dasharray="6 4"/>';
      const svg =
        `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 210">` +
        `<rect width="280" height="210" fill="hsl(${hue} 18% 28%)"/>` +
        `<rect y="160" width="280" height="50" fill="hsl(${hue} 14% 20%)"/>` +
        `<circle cx="140" cy="68" r="22" fill="hsl(${hue} 10% 70%)"/>` +
        `<path d="M104 180 q0-70 36-70 q36 0 36 70z" fill="hsl(${hue} 10% 62%)"/>` +
        helmet + vest +
        `<text x="10" y="200" font-family="monospace" font-size="11" fill="#ffffffaa">${row.device_id} DEMO</text></svg>`;
      return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    }
    function make(at) {
      const r = Math.random();
      const row = {
        id: nextId++,
        created_at: at.toISOString(),
        device_id: devices[Math.floor(Math.random() * devices.length)],
        has_helmet: r > 0.55,
        has_vest: r <= 0.55 ? Math.random() > 0.5 : false,
        confidence: Math.round((0.55 + Math.random() * 0.43) * 100) / 100,
      };
      row.image_url = photo(row);
      return row;
    }
    // 지난 3일치 가짜 기록
    let t = Date.now() - 3 * 24 * 3600 * 1000;
    while (t < Date.now() - 60 * 1000) {
      rows.push(make(new Date(t)));
      t += (20 + Math.random() * 140) * 60 * 1000;
    }
    rows.reverse();

    const filtered = (f) =>
      rows.filter((r) => {
        const start = rangeStart(f.range);
        if (start && new Date(r.created_at) < start) return false;
        if (f.kind === "helmet" && r.has_helmet) return false;
        if (f.kind === "vest" && r.has_vest) return false;
        if (f.device && r.device_id !== f.device) return false;
        return true;
      });

    return {
      mode: "demo",
      async list(f, offset, limit) {
        const all = filtered(f);
        return { rows: all.slice(offset, offset + limit), total: all.length };
      },
      async stats() {
        const today = filtered({ range: "today", kind: "all" });
        return {
          today: today.length,
          helmet: today.filter((r) => !r.has_helmet).length,
          vest: today.filter((r) => !r.has_vest).length,
          last: rows[0] || null,
        };
      },
      async devices() {
        return devices;
      },
      subscribe(onInsert, onStatus) {
        onStatus("DEMO");
        setInterval(() => {
          const row = make(new Date());
          rows.unshift(row);
          onInsert(row);
        }, 12000);
      },
    };
  }

  // ---------- 화면 ----------
  function tagsHtml(row) {
    const tags = [];
    if (!row.has_helmet) tags.push('<span class="tag helmet">안전모 미착용</span>');
    if (!row.has_vest) tags.push('<span class="tag vest">조끼 미착용</span>');
    if (!tags.length) tags.push('<span class="tag ok">착용 확인</span>');
    return tags.join("");
  }
  function rowHtml(row, isNew) {
    const conf = typeof row.confidence === "number" ? row.confidence : null;
    const pct = conf === null ? null : Math.round(conf * 100);
    const thumb = row.image_url
      ? `<button class="thumb" type="button" data-id="${escapeHtml(row.id)}" aria-label="사진 크게 보기"><img src="${escapeHtml(row.image_url)}" alt="" loading="lazy"></button>`
      : '<button class="thumb" type="button" disabled>사진 없음</button>';
    return `
      <article class="row${isNew ? " new" : ""}" data-row="${escapeHtml(row.id)}">
        ${thumb}
        <div class="meta">
          <div class="when"><span class="mono">${escapeHtml(fmtTime(row.created_at))}</span><span class="ago" data-ago="${escapeHtml(row.created_at)}">${ago(row.created_at)}</span></div>
          <div class="device mono">${escapeHtml(row.device_id)}</div>
          <div class="tags">${tagsHtml(row)}</div>
        </div>
        <div class="conf">
          <div><div class="num mono">${pct === null ? "–" : pct + "%"}</div><div class="lbl">신뢰도</div></div>
          <div class="bar"><i style="width:${pct || 0}%"></i></div>
        </div>
      </article>`;
  }

  function renderList() {
    const list = $("list");
    if (!state.rows.length) {
      list.innerHTML = '<div class="empty">조건에 맞는 위반 기록이 없습니다.</div>';
    } else {
      list.innerHTML = state.rows.map((r) => rowHtml(r, false)).join("");
    }
    $("list-count").textContent = state.total ? `${state.total.toLocaleString("ko-KR")}건` : "";
    $("more").hidden = state.rows.length >= state.total;
  }

  function renderStats(s) {
    $("v-today").textContent = s.today.toLocaleString("ko-KR");
    $("v-helmet").textContent = s.helmet.toLocaleString("ko-KR");
    $("v-vest").textContent = s.vest.toLocaleString("ko-KR");
    if (s.last) {
      $("v-last").textContent = ago(s.last.created_at);
      $("v-last").dataset.ago = s.last.created_at;
      $("v-last-device").textContent = s.last.device_id;
    } else {
      $("v-last").textContent = "기록 없음";
      $("v-last-device").textContent = "";
    }
  }

  function renderDevices() {
    const sel = $("f-device");
    const current = sel.value;
    const opts = [...state.devices].sort();
    sel.innerHTML =
      '<option value="">모든 장치</option>' + opts.map((d) => `<option value="${escapeHtml(d)}">${escapeHtml(d)}</option>`).join("");
    sel.value = opts.includes(current) ? current : "";
  }

  function setStatus(kind, text) {
    $("status").dataset.state = kind;
    $("status-text").textContent = text;
  }
  function showBanner(html, isError) {
    const b = $("banner");
    b.innerHTML = html;
    b.classList.toggle("error", !!isError);
    b.hidden = false;
  }

  // ---------- 동작 ----------
  let source;
  let stats = { today: 0, helmet: 0, vest: 0, last: null };

  async function reload() {
    const f = { range: state.range, kind: state.kind, device: state.device };
    const { rows, total } = await source.list(f, 0, cfg.pageSize);
    state.rows = rows;
    state.total = total;
    renderList();
  }
  async function loadMore() {
    const btn = $("more");
    btn.disabled = true;
    try {
      const f = { range: state.range, kind: state.kind, device: state.device };
      const { rows, total } = await source.list(f, state.rows.length, cfg.pageSize);
      state.rows = state.rows.concat(rows);
      state.total = total;
      renderList();
    } catch (e) {
      fail(e);
    } finally {
      btn.disabled = false;
    }
  }

  function onInsert(row) {
    // 오늘 수치
    if (new Date(row.created_at) >= startOfToday()) {
      stats.today += 1;
      if (!row.has_helmet) stats.helmet += 1;
      if (!row.has_vest) stats.vest += 1;
    }
    stats.last = row;
    renderStats(stats);
    const card = $("stat-today");
    card.classList.remove("bump");
    void card.offsetWidth;
    card.classList.add("bump");

    if (!state.devices.has(row.device_id)) {
      state.devices.add(row.device_id);
      renderDevices();
    }
    // 지금 보는 조건에 맞으면 맨 위에 넣는다
    if (!matchesFilter(row) || state.rows.some((r) => r.id === row.id)) return;
    state.rows.unshift(row);
    state.total += 1;
    const list = $("list");
    if (state.rows.length === 1) list.innerHTML = "";
    list.insertAdjacentHTML("afterbegin", rowHtml(row, true));
    $("list-count").textContent = `${state.total.toLocaleString("ko-KR")}건`;
  }

  function onRealtimeStatus(status) {
    if (status === "DEMO") setStatus("demo", "데모 데이터");
    else if (status === "SUBSCRIBED") setStatus("live", "실시간 연결됨");
    else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") setStatus("error", "실시간 끊김");
    else if (status === "CLOSED") setStatus("idle", "연결 닫힘");
  }

  function fail(e) {
    console.error(e);
    setStatus("error", "불러오기 실패");
    showBanner(`Supabase에서 기록을 읽지 못했습니다: <code>${escapeHtml(e && (e.message || e))}</code>`, true);
  }

  function openViewer(id) {
    const row = state.rows.find((r) => String(r.id) === String(id));
    if (!row || !row.image_url) return;
    $("viewer-img").src = row.image_url;
    $("viewer-img").alt = `${row.device_id} ${fmtTime(row.created_at)} 위반 사진`;
    $("viewer-when").textContent = `${fmtTime(row.created_at)} · ${ago(row.created_at)}`;
    $("viewer-device").textContent = row.device_id;
    $("viewer-tags").innerHTML = tagsHtml(row);
    $("viewer").showModal();
  }

  function bindUi() {
    document.querySelectorAll("[data-range]").forEach((btn) =>
      btn.addEventListener("click", () => {
        state.range = btn.dataset.range;
        document.querySelectorAll("[data-range]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
        reload().catch(fail);
      })
    );
    $("f-kind").addEventListener("change", (e) => {
      state.kind = e.target.value;
      reload().catch(fail);
    });
    $("f-device").addEventListener("change", (e) => {
      state.device = e.target.value;
      reload().catch(fail);
    });
    $("more").addEventListener("click", loadMore);
    $("list").addEventListener("click", (e) => {
      const t = e.target.closest(".thumb[data-id]");
      if (t) openViewer(t.dataset.id);
    });
    $("viewer-close").addEventListener("click", () => $("viewer").close());
    $("viewer").addEventListener("click", (e) => {
      if (e.target === $("viewer")) $("viewer").close();
    });
    $("theme").addEventListener("click", () => {
      const root = document.documentElement;
      const dark = root.dataset.theme
        ? root.dataset.theme === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.theme = dark ? "light" : "dark";
      try {
        localStorage.setItem("safety-theme", root.dataset.theme);
      } catch (_) {
        /* 저장이 막힌 브라우저는 무시 */
      }
    });
    try {
      const saved = localStorage.getItem("safety-theme");
      if (saved) document.documentElement.dataset.theme = saved;
    } catch (_) {
      /* 무시 */
    }
    // "n분 전" 표시를 주기적으로 갱신
    setInterval(() => {
      document.querySelectorAll("[data-ago]").forEach((el) => {
        el.textContent = ago(el.dataset.ago);
      });
    }, 30000);
  }

  async function start() {
    bindUi();
    const configured = cfg.supabaseUrl && cfg.supabaseAnonKey;
    if (configured && !window.supabase) {
      fail(new Error("supabase-js를 불러오지 못했습니다 (네트워크 확인)"));
      return;
    }
    if (configured) {
      source = supabaseSource();
    } else {
      source = demoSource();
      showBanner(
        "데모 모드입니다. 실제 기록을 보려면 <code>web/config.js</code>에 Supabase URL과 anon key를 넣으세요. 화면의 기록은 모두 가짜입니다."
      );
    }
    try {
      const [s, devices] = await Promise.all([source.stats(), source.devices(), reload()]);
      stats = s;
      renderStats(stats);
      devices.forEach((d) => state.devices.add(d));
      renderDevices();
      source.subscribe(onInsert, onRealtimeStatus);
    } catch (e) {
      fail(e);
    }
  }

  start();
})();
