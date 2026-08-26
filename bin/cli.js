#!/usr/bin/env node
/**
 * ios-marketing-ops CLI
 * Installs the skill into ~/.claude/skills/ or ~/.kiro/skills/
 *
 * Usage:
 *   npx ios-marketing-ops install          # install to ~/.claude/skills/
 *   npx ios-marketing-ops install --kiro   # install to ~/.kiro/skills/
 *   npx ios-marketing-ops install --path /custom/path
 */
const fs   = require("fs");
const path = require("path");
const os   = require("os");

const SKILL_NAME = "ios-marketing-ops";
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
  console.log(`✓ ios-marketing-ops installed → ${target}`);
  console.log(`  Symlink points to: ${SKILL_DIR}`);
  console.log(`\nUsage in Claude Code / Kiro: /ios-marketing-ops`);

} else if (cmd === "uninstall") {
  const targets = [
    path.join(os.homedir(), ".claude", "skills", SKILL_NAME),
    path.join(os.homedir(), ".kiro",   "skills", SKILL_NAME),
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
  console.log(`ios-marketing-ops v${require("../package.json").version}`);
  console.log("App Store marketing operations skill for Claude/Kiro\n");
  console.log("Commands:");
  console.log("  npx ios-marketing-ops install          Install to ~/.claude/skills/");
  console.log("  npx ios-marketing-ops install --kiro   Install to ~/.kiro/skills/");
  console.log("  npx ios-marketing-ops install --path P Install to custom path");
  console.log("  npx ios-marketing-ops uninstall        Remove symlinks");
}
