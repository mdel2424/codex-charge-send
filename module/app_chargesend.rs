// Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
//! Invalidation and key-release draining before overlays, chords, and thread
//! replacement can own input. The application latch outlives a ChatWidget.

use super::*;

impl App {
    pub(super) fn chargesend_state_transition(&mut self) {
        self.chargesend_enter_down |= self.chat_widget.chargesend_enter_down();
        self.chat_widget.cancel_chargesend();
    }

    pub(super) fn chargesend_pre_event(&mut self, event: &TuiEvent) -> bool {
        self.chargesend_enter_down |= self.chat_widget.chargesend_enter_down();
        if self.overlay.is_some()
            || self.reconnect.offline
            || matches!(
                event,
                TuiEvent::FocusLost | TuiEvent::Paste(_) | TuiEvent::Mouse(_) | TuiEvent::Resume
            )
        {
            self.chat_widget.cancel_chargesend();
        }
        if let TuiEvent::Key(key) = event {
            if key.code == KeyCode::Enter && self.chargesend_enter_down {
                // A replacement widget has no matching charge. Drain this key
                // anyway so an old repeat cannot submit its new draft.
                if self.chat_widget.chargesend_enter_down() {
                    self.chat_widget.handle_chargesend_key(*key);
                }
                if key.kind == KeyEventKind::Release {
                    self.chargesend_enter_down = false;
                }
                return true;
            }
            if key.kind == KeyEventKind::Release
                && (key.code == KeyCode::Enter
                    || self.overlay.is_some()
                    || !self.chat_widget.no_modal_or_popup_active())
            {
                return true;
            }
            if key.kind != KeyEventKind::Release && key.code != KeyCode::Enter {
                if key.code == KeyCode::Esc
                    && key.modifiers.is_empty()
                    && self.chat_widget.chargesend_active()
                    && self.chat_widget.handle_chargesend_key(*key)
                {
                    return true;
                }
                self.chat_widget.cancel_chargesend();
            }
        }
        false
    }
}

#[cfg(test)]
#[path = "app_chargesend_tests.rs"]
mod tests;
