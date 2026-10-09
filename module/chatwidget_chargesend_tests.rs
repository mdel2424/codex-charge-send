// Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
//! Exercise actual composer/submission code through upstream's mock Op receiver.
//! No API credentials, network requests, or live inference.

use super::*;
use crate::app_command::AppCommand as Op;
use crate::chatwidget::tests::make_chatwidget_manual_with_sender;
use crate::render::renderable::Renderable;
use codex_protocol::openai_models::InputModality;
use codex_protocol::openai_models::ReasoningEffortPreset;
use pretty_assertions::assert_eq;
use tokio::sync::mpsc::UnboundedReceiver;

type Fixture = (
    ChatWidget,
    UnboundedReceiver<AppEvent>,
    UnboundedReceiver<Op>,
);

async fn fixture() -> Fixture {
    let (mut chat, _sender, rx, op_rx) = make_chatwidget_manual_with_sender().await;
    chat.thread_id = Some(ThreadId::new());
    chat.chargesend.terminal_available = true;
    chat.set_reasoning_effort(Some(ReasoningEffortConfig::Low));
    catalog(
        &mut chat,
        vec![
            ReasoningEffortConfig::Low,
            ReasoningEffortConfig::Medium,
            ReasoningEffortConfig::High,
        ],
    );
    draft(&mut chat, "hello");
    (chat, rx, op_rx)
}

fn next_submit_op(receiver: &mut UnboundedReceiver<Op>) -> Op {
    loop {
        let op = receiver.try_recv().expect("expected a submitted UserTurn");
        if matches!(op, Op::UserTurn { .. }) {
            return op;
        }
    }
}

fn assert_no_submit_op(receiver: &mut UnboundedReceiver<Op>) {
    while let Ok(op) = receiver.try_recv() {
        assert!(
            !matches!(op, Op::UserTurn { .. }),
            "unexpected turn: {op:?}"
        );
    }
}

fn catalog(chat: &mut ChatWidget, efforts: Vec<ReasoningEffortConfig>) {
    let mut preset = chat.current_model_preset().expect("fixture model exists");
    preset.input_modalities = vec![InputModality::Text, InputModality::Image];
    preset.default_reasoning_effort = ReasoningEffortConfig::Medium;
    preset.supported_reasoning_efforts = efforts
        .into_iter()
        .map(|effort| ReasoningEffortPreset {
            effort,
            description: String::new(),
        })
        .collect();
    chat.model_catalog = Arc::new(
        crate::model_catalog::ModelCatalog::new(vec![preset])
            .with_collaboration_modes(chat.model_catalog.collaboration_modes.clone()),
    );
}

fn draft(chat: &mut ChatWidget, text: &str) {
    chat.bottom_pane
        .set_composer_text(text.to_string(), Vec::new(), Vec::new());
}

fn enter(chat: &mut ChatWidget, kind: KeyEventKind) {
    chat.handle_key_event(KeyEvent::new_with_kind(
        KeyCode::Enter,
        KeyModifiers::NONE,
        kind,
    ));
}

fn reset_idle(chat: &mut ChatWidget) {
    chat.input_queue.user_turn_pending_start = false;
    chat.turn_lifecycle.agent_turn_running = false;
    chat.bottom_pane.set_task_running(false);
}

fn assert_effort(op: &Op, effort: ReasoningEffortConfig, kind: ModeKind) {
    let Op::UserTurn {
        effort: actual,
        collaboration_mode,
        ..
    } = op
    else {
        panic!("expected UserTurn, got {op:?}");
    };
    assert_eq!(actual, &Some(effort.clone()));
    let mode = collaboration_mode
        .as_ref()
        .expect("explicit mode accompanies effort");
    assert_eq!(mode.mode, kind);
    assert_eq!(mode.reasoning_effort(), Some(effort));
}

/// Mimic the backend's sticky thread settings and collaboration precedence.
/// Each record is the settings captured by the actual submitted operation.
#[derive(Default)]
struct StickyBackend {
    effort: Option<ReasoningEffortConfig>,
    captured: Vec<Option<ReasoningEffortConfig>>,
    settings_updates: usize,
}

