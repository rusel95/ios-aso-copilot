// Store funnel, Money, Apple Ads, In-app, How data gets here. Each family is drawn from whatever periods hold it,
// so a tab fills in by itself the day its series is stored; until then it says why it is empty.

// Why a family has no reading anywhere: the newest reason its files give, or that no file holds it. Null when read.
ASO.familyGap = function (payload, family) {
  var newest = null, read = false;
  ASO.periods(payload, family).forEach(function (file) {
    var found = file.families[family];
    if (!found) { return; }
    if (found.unavailable) { newest = found.unavailable; } else { read = true; }
  });
  return read ? null : newest || { code: "no_source", reason: "No data file holds a reading of it." };
};

ASO.gapNote = function (gap) {
  return '<p class="note"><span class="missing">' + ASO.esc(ASO.MISSING[gap.code]) + "</span> " + ASO.esc(gap.reason) + "</p>";
};

ASO.readFiles = function (payload, family) {
  return ASO.periods(payload, family).filter(function (file) { return file.families[family] && !file.families[family].unavailable; });
};

// One row per period that holds the family, newest first; one column per figure.
ASO.periodTable = function (payload, family, names, limit) {
  var files = ASO.readFiles(payload, family).slice().reverse().slice(0, limit || 26), week = payload.catalog.families[family].kind === "week";
  var cells = {};
  names.forEach(function (name) {
    ASO.series(payload, family + "." + name).forEach(function (e) { (cells[e.id] = cells[e.id] || {})[name] = e; });
  });
  return '<div class="scroll"><table class="grid-table"><thead><tr><th>' + (week ? "Week of" : "Read on") + "</th>" + names.map(function (name) {
    return "<th>" + ASO.esc(ASO.spec(payload, family + "." + name).title) + "</th>";
  }).join("") + "</tr></thead><tbody>" + files.map(function (file) {
    return '<tr class="period"><td>' + ASO.esc(file.period.id) + "</td>" + names.map(function (name) {
      return "<td>" + ASO.figure(payload, family + "." + name, (cells[file.period.id] || {})[name]) + "</td>";
    }).join("") + "</tr>";
  }).join("") + "</tbody></table></div>";
};

// The newest period's figures split by storefront (or campaign), largest first by the first figure.
ASO.splitTable = function (payload, family, names, by) {
  var file = ASO.last(ASO.readFiles(payload, family));
  if (!file) { return ""; }
  var figures = file.families[family].figures, lead = (figures[names[0]] || {})[by] || {};
  var who = Object.keys(lead).sort(function (a, b) { return (lead[b] || 0) - (lead[a] || 0) || (a < b ? -1 : 1); });
  if (!who.length) { return '<p class="meta">The data holds no split for ' + ASO.esc(file.period.id) + ".</p>"; }
  return '<p class="meta">' + (payload.catalog.families[family].kind === "week" ? "week of " : "read on ") + ASO.esc(file.period.id) +
    '</p><div class="scroll"><table class="grid-table"><thead><tr><th>' + (by === "by_market" ? "Mkt" : "Campaign") + "</th>" + names.map(function (name) {
      return "<th>" + ASO.esc(ASO.spec(payload, family + "." + name).title) + "</th>";
    }).join("") + "</tr></thead><tbody>" + who.map(function (one) {
      return '<tr class="split-row"><td class="id">' + ASO.esc(one) + "</td>" + names.map(function (name) {
        var value = ((figures[name] || {})[by] || {})[one];
        return "<td>" + (typeof value === "number" ? ASO.esc(ASO.fmt(value, ASO.spec(payload, family + "." + name).unit)) : "–") + "</td>";
      }).join("") + "</tr>";
    }).join("") + "</tbody></table></div>";
};

// The latest reading of each figure of a family, as pairs.
ASO.latestPairs = function (payload, family, names) {
  return '<dl class="pairs">' + names.map(function (name) {
    var key = family + "." + name;
    return "<dt>" + ASO.esc(ASO.spec(payload, key).title) + "</dt><dd>" + ASO.figure(payload, key, ASO.last(ASO.series(payload, key))) + "</dd>";
  }).join("") + "</dl>";
};

ASO.familyBlock = function (payload, today, title, family, body) {
  var gap = ASO.familyGap(payload, family), day = ASO.fetched(payload, family);
  return '<section class="block">\n<h2>' + ASO.esc(title) + "</h2>" + (gap ? ASO.gapNote(gap) :
    '<p class="meta">fetched ' + ASO.esc(day) + " " + ASO.age(day, today) + "</p>" + body()) + "</section>";
};

