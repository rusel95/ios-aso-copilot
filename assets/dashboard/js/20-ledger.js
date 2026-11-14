// Ledger: what to judge, what to decide, what comes next; every hypothesis as a square; the timeline; and for each
// hypothesis whose window has closed, what was read against what it predicted. The page writes no verdict.
ASO.MARKS = [["worked", "worked"], ["no-effect", "no-effect"], ["adverse", "adverse"], ["withheld", "withheld"],
             ["due", "due"], ["open", "open"], ["not-shipped", "not shipped"]];
ASO.SERIES = ["s1", "s2", "s3", "s4"];        // a fixed order of series colours; a fifth query and on is drawn grey

ASO.markLabel = function (mark) {
  var found = ASO.MARKS.filter(function (m) { return m[0] === mark; })[0];
  return found ? found[1] : mark;
};

ASO.basketLine = function (h) {
  if (!h.basket) { return ""; }
  return h.basket.up + " up · " + h.basket.down + " down · " + h.basket.flat + " flat" +
    (h.basket.unpaired ? " · " + h.basket.unpaired + " unpaired" : "") +
    (h.basket.unmeasurable ? " · " + h.basket.unmeasurable + " unmeasurable" : "");
};

ASO.queueList = function (payload, today) {
  var queue = payload.events.queue;
  if (!queue.length) { return "<p>Nothing is queued.</p>"; }
  return '<ul class="rows">' + queue.map(function (q) {
    return '<li><span class="id">' + ASO.esc(q.id) + "</span> <span>" + ASO.esc(q.title) + '</span> <span class="meta">queued ' +
      ASO.days(q.date, today) + " d ago</span></li>";
  }).join("") + "</ul>";
};

// The ledger's own order: by score, then storefront, then key, all descending. The page sorts; it scores nothing.
ASO.nextList = function (payload, limit) {
  var rows = payload.keys.keys.filter(function (k) { return k.priority; }).sort(function (a, b) {
    return b.priority.score - a.priority.score || (a.market < b.market ? 1 : a.market > b.market ? -1 : 0) ||
      (a.keyword < b.keyword ? 1 : -1);
  }).slice(0, limit);
  if (!rows.length) { return "<p>" + ASO.missing("no_data") + "</p>"; }
  return '<ul class="next">' + rows.map(function (k) {
    return '<li><span class="id">' + ASO.esc(k.market) + "</span> <span>" + ASO.esc(k.keyword) + ' <span class="meta">' +
      ASO.esc(k.priority.status.toLowerCase()) + '</span></span> <span class="mono">' +
      (k.priority.position === null ? "beyond depth" : "#" + k.priority.position) + '</span> <span class="mono strong">' +
      k.priority.score.toFixed(2) + "</span></li>";
  }).join("") + "</ul>";
};

ASO.squares = function (payload) {
  var all = payload.hypotheses.hypotheses, counts = {};
  all.forEach(function (h) { var m = ASO.mark(h); counts[m] = (counts[m] || 0) + 1; });
  var judged = all.filter(function (h) { return h.state === "judged"; }).length;
  return '<div class="squares">' + all.map(function (h) {
    return '<span class="sq m-' + ASO.esc(ASO.mark(h)) + '" title="' + ASO.esc(h.id + " · " + ASO.markLabel(ASO.mark(h))) + '"></span>';
  }).join("") + '</div><ul class="legend">' + ASO.MARKS.filter(function (m) { return counts[m[0]]; }).map(function (m) {
    return '<li><span class="sq m-' + m[0] + '"></span><strong>' + counts[m[0]] + "</strong> " + ASO.esc(m[1]) + "</li>";
  }).join("") + '</ul><p class="lead">Of ' + judged + " judged, " + (counts.worked || 0) + " worked.</p>";
};

ASO.verdictList = function (payload, verdict) {
  var rows = payload.hypotheses.hypotheses.filter(function (h) { return h.verdict === verdict; });
  if (!rows.length) { return '<p class="meta">None.</p>'; }
  return '<ul class="rows two">' + rows.map(function (h) {
    return '<li><span class="id">' + ASO.esc(h.id) + "</span> <span>" + ASO.esc(h.title) +
      (h.basket ? ' <span class="meta">' + ASO.esc(ASO.basketLine(h)) + "</span>" : "") + "</span></li>";
  }).join("") + "</ul>";
};