impl StickyBackend {
    fn accept(&mut self, op: Op) {
        match op {
            Op::UserTurn {
                effort,
                collaboration_mode,
                ..
            } => {
                if effort.is_some() {
                    self.effort = effort;
                }
                if let Some(mode) = collaboration_mode {
                    self.effort = mode.reasoning_effort();
                }
                self.captured.push(self.effort.clone());
            }
            Op::OverrideTurnContext {
                effort,
                collaboration_mode,
                ..
            } => {
                self.settings_updates += 1;
                if let Some(effort) = effort {
                    self.effort = effort;
                }
                if let Some(mode) = collaboration_mode {
                    self.effort = mode.reasoning_effort();
                }
            }
            _ => {}
        }
    }

    fn drain(&mut self, receiver: &mut UnboundedReceiver<Op>) {
        while let Ok(op) = receiver.try_recv() {
            self.accept(op);
        }
    }
}

#[tokio::test(start_paused = true)]
async fn chargesend_tap_submits_once_and_keeps_intended_default() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    let original = chat.effective_collaboration_mode();
    let config_file = chat.config.codex_home.join("config.toml");
    let original_file = std::fs::read(&config_file).ok();
    enter(&mut chat, KeyEventKind::Press);
    assert!(chat.chargesend_active());
    assert_no_submit_op(&mut op_rx);
    enter(&mut chat, KeyEventKind::Repeat);
    enter(&mut chat, KeyEventKind::Press);
    tokio::time::advance(Duration::from_millis(60)).await;
    enter(&mut chat, KeyEventKind::Release);
    let op = next_submit_op(&mut op_rx);
    assert_effort(&op, ReasoningEffortConfig::Low, ModeKind::Default);
    let mut backend = StickyBackend::default();
    backend.accept(op);
    backend.drain(&mut op_rx);
    assert_eq!(backend.effort, Some(ReasoningEffortConfig::Low));
    assert_eq!(backend.captured, vec![Some(ReasoningEffortConfig::Low)]);
    assert_eq!(
        backend.settings_updates, 0,
        "a charge must not cancel backend continuations through a standalone settings update"
    );
    enter(&mut chat, KeyEventKind::Release);
    assert_no_submit_op(&mut op_rx);
    assert_eq!(chat.effective_collaboration_mode(), original);
    assert_eq!(std::fs::read(&config_file).ok(), original_file);
}

#[tokio::test(start_paused = true)]
async fn chargesend_hold_and_descending_release_use_painted_effort() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    enter(&mut chat, KeyEventKind::Press);
    tokio::time::advance(Duration::from_secs(2)).await;
    chat.paint_chargesend();
    enter(&mut chat, KeyEventKind::Release);
    assert_effort(
        &next_submit_op(&mut op_rx),
        ReasoningEffortConfig::High,
        ModeKind::Default,
    );
    reset_idle(&mut chat);
    draft(&mut chat, "second");
    enter(&mut chat, KeyEventKind::Press);
    tokio::time::advance(Duration::from_secs(3)).await;
    chat.paint_chargesend();
    enter(&mut chat, KeyEventKind::Release);
    assert_effort(
        &next_submit_op(&mut op_rx),
        ReasoningEffortConfig::Medium,
        ModeKind::Default,
    );
}

#[tokio::test]
async fn chargesend_escape_retains_draft_and_attachment() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    draft(&mut chat, "keep this");
    chat.attach_image(PathBuf::from("/tmp/chargesend-image.png"));
    let before = chat.bottom_pane.composer_text();
    enter(&mut chat, KeyEventKind::Press);
    assert!(chat.chargesend_active());
    chat.handle_key_event(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE));
    assert_eq!(chat.bottom_pane.composer_text(), before);
    // The canceled Enter's repeats and release cannot drain the attachment.
    enter(&mut chat, KeyEventKind::Repeat);
    enter(&mut chat, KeyEventKind::Release);
    assert_no_submit_op(&mut op_rx);
    assert_eq!(chat.bottom_pane.composer_local_images().len(), 1);
}