ASO.FUNNEL = ["impressions", "page_views", "first_downloads", "view_rate", "page_cvr", "impression_cvr"];
ASO.LIFECYCLE = ["optin_installs", "optin_deletions", "deleted_within_1d", "deletions_per_100"];
ASO.MONEY = ["proceeds_usd", "ad_spend_usd", "net_cashflow_usd", "transactions", "new_trials"];
ASO.SUBSCRIPTIONS = ["active_subscriptions", "active_trials", "mrr_usd", "revenue_28d_usd", "new_customers_28d", "active_users_28d"];
ASO.ADS = ["spend_usd", "impressions", "taps", "installs", "ttr", "cpi_usd"];

ASO.pages["#/funnel"] = function (payload, today) {
  return '<h1 class="page">Store funnel</h1><p class="meta">Only closed weeks are shown. The week in progress appears the Monday after it ends.</p>' +
    ASO.familyBlock(payload, today, "Closed weeks", "store_funnel", function () { return ASO.periodTable(payload, "store_funnel", ASO.FUNNEL); }) +
    ASO.familyBlock(payload, today, "By storefront", "store_funnel", function () { return ASO.splitTable(payload, "store_funnel", ASO.FUNNEL, "by_market"); }) +
    ASO.familyBlock(payload, today, "Install lifecycle", "lifecycle", function () {
      return ASO.periodTable(payload, "lifecycle", ASO.LIFECYCLE) + ASO.splitTable(payload, "lifecycle", ASO.LIFECYCLE, "by_market");
    });
};

ASO.pages["#/money"] = function (payload, today) {
  return '<h1 class="page">Money</h1><p class="meta">What was read, never a forecast.</p>' +
    ASO.familyBlock(payload, today, "Subscriptions", "subscriptions", function () {
      return ASO.latestPairs(payload, "subscriptions", ASO.SUBSCRIPTIONS) + ASO.periodTable(payload, "subscriptions", ASO.SUBSCRIPTIONS);
    }) +
    ASO.familyBlock(payload, today, "Money by closed week", "money", function () {
      return ASO.periodTable(payload, "money", ASO.MONEY) + ASO.splitTable(payload, "money", ASO.MONEY, "by_market");
    });
};

// The newest snapshot that holds one of a family's row lists.
ASO.listOf = function (payload, family, name) {
  var file = ASO.last(payload.snapshots.filter(function (f) { return f.families[family] && f.families[family][name]; }));
  return file ? { rows: file.families[family][name], family: file.families[family] } : null;
};

ASO.measured = function (family) {
  return '<p class="meta">' + (family.measured ? "measured " + ASO.esc(family.measured.start) + " → " + ASO.esc(family.measured.end) + " · " : "") +
    "captured " + ASO.esc(family.fetched_at) + "</p>";
};

ASO.pages["#/ads"] = function (payload, today) {
  var out = '<h1 class="page">Apple Ads</h1>' + ASO.familyBlock(payload, today, "Apple Ads by closed week", "ads", function () {
    return ASO.periodTable(payload, "ads", ASO.ADS) + ASO.splitTable(payload, "ads", ASO.ADS, "by_campaign");
  });
  var share = ASO.listOf(payload, "impression_share", "rows");
  out += '<div class="blocks"><section class="block">\n<h2>Impression share</h2>' + (share ? ASO.measured(share.family) + '<ul class="next range">' +
    share.rows.map(function (r) {
      return '<li><span class="id">' + ASO.esc(r.market) + "</span> <span>" + ASO.esc(r.term) + '</span> <span class="mono">#' + r.rank +
        '</span> <span class="mono strong">' + ASO.fmt(r.share_low, "ratio") + (r.share_high !== r.share_low ? "–" + ASO.fmt(r.share_high, "ratio") : "") + "</span></li>";
    }).join("") + "</ul>" : ASO.gapNote({ code: "no_source", reason: "No data file holds a reading of it." })) + "</section>";

  var heads = ASO.listOf(payload, "demand", "rows"), cuts = ASO.listOf(payload, "demand", "cuts");
  out += '<section class="block">\n<h2>Apple search popularity</h2>';
  if (!heads && !cuts) {
    out += ASO.gapNote({ code: "no_source", reason: "No data file holds a reading of it." });
  } else {
    out += ASO.measured((heads || cuts).family) + '<ul class="next three">' + (heads ? heads.rows : []).slice().sort(function (a, b) {
      return b.popularity_100 - a.popularity_100 || (a.term < b.term ? -1 : 1);
    }).map(function (r) {
      // every week the data holds a score for this term, oldest first: drawn, not summed
      var weeks = payload.snapshots.map(function (file) {
        var rows = file.families.demand && file.families.demand.rows || [];
        return rows.filter(function (x) { return x.market === r.market && x.genre === r.genre && x.term === r.term; })[0];
      }).filter(Boolean).map(function (x) { return x.popularity_100; });
      return '<li><span class="id">' + ASO.esc(r.market) + '</span> <span class="meta">' + ASO.esc(r.genre) + "</span> <span>" + ASO.esc(r.term) +
        '</span> <span class="mono strong">' + r.popularity_100 + "</span>" +
        ASO.spark(weeks, r.term + " in " + r.market + ": Apple search popularity over " + weeks.length + " weeks") + "</li>";
    }).join("") + '</ul><p class="cap">What Apple lists per storefront</p><ul class="rows two">' + (cuts ? cuts.rows : []).map(function (r) {
      return '<li><span class="id">' + ASO.esc(r.market) + "</span> <span>" + (r.listed ? ASO.esc(r.genre) + " " + ASO.group(r.listed) +
        " terms listed, lowest score " + (r.min_popularity_100 === null ? "unknown" : r.min_popularity_100) : "Apple lists nothing here") + "</span></li>";
    }).join("") + '</ul><p class="meta">A tracked term that is not listed is below the lowest score listed: volume unknown, not zero.</p>';
  }
  return out + "</section></div>";
};

