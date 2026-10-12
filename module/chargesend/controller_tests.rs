// Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
use super::*;

fn context() -> (u32, Vec<&'static str>, &'static str) {
    (1, vec!["low", "medium", "high"], "low")
}

fn begin() -> (Controller<u32, &'static str>, Instant) {
    let now = Instant::now();
    let mut charge = Controller::new(Timing::default());
    assert_eq!(
        charge.handle(Input::EnterPress, Some(context()), now),
        Outcome::Consume
    );
    (charge, now)
}

#[test]
fn chargesend_tap_and_unmatched_release() {
    let (mut charge, now) = begin();
    assert_eq!(
        charge.handle(
            Input::EnterRelease,
            Some(context()),
            now + Duration::from_millis(150)
        ),
        Outcome::Submit("low")
    );
    assert_eq!(
        charge.handle(Input::EnterRelease, Some(context()), now),
        Outcome::Pass
    );
}

#[test]
fn chargesend_hold_descend_cycle_and_boundaries() {
    let (mut charge, now) = begin();
    for (ms, effort, permille, descending) in [
        (0, "low", 0, false),
        (499, "low", 249, false),
        (500, "medium", 250, false),
        (1000, "medium", 500, false),
        (1500, "high", 750, false),
        (1999, "high", 999, false),
        (2000, "high", 1000, true),
        (2500, "high", 750, true),
        (3000, "medium", 500, true),
        (3501, "low", 249, true),
        (3999, "low", 0, true),
        (4000, "low", 0, false),
        (6000, "high", 1000, true),
    ] {
        assert_eq!(
            charge.paint(now + Duration::from_millis(ms)),
            Some(Snapshot {
                effort,
                permille,
                descending
            }),
            "at {ms}ms"
        );
    }
}

#[test]
fn chargesend_repeats_do_not_restart_or_submit() {
    let (mut charge, now) = begin();
    for ms in [100, 900, 1900] {
        assert_eq!(
            charge.handle(
                Input::EnterRepeat,
                Some(context()),
                now + Duration::from_millis(ms)
            ),
            Outcome::Consume
        );
    }
    assert_eq!(
        charge.paint(now + Duration::from_secs(2)).unwrap().effort,
        "high"
    );
    assert_eq!(
        charge.handle(
            Input::EnterRelease,
            Some(context()),
            now + Duration::from_secs(2)
        ),
        Outcome::Submit("high")
    );
    assert_eq!(
        charge.handle(
            Input::EnterRelease,
            Some(context()),
            now + Duration::from_secs(2)
        ),
        Outcome::Pass
    );
    assert_eq!(
        charge.handle(Input::EnterRepeat, Some(context()), now),
        Outcome::Consume
    );
    assert!(!charge.active());
}

#[test]
fn chargesend_sends_the_painted_label_at_a_frame_boundary() {
    let (mut charge, now) = begin();
    charge.paint(now + Duration::from_millis(1499));
    assert_eq!(
        charge.handle(
            Input::EnterRelease,
            Some(context()),
            now + Duration::from_millis(1501)
        ),
        Outcome::Submit("medium")
    );
}

#[test]
fn chargesend_escape_invalidation_and_edit_cancel_until_release() {
    for input in [Input::Escape, Input::OtherPress] {
        let (mut charge, now) = begin();
        charge.handle(input, Some(context()), now);
        assert!(!charge.active());
        assert_eq!(
            charge.handle(Input::EnterRepeat, Some(context()), now),
            Outcome::Consume
        );
        assert_eq!(
            charge.handle(Input::EnterPress, Some(context()), now),
            Outcome::Consume
        );
        assert_eq!(
            charge.handle(Input::EnterRelease, Some(context()), now),
            Outcome::Consume
        );
    }
    for eligible in [
        None,
        Some((2, context().1, "low")),
        Some((1, vec!["low"], "low")),
    ] {
        let (mut charge, now) = begin();
        assert_eq!(
            charge.handle(Input::EnterRelease, eligible, now),
            Outcome::Consume
        );
        assert!(!charge.active());
    }
}

#[test]
fn chargesend_fallback_and_single_model_tier() {
    let mut charge = Controller::<u32, &str>::new(Timing::default());
    let now = Instant::now();
    assert_eq!(charge.handle(Input::EnterPress, None, now), Outcome::Pass);
    assert_eq!(charge.handle(Input::EnterRelease, None, now), Outcome::Pass);
    assert_eq!(
        charge.handle(Input::EnterPress, Some((1, Vec::new(), "low")), now),
        Outcome::Pass
    );
    charge.handle(Input::EnterPress, Some((1, vec!["custom"], "custom")), now);
    assert_eq!(
        charge.paint(now + Duration::from_secs(2)).unwrap().effort,
        "custom"
    );
}

