# Preparing the independent GitHub project

Use repository name **chargesend** and describe it as an unofficial community
modification of Codex CLI. Include the patch files, `module/`, scripts, tests,
release catalog, overlays, README, docs, LICENSE, NOTICE, UPSTREAM-NOTICE, and
`.github/workflows/ci.yml`. Keep `.build/`, local installs, and native bundles out
of Git; `.gitignore` covers them.

Review `docs/verification.md` before a first release. Preserve pending manual
limitations and do not call a new terminal or transport verified based only on
protocol support. The native bundle's manifest identifies its baseline and
build inputs; distribute notices with every binary.

The project files and GitHub Actions workflow are prepared locally. This workflow
does not create a GitHub repository, configure a remote, push, or publish a
release. Those are separate actions after reviewing the local result. No external
upstream pull request is needed to distribute ChargeSend independently.
