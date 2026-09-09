#!/usr/bin/env node
/**
 * ios-aso-copilot CLI
 * Installs the skill into ~/.claude/skills/, ~/.kiro/skills/, or custom path
 *
 * Usage:
 *   npx ios-aso-copilot install          # install to ~/.claude/skills/
 *   npx ios-aso-copilot install --kiro   # install to ~/.kiro/skills/
 *   npx ios-aso-copilot install --path /custom/path
 */
const fs   = require("fs");
const path = require("path");
const os   = require("os");

const SKILL_NAME = "ios-aso-copilot";
const SKILL_DIR  = path.resolve(__dirname, "..");

const args = process.argv.slice(2);
const cmd  = args[0];

if (cmd === "install") {
  const useKiro   = args.includes("--kiro");
  const pathIdx   = args.indexOf("--path");
  const customPath = pathIdx !== -1 ? args[pathIdx + 1] : null;

  const base = customPath
    ? customPath
    : useKiro
      ? path.join(os.homedir(), ".kiro", "skills")
      : path.join(os.homedir(), ".claude", "skills");

  const target = path.join(base, SKILL_NAME);

  fs.mkdirSync(base, { recursive: true });

  if (fs.existsSync(target)) {
    const stat = fs.lstatSync(target);
    if (stat.isSymbolicLink()) {
      fs.unlinkSync(target);
      console.log(`Removed existing symlink at ${target}`);
    } else {
      console.error(`Error: ${target} exists and is not a symlink. Remove it manually first.`);
      process.exit(1);
    }
  }

  fs.symlinkSync(SKILL_DIR, target);
  console.log(`✓ ios-aso-copilot installed → ${target}`);
  console.log(`  Symlink points to: ${SKILL_DIR}`);
  console.log(`\nUsage in Claude Code / Kiro: /ios-aso-copilot`);

} else if (cmd === "uninstall") {
  const targets = [
    path.join(os.homedir(), ".claude", "skills", SKILL_NAME),
    path.join(os.homedir(), ".kiro",   "skills", SKILL_NAME),
    path.join(os.homedir(), ".claude", "skills", "ios-marketing-ops"),
    path.join(os.homedir(), ".kiro",   "skills", "ios-marketing-ops"),
  ];
  let removed = 0;
  for (const t of targets) {
    if (fs.existsSync(t) && fs.lstatSync(t).isSymbolicLink()) {
      fs.unlinkSync(t);
      console.log(`✓ Removed ${t}`);
      removed++;
    }
  }
  if (!removed) console.log("Nothing to uninstall.");

} else {
  console.log(`ios-aso-copilot v${require("../package.json").version}`);
  console.log("App Store Optimization (ASO) & Growth AI Copilot for Claude/Kiro/Antigravity/Cursor\n");
  console.log("Commands:");
  console.log("  npx ios-aso-copilot install          Install to ~/.claude/skills/");
  console.log("  npx ios-aso-copilot install --kiro   Install to ~/.kiro/skills/");
  console.log("  npx ios-aso-copilot install --path P Install to custom path");
  console.log("  npx ios-aso-copilot uninstall        Remove symlinks");
}
