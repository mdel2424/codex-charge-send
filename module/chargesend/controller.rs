// Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
//! A terminal-independent, monotonic hold/release state machine.
//!
//! The UI supplies an eligible context and its allowed efforts. It calls `paint`
//! immediately before drawing. Release returns the last painted effort, so a
//! boundary crossed between frames cannot send an effort the user never saw.
//! Cancellation keeps a key-down latch until release: repeats cannot become a
//! fresh submission after Escape, focus loss, or a context change.

use std::time::Duration;
use std::time::Instant;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Timing {
    pub(crate) half_cycle: Duration,
    pub(crate) tap: Duration,
    pub(crate) frame: Duration,
}

impl Default for Timing {
    fn default() -> Self {
        Self {
            half_cycle: Duration::from_millis(2000),
            tap: Duration::from_millis(150),
            frame: Duration::from_millis(33),
        }
    }
}

impl Timing {
    pub(crate) fn from_millis(half_cycle: u64, tap: u64, frame: u64) -> Option<Self> {
        if !(250..=60_000).contains(&half_cycle)
            || tap >= half_cycle / 2
            || !(10..=100).contains(&frame)
        {
            return None;
        }
        Some(Self {
            half_cycle: Duration::from_millis(half_cycle),
            tap: Duration::from_millis(tap),
            frame: Duration::from_millis(frame),
        })
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Input {
    EnterPress,
    EnterRepeat,
    EnterRelease,
    Escape,
    OtherPress,
    OtherRelease,
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Outcome<E> {
    Pass,
    Consume,
    Submit(E),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Snapshot<E> {
    pub(crate) effort: E,
    pub(crate) permille: u16,
    pub(crate) descending: bool,
}

#[derive(Clone, Debug)]
struct Charge<C, E> {
    started: Instant,
    context: C,
    choices: Vec<E>,
    painted: E,
}

#[derive(Clone, Debug)]
pub(crate) struct Controller<C, E> {
    timing: Timing,
    active: Option<Charge<C, E>>,
    enter_down: bool,
}

impl<C: PartialEq, E: Clone + PartialEq> Controller<C, E> {
    pub(crate) fn new(timing: Timing) -> Self {
        Self {
            timing,
            active: None,
            enter_down: false,
        }
    }

    pub(crate) fn active(&self) -> bool {
        self.active.is_some()
    }

    pub(crate) fn enter_down(&self) -> bool {
        self.enter_down
    }

    pub(crate) fn frame_interval(&self) -> Duration {
        self.timing.frame
    }

    pub(crate) fn cancel(&mut self) {
        self.active = None;
    }

    /// Invalidate on changes to model, thread, settings, choices, or eligibility.
    pub(crate) fn validate(&mut self, eligible: Option<&(C, Vec<E>)>) {
        if self.active.as_ref().is_some_and(|active| {
            eligible.is_none_or(|(context, choices)| {
                active.context != *context || active.choices != *choices
            })
        }) {
            self.cancel();
        }
    }

    pub(crate) fn handle(
        &mut self,
        input: Input,
        eligible: Option<(C, Vec<E>)>,
        now: Instant,
    ) -> Outcome<E> {
        self.validate(eligible.as_ref());
        match input {
            Input::EnterRelease if self.enter_down => {
                self.enter_down = false;
                self.active.take().map_or(Outcome::Consume, |charge| {
                    // A short tap always selects the lowest allowed effort.
                    let effort = if now.saturating_duration_since(charge.started) <= self.timing.tap
                    {
                        charge.choices[0].clone()
                    } else {
                        charge.painted
                    };
                    Outcome::Submit(effort)
                })
            }
            Input::EnterPress | Input::EnterRepeat if self.enter_down => Outcome::Consume,
            Input::EnterRepeat if eligible.is_some() => Outcome::Consume,
            Input::EnterPress => {
                let Some((context, choices)) = eligible.filter(|(_, choices)| !choices.is_empty())
                else {
                    return Outcome::Pass;
                };
                let painted = choices[0].clone();
                self.active = Some(Charge {
                    started: now,
                    context,
                    choices,
                    painted,
                });
                self.enter_down = true;
                Outcome::Consume
            }
            Input::Escape if self.active() => {
                self.cancel();
                Outcome::Consume
            }
            Input::OtherPress | Input::Escape => {
                self.cancel();
                Outcome::Pass
            }
            _ => Outcome::Pass,
        }
    }

    /// Compute charge using elapsed time, never key repeats or a frame counter.
    pub(crate) fn paint(&mut self, now: Instant) -> Option<Snapshot<E>> {
        let charge = self.active.as_mut()?;
        let half = self.timing.half_cycle.as_nanos();
        let elapsed = now.saturating_duration_since(charge.started).as_nanos();
        let phase = elapsed % (half * 2);
        let descending = phase >= half;
        let rising = if descending { half * 2 - phase } else { phase };
        let index = if rising <= self.timing.tap.as_nanos() {
            0
        } else {
            // Round to the closest advertised tier. The endpoints have a usable
            // dwell interval; the bar itself reaches full at exactly half_cycle.
            ((rising * (charge.choices.len() - 1) as u128 + half / 2) / half) as usize
        };
        let effort = charge.choices[index].clone();
        charge.painted = effort.clone();
        Some(Snapshot {
            effort,
            permille: (rising * 1000 / half) as u16,
            descending,
        })
    }
}

#[cfg(test)]
#[path = "controller_tests.rs"]
mod tests;
