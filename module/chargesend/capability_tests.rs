// Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
use super::*;

#[test]
fn chargesend_requires_both_flags_and_a_direct_supported_terminal() {
    for flags in [0, 1, 2, 5, 7, 8, 9] {
        assert!(!flags_allow_enter_release(flags));
    }
    for flags in [10, 11, 15, 31] {
        assert!(flags_allow_enter_release(flags));
    }
    assert!(allowed_terminal(true, false, false));
    assert!(!allowed_terminal(false, false, false));
    assert!(!allowed_terminal(true, true, false));
    assert!(!allowed_terminal(true, false, true));
}