ASO.pages["#/in-app"] = function (payload, today) {
  var gap = ASO.familyGap(payload, "in_app");
  if (gap) { return '<h1 class="page">In-app</h1><section class="block">\n<h2>In-app</h2>' + ASO.gapNote(gap) + "</section>"; }
  var files = ASO.readFiles(payload, "in_app").slice().reverse().slice(0, 8), sections = {};
  files.forEach(function (file) {
    Object.keys(file.families.in_app.figures || {}).forEach(function (key) {
      var section = key.slice(0, key.indexOf("."));
      (sections[section] = sections[section] || {})[key] = true;
    });
  });
  var day = ASO.fetched(payload, "in_app");
  return '<h1 class="page">In-app</h1><p class="meta">What the app\'s own events say, by closed week · fetched ' + ASO.esc(day) + " " + ASO.age(day, today) +
    "</p>" + Object.keys(sections).sort().map(function (section) {
      return '<section class="block">\n<h2>' + ASO.esc(section) + '</h2><div class="scroll"><table class="grid-table"><thead><tr><th>Metric</th>' +
        files.map(function (file) { return "<th>" + ASO.esc(file.period.id) + "</th>"; }).join("") + "</tr></thead><tbody>" +
        Object.keys(sections[section]).sort().map(function (key) {
          var cells = {};
          ASO.series(payload, "in_app." + key).forEach(function (e) { cells[e.id] = e; });
          return "<tr><td>" + ASO.esc(key.slice(section.length + 1).replace(/[._]/g, " ")) + "</td>" + files.map(function (file) {
            return "<td>" + (cells[file.period.id] ? ASO.figure(payload, "in_app." + key, cells[file.period.id]) : "–") + "</td>";
          }).join("") + "</tr>";
        }).join("") + "</tbody></table></div></section>";
    }).join("");
};

ASO.pages["#/how"] = function (payload) {
  var codes = Object.keys(ASO.MISSING).map(function (code) {
    return "<dt>" + ASO.missing(code) + '</dt><dd><span class="mono">' + code + "</span> · " + ASO.esc({
      no_source: "nothing stores this figure yet", no_data: "the source answered and had nothing to count",
      not_configured: "the store's config lacks what the collector needs", unreachable: "the request failed"
    }[code]) + "</dd>";
  }).join("");
  return '<h1 class="page">How data gets here</h1><div class="blocks"><section class="block">\n<h2>Three steps</h2><dl class="terms">' +
    "<dt>Collect</dt><dd>Commands read App Store Connect, the search API, the subscription provider and the app's own events, and append what they " +
    "read to the store. This is the only step that touches the network.</dd>" +
    "<dt>Export</dt><dd>One command derives the data files from the store for a given day. It reads no network and no clock: the same store and " +
    "the same day give the same bytes.</dd>" +
    "<dt>Build</dt><dd>One command checks every data file against the contract and builds this page from them, and from nothing else.</dd></dl></section>" +
    '<section class="block">\n<h2>How to read a figure</h2><dl class="terms"><dt>Measured</dt><dd>A value read from a source. Open it to see its ' +
    "definition, its source and the day it was fetched.</dd><dt>Approximation</dt><dd>Marked ≈. It stands in for something that cannot be measured " +
    'directly; its panel says how.</dd><dt>Missing</dt><dd>Words on a hatched mark, never a zero. A measured zero reads 0.</dd></dl><dl class="terms">' +
    codes + '</dl></section><section class="block">\n<h2>Rules the page keeps</h2><ul class="plain"><li>Every figure comes from a data file; the page ' +
    "computes none.</li><li>Only closed weeks are shown.</li><li>A rank sweep that read under half of the tracked keys is left out of trends.</li>" +
    "<li>A source older than " + ASO.STALE_AFTER + " days is marked stale, by the reader's clock.</li><li>The page writes no verdict and no forecast.</li>" +
    '</ul><p class="meta">Data as of ' + ASO.esc(payload.hypotheses.as_of) + ".</p></section></div>";
};
