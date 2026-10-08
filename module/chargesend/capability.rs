// Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
//! Negotiation is independent of generic Kitty-protocol support: Enter needs
//! both REPORT_EVENT_TYPES (2) and REPORT_ALL_KEYS_AS_ESCAPE_CODES (8).

use std::sync::atomic::AtomicBool;
use std::sync::atomic::Ordering;

static REQUESTED: AtomicBool = AtomicBool::new(false);
static VERIFIED: AtomicBool = AtomicBool::new(false);

pub(crate) fn allowed_terminal(kitty: bool, multiplexer: bool, disabled: bool) -> bool {
    kitty && !multiplexer && !disabled
}

pub(crate) fn requested(success: bool) {
    REQUESTED.store(success, Ordering::Relaxed);
}

pub(crate) fn flags_allow_enter_release(bits: u8) -> bool {
    bits & 10 == 10
}

/// Called by the existing startup probe after requesting enhancements, before
/// the asynchronous event reader owns stdin. A timeout never grants support.
pub(crate) fn observe_flags(bits: u8) {
    VERIFIED.store(flags_allow_enter_release(bits), Ordering::Relaxed);
}

pub(crate) fn available() -> bool {
    REQUESTED.load(Ordering::Relaxed) && VERIFIED.load(Ordering::Relaxed)
}

#[cfg(test)]
#[path = "capability_tests.rs"]
mod tests;
