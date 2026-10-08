// Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
//! Upstream-specific ChargeSend glue. No config setters or persistence calls.
//!
//! Charging belongs to this widget, not the terminal reader or a backend turn.
//! Eligible Enter presses are intercepted before normal input dispatch; release
//! reuses the composer and submission path with a prompt-local settings envelope.

use super::*;
use crate::chargesend::Controller;
use crate::chargesend::Input;
use crate::chargesend::Outcome;
use std::collections::VecDeque;

#[derive(Clone, Debug, PartialEq, Eq)]
struct Context {
    thread: ThreadId,
    mode: CollaborationMode,
    draft: String,
}

/// Retained across asynchronous image preparation, never in config.toml.
#[derive(Clone, Debug)]
pub(super) struct PromptEffort {
    thread: ThreadId,
    pub(super) mode: CollaborationMode,
    pub(super) effort: ReasoningEffortConfig,
}

#[derive(Clone, Debug)]
struct ExpectedSettings {
    sent: CollaborationMode,
}

pub(super) struct ChargeSend {
    controller: Controller<Context, ReasoningEffortConfig>,
    pub(super) terminal_available: bool,
    announced: bool,
    pub(super) has_charged: bool,
    echoes: VecDeque<ExpectedSettings>,
}

impl Default for ChargeSend {
    fn default() -> Self {
        Self {
            controller: Controller::new(crate::chargesend::timing_from_env()),
            terminal_available: crate::chargesend::capability::available(),
            // Existing upstream fixtures should not gain environment-specific
            // history. ChargeSend tests explicitly enable the notice when needed.
            announced: cfg!(test),
            has_charged: false,
            echoes: VecDeque::new(),
        }
    }
}

impl ChatWidget {
    fn chargesend_choices(&self) -> Vec<ReasoningEffortConfig> {
        let Some(preset) = self.current_model_preset() else {
            return Vec::new();
        };
        let explicit = self.effective_reasoning_effort();
        let mut choices = Vec::new();
        for option in preset.supported_reasoning_efforts {
            // Only the advanced tier already explicitly selected in the active
            // settings is opted in. Never infer opt-in from a model default.
            if (!Self::is_advanced_reasoning_effort(&option.effort)
                || explicit.as_ref() == Some(&option.effort))
                && !choices.contains(&option.effort)
            {
                choices.push(option.effort);
            }
        }
        choices
    }

    fn chargesend_context(&self) -> Option<(Context, Vec<ReasoningEffortConfig>)> {
        if !self.chargesend.terminal_available
            || self.blocks_direct_input
            || self.fork_in_progress
            || self.is_user_turn_pending_or_running()
            || self.only_user_shell_commands_running()
            || self.is_plan_streaming_in_tui()
            || self.input_queue.startup_submission.is_some()
            || self.pending_image_submission.is_some()
            || self.input_queue.suppress_queue_autosend
            || self.input_queue.recovered_queue
            || self.input_queue.rate_limit_recovery_pending
            || self.input_queue.has_queued_follow_up_messages()
            || self.has_misalignment_policy_violation()
            || self.realtime_conversation_is_running()
            || !self.bottom_pane.chargesend_eligible()
        {
            return None;
        }
        let choices = self.chargesend_choices();
        if choices.is_empty() {
            return None;
        }
        Some((
            Context {
                thread: self.thread_id?,
                mode: self.effective_collaboration_mode(),
                draft: self.bottom_pane.composer_text(),
            },
            choices,
        ))
    }

    pub(crate) fn cancel_chargesend(&mut self) {
        self.chargesend.controller.cancel();
        self.bottom_pane.set_chargesend_status(None);
    }

    pub(crate) fn chargesend_enter_down(&self) -> bool {
        self.chargesend.controller.enter_down()
    }

    pub(crate) fn chargesend_active(&self) -> bool {
        self.chargesend.controller.active()
    }

    /// Called immediately before drawing, through the existing redraw scheduler.
    pub(crate) fn paint_chargesend(&mut self) {
        if !self.chargesend.announced {
            self.chargesend.announced = true;
            if !self.chargesend.terminal_available {
                self.add_info_message(
                    "ChargeSend: hold-to-charge unavailable. Requires direct Kitty with verified Enter releases; Enter sends normally.".to_string(),
                    None,
                );
            }
        }
        let context = self.chargesend_context();
        self.chargesend.controller.validate(context.as_ref());
        let now = tokio::time::Instant::now().into_std();
        let status = self.chargesend.controller.paint(now).map(|snapshot| {
            let filled = usize::from(snapshot.permille) * 12 / 1000;
            let direction = if snapshot.descending { "v" } else { "^" };
            format!(
                "{} [{}{}] {direction} · release Enter to send · Esc cancels",
                Self::reasoning_effort_label(&snapshot.effort),
                "=".repeat(filled),
                "-".repeat(12 - filled),
            )
        });
        self.bottom_pane.set_chargesend_status(status);
        if self.chargesend.controller.active() {
            self.frame_requester
                .schedule_frame_in(self.chargesend.controller.frame_interval());
        }
    }