// One drawing for all hypotheses that went live: a bar from the live day to the end of the declared window.
ASO.timeline = function (payload, today) {
  var live = payload.hypotheses.hypotheses.filter(function (h) { return h.went_live; })
    .sort(function (a, b) { return a.went_live < b.went_live ? -1 : a.went_live > b.went_live ? 1 : (a.id < b.id ? -1 : 1); });
  if (!live.length) { return "<p>No hypothesis has gone live yet.</p>"; }
  var first = live[0].went_live.slice(0, 8) + "01";
  var last = live.reduce(function (day, h) { return h.window_end > day ? h.window_end : day; }, today);
  var span = ASO.days(first, last) + 3, left = 340, width = 650, row = 24, top = 30;
  var height = top + live.length * row + 6;
  function x(day) { return (left + width * ASO.days(first, day) / span).toFixed(1); }
  var out = '<svg class="timeline" viewBox="0 0 1000 ' + height + '" role="img" aria-label="Hypotheses from the day each went live to the end of its window">';
  for (var month = first; month <= last;) {
    out += '<line class="tl-month" x1="' + x(month) + '" y1="18" x2="' + x(month) + '" y2="' + height + '"/><text class="tl-axis" x="' +
      (+x(month) + 4) + '" y="12">' + ASO.esc(month.slice(0, 7)) + "</text>";
    var y = +month.slice(0, 4), m = +month.slice(5, 7) + 1;
    if (m > 12) { m = 1; y += 1; }
    month = y + "-" + (m < 10 ? "0" : "") + m + "-01";
  }
  payload.events.releases.forEach(function (r) {
    if (r.date >= first && r.date <= last) {
      out += '<line class="tl-release" x1="' + x(r.date) + '" y1="18" x2="' + x(r.date) + '" y2="' + height + '"/><text class="tl-axis strong" x="' +
        (+x(r.date) + 4) + '" y="26">' + ASO.esc(r.version) + "</text>";
    }
  });
  out += '<line class="tl-today" x1="' + x(today) + '" y1="18" x2="' + x(today) + '" y2="' + height + '"/><text class="tl-axis strong" x="' +
    (+x(today) - 4) + '" y="12" text-anchor="end">today</text>';
  live.forEach(function (h, i) {
    var mid = top + i * row + 12, mark = ASO.mark(h), title = h.title.length > 36 ? h.title.slice(0, 35) + "…" : h.title;
    out += '<text class="tl-id" x="0" y="' + (mid + 4) + '">' + ASO.esc(h.id) + '</text><text class="tl-title" x="48" y="' + (mid + 4) + '">' +
      ASO.esc(title) + '</text><rect class="tl-bar m-' + ASO.esc(mark) + '" x="' + x(h.went_live) + '" y="' + (mid - 6) + '" width="' +
      Math.max(3, +x(h.window_end) - +x(h.went_live)).toFixed(1) + '" height="12" rx="3"><title>' +
      ASO.esc(h.id + " · " + ASO.markLabel(mark) + " · " + h.went_live + " → " + h.window_end) + "</title></rect>";
  });
  return '<div class="scroll">' + out + "</svg></div>";
};

// The positions of a hypothesis's own keys, read by read, with the live day, the end of its window and today.
ASO.rankChart = function (payload, h, today) {
  var dates = payload.keys.dates, byKey = {};
  payload.keys.keys.forEach(function (k) { byKey[k.market + "\n" + k.keyword] = k; });
  var keys = h.basket_keys.map(function (pair) { return byKey[pair[0] + "\n" + pair[1]]; }).filter(Boolean);
  if (!keys.length || !dates.length) { return ""; }
  var first = dates[0] < h.went_live ? dates[0] : h.went_live, span = ASO.days(first, today) || 1, deepest = 30;
  keys.forEach(function (k) { k.positions.forEach(function (p) { if (typeof p === "number" && p > deepest) { deepest = p; } }); });
  function x(day) { return (40 + 700 * ASO.days(first, day) / span).toFixed(1); }
  function y(position) { return (16 + 170 * (position - 1) / (deepest - 1)).toFixed(1); }
  var out = '<svg class="rank-chart" viewBox="0 0 760 214" role="img" aria-label="Positions of this hypothesis\'s keys, read by read">';
  [1, Math.round(deepest / 2), deepest].forEach(function (rank) {
    out += '<line class="grid" x1="40" y1="' + y(rank) + '" x2="750" y2="' + y(rank) + '"/><text class="tl-axis" x="34" y="' +
      (+y(rank) + 4) + '" text-anchor="end">#' + rank + "</text>";
  });
  [["v-live", h.went_live, "live " + h.went_live], ["v-end", h.window_end, "window end"], ["v-today", today, "today"]].forEach(function (v) {
    if (v[1] >= first && v[1] <= today) {
      out += '<line class="' + v[0] + '" x1="' + x(v[1]) + '" y1="10" x2="' + x(v[1]) + '" y2="192"/><text class="tl-axis" x="' +
        (+x(v[1]) - 4) + '" y="206" text-anchor="end">' + ASO.esc(v[2]) + "</text>";
    }
  });
  var legend = "";
  keys.forEach(function (k, i) {
    var tone = ASO.SERIES[i] || "s-rest", points = [], latest = null;
    k.positions.forEach(function (p, at) {
      if (typeof p === "number") { points.push(x(dates[at]) + "," + y(p)); latest = p; }
    });
    out += '<polyline class="' + tone + '" points="' + points.join(" ") + '"/>';
    points.forEach(function (point) {
      var xy = point.split(",");
      out += '<circle class="' + tone + '" cx="' + xy[0] + '" cy="' + xy[1] + '" r="3"/>';
    });
    legend += '<li><svg class="swatch" viewBox="0 0 14 4"><rect class="' + tone + '" width="14" height="4"/></svg>' +
      ASO.esc(k.market) + " · " + ASO.esc(k.keyword) + ' <span class="mono">' + (latest === null ? "no position yet" : "#" + latest) + "</span></li>";
  });
  return '<ul class="legend">' + legend + '</ul><div class="scroll">' + out + "</svg></div>";
};

