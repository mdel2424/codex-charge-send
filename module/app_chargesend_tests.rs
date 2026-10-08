// Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
use super::*;

#[tokio::test]
async fn chargesend_app_latch_outlives_widget_transitions() {
    let mut app = crate::app::test_support::make_test_app().await;
    app.chargesend_enter_down = true;
    app.chargesend_state_transition();
    let mut replacement = crate::app::test_support::make_test_app().await;
    std::mem::swap(&mut app.chat_widget, &mut replacement.chat_widget);
    for kind in [KeyEventKind::Repeat, KeyEventKind::Press] {
        assert!(
            app.chargesend_pre_event(&TuiEvent::Key(KeyEvent::new_with_kind(
                KeyCode::Enter,
                KeyModifiers::NONE,
                kind,
            )))
        );
        assert!(app.chargesend_enter_down);
    }
    assert!(
        app.chargesend_pre_event(&TuiEvent::Key(KeyEvent::new_with_kind(
            KeyCode::Enter,
            KeyModifiers::NONE,
            KeyEventKind::Release,
        )))
    );
    assert!(!app.chargesend_enter_down);
    assert!(!app.chargesend_pre_event(&TuiEvent::Key(KeyEvent::new(
        KeyCode::Enter,
        KeyModifiers::NONE,
    ))));
}