    pub(crate) fn handle_chargesend_key(&mut self, key: KeyEvent) -> bool {
        // Native paste classification runs first. An Enter in a paste burst
        // retains upstream's newline behavior, including its suppression window.
        self.bottom_pane.flush_paste_burst_if_due();
        let input = match (key.code, key.kind) {
            (KeyCode::Enter, KeyEventKind::Release) => Input::EnterRelease,
            (KeyCode::Enter, KeyEventKind::Repeat)
                if key.modifiers.is_empty() || self.chargesend.controller.enter_down() =>
            {
                Input::EnterRepeat
            }
            (KeyCode::Enter, KeyEventKind::Press) if key.modifiers.is_empty() => Input::EnterPress,
            (KeyCode::Esc, KeyEventKind::Press) if key.modifiers.is_empty() => Input::Escape,
            (_, KeyEventKind::Release) => Input::OtherRelease,
            _ => Input::OtherPress,
        };
        let context = self.chargesend_context();
        let outcome = self.chargesend.controller.handle(
            input,
            context,
            tokio::time::Instant::now().into_std(),
        );
        match outcome {
            Outcome::Pass => {
                if !self.chargesend.controller.active() {
                    self.bottom_pane.set_chargesend_status(None);
                }
                false
            }
            Outcome::Consume => {
                if !self.chargesend.controller.active() {
                    self.bottom_pane.set_chargesend_status(None);
                }
                self.request_redraw();
                true
            }
            Outcome::Submit(effort) => {
                self.bottom_pane.set_chargesend_status(None);
                // Context was revalidated on this release, before the composer
                // clears anything. The ordinary composer still validates content,
                // resolves paste placeholders, and drains images and mentions.
                let Some(thread) = self.thread_id else {
                    return true;
                };
                let prompt_effort = PromptEffort {
                    thread,
                    mode: self.effective_collaboration_mode(),
                    effort,
                };
                let result = self
                    .bottom_pane
                    .handle_key_event(KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE));
                if matches!(
                    result,
                    InputResult::None | InputResult::ParentOwnedInputBlocked
                ) {
                    self.refresh_startup_recovery();
                }
                crate::startup_recovery::submitted(&result);
                self.sync_backend_banner_view();
                self.handle_composer_input_result_with_effort(result, false, Some(prompt_effort));
                self.request_redraw();
                true
            }
        }
    }

    /// A delayed image submission must still belong to the same idle context.
    pub(super) fn chargesend_prompt_valid(&self, prompt: &PromptEffort) -> bool {
        self.thread_id == Some(prompt.thread)
            && self.effective_collaboration_mode() == prompt.mode
            && !self.is_user_turn_pending_or_running()
            && !self.input_queue.suppress_queue_autosend
            && !self.input_queue.recovered_queue
            && !self.input_queue.rate_limit_recovery_pending
            && !self.blocks_direct_input
            && !self.fork_in_progress
            && self.pending_image_submission.is_none()
            && !self.only_user_shell_commands_running()
            && self.chargesend_choices().contains(&prompt.effort)
    }

    pub(super) fn chargesend_request_mode(
        &self,
        intended: &CollaborationMode,
        prompt: Option<&PromptEffort>,
    ) -> CollaborationMode {
        let effort = prompt.map(|prompt| prompt.effort.clone()).or_else(|| {
            intended.reasoning_effort().or_else(|| {
                let preset = self.current_model_preset()?;
                preset
                    .supported_reasoning_efforts
                    .iter()
                    .any(|option| option.effort == preset.default_reasoning_effort)
                    .then_some(preset.default_reasoning_effort)
            })
        });
        intended.with_updates(None, Some(effort), None)
    }

    pub(super) fn note_chargesend_request(&mut self, sent: CollaborationMode, charged: bool) {
        self.chargesend.has_charged |= charged;
        if self.chargesend.has_charged {
            // Server settings notifications have no request ID. Recognize only
            // complete mode/model/effort matches from our own accepted requests.
            // Bound the queue when the backend elides unchanged notifications.
            if self.chargesend.echoes.len() == 32 {
                self.chargesend.echoes.pop_front();
            }
            self.chargesend.echoes.push_back(ExpectedSettings { sent });
        }
    }

    /// Stop backend echoes of prompt-local overrides from changing UI defaults.
    /// Other settings updates keep their ordinary upstream synchronization path.
    pub(super) fn normalize_chargesend_echo(&mut self, settings: &mut ThreadSettings) {
        let incoming = settings.collaboration_mode.with_updates(
            Some(settings.model.clone()),
            Some(settings.effort.clone()),
            None,
        );
        if let Some(intended) = self.chargesend_echo_mode(&incoming) {
            settings.model = intended.model().to_string();
            settings.effort = intended.reasoning_effort();
            settings.collaboration_mode = intended;
        }
    }

    fn chargesend_echo_mode(&mut self, incoming: &CollaborationMode) -> Option<CollaborationMode> {
        let index = self
            .chargesend
            .echoes
            .iter()
            .position(|echo| &echo.sent == incoming)?;
        self.chargesend.echoes.drain(..=index);
        Some(self.effective_collaboration_mode())
    }
}

#[cfg(test)]
#[path = "chargesend_tests.rs"]
mod tests;