#[tokio::test]
async fn chargesend_focus_thread_model_and_settings_invalidate() {
    for transition in 0..4 {
        let (mut chat, _rx, mut op_rx) = fixture().await;
        enter(&mut chat, KeyEventKind::Press);
        match transition {
            0 => chat.cancel_chargesend(), // app FocusLost path
            1 => chat.thread_id = Some(ThreadId::new()),
            2 => chat.set_model("different-model"),
            _ => chat.set_reasoning_effort(Some(ReasoningEffortConfig::Medium)),
        }
        enter(&mut chat, KeyEventKind::Repeat);
        enter(&mut chat, KeyEventKind::Release);
        assert_no_submit_op(&mut op_rx);
        assert_eq!(chat.bottom_pane.composer_text(), "hello");
    }
}

#[tokio::test]
async fn chargesend_unsupported_terminal_preserves_normal_press_submission() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    chat.set_reasoning_effort(Some(ReasoningEffortConfig::High));
    chat.chargesend.terminal_available = false;
    enter(&mut chat, KeyEventKind::Press);
    assert!(!chat.chargesend_active());
    let op = next_submit_op(&mut op_rx);
    let Op::UserTurn { effort, .. } = op else {
        unreachable!()
    };
    assert_eq!(effort, Some(ReasoningEffortConfig::High));
    enter(&mut chat, KeyEventKind::Release);
    assert_no_submit_op(&mut op_rx);
}

#[tokio::test]
async fn chargesend_menu_slash_newline_and_busy_paths_are_preserved() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    chat.open_reasoning_popup(chat.current_model_preset().unwrap());
    enter(&mut chat, KeyEventKind::Press);
    assert!(!chat.chargesend_active());
    enter(&mut chat, KeyEventKind::Release);
    assert_no_submit_op(&mut op_rx);

    let (mut chat, _rx, mut op_rx) = fixture().await;
    draft(&mut chat, "/model");
    enter(&mut chat, KeyEventKind::Press);
    assert!(!chat.chargesend_active());
    enter(&mut chat, KeyEventKind::Release);
    assert_no_submit_op(&mut op_rx);

    let (mut chat, _rx, mut op_rx) = fixture().await;
    chat.handle_key_event(KeyEvent::new(KeyCode::Enter, KeyModifiers::SHIFT));
    assert_eq!(chat.bottom_pane.composer_text(), "hello\n");
    assert!(!chat.chargesend_active());
    assert_no_submit_op(&mut op_rx);

    let (mut chat, _rx, mut op_rx) = fixture().await;
    chat.turn_lifecycle.agent_turn_running = true;
    chat.bottom_pane.set_task_running(true);
    enter(&mut chat, KeyEventKind::Press);
    assert!(!chat.chargesend_active());
    let _steer = next_submit_op(&mut op_rx);
    enter(&mut chat, KeyEventKind::Release);
    assert_no_submit_op(&mut op_rx);
}

#[tokio::test]
async fn chargesend_busy_queue_and_external_editor_keep_normal_routing() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    chat.turn_lifecycle.agent_turn_running = true;
    chat.bottom_pane.set_task_running(true);
    chat.handle_key_event(KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE));
    assert!(!chat.chargesend_active());
    assert!(chat.input_queue.has_queued_follow_up_messages());
    assert_no_submit_op(&mut op_rx);
    enter(&mut chat, KeyEventKind::Release);
    assert_no_submit_op(&mut op_rx);

    let (mut chat, _rx, mut op_rx) = fixture().await;
    enter(&mut chat, KeyEventKind::Press);
    chat.apply_external_edit("edited externally".to_string());
    enter(&mut chat, KeyEventKind::Repeat);
    enter(&mut chat, KeyEventKind::Release);
    assert_no_submit_op(&mut op_rx);
    assert_eq!(chat.bottom_pane.composer_text(), "edited externally");
    enter(&mut chat, KeyEventKind::Press);
    enter(&mut chat, KeyEventKind::Release);
    assert_effort(
        &next_submit_op(&mut op_rx),
        ReasoningEffortConfig::Low,
        ModeKind::Default,
    );
}

