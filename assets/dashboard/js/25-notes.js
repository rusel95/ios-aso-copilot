// Notes: what the store's own prose says, as written. The newest entries of decisions.md and the latest cycle report.
// The page adds nothing to them and judges nothing; every character of them goes through ASO.esc.
ASO.decisionList = function (decisions) {
  if (!decisions.length) { return "<p>decisions.md holds no entry dated on or before the day exported.</p>"; }
  return decisions.map(function (d) {
    return '<article class="entry"><h3><span class="mono">' + ASO.esc(d.date) + "</span> " + ASO.esc(d.title) + '</h3><div class="prose">' +
      ASO.prose(d.text) + "</div>" + (d.truncated ? '<p class="meta">Cut here; the rest is in decisions.md.</p>' : "") + "</article>";
  }).join("");
};

ASO.reportBlock = function (report) {
  if (!report) {
    return "<p>No cycle report yet. The page shows the newest <span class=\"mono\">reports/*cycle*.md</span> of the store, by the day in its name.</p>";
  }
  return '<details><summary><span class="mono">' + ASO.esc(report.name) + "</span> · " + ASO.esc(report.date) + " · " +
    ASO.group(report.text.length) + ' characters</summary><pre class="report">' + ASO.esc(report.text) + "</pre>" +
    (report.truncated ? '<p class="meta">Cut here; the rest is in the file.</p>' : "") + "</details>";
};

ASO.pages["#/notes"] = function (payload) {
  var notes = payload.notes;
  return '<h1 class="page">Notes</h1><p class="meta">What the store\'s own files say, as written there · data as of ' +
    ASO.esc(notes.as_of) + '</p><section class="block">\n<h2>Decisions, newest first</h2>' + ASO.decisionList(notes.decisions) +
    '</section><section class="block">\n<h2>Latest cycle report</h2>' + ASO.reportBlock(notes.report) + "</section>";
};
