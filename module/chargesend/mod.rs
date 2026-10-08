// Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
//! ChargeSend's small input state machine and verified terminal capability.
//! Upstream-specific glue lives in `chatwidget/chargesend.rs`.

mod bar;
pub(crate) mod capability;
mod controller;
pub(crate) use bar::status_line;

pub(crate) use controller::Controller;
pub(crate) use controller::Input;
pub(crate) use controller::Outcome;
pub(crate) use controller::Timing;

pub(crate) fn timing_from_env() -> Timing {
    let read = |name: &str, default: u64| -> Option<u64> {
        match std::env::var(name) {
            Ok(value) => value.parse().ok(),
            Err(std::env::VarError::NotPresent) => Some(default),
            Err(_) => None,
        }
    };
    let timing = read("CHARGESEND_HALF_CYCLE_MS", 2000)
        .zip(read("CHARGESEND_TAP_MS", 150))
        .zip(read("CHARGESEND_FRAME_MS", 33))
        .and_then(|((half, tap), frame)| Timing::from_millis(half, tap, frame));
    timing.unwrap_or_else(|| {
        tracing::warn!("invalid ChargeSend timing; using 2000/150/33ms defaults");
        Timing::default()
    })
}