#[tokio::test]
async fn chargesend_unavailable_notice_is_drawn_once() {
    let (mut chat, mut rx, _op_rx) = fixture().await;
    while rx.try_recv().is_ok() {}
    chat.chargesend.terminal_available = false;
    chat.chargesend.announced = false;
    chat.paint_chargesend();
    chat.paint_chargesend();
    let mut notices = 0;
    while let Ok(event) = rx.try_recv() {
        if let AppEvent::InsertHistoryCell(cell) = event {
            let text = cell
                .display_lines(100)
                .iter()
                .map(ToString::to_string)
                .collect::<Vec<_>>()
                .join("\n");
            notices += usize::from(text.contains("hold-to-charge unavailable"));
        }
    }
    assert_eq!(notices, 1);
}

#[tokio::test]
async fn chargesend_bracketed_paste_expands_through_normal_submission() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    draft(&mut chat, "");
    let payload = "a".repeat(1500);
    chat.handle_paste(payload.clone());
    enter(&mut chat, KeyEventKind::Press);
    assert_no_submit_op(&mut op_rx);
    enter(&mut chat, KeyEventKind::Release);
    let Op::UserTurn { items, .. } = next_submit_op(&mut op_rx) else {
        unreachable!()
    };
    assert_eq!(
        items,
        vec![UserInput::Text {
            text: payload,
            text_elements: Vec::new()
        }]
    );
}

#[tokio::test(start_paused = true)]
async fn chargesend_paste_burst_enter_keeps_newline_suppression() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    draft(&mut chat, "");
    chat.handle_key_event(KeyEvent::new(KeyCode::Char('a'), KeyModifiers::NONE));
    tokio::time::advance(Duration::from_millis(1)).await;
    chat.handle_key_event(KeyEvent::new(KeyCode::Char('b'), KeyModifiers::NONE));
    enter(&mut chat, KeyEventKind::Press);
    assert!(!chat.chargesend_active());
    enter(&mut chat, KeyEventKind::Release);
    assert_no_submit_op(&mut op_rx);
}

#[tokio::test]
async fn chargesend_model_specific_tiers_include_max_and_exclude_ultra() {
    let (mut chat, _rx, _op_rx) = fixture().await;
    let custom = ReasoningEffortConfig::Custom("future".to_string());
    catalog(
        &mut chat,
        vec![
            ReasoningEffortConfig::Medium,
            custom.clone(),
            ReasoningEffortConfig::Max,
            ReasoningEffortConfig::Ultra,
            custom.clone(),
        ],
    );
    assert_eq!(
        chat.chargesend_choices(),
        vec![
            ReasoningEffortConfig::Medium,
            custom.clone(),
            ReasoningEffortConfig::Max
        ]
    );
    chat.set_reasoning_effort(Some(ReasoningEffortConfig::Max));
    assert_eq!(
        chat.chargesend_choices(),
        vec![
            ReasoningEffortConfig::Medium,
            custom,
            ReasoningEffortConfig::Max
        ]
    );
    chat.set_reasoning_effort(Some(ReasoningEffortConfig::Ultra));
    assert!(
        !chat
            .chargesend_choices()
            .contains(&ReasoningEffortConfig::Ultra)
    );
    catalog(&mut chat, Vec::new());
    assert!(chat.chargesend_context().is_none());
}

