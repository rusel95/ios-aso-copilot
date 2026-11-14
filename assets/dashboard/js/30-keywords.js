// Keywords: the share of keys in each rank band sweep by sweep, the newest sweep by storefront, what moved,
// how much of the ledger can be compared at all, and every tracked key with its own series.
ASO.partialSweeps = function (payload) {
  var full = ASO.fullSweeps(payload);
  return payload.snapshots.filter(function (file) { return file.families.ranks && file.families.ranks.figures && full.indexOf(file) < 0; });
};

// One column per full sweep: the share of the keys read that day in each band, best band at the bottom.
ASO.bandChart = function (sweeps) {
  var step = 78, width = Math.max(520, 60 + sweeps.length * step), out = "";
  sweeps.forEach(function (file, i) {
    var f = file.families.ranks.figures, read = f.keys_read.value, x = 50 + i * step, y = 150;
    out += '<rect class="col-track" x="' + x + '" y="10" width="44" height="140"/>';
    ASO.BANDS.forEach(function (band) {
      var height = read ? 140 * f[band[0]].value / read : 0;
      if (height > 0) {
        y -= height;
        out += '<rect class="band-' + band[0] + '" x="' + x + '" y="' + y.toFixed(1) + '" width="44" height="' +
          Math.max(0, height - 1).toFixed(1) + '"><title>' + ASO.esc(band[1] + " · " + f[band[0]].value + " of " + read + " read") + "</title></rect>";
      }
    });
    out += '<text class="tl-axis" x="' + (x + 22) + '" y="166" text-anchor="middle">' + ASO.esc(file.period.id.slice(5)) + "</text>" +
      '<text class="tl-axis strong" x="' + (x + 22) + '" y="181" text-anchor="middle">' +
      (f.share_top30.unavailable ? "–" : ASO.esc(ASO.fmt(f.share_top30.value, "ratio"))) + "</text>";
  });
  return '<div class="scroll"><svg class="band-chart" viewBox="0 0 ' + width + ' 188" role="img" aria-label="Share of keys read in each rank band, sweep by sweep">' +
    '<line class="grid" x1="40" y1="150" x2="' + width + '" y2="150"/><text class="tl-axis" x="36" y="14" text-anchor="end">100%</text>' +
    '<text class="tl-axis" x="36" y="154" text-anchor="end">0%</text>' + out + "</svg></div>";
};

ASO.sweepTable = function (payload, sweeps) {
  var keys = ["ranks.keys_read", "ranks.top10", "ranks.top30", "ranks.top100", "ranks.top200", "ranks.share_top30"];
  var head = "<tr><th>Sweep</th>" + keys.map(function (k) { return "<th>" + ASO.esc(ASO.spec(payload, k).title) + "</th>"; }).join("") + "</tr>";
  var series = {};
  keys.forEach(function (k) { ASO.series(payload, k).forEach(function (e) { (series[e.id] = series[e.id] || {})[k] = e; }); });
  return '<div class="scroll"><table class="grid-table"><thead>' + head + "</thead><tbody>" + sweeps.slice().reverse().map(function (file) {
    return '<tr class="sweep"><td>' + ASO.esc(file.period.id) + "</td>" + keys.map(function (k) {
      return "<td>" + ASO.figure(payload, k, series[file.period.id][k]) + "</td>";
    }).join("") + "</tr>";
  }).join("") + "</tbody></table></div>";
};

ASO.storefronts = function (sweep) {
  var f = sweep.families.ranks.figures, share = f.share_top30.by_market || {}, read = f.keys_read.by_market || {};
  var markets = Object.keys(read).filter(function (m) { return read[m] > 0; }).sort(function (a, b) {
    return (share[b] || 0) - (share[a] || 0) || (a < b ? -1 : 1);
  });
  return '<ul class="bars">' + markets.map(function (m) {
    return '<li><span class="id">' + ASO.esc(m) + "</span>" + ASO.bar(share[m] || 0, m + " share of keys read in the top 30") +
      '<span class="mono">' + (share[m] === null ? "–" : ASO.fmt(share[m], "ratio")) + " of " + read[m] + " read</span></li>";
  }).join("") + "</ul>";
};

ASO.position = function (p) { return p === null ? "beyond depth" : "#" + p; };

ASO.moverList = function (rows) {
  if (!rows.length) { return '<p class="meta">None.</p>'; }
  return '<ul class="next">' + rows.map(function (k) {
    var m = k.movement;
    return '<li><span class="id">' + ASO.esc(k.market) + "</span> <span>" + ASO.esc(k.keyword) + '</span> <span class="mono">' +
      ASO.position(m.first) + " → " + ASO.position(m.last) + '</span> <span class="mono strong">' + (m.delta > 0 ? "+" : "−") + Math.abs(m.delta) + "</span></li>";
  }).join("") + "</ul>";
};

ASO.READ = { b: "beyond depth", e: "request failed", z: "no results" };

