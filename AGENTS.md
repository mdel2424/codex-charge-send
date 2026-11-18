# ChargeSend repository

For a request to update, port, build, or troubleshoot a ChargeSend release, read
[the ChargeSend update skill](skills/chargesend-update/SKILL.md) and use its
pipeline. It records the release pin, keeps one editable checkout, checks lint
before full compilation, and resumes checks whose inputs still match.

Keep existing user edits and installed binaries intact while preparing a port.
Do not discard a development checkout to get past the prepared-source guard;
the pipeline proves it matches a fresh application of the exported patches.

## UI design preferences

Automatically use the `design-taste-frontend` skill whenever designing, building,
redesigning, restyling, polishing, or reviewing frontend UI, including websites,
web apps, dashboards, and individual components. The user does not need to
explicitly invoke the skill.

Read `/home/mdel2424/.codex/skills/design-taste-frontend/SKILL.md` before beginning
relevant UI work and apply its guidance within the task's scope. Preserve
existing project conventions and design systems, and prioritize the user's
explicit requirements when they differ from the skill's defaults. Use other
applicable skills alongside it when needed.