#[tokio::test(start_paused = true)]
async fn chargesend_peak_submits_max_without_changing_default_effort() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    chat.set_reasoning_effort(Some(ReasoningEffortConfig::XHigh));
    catalog(
        &mut chat,
        vec![
            ReasoningEffortConfig::Low,
            ReasoningEffortConfig::Medium,
            ReasoningEffortConfig::High,
            ReasoningEffortConfig::XHigh,
            ReasoningEffortConfig::Max,
            ReasoningEffortConfig::Ultra,
        ],
    );
    let intended = chat.effective_collaboration_mode();
    enter(&mut chat, KeyEventKind::Press);
    tokio::time::advance(Duration::from_secs(2)).await;
    chat.paint_chargesend();
    enter(&mut chat, KeyEventKind::Release);
    assert_effort(
        &next_submit_op(&mut op_rx),
        ReasoningEffortConfig::Max,
        ModeKind::Default,
    );
    assert_eq!(chat.effective_collaboration_mode(), intended);
}

#[tokio::test(start_paused = true)]
async fn chargesend_followup_explicitly_restores_intended_effort_and_echoes() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    chat.set_reasoning_effort(Some(ReasoningEffortConfig::High));
    enter(&mut chat, KeyEventKind::Press);
    tokio::time::advance(Duration::from_secs(4)).await;
    chat.paint_chargesend();
    enter(&mut chat, KeyEventKind::Release);
    let charged = next_submit_op(&mut op_rx);
    let Op::UserTurn {
        collaboration_mode: Some(sent),
        ..
    } = &charged
    else {
        unreachable!()
    };
    let intended = chat
        .chargesend_echo_mode(sent)
        .expect("charge echo is recognized");
    assert_eq!(
        intended.reasoning_effort(),
        Some(ReasoningEffortConfig::High)
    );
    assert!(
        chat.chargesend_echo_mode(sent).is_none(),
        "echo consumed once"
    );
    let mut backend = StickyBackend::default();
    backend.accept(charged);
    backend.drain(&mut op_rx);
    reset_idle(&mut chat);
    // Use an existing submit shortcut to bypass charging on the next prompt.
    let message = UserMessage {
        text: "next".to_string(),
        local_images: Vec::new(),
        remote_image_urls: Vec::new(),
        text_elements: Vec::new(),
        mention_bindings: Vec::new(),
    };
    chat.submit_user_message(message);
    let ordinary = next_submit_op(&mut op_rx);
    assert_effort(&ordinary, ReasoningEffortConfig::High, ModeKind::Default);
    backend.accept(ordinary);
    assert_eq!(
        backend.captured,
        vec![
            Some(ReasoningEffortConfig::Low),
            Some(ReasoningEffortConfig::High)
        ]
    );
}

#[tokio::test]
async fn chargesend_unset_default_and_plan_override_are_consistent() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    chat.set_reasoning_effort(None);
    enter(&mut chat, KeyEventKind::Press);
    enter(&mut chat, KeyEventKind::Release);
    assert_effort(
        &next_submit_op(&mut op_rx),
        ReasoningEffortConfig::Medium,
        ModeKind::Default,
    );
    let mut backend = StickyBackend::default();
    backend.drain(&mut op_rx);
    reset_idle(&mut chat);
    chat.submit_user_message(UserMessage {
        text: "next".to_string(),
        local_images: Vec::new(),
        remote_image_urls: Vec::new(),
        text_elements: Vec::new(),
        mention_bindings: Vec::new(),
    });
    assert_effort(
        &next_submit_op(&mut op_rx),
        ReasoningEffortConfig::Medium,
        ModeKind::Default,
    );
    assert_eq!(chat.effective_reasoning_effort(), None);

    let (mut chat, _rx, mut op_rx) = fixture().await;
    let mask = collaboration_modes::plan_mask(chat.model_catalog.as_ref()).unwrap();
    chat.set_collaboration_mask(mask);
    chat.set_plan_mode_reasoning_effort(Some(ReasoningEffortConfig::High));
    let global = chat.current_collaboration_mode.clone();
    enter(&mut chat, KeyEventKind::Press);
    enter(&mut chat, KeyEventKind::Release);
    assert_effort(
        &next_submit_op(&mut op_rx),
        ReasoningEffortConfig::High,
        ModeKind::Plan,
    );
    assert_eq!(
        chat.config.plan_mode_reasoning_effort,
        Some(ReasoningEffortConfig::High)
    );
    assert_eq!(chat.current_collaboration_mode, global);
    reset_idle(&mut chat);
    chat.submit_user_message(UserMessage {
        text: "plan next".to_string(),
        local_images: Vec::new(),
        remote_image_urls: Vec::new(),
        text_elements: Vec::new(),
        mention_bindings: Vec::new(),
    });
    assert_effort(
        &next_submit_op(&mut op_rx),
        ReasoningEffortConfig::High,
        ModeKind::Plan,
    );
}

