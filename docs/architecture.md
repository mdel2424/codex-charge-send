# Patch boundaries

`module/chargesend/controller.rs` owns the monotonic timer (default-to-peak first, then a Low–Max triangle wave),
last-painted effort, and matching-key latch. It accepts eligible context/effort
choices plus the resolved starting effort and produces Pass, Consume, or Submit. It does not know Codex models,
terminal I/O, backend operations, or configuration. It has standalone Rust tests.

`module/chargesend/capability.rs` requires both Enter-release flag bits and a
successful request for direct Kitty. The existing keyboard stack push/pop/reset
still owns terminal setup and teardown. The existing startup probe confirms
active flags before the asynchronous event reader starts. A timeout leaves the
feature unavailable. No second reader competes for stdin.

`module/chatwidget_chargesend.rs` supplies the active thread/model/mode/draft and
advertised, permitted efforts. It intercepts eligible plain Enter before normal
dispatch, handles release once, and schedules draws through FrameRequester. A
synthetic ordinary Enter reuses composer validation, paste expansion, mention
resolution, and attachment draining. The bar occupies the existing measured
composer footer. `module/chargesend/bar.rs` renders styled spans with a
green–yellow–red gradient and a label colored by charge position.
`CHARGESEND_DEFAULT_EFFORT` defaults to xhigh; the model-specific starting
tier is resolved before charging. Tap and every new press use that tier.
The charge bar pads the effort name to a fixed ten-character field.

`module/chargesend/status.rs` appends the active turn's reasoning label directly
after the Working timer/interrupt controls, before optional background activity.
The working controls remain left-aligned. Background activity truncates after
the label and hook activity can overflow to its usual details row. When the
core controls and label cannot fit together, the label hides without adding a
row. Accepted new submissions capture their effective request effort; busy
steering and queueing leave the active value unchanged. Turn start restores
the label after status-row recreation, and completion/finalization clears it
before the next queued submission. Restored turns fall back to thread effort.

`module/app_chargesend.rs` invalidates charging before overlays and transitions
can take ownership. Its key latch outlives widget replacement, so a held key from
an old thread cannot submit a new thread's draft. Other release events are
filtered before active menus and popups so reporting all keys does not activate
an action twice. Focus loss, paste, mouse activity, resume, and app events cancel
an active charge conservatively.

## Submission settings

A PromptEffort envelope contains the originating thread, original collaboration
mode, and selected effort. It follows normal submission and asynchronous image
preparation without changing UserMessage or persisting settings. A delayed
submission is revalidated; an invalid envelope restores the draft/images.

For a charged turn, the request's effort and collaboration-mode effort are set
to the same value. This prevents a Plan-mode mask from overriding the charge.
Subsequent submissions carry an explicit intended effort after the first charge.
There is no immediate standalone thread-settings reset: upstream treats that
operation as a manual settings change and cancels automatic continuations.
If the intended effort is unset, the active model's advertised default is used
for the request.

The backend's saved thread effort can remain at the last charged value until the
next submission. The current widget retains its intended defaults and makes the
next request explicit. Restart/resume and multiple-client synchronization still
need physical/end-to-end verification; the patch never writes config.toml.

The backend can echo request settings as thread settings. A bounded queue
recognizes complete mode/model/effort echoes from accepted ChargeSend requests
and keeps the local intended defaults intact. Unrecognized updates follow the
existing upstream synchronization path. Those notifications have no request ID:
an identical external settings update could be indistinguishable from an expected
echo. Multi-client settings synchronization requires further testing.

## Scope

Charging starts only in an idle, focused composer with content, no active popup,
and no pending paste/newline suppression. Slash commands and shell escapes,
busy steering/queuing, pending image submissions, realtime, input blocking,
queued follow-ups, and recovery states keep their normal input behavior.
The personal-use charge range includes Max whenever the active model advertises
it, without requiring Max as the default. Ultra is excluded even when selected
in settings. Unsupported tiers are never added to the model's advertised choices.

The patch adds narrow hooks in terminal setup/probing, composer/footer, widget
construction/input/settings/image submission, and app transitions/draws. The
event stream already preserves press/repeat/release events and needs no rewrite.
`patches/chargesend.patch` contains these hooks; `overlays.json` places the modules.