ASO.dueCard = function (payload, h, today) {
  var reads = h.reads_in_window;
  var out = '<section class="block due-card" id="due-' + ASO.esc(h.id) + '"><h2><span class="id">' + ASO.esc(h.id) + "</span> " +
    ASO.esc(h.title) + ' <span class="chip due">due · window closed ' + ASO.esc(h.window_end) + '</span></h2><p class="meta">live ' +
    ASO.esc(h.went_live) + " · " + h.window_days + " days · signal: " + ASO.esc(h.signal) +
    (h.markets.length ? " · " + ASO.esc(h.markets.join(", ")) : "") + "</p>";
  if (reads === null) {
    out += '<p class="note">This hypothesis is not judged on rank, so there is no position to draw. Its evidence is in the ' +
      ASO.esc(h.signal) + " figures of its window.</p>";
  } else {
    out += '<p class="lead"><span class="chip' + (reads ? "" : " due") + '">' + reads + (reads === 1 ? " read" : " reads") +
      " inside the window</span> " + ASO.esc(ASO.basketLine(h)) + "</p>" + ASO.rankChart(payload, h, today);
    if (h.queries.length > h.basket_keys.length) {
      out += '<p class="meta">' + (h.queries.length * Math.max(1, h.markets.length) - h.basket_keys.length) +
        " of its queries name no tracked key, so nothing was read for them.</p>";
    }
  }
  out += '<dl class="terms">';
  [["Queries", h.queries.join(" · ")], ["Prediction", h.prediction], ["Kill criterion", h.kill_criterion],
   ["Confounds", h.confounds.join(" · ")]].forEach(function (pair) {
    if (pair[1]) { out += "<dt>" + pair[0] + "</dt><dd>" + ASO.esc(pair[1]) + "</dd>"; }
  });
  return out + "</dl></section>";
};

ASO.pages["#/ledger"] = function (payload, today) {
  var due = payload.hypotheses.hypotheses.filter(function (h) { return h.state === "due"; })
    .sort(function (a, b) { return b.days_past_window - a.days_past_window || (a.id < b.id ? -1 : 1); });
  var out = '<h1 class="page">Close before proposing</h1><div class="blocks"><section class="block">\n<h2>Judge</h2><p class="meta">' +
    due.length + " window" + (due.length === 1 ? "" : "s") + " closed with no verdict</p>" + ASO.dueList(payload) +
    '</section><section class="block">\n<h2>Decide</h2><p class="meta">' + payload.events.queue.length + " queued approval" +
    (payload.events.queue.length === 1 ? "" : "s") + "</p>" + ASO.queueList(payload, today) +
    '</section><section class="block">\n<h2>Next by money at stake</h2>' + ASO.nextList(payload, 5) +
    '<p class="meta">Score = net proceeds per subscriber × unclaimed gain × reach. An order, not a forecast.</p></section></div>';

  out += '<div class="blocks"><section class="block">\n<h2>' + payload.hypotheses.hypotheses.length + " hypotheses</h2>" + ASO.squares(payload) +
    '</section><section class="block">\n<h2>What worked</h2>' + ASO.verdictList(payload, "worked") +
    '</section><section class="block">\n<h2>What hurt</h2>' + ASO.verdictList(payload, "adverse") + "</section></div>";

  out += '<section class="block">\n<h2>Timeline</h2><p class="meta">Each bar runs from the day a change went live to the end of its declared window.</p>' +
    ASO.timeline(payload, today) + "</section>";
  if (due.length) {
    out += '<h1 class="page">Due: what was predicted, what was read</h1>' +
      due.map(function (h) { return ASO.dueCard(payload, h, today); }).join("");
  }
  return out;
};