#[tokio::test]
async fn chargesend_image_preparation_retains_its_prompt_effort() {
    let (mut chat, mut rx, mut op_rx) = fixture().await;
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("image.png");
    image::RgbaImage::from_pixel(2, 2, image::Rgba([0, 0, 0, 255]))
        .save(&path)
        .unwrap();
    chat.snapshot_local_images = true;
    draft(&mut chat, "image prompt");
    chat.attach_image(path);
    assert!(chat.current_model_supports_images());
    assert!(
        chat.chargesend_context().is_some(),
        "image composer must be eligible"
    );
    enter(&mut chat, KeyEventKind::Press);
    assert!(
        chat.chargesend_active(),
        "image Enter press must start a charge"
    );
    enter(&mut chat, KeyEventKind::Release);
    assert!(
        chat.pending_image_submission.is_some(),
        "image preparation missing; operation {:?}; remaining text {:?}; images {}",
        op_rx.try_recv(),
        chat.bottom_pane.composer_text(),
        chat.bottom_pane.composer_local_images().len()
    );
    assert_no_submit_op(&mut op_rx);
    let id = tokio::time::timeout(Duration::from_secs(10), async {
        loop {
            if let AppEvent::ImagesPrepared(id) = rx.recv().await.expect("image worker event") {
                break id;
            }
        }
    })
    .await
    .unwrap();
    chat.on_images_prepared(id);
    assert_effort(
        &next_submit_op(&mut op_rx),
        ReasoningEffortConfig::Low,
        ModeKind::Default,
    );
}

