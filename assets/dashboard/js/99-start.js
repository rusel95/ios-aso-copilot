// The only part that touches the page: reads the data, draws the route, opens the panel behind a figure.
ASO.start = function () {
  var payload = JSON.parse(document.getElementById("payload").textContent);
  var main = document.getElementById("app"), dialog = document.getElementById("figure");

  function today() {
    var now = new Date(), two = function (n) { return (n < 10 ? "0" : "") + n; };
    return now.getFullYear() + "-" + two(now.getMonth() + 1) + "-" + two(now.getDate());
  }

  function show() {
    document.getElementById("tabs").innerHTML = ASO.nav(location.hash);
    main.innerHTML = ASO.render(location.hash, payload, today());
    // a filter on the ledger's list keeps the reader at the list
    var list = document.getElementById("all-hypotheses");
    if (location.hash.indexOf("?") > 0 && list) { list.scrollIntoView(); } else { window.scrollTo(0, 0); }
  }

  document.getElementById("app-name").textContent = payload.name;
  document.getElementById("as-of").textContent = "data as of " + payload.hypotheses.as_of;
  document.title = "ASO Copilot · " + payload.name;

  main.addEventListener("click", function (event) {
    var card = event.target.closest("[data-hyp]"), button = event.target.closest("[data-fig]");
    if (card) {
      dialog.className = "wide";
      dialog.innerHTML = ASO.hypCard(payload, card.getAttribute("data-hyp"), today());
      dialog.showModal();
      dialog.scrollTop = 0;       // showModal focuses the Close button at the foot of a long card
    } else if (button) {
      dialog.className = "";
      dialog.innerHTML = ASO.panel(payload, button.getAttribute("data-fig"), button.getAttribute("data-period"));
      dialog.showModal();
    }
  });
  dialog.addEventListener("click", function (event) {
    if (event.target === dialog || event.target.hasAttribute("data-close")) { dialog.close(); }
  });
  window.addEventListener("hashchange", show);
  show();
};

if (typeof document !== "undefined") { ASO.start(); }
