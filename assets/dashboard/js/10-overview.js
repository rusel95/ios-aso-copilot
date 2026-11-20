// Overview: how old each source is, six headline figures, and one summary block per tab.
ASO.SOURCES = [["Keyword ranks", "ranks"], ["Store funnel", "store_funnel"], ["Install lifecycle", "lifecycle"],
               ["Money", "money"], ["Apple Ads", "ads"], ["In-app", "in_app"], ["Subscriptions", "subscriptions"],
               ["Ratings and reviews", "ratings"], ["Apple search popularity", "demand"]];

ASO.sources = function (payload, today) {
  return '<ul class="sources">' + ASO.SOURCES.map(function (source) {
    // ranks are as fresh as the newest sweep that covered the basket; a later read of three keys does not refresh them
    var sweep = ASO.last(ASO.fullSweeps(payload));
    var day = source[1] === "ranks" ? (sweep ? sweep.period.id : null) : ASO.fetched(payload, source[1]);
    return '<li><span class="src-name">' + ASO.esc(source[0]) + "</span> " +
      (day ? '<span class="src-day">' + ASO.esc(day) + "</span> " + ASO.age(day, today) : ASO.missing("no_source")) + "</li>";
  }).join("") + "</ul>";
};

ASO.stateLine = function (payload) {
  var counts = ASO.countStates(payload);
  return ASO.STATES.filter(function (s) { return counts[s[0]]; }).map(function (s) { return counts[s[0]] + " " + s[1]; }).join(" · ");
};

ASO.headlineTiles = function (payload) {
  var sweep = ASO.last(ASO.fullSweeps(payload)), tiles = [];
  tiles.push(ASO.tile("Hypotheses", String(payload.hypotheses.hypotheses.length), ASO.esc(ASO.stateLine(payload))));

  var shares = ASO.series(payload, "ranks.share_top30").filter(function (e) {
    return ASO.fullSweeps(payload).some(function (file) { return file.period.id === e.id; });
  });
  var share = sweep ? shares.filter(function (e) { return e.id === sweep.period.id; })[0] : null;
  var top10 = sweep ? sweep.families.ranks.figures.top10.value : null;
  tiles.push(ASO.tile("Keys in top 30", ASO.figure(payload, "ranks.share_top30", share, "numerator"),
    share && !share.unavailable ? "of " + ASO.group(share.denominator) + " keys read · " + ASO.group(top10) + " in top 10 · sweep of " +
      ASO.esc(sweep.period.id) : "",
    ASO.spark(ASO.values(shares).map(function (e) { return e.value; }), "Share of keys in the top 30, sweep by sweep")));

  var downloads = ASO.series(payload, "store_funnel.first_downloads"), week = ASO.last(downloads);
  var seen = ASO.last(ASO.series(payload, "store_funnel.impressions")), rate = ASO.last(ASO.series(payload, "store_funnel.impression_cvr"));
  tiles.push(ASO.tile("First-time downloads", ASO.figure(payload, "store_funnel.first_downloads", week),
    week && typeof week.value === "number" && seen && typeof seen.value === "number" && rate && typeof rate.value === "number" ?
      ASO.group(seen.value) + " impressions · " + ASO.fmt(rate.value, "ratio") + " download · week of " + ASO.esc(week.id) : "",
    ASO.spark(ASO.values(downloads).map(function (e) { return e.value; }), "First-time downloads, week by week")));

  [["MRR", "subscriptions.mrr_usd"], ["Net cashflow", "money.net_cashflow_usd"],
   ["Deletions per 100 installs", "lifecycle.deletions_per_100"]].forEach(function (pair) {
    var entries = ASO.series(payload, pair[1]), entry = ASO.last(entries);
    tiles.push(ASO.tile(pair[0], ASO.figure(payload, pair[1], entry),
      entry && typeof entry.value === "number" ? ASO.esc((payload.catalog.families[ASO.split(pair[1])[0]].kind === "week" ?
        "week of " : "read on ") + entry.id) : "",
      ASO.spark(ASO.values(entries).map(function (e) { return e.value; }), pair[0] + " over time")));
  });
  return '<div class="tiles">' + tiles.join("") + "</div>";
};