#[tokio::test(start_paused = true)]
async fn chargesend_bar_uses_measured_composer_space_at_narrow_widths() {
    let (mut chat, _rx, _op_rx) = fixture().await;
    enter(&mut chat, KeyEventKind::Press);
    chat.paint_chargesend();
    let mut snapshots = Vec::new();
    for width in [8, 24, 80] {
        let height = chat.bottom_pane.desired_height(width);
        let area = ratatui::layout::Rect::new(0, 0, width, height);
        let mut buffer = ratatui::buffer::Buffer::empty(area);
        chat.bottom_pane.render(area, &mut buffer);
        let visible = buffer
            .content
            .chunks(usize::from(width))
            .map(|row| {
                row.iter()
                    .map(ratatui::buffer::Cell::symbol)
                    .collect::<String>()
                    .trim_end()
                    .to_string()
            })
            .collect::<Vec<_>>()
            .join("\n");
        assert!(
            visible.contains("Low"),
            "effort label must survive clipping at {width} columns"
        );
        assert_eq!(chat.bottom_pane.composer_text(), "hello");
        snapshots.push(format!("{width} columns:\n{visible}"));
    }
    insta::assert_snapshot!(snapshots.join("\n\n"), @"
    8 columns:

    › hello


      Low

    24 columns:

    › hello

      Low        [----------

    80 columns:

    › hello

      Low        [------------] ^ · release Enter to send · Esc cancels
    ");
}

#[tokio::test]
async fn chargesend_pending_images_restore_on_mode_change() {
    let (mut chat, mut rx, mut op_rx) = fixture().await;
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("image.png");
    image::RgbaImage::from_pixel(2, 2, image::Rgba([0, 0, 0, 255]))
        .save(&path)
        .unwrap();
    chat.snapshot_local_images = true;
    draft(&mut chat, "keep image");
    chat.attach_image(path);
    enter(&mut chat, KeyEventKind::Press);
    assert!(
        chat.chargesend_active(),
        "image Enter press must start a charge"
    );
    enter(&mut chat, KeyEventKind::Release);
    assert!(
        chat.pending_image_submission.is_some(),
        "expected delayed image preparation"
    );
    chat.set_reasoning_effort(Some(ReasoningEffortConfig::Medium));
    let id = tokio::time::timeout(Duration::from_secs(10), async {
        loop {
            if let AppEvent::ImagesPrepared(id) = rx.recv().await.expect("image worker event") {
                break id;
            }
        }
    })
    .await
    .unwrap();
    chat.on_images_prepared(id);
    assert_no_submit_op(&mut op_rx);
    assert!(chat.bottom_pane.composer_text().contains("keep image"));
    assert_eq!(chat.bottom_pane.composer_local_images().len(), 1);
}

#[tokio::test(start_paused = true)]
async fn chargesend_tap_and_initial_bar_follow_selected_effort_between_turns() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    catalog(
        &mut chat,
        vec![
            ReasoningEffortConfig::Low,
            ReasoningEffortConfig::Medium,
            ReasoningEffortConfig::High,
            ReasoningEffortConfig::XHigh,
            ReasoningEffortConfig::Max,
        ],
    );
    let config_file = chat.config.codex_home.join("config.toml");
    let original_file = std::fs::read(&config_file).ok();
    let mut bars = Vec::new();
    for selected in [
        ReasoningEffortConfig::Low,
        ReasoningEffortConfig::High,
        ReasoningEffortConfig::XHigh,
        ReasoningEffortConfig::Medium,
        ReasoningEffortConfig::Max,
    ] {
        reset_idle(&mut chat);
        draft(&mut chat, "next prompt");
        chat.set_reasoning_effort(Some(selected.clone()));
        let intended = chat.effective_collaboration_mode();
        enter(&mut chat, KeyEventKind::Press);
        chat.paint_chargesend();
        let width = 100;
        let area = ratatui::layout::Rect::new(0, 0, width, chat.bottom_pane.desired_height(width));
        let mut buffer = ratatui::buffer::Buffer::empty(area);
        chat.bottom_pane.render(area, &mut buffer);
        let footer = buffer
            .content
            .chunks(usize::from(width))
            .find_map(|row| {
                let line: String = row.iter().map(ratatui::buffer::Cell::symbol).collect();
                line.contains("release Enter to send")
                    .then(|| line.trim_end().to_owned())
            })
            .expect("charge footer is rendered");
        bars.push(format!("{selected}:\n{footer}"));
        tokio::time::advance(Duration::from_millis(100)).await;
        enter(&mut chat, KeyEventKind::Release);
        assert_effort(&next_submit_op(&mut op_rx), selected, ModeKind::Default);
        assert_eq!(chat.effective_collaboration_mode(), intended);
        assert_eq!(std::fs::read(&config_file).ok(), original_file);
    }
    insta::assert_snapshot!(bars.join("\n\n"), @"
    low:
      Low        [------------] ^ · release Enter to send · Esc cancels

    high:
      High       [======------] ^ · release Enter to send · Esc cancels

    xhigh:
      Extra high [=========---] ^ · release Enter to send · Esc cancels

    medium:
      Medium     [===---------] ^ · release Enter to send · Esc cancels

    max:
      Max        [============] ^ · release Enter to send · Esc cancels
    ");
}

#[tokio::test]
async fn chargesend_selected_effort_uses_only_available_tiers() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    catalog(
        &mut chat,
        vec![
            ReasoningEffortConfig::Low,
            ReasoningEffortConfig::High,
            ReasoningEffortConfig::Max,
        ],
    );
    for (selected, expected) in [
        (ReasoningEffortConfig::XHigh, ReasoningEffortConfig::High),
        (ReasoningEffortConfig::Ultra, ReasoningEffortConfig::Max),
    ] {
        reset_idle(&mut chat);
        draft(&mut chat, "supported fallback");
        chat.set_reasoning_effort(Some(selected));
        let intended = chat.effective_collaboration_mode();
        enter(&mut chat, KeyEventKind::Press);
        enter(&mut chat, KeyEventKind::Release);
        assert_effort(&next_submit_op(&mut op_rx), expected, ModeKind::Default);
        assert_eq!(chat.effective_collaboration_mode(), intended);
    }
}

fn working_text(chat: &ChatWidget) -> String {
    let width = 80;
    let area = ratatui::layout::Rect::new(0, 0, width, chat.bottom_pane.desired_height(width));
    let mut buffer = ratatui::buffer::Buffer::empty(area);
    chat.bottom_pane.render(area, &mut buffer);
    buffer
        .content
        .iter()
        .map(ratatui::buffer::Cell::symbol)
        .collect()
}

#[tokio::test(start_paused = true)]
async fn chargesend_working_label_tracks_active_request_and_queued_next_turn() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    catalog(
        &mut chat,
        vec![
            ReasoningEffortConfig::Low,
            ReasoningEffortConfig::Medium,
            ReasoningEffortConfig::High,
            ReasoningEffortConfig::XHigh,
            ReasoningEffortConfig::Max,
        ],
    );
    chat.set_reasoning_effort(Some(ReasoningEffortConfig::XHigh));
    enter(&mut chat, KeyEventKind::Press);
    tokio::time::advance(Duration::from_secs(2)).await;
    chat.paint_chargesend();
    enter(&mut chat, KeyEventKind::Release);
    assert_effort(
        &next_submit_op(&mut op_rx),
        ReasoningEffortConfig::Max,
        ModeKind::Default,
    );
    chat.on_task_started();
    assert_eq!(
        chat.chargesend.active_effort,
        Some(ReasoningEffortConfig::Max)
    );
    assert!(working_text(&chat).contains("to interrupt) · Max Reasoning"));
    draft(&mut chat, "queued follow-up");
    chat.handle_key_event(KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE));
    assert!(chat.input_queue.has_queued_follow_up_messages());
    assert_no_submit_op(&mut op_rx);
    assert!(working_text(&chat).contains("to interrupt) · Max Reasoning"));
    // Streaming can temporarily remove and recreate the status row.
    chat.bottom_pane.hide_status_indicator();
    chat.bottom_pane.ensure_status_indicator();
    assert!(working_text(&chat).contains("to interrupt) · Max Reasoning"));
    chat.on_task_complete(None, None, false);
    assert_effort(
        &next_submit_op(&mut op_rx),
        ReasoningEffortConfig::XHigh,
        ModeKind::Default,
    );
    chat.on_task_started();
    assert!(working_text(&chat).contains("to interrupt) · xHigh Reasoning"));
    assert_eq!(
        chat.chargesend.active_effort,
        Some(ReasoningEffortConfig::XHigh)
    );
    chat.on_task_complete(None, None, false);
    assert!(chat.chargesend.active_effort.is_none());
    assert!(!working_text(&chat).contains("Reasoning"));
}

#[tokio::test]
async fn chargesend_working_label_restores_effort_and_ignores_busy_steering() {
    let (mut chat, _rx, mut op_rx) = fixture().await;
    chat.set_reasoning_effort(Some(ReasoningEffortConfig::High));
    chat.on_task_started();
    assert!(working_text(&chat).contains("to interrupt) · High Reasoning"));
    chat.set_reasoning_effort(Some(ReasoningEffortConfig::Medium));
    draft(&mut chat, "steer this turn");
    enter(&mut chat, KeyEventKind::Press);
    let _steer = next_submit_op(&mut op_rx);
    assert_eq!(
        chat.chargesend.active_effort,
        Some(ReasoningEffortConfig::High)
    );
    assert!(working_text(&chat).contains("to interrupt) · High Reasoning"));
}
