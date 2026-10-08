# Physical Kitty verification

Use a real keyboard in a direct Kitty window. Record Ubuntu/Kitty/Codex versions,
keyboard layout, and any remote transport. Do not label tmux, another terminal,
or SSH verified based on this test.

1. Run `python3 scripts/kitty-keycheck.py --report .build/kitty-keycheck.json` in
   Kitty. Tap Enter, hold it until it repeats, and release it. The report must
   confirm both required keyboard flags, press/repeat/release events, and the
   held interval. This check sends no model request.
2. Run the built `bin/chargesend` in Kitty. In an idle prompt, hold Enter while
   observing the label and bar through the peak and descending cycle. Release
   at Low, Medium, and the model's permitted top tier. Check that each prompt
   submits once at the displayed effort.
3. Charge then press Escape while still holding Enter. Release and confirm the
   draft and image remain. Repeat with focus loss, thread/model/mode changes,
   an approval or other overlay, and an external-editor transition. Held repeats
   and late releases must not submit a new draft or activate a popup.
4. Check Shift-Enter and configured newline shortcuts, multiline drafts, bracketed
   paste and rapid paste bursts, image paste/file attachments, completion popups,
   slash commands, and non-US/dead-key/IME text entry.
5. While a turn runs, verify normal steering and queuing. Confirm that holding
   Enter does not offer a charge or claim to change the current turn's effort.
6. Check Plan mode: charge a prompt at a different effort than its configured
   default, then submit normally. The charged request uses the selected effort;
   the next request uses its intended Plan setting. Confirm config.toml was not
   written by the charge selection.
7. Resize to narrow and short terminal dimensions while charging. Keep the
   displayed effort legible within the composer and the draft intact.
8. Exit, suspend/resume, and launch a fresh shell. Confirm normal key reporting
   is restored. In a fallback terminal or with `CHARGESEND_DISABLE=1`, confirm
   the unavailable notice and ordinary Enter submission.

Use the automated mock-backend tests to inspect settings without paid inference.
For live physical UI submissions, use short prompts and your normal account;
the keycheck alone cannot verify request settings or composer routing.

Step 1 passed with a physical keyboard in Kitty 0.45.0 on Ubuntu 26.04; see
[kitty-0.45.0-enter.json](kitty-0.45.0-enter.json). The user also verified bar
ascent/descent and Escape cancellation followed by Enter release in the compiled
0.161.0 UI using `--no-daemon`; the draft remained and no prompt was submitted.
[kitty-0.45.0-ui.json](kitty-0.45.0-ui.json) records that build's identity.
Physical submissions, attachment cancellation, other transitions, and the
remaining checks in steps 2–8 are outstanding.