ASO.dueList = function (payload, limit) {
  var due = payload.hypotheses.hypotheses.filter(function (h) { return h.state === "due"; })
    .sort(function (a, b) { return b.days_past_window - a.days_past_window || (a.id < b.id ? -1 : 1); });
  if (!due.length) { return "<p>Nothing is waiting for a verdict.</p>"; }
  return '<ul class="rows">' + due.slice(0, limit || due.length).map(function (h) {
    return '<li><span class="id">' + ASO.esc(h.id) + "</span> <span>" + ASO.esc(h.title) + '</span> <span class="meta">closed ' +
      h.days_past_window + " d ago</span></li>";
  }).join("") + "</ul>";
};

ASO.BANDS = [["top10", "Top 10"], ["top30", "11–30"], ["top100", "31–100"], ["top200", "101–200"]];

ASO.pages["#/"] = function (payload, today) {
  var counts = ASO.countStates(payload), sweep = ASO.last(ASO.fullSweeps(payload));
  var out = '<section class="strip"><h2 class="cap">Sources and their age · stale is older than ' + ASO.STALE_AFTER +
    " days</h2>" + ASO.sources(payload, today) + "</section>" + ASO.headlineTiles(payload);

  out += '<div class="blocks"><section class="block"><h2>Hypotheses</h2><p class="lead">' +
    (counts.due || 0) + " due · " + (counts.open || 0) + " open · " + (counts["not-shipped"] || 0) + " not shipped</p>" +
    ASO.dueList(payload, 5) + '<p><a href="#/ledger">Open the ledger</a></p></section>';

  out += '<section class="block"><h2>Keyword ranks</h2>';
  if (sweep) {
    var figures = sweep.families.ranks.figures;
    out += ASO.stack(ASO.BANDS.map(function (b) { return ["band-" + b[0], figures[b[0]].value, b[1]]; }),
      "Keys by rank band on " + sweep.period.id) + '<p class="lead">' + ASO.BANDS.map(function (b) {
      return ASO.group(figures[b[0]].value) + " " + ASO.esc(b[1]);
    }).join(" · ") + '</p><p class="meta">sweep of ' + ASO.esc(sweep.period.id) + " · " + ASO.group(figures.keys_read.value) +
      " of " + ASO.group(figures.tracked_keys.value) + " tracked keys read</p>";
  } else {
    out += "<p>" + ASO.missing("no_source") + "</p>";
  }
  out += '<p><a href="#/keywords">Open keywords</a></p></section>';

  out += '<section class="block"><h2>Store funnel</h2><dl class="pairs">' +
    [["Impressions", "store_funnel.impressions"], ["Product page views", "store_funnel.page_views"],
     ["First-time downloads", "store_funnel.first_downloads"], ["Downloads per page view", "store_funnel.page_cvr"]
    ].map(function (pair) {
      return "<dt>" + ASO.esc(pair[0]) + "</dt><dd>" + ASO.figure(payload, pair[1], ASO.last(ASO.series(payload, pair[1]))) + "</dd>";
    }).join("") + '</dl><p><a href="#/funnel">Open the store funnel</a></p></section>';

  out += '<section class="block"><h2>Ratings and reviews</h2><dl class="pairs">' +
    payload.places.overview.filter(function (key) { return key.indexOf("ratings.") === 0; }).map(function (key) {
      return "<dt>" + ASO.esc(ASO.spec(payload, key).title) + "</dt><dd>" + ASO.figure(payload, key, ASO.last(ASO.series(payload, key))) + "</dd>";
    }).join("") + "</dl></section>";

  var charts = ASO.listOf(payload, "charts", "rows");
  out += '<section class="block">\n<h2>Category charts</h2>' + (charts ? '<p class="meta">read on ' + ASO.esc(charts.family.fetched_at) + " " +
    ASO.age(charts.family.fetched_at, today) + '</p><ul class="rows two">' + charts.rows.map(function (r) {
      return '<li><span class="id">' + ASO.esc(r.market) + "</span> <span>" + ASO.esc(r.genre) + " " + ASO.esc(r.chart_type) + ' <span class="mono strong">' +
        (r.status === "ok" ? "#" + r.position : r.status === "error" ? "request failed" : "not in the chart") + "</span></span></li>";
    }).join("") + "</ul>" : ASO.gapNote({ code: "no_source", reason: "No data file holds a reading of it." })) + "</section></div>";
  return out;
};
