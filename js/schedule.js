/* =====================================================================
   index.html — Laboratory Schedule + Room Plotting viewer
   - Builds the weekly schedule grid from data/room-plotting-data.js
   - Makes the room plotting image clickable (full-screen, zoomable)
========================================================================*/
(function () {
  const RP = window.ROOM_PLOTTING;
  const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
  
  const toMin = t => { const [h, m] = t.split(":").map(Number); return h * 60 + m; };
  const fmtHour = h => { const ap = h >= 12 ? "PM" : "AM"; const hh = h % 12 || 12; return `${hh}:00 ${ap}`; };
  const fmtTime = t => { const [h, m] = t.split(":").map(Number); const ap = h >= 12 ? "PM" : "AM"; return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${ap}`; };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /* ---------- Weekly schedule grid ---------- */
  function renderSchedule() {
    const host = document.getElementById("scheduleGrid");
    if (!host || !RP) return;

    // Grid covers 8 AM – 5 PM, and stretches automatically if the data has earlier/later classes
    let FIRST_HOUR = 8, LAST_HOUR = 17;
    RP.classes.forEach(c => {
      FIRST_HOUR = Math.min(FIRST_HOUR, Math.floor(toMin(c.start) / 60));
      LAST_HOUR = Math.max(LAST_HOUR, Math.ceil(toMin(c.end) / 60));
    });

    // Which block (if any) starts at / covers each day+hour
    const starts = {}, covered = {};
    RP.classes.forEach(c => {
      const s = toMin(c.start), e = toMin(c.end);
      starts[`${c.day}|${Math.floor(s / 60)}`] = c;
      for (let h = Math.floor(s / 60) + 1; h * 60 < e; h++) covered[`${c.day}|${h}`] = true;
    });

    const lunch = RP.lunch || { start: "12:00", end: "13:00" };
    let html = `<table class="sched-grid"><thead><tr><th>Time</th>${DAYS.map(d => `<th>${d}</th>`).join("")}</tr></thead><tbody>`;
    for (let h = FIRST_HOUR; h < LAST_HOUR; h++) {
      html += `<tr><th class="time-col">${fmtHour(h)} – ${fmtHour(h + 1)}</th>`;
      DAYS.forEach(day => {
        const key = `${day}|${h}`;
        if (covered[key]) return;                       // swallowed by a rowspan
        const c = starts[key];
        if (c) {
          const span = Math.max(1, Math.ceil((toMin(c.end) - toMin(c.start)) / 60));
          html += `<td class="sched-class" rowspan="${span}">
            <strong>${esc(c.subject)}</strong>
            <span>${esc(c.section)}</span>
            <em>${esc(c.instructor)}</em>
            <small>${fmtTime(c.start)} – ${fmtTime(c.end)}</small></td>`;
        } else if (h * 60 >= toMin(lunch.start) && h * 60 < toMin(lunch.end)) {
          html += `<td class="sched-lunch">Lunch break</td>`;
        } else {
          html += `<td class="sched-vacant">Vacant</td>`;
        }
      });
      html += `</tr>`;
    }
    html += `</tbody></table>`;
    host.innerHTML = html;

    const meta = document.getElementById("scheduleMeta");
    if (meta) meta.textContent = `${RP.room} • ${RP.term}`;
  }

  /* ---------- Room plotting image viewer ---------- */
  function setupViewer() {
    const trigger = document.getElementById("planTrigger");
    const viewer = document.getElementById("planViewer");
    if (!trigger || !viewer) return;
    const stage = viewer.querySelector(".pv-stage");
    const img = viewer.querySelector("img");
    const zoomBtn = viewer.querySelector("[data-zoom]");
    let zoomed = false;

    const setZoom = on => {
      zoomed = on;
      viewer.classList.toggle("zoomed", on);
      zoomBtn.textContent = on ? "🔍 Fit to screen" : "🔍 Zoom in";
      if (on) { stage.scrollLeft = (stage.scrollWidth - stage.clientWidth) / 2; stage.scrollTop = 0; }
    };
    const open = () => { viewer.classList.add("open"); document.body.style.overflow = "hidden"; setZoom(false); };
    const close = () => { viewer.classList.remove("open"); document.body.style.overflow = ""; };

    trigger.addEventListener("click", open);
    trigger.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
    viewer.querySelector("[data-close]").addEventListener("click", close);
    zoomBtn.addEventListener("click", () => setZoom(!zoomed));
    img.addEventListener("click", () => setZoom(!zoomed));
    stage.addEventListener("click", e => { if (e.target === stage) close(); });
    document.addEventListener("keydown", e => { if (e.key === "Escape" && viewer.classList.contains("open")) close(); });
  }

  document.addEventListener("DOMContentLoaded", () => { renderSchedule(); setupViewer(); });
})();
