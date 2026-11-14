// Evaluate one expression against the built page, with no browser: node tests/page_smoke.js <index.html> "<expression>"
// In scope: ASO (the page's script, loaded with `document` undefined) and payload (the page's data).
// Prints the result: a string as it is, anything else as JSON.
"use strict";
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const data = /<script id="payload" type="application\/json">([\s\S]*?)<\/script>/.exec(html)[1];
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
const source = scripts[scripts.length - 1][1];
const ASO = new Function(source + "\n;return ASO;")();
const payload = JSON.parse(data);
const result = new Function("ASO", "payload", "return (" + process.argv[3] + ");")(ASO, payload);
process.stdout.write(typeof result === "string" ? result : JSON.stringify(result));
