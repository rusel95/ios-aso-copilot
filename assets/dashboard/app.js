"use strict";
var ASO = {};
ASO.start = function () {
  var payload = JSON.parse(document.getElementById("payload").textContent);
  document.getElementById("app-name").textContent = payload.name;
  document.title = "ASO Copilot · " + payload.name;
};
if (typeof document !== "undefined") { ASO.start(); }
