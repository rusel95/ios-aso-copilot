"use strict";
// The page's logic. Every function that returns markup is pure: data in, a string out, no DOM. The DOM is touched
// only in 99-start.js. Every string that comes from the data goes through ASO.esc. The page computes no figure:
// it formats, sorts and draws what the data files hold.
var ASO = { pages: {} };

ASO.TABS = [["#/", "Overview"], ["#/ledger", "Ledger"], ["#/keywords", "Keywords"], ["#/funnel", "Store funnel"],
            ["#/money", "Money"], ["#/ads", "Apple Ads"], ["#/in-app", "In-app"], ["#/how", "How data gets here"]];
ASO.MISSING = { no_source: "Not stored yet", no_data: "Nothing to measure", not_configured: "Not set up",
                unreachable: "Could not be fetched" };
ASO.STALE_AFTER = 14;       // days; a source older than this is marked stale
ASO.PARTIAL_UNDER = 0.5;    // a sweep that read less than this share of the tracked keys is left out of trends

ASO.esc = function (text) {
  return String(text == null ? "" : text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
};

ASO.group = function (digits) { return String(digits).replace(/\B(?=(\d{3})+(?!\d))/g, ","); };

ASO.fmt = function (value, unit) {
  if (unit === "ratio") { return (value * 100).toFixed(1) + "%"; }
  if (unit === "usd") {
    var parts = Math.abs(value).toFixed(2).split(".");
    return (value < 0 ? "−$" : "$") + ASO.group(parts[0]) + "." + parts[1];
  }
  if (unit === "per_100") { return value.toFixed(1); }
  if (unit === "stars") { return value.toFixed(2); }
  return Number.isInteger(value) ? ASO.group(value) : value.toFixed(1);
};

ASO.days = function (from, to) {
  return Math.round((Date.parse(to + "T00:00:00Z") - Date.parse(from + "T00:00:00Z")) / 864e5);
};

// ---- reading the data
ASO.split = function (key) { var at = key.indexOf("."); return [key.slice(0, at), key.slice(at + 1)]; };

ASO.spec = function (payload, key) {
  var parts = ASO.split(key), family = payload.catalog.families[parts[0]];
  return family.figures[parts[1]] || { title: parts[1].replace(/[._]/g, " "), unit: "count", ratio: null, approximation: null,
                                       open: true, definition: "A number the app's own telemetry stores under this name." };
};

// The unit a value is printed in. A figure of an open family has no catalog entry: it is a share when the data
// holds its two totals, else a count.
ASO.unit = function (spec, entry) {
  return spec.open && entry && typeof entry.denominator === "number" ? "ratio" : spec.unit;
};

ASO.periods = function (payload, family) {
  return payload.catalog.families[family].kind === "week" ? payload.weeks : payload.snapshots;
};

// One entry per period that holds the figure: its id, its value or its unavailable, and its family's source.
ASO.series = function (payload, key) {
  var parts = ASO.split(key), out = [];
  ASO.periods(payload, parts[0]).forEach(function (file) {
    var family = file.families[parts[0]];
    if (!family) { return; }
    var figure = family.unavailable ? { unavailable: family.unavailable } : (family.figures || {})[parts[1]];
    if (!figure) { return; }
    var entry = { id: file.period.id, source: family.source || null, fetched_at: family.fetched_at || null };
    Object.keys(figure).forEach(function (name) { entry[name] = figure[name]; });
    out.push(entry);
  });
  return out;
};

ASO.last = function (entries) { return entries.length ? entries[entries.length - 1] : null; };

ASO.values = function (entries) { return entries.filter(function (e) { return typeof e.value === "number"; }); };

// Snapshots that hold a rank sweep covering enough of the basket to be compared with the others.
ASO.fullSweeps = function (payload) {
  return payload.snapshots.filter(function (file) {
    var ranks = file.families.ranks;
    if (!ranks || !ranks.figures) { return false; }
    var read = ranks.figures.keys_read.value, tracked = ranks.figures.tracked_keys.value;
    return tracked > 0 && read / tracked >= ASO.PARTIAL_UNDER;
  });
};

// The newest day a family was fetched, or null when no file holds a reading of it.
ASO.fetched = function (payload, family) {
  var files = ASO.periods(payload, family), day = null;
  files.forEach(function (file) {
    var found = file.families[family];
    if (found && !found.unavailable && found.fetched_at && (day === null || found.fetched_at > day)) { day = found.fetched_at; }
  });
  return day;
};

// ---- drawing
ASO.missing = function (code, reason, key, period) {
  var words = ASO.esc(ASO.MISSING[code] || ASO.MISSING.no_source);
  if (!key) { return '<span class="missing">' + words + "</span>"; }
  return '<button class="fig missing" data-fig="' + ASO.esc(key) + '" data-period="' + ASO.esc(period) + '" title="' +
    ASO.esc(reason) + '">' + words + "</button>";
};

// A figure as the reader meets it: a value to click for its source, an approximation marked as one, or the words for
// why it is missing. `show` picks what is printed: "value" (default), "numerator" or "denominator".
ASO.figure = function (payload, key, entry, show) {
  if (!entry) { return ASO.missing("no_source"); }
  if (entry.unavailable) { return ASO.missing(entry.unavailable.code, entry.unavailable.reason, key, entry.id); }
  var spec = ASO.spec(payload, key), part = show || "value";
  var text = part === "value" ? ASO.fmt(entry.value, ASO.unit(spec, entry)) : ASO.group(entry[part]);
  return '<button class="fig' + (spec.approximation ? " approx" : "") + '" data-fig="' + ASO.esc(key) + '" data-period="' +
    ASO.esc(entry.id) + '">' + (spec.approximation ? "≈ " : "") + ASO.esc(text) + "</button>";
};

ASO.tile = function (title, number, sub, extra) {
  return '<section class="tile">\n<h3>' + ASO.esc(title) + '</h3><div class="num">' + number + "</div>" +
    (sub ? '<p class="sub">' + sub + "</p>" : "") + (extra || "") + "</section>";
};

// A line over a series of numbers, newest last. Geometry is in attributes: the page's policy refuses style attributes.
ASO.spark = function (numbers, label) {
  if (numbers.length < 2) { return ""; }
  var low = Math.min.apply(null, numbers), high = Math.max.apply(null, numbers), span = high - low || 1;
  var points = numbers.map(function (n, i) {
    return (2 + 116 * i / (numbers.length - 1)).toFixed(1) + "," + (26 - 24 * (n - low) / span).toFixed(1);
  });
  var end = points[points.length - 1].split(",");
  return '<svg class="spark" viewBox="0 0 120 28" role="img" aria-label="' + ASO.esc(label) + '"><polyline points="' +
    points.join(" ") + '"/><circle cx="' + end[0] + '" cy="' + end[1] + '" r="3"/></svg>';
};

// A filled share of a track, 0 to 1.
ASO.bar = function (share, label, tone) {
  var width = (100 * Math.max(0, Math.min(1, share))).toFixed(1);
  return '<svg class="bar' + (tone ? " " + tone : "") + '" viewBox="0 0 100 8" preserveAspectRatio="none" role="img" aria-label="' +
    ASO.esc(label) + '"><rect class="track" width="100" height="8"/><rect class="fill" width="' + width + '" height="8"/></svg>';
};

// Parts of a whole side by side: [[class, count, label], ...].
ASO.stack = function (parts, label) {
  var total = parts.reduce(function (sum, p) { return sum + p[1]; }, 0), x = 0, out = "";
  if (!total) { return ""; }
  parts.forEach(function (p) {
    var width = 100 * p[1] / total;
    if (p[1]) {
      out += '<rect class="' + p[0] + '" x="' + x.toFixed(2) + '" width="' + Math.max(0, width - 0.4).toFixed(2) +
        '" height="10"><title>' + ASO.esc(p[2] + " · " + p[1]) + "</title></rect>";
    }
    x += width;
  });
  return '<svg class="stack" viewBox="0 0 100 10" preserveAspectRatio="none" role="img" aria-label="' + ASO.esc(label) + '">' +
    out + "</svg>";
};

ASO.age = function (day, today) {
  var old = ASO.days(day, today);
  return '<span class="age' + (old > ASO.STALE_AFTER ? " stale" : "") + '">' + old + " d" +
    (old > ASO.STALE_AFTER ? " · stale" : "") + "</span>";
};

// ---- hypotheses
ASO.STATES = [["judged", "judged"], ["due", "due"], ["open", "open"], ["not-shipped", "not shipped"]];

ASO.countStates = function (payload) {
  var counts = {};
  payload.hypotheses.hypotheses.forEach(function (h) { counts[h.state] = (counts[h.state] || 0) + 1; });
  return counts;
};

// What a hypothesis is drawn as: its verdict when judged, else its state.
ASO.mark = function (h) { return h.state === "judged" ? (h.verdict || "judged") : h.state; };

// ---- shell
ASO.route = function (hash) { return !hash || hash === "#" ? "#/" : hash; };

ASO.nav = function (hash) {
  var current = ASO.route(hash);
  return ASO.TABS.map(function (tab) {
    return '<a href="' + tab[0] + '"' + (tab[0] === current ? ' aria-current="page"' : "") + ">" + ASO.esc(tab[1]) + "</a>";
  }).join("");
};

ASO.render = function (hash, payload, today) {
  var page = ASO.pages[ASO.route(hash)];
  if (!page) { return '<section class="block"><h2>No such page</h2><p><a href="#/">Back to the overview</a></p></section>'; }
  return page(payload, today);
};

// ---- the panel behind a figure
ASO.panel = function (payload, key, periodId) {
  var spec = ASO.spec(payload, key), family = payload.catalog.families[ASO.split(key)[0]];
  var entry = ASO.series(payload, key).filter(function (e) { return e.id === periodId; })[0];
  // the two totals of a ratio are named as the reader knows them: by their figure's title, in lower case
  function named(part) { return family.figures[part] ? family.figures[part].title.toLowerCase() : part; }
  var out = '<h2 id="figure-title">' + ASO.esc(spec.title) + '</h2><p class="meta">' + ASO.esc(family.title) + " · " +
    ASO.esc(family.kind === "week" ? "week of " : "read on ") + ASO.esc(periodId) + "</p>";
  if (!entry || entry.unavailable) {
    var gone = entry ? entry.unavailable : { code: "no_source", reason: "No data file holds this figure for that period." };
    out += '<p class="panel-value"><span class="missing">' + ASO.esc(ASO.MISSING[gone.code]) + "</span></p><p>" +
      ASO.esc(gone.reason) + '</p><p class="meta">code: ' + ASO.esc(gone.code) + "</p>";
  } else {
    out += '<p class="panel-value">' + ASO.esc(ASO.fmt(entry.value, ASO.unit(spec, entry))) + ' <span class="chip">' +
      (spec.approximation ? "Approximation" : "Measured") + "</span></p>";
    if (typeof entry.numerator === "number" && typeof entry.denominator === "number") {
      out += "<p>" + ASO.group(entry.numerator) + " of " + ASO.group(entry.denominator) +
        (spec.ratio ? ' <span class="meta">(' + ASO.esc(named(spec.ratio[0])) + " over " + ASO.esc(named(spec.ratio[1])) + ")</span>" : "") + "</p>";
    }
    if (spec.approximation) { out += "<p>" + ASO.esc(spec.approximation) + "</p>"; }
  }
  out += '<p class="def">' + ASO.esc(spec.definition) + "</p>";
  if (entry && entry.source) {
    out += '<p class="meta">source: ' + ASO.esc(entry.source) + " · fetched " + ASO.esc(entry.fetched_at) + "</p>";
  }
  ["by_market", "by_campaign"].forEach(function (name) {
    var parts = entry && entry[name];
    if (!parts) { return; }
    out += '<ul class="split">' + Object.keys(parts).sort().map(function (who) {
      return "<li><span>" + ASO.esc(who) + "</span> <span>" +
        (parts[who] === null ? ASO.esc(ASO.MISSING.no_data) : ASO.esc(ASO.fmt(parts[who], spec.unit))) + "</span></li>";
    }).join("") + "</ul>";
  });
  return out + '<p><button class="close" data-close="1">Close</button></p>';
};