#[test]
fn chargesend_other_releases_and_clock_regression_are_safe() {
    let (mut charge, now) = begin();
    charge.handle(Input::OtherRelease, Some(context()), now);
    assert!(charge.active());
    assert_eq!(
        charge.paint(now - Duration::from_secs(1)).unwrap().permille,
        0
    );
}

#[test]
fn chargesend_adjustable_timing_and_invalid_values() {
    assert!(Timing::from_millis(0, 0, 33).is_none());
    assert!(Timing::from_millis(2000, 1000, 33).is_none());
    assert!(Timing::from_millis(2000, 150, 0).is_none());
    let mut charge = Controller::new(Timing::from_millis(1000, 100, 20).unwrap());
    let now = Instant::now();
    charge.handle(Input::EnterPress, Some(context()), now);
    assert_eq!(
        charge.paint(now + Duration::from_secs(1)).unwrap().permille,
        1000
    );
    assert_eq!(
        charge.paint(now + Duration::from_secs(2)).unwrap().permille,
        0
    );
}

#[test]
fn chargesend_configured_start_peak_low_and_reset() {
    let now = Instant::now();
    let context = || (1, vec!["low", "medium", "high", "xhigh", "max"], "xhigh");
    let mut charge = Controller::new(Timing::default());
    charge.handle(Input::EnterPress, Some(context()), now);
    for (ms, effort, permille, descending) in [
        (0, "xhigh", 750, false),
        (150, "xhigh", 825, false),
        (250, "max", 875, false),
        (500, "max", 1000, true),
        (1000, "xhigh", 750, true),
        (1500, "high", 500, true),
        (2500, "low", 0, false),
        (4500, "max", 1000, true),
    ] {
        assert_eq!(
            charge.paint(now + Duration::from_millis(ms)),
            Some(Snapshot {
                effort,
                permille,
                descending
            })
        );
    }
    assert_eq!(
        charge.handle(
            Input::EnterRelease,
            Some(context()),
            now + Duration::from_millis(4500)
        ),
        Outcome::Submit("max")
    );
    let next = now + Duration::from_secs(7);
    charge.handle(Input::EnterPress, Some(context()), next);
    assert_eq!(
        charge.handle(
            Input::EnterRelease,
            Some(context()),
            next + Duration::from_millis(150)
        ),
        Outcome::Submit("xhigh")
    );
}

#[test]
fn chargesend_constant_speed_from_every_start_without_initial_pause() {
    let now = Instant::now();
    let choices = vec!["low", "medium", "high", "xhigh", "max"];
    for (start, effort) in choices.iter().enumerate() {
        let mut charge = Controller::new(Timing::default());
        charge.handle(Input::EnterPress, Some((1, choices.clone(), *effort)), now);
        for ms in [0, 100, 200] {
            let snapshot = charge.paint(now + Duration::from_millis(ms)).unwrap();
            let distance = ms / 2;
            assert_eq!(
                u64::from(snapshot.permille),
                if start == 4 {
                    1000 - distance
                } else {
                    start as u64 * 250 + distance
                },
                "start {effort}, elapsed {ms}ms"
            );
            assert_eq!(snapshot.descending, start == 4);
        }
        let first_peak = (4 - start) as u64 * 500;
        let peak = charge
            .paint(now + Duration::from_millis(first_peak))
            .unwrap();
        assert_eq!(peak.permille, 1000);
        assert!(peak.descending);
        let trough = charge
            .paint(now + Duration::from_millis(first_peak + 2000))
            .unwrap();
        assert_eq!(trough.permille, 0);
        assert!(!trough.descending);
    }
}

#[test]
fn chargesend_fast_motion_preserves_tap_label_and_submission() {
    let now = Instant::now();
    let mut charge = Controller::new(Timing::from_millis(500, 200, 20).unwrap());
    let context = || (1, vec!["low", "medium", "high", "xhigh", "max"], "low");
    charge.handle(Input::EnterPress, Some(context()), now);
    let snapshot = charge.paint(now + Duration::from_millis(200)).unwrap();
    assert_eq!(snapshot.permille, 400);
    assert_eq!(snapshot.effort, "low");
    assert_eq!(
        charge.handle(
            Input::EnterRelease,
            Some(context()),
            now + Duration::from_millis(200)
        ),
        Outcome::Submit("low")
    );
}