// A key's positions as a small line, rank 1 at the top; only the reads that returned a position are joined.
ASO.keySpark = function (positions) {
  var seen = [];
  positions.forEach(function (p, i) { if (typeof p === "number") { seen.push([i, p]); } });
  if (seen.length < 2) { return ""; }
  var low = Math.min.apply(null, seen.map(function (s) { return s[1]; })), high = Math.max.apply(null, seen.map(function (s) { return s[1]; }));
  var span = high - low || 1, last = positions.length - 1 || 1;
  return '<svg class="spark" viewBox="0 0 120 28" aria-hidden="true"><polyline points="' + seen.map(function (s) {
    return (2 + 116 * s[0] / last).toFixed(1) + "," + (2 + 24 * (s[1] - low) / span).toFixed(1);
  }).join(" ") + '"/></svg>';
};

ASO.keyTable = function (payload) {
  var rows = payload.keys.keys.map(function (k) {
    var latest = null;
    k.positions.forEach(function (p) { if (p !== null) { latest = p; } });
    var m = k.movement;
    return '<tr class="key' + (k.brand ? " is-brand" : "") + '"><td class="id">' + ASO.esc(k.market) + "</td><td>" + ASO.esc(k.keyword) +
      (k.brand ? ' <span class="chip">brand</span>' : "") + '</td><td class="meta">' + ASO.esc(k.group) + "</td><td>" + ASO.keySpark(k.positions) +
      '</td><td class="mono">' + (latest === null ? "never read" : typeof latest === "number" ? "#" + latest : ASO.READ[latest]) +
      '</td><td class="mono">' + (m && m.delta !== null ? (m.delta > 0 ? "+" : m.delta < 0 ? "−" : "") + Math.abs(m.delta) : m ? ASO.esc(m.label.toLowerCase()) : "") +
      '</td><td class="mono">' + (k.priority && k.priority.demand ? ASO.esc(k.priority.demand) : "") + "</td></tr>";
  }).join("");
  return '<div class="scroll"><table class="grid-table keys"><thead><tr><th>Mkt</th><th>Key</th><th>Group</th><th>Positions</th><th>Latest read</th>' +
    "<th>First → latest</th><th>Apple demand</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
};

ASO.pages["#/keywords"] = function (payload, today) {
  var sweeps = ASO.fullSweeps(payload), partial = ASO.partialSweeps(payload), newest = ASO.last(sweeps);
  if (!newest) {
    return '<h1 class="page">Keyword ranks</h1><section class="block"><p>' + ASO.missing("no_source") +
      "</p><p>No full rank sweep is in the data yet.</p></section>";
  }
  var movers = payload.keys.keys.filter(function (k) { return !k.brand && k.movement; });
  var gains = movers.filter(function (k) { return k.movement.delta > 0; }).sort(function (a, b) { return b.movement.delta - a.movement.delta; });
  var losses = movers.filter(function (k) { return k.movement.delta < 0; }).sort(function (a, b) { return a.movement.delta - b.movement.delta; });
  var entered = movers.filter(function (k) { return k.movement.label.indexOf("ENTERED") === 0; }).length;
  var exited = movers.filter(function (k) { return k.movement.label.indexOf("EXITED") === 0; }).length;

  var out = '<h1 class="page">Keyword ranks</h1><p class="meta">Non-brand keys · newest full sweep ' + ASO.esc(newest.period.id) + " " +
    ASO.age(newest.period.id, today) + '</p><div class="blocks wide"><section class="block">\n<h2>Share of keys read in each band</h2><ul class="legend">' +
    ASO.BANDS.map(function (b) { return '<li><svg class="swatch tall" viewBox="0 0 12 12"><rect class="band-' + b[0] + '" width="12" height="12"/></svg>' + ASO.esc(b[1]) + "</li>"; }).join("") +
    "</ul>" + ASO.bandChart(sweeps) + '<p class="meta">A column is 100% of the keys read that day; the number under it is the share at positions 1 to 30.' +
    (partial.length ? " " + partial.length + " sweep" + (partial.length === 1 ? "" : "s") + " left out as partial: " + partial.map(function (file) {
      var f = file.families.ranks.figures;
      return ASO.esc(file.period.id) + " read " + f.keys_read.value + " of " + f.tracked_keys.value + " tracked keys";
    }).join("; ") + "." : "") + "</p>" + ASO.sweepTable(payload, sweeps) + "</section>";

  out += '<section class="block">\n<h2>Top 30 by storefront</h2><p class="meta">sweep of ' + ASO.esc(newest.period.id) + "</p>" + ASO.storefronts(newest) + "</section></div>";

  out += '<div class="blocks"><section class="block">\n<h2>Largest gains</h2>' + ASO.moverList(gains.slice(0, 8)) +
    '</section><section class="block">\n<h2>Largest losses</h2>' + ASO.moverList(losses.slice(0, 8)) +
    '</section><section class="block">\n<h2>Coverage of the measurement</h2><dl class="pairs">' +
    payload.places.keywords.filter(function (key) { return key.indexOf("coverage.") === 0; }).map(function (key) {
      return "<dt>" + ASO.esc(ASO.spec(payload, key).title) + "</dt><dd>" + ASO.figure(payload, key, ASO.last(ASO.series(payload, key))) + "</dd>";
    }).join("") + '</dl><p class="meta">First read against the latest, per key. ' + entered + " entered the ranking · " + exited +
    " fell out of depth.</p></section></div>";

  out += '<section class="block">\n<h2>Every tracked key</h2><p class="meta">' + payload.keys.keys.length + " keys on " + payload.keys.dates.length +
    " sweep dates</p>" + ASO.keyTable(payload) + "</section>";
  return out;
};
