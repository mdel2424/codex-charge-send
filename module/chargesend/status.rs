// Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
//! Append the running turn's effort after the working timer/interrupt controls.
use crate::line_truncation::line_width;
use crate::line_truncation::truncate_line_with_ellipsis_if_overflow;
use ratatui::style::Stylize;
use ratatui::text::Line;

const LABEL_WIDTH: usize = 20;
const SEPARATOR: &str = " · ";

pub(crate) fn append_reasoning(
    mut header: Line<'static>,
    label: Option<&str>,
    width: u16,
) -> Line<'static> {
    if let Some(label) = label.filter(|label| !label.is_empty()) {
        let label =
            truncate_line_with_ellipsis_if_overflow(Line::from(label.to_owned()), LABEL_WIDTH);
        if line_width(&header) + SEPARATOR.chars().count() + line_width(&label)
            <= usize::from(width)
        {
            header.spans.push(SEPARATOR.dim());
            header
                .spans
                .extend(label.spans.into_iter().map(Stylize::dim));
        }
    }
    header
}

#[cfg(test)]
mod tests {
    use super::*;
    use pretty_assertions::assert_eq;

    #[test]
    fn chargesend_working_label_follows_controls_across_efforts_and_timers() {
        for (width, header) in [
            (80, "Working (9s • esc to interrupt)"),
            (80, "Working (1m 34s • esc to interrupt)"),
            (100, "Working (1h 02m 34s • esc to interrupt)"),
        ] {
            for label in [
                "Low Reasoning",
                "Medium Reasoning",
                "xHigh Reasoning",
                "Max Reasoning",
            ] {
                let line = append_reasoning(Line::from(header), Some(label), width);
                assert_eq!(line.to_string(), format!("{header} · {label}"));
                assert!(line_width(&line) <= usize::from(width));
            }
        }
    }

    #[test]
    fn chargesend_working_label_hides_only_when_controls_and_label_cannot_fit() {
        let header = "Working (0s • esc to interrupt)";
        let label = "Max Reasoning";
        let exact_width = (line_width(&Line::from(header)) + 3 + label.len()) as u16;
        for width in [8, 24, 40, exact_width - 1] {
            let line = append_reasoning(Line::from(header), Some(label), width);
            assert_eq!(line, Line::from(header));
        }
        let line = append_reasoning(Line::from(header), Some(label), exact_width);
        assert_eq!(line_width(&line), usize::from(exact_width));
        assert_eq!(line.to_string(), format!("{header} · {label}"));
        for label in [None, Some("")] {
            assert_eq!(
                append_reasoning(Line::from(header), label, 80),
                Line::from(header)
            );
        }
    }

    #[test]
    fn chargesend_working_label_clips_unicode_by_display_width() {
        let header = "Working (0s • esc to interrupt)";
        let label = "推論能力が非常に高い Reasoning";
        let line = append_reasoning(Line::from(header), Some(label), 80);
        assert!(line.to_string().starts_with(&format!("{header} · 推論")));
        assert!(line.to_string().ends_with('…'));
        assert!(line_width(&line) <= line_width(&Line::from(header)) + 3 + LABEL_WIDTH);
    }
}

#[cfg(test)]
mod widget_tests {
    use crate::app_event_sender::AppEventSender;
    use crate::render::renderable::Renderable;
    use crate::status_indicator_widget::{StatusIndicatorWidget, StatusTimer};
    use crate::tui::FrameRequester;
    use pretty_assertions::assert_eq;
    use ratatui::buffer::Buffer;
    use ratatui::layout::Rect;
    use tokio::sync::mpsc::unbounded_channel;

    fn render(row: &StatusIndicatorWidget, timer: &StatusTimer, width: u16) -> Buffer {
        let indicator = row.with_timer(timer);
        let area = Rect::new(0, 0, width, indicator.desired_height(width));
        let mut buffer = Buffer::empty(area);
        indicator.render(area, &mut buffer);
        buffer
    }

    #[test]
    fn chargesend_working_widget_suffix_does_not_move_controls_or_change_height() {
        let (tx, _rx) = unbounded_channel();
        let mut row = StatusIndicatorWidget::new(
            AppEventSender::new(tx),
            FrameRequester::test_dummy(),
            /*animations_enabled*/ false,
            Default::default(),
        );
        let mut timer = StatusTimer::default();
        timer.pause_at(std::time::Instant::now());
        timer.reset(std::time::Duration::ZERO);
        let original = render(&row, &timer, 80);
        for label in [
            "Low Reasoning",
            "Medium Reasoning",
            "xHigh Reasoning",
            "Max Reasoning",
        ] {
            row.update_reasoning_label(Some(label.to_owned()));
            let buffer = render(&row, &timer, 80);
            assert_eq!(buffer.area.height, 1);
            assert_eq!(&buffer.content[..30], &original.content[..30]);
            let text: String = buffer
                .content
                .iter()
                .map(ratatui::buffer::Cell::symbol)
                .collect();
            assert!(text.starts_with(&format!("Working (0s • esc to interrupt) · {label}")));
        }
        for width in [8, 24, 40] {
            let buffer = render(&row, &timer, width);
            assert_eq!(buffer.area.height, 1);
            let text: String = buffer
                .content
                .iter()
                .map(ratatui::buffer::Cell::symbol)
                .collect();
            assert!(!text.contains("Reasoning"));
        }
    }

    #[test]
    fn chargesend_working_suffix_keeps_label_at_exact_fit_with_activity() {
        let (tx, _rx) = unbounded_channel();
        let mut row = StatusIndicatorWidget::new(
            AppEventSender::new(tx),
            FrameRequester::test_dummy(),
            /*animations_enabled*/ false,
            Default::default(),
        );
        let mut timer = StatusTimer::default();
        timer.pause_at(std::time::Instant::now());
        timer.reset(std::time::Duration::ZERO);
        row.update_reasoning_label(Some("Max Reasoning".to_owned()));
        row.update_inline_message(Some("3 background terminals".to_owned()));
        let expected = "Working (0s • esc to interrupt) · Max Reasoning";
        let buffer = render(&row, &timer, expected.chars().count() as u16);
        let text: String = buffer
            .content
            .iter()
            .map(ratatui::buffer::Cell::symbol)
            .collect();
        assert_eq!(text, expected);
        assert_eq!(buffer.area.height, 1);
    }

    #[test]
    fn chargesend_working_suffix_rendering_snapshot() {
        let (tx, _rx) = unbounded_channel();
        let mut row = StatusIndicatorWidget::new(
            AppEventSender::new(tx),
            FrameRequester::test_dummy(),
            /*animations_enabled*/ false,
            Default::default(),
        );
        let mut timer = StatusTimer::default();
        timer.pause_at(std::time::Instant::now());
        timer.reset(std::time::Duration::from_secs(94));
        let mut snapshots = Vec::new();
        for (width, label, activity, hook) in [
            (80, None, None, None),
            (80, Some("xHigh Reasoning"), None, None),
            (
                80,
                Some("Max Reasoning"),
                Some("3 background terminals"),
                None,
            ),
            (
                60,
                Some("Max Reasoning"),
                Some("3 background terminals"),
                None,
            ),
            (
                60,
                Some("Max Reasoning"),
                None,
                Some("Running SessionStart hook"),
            ),
            (40, Some("Max Reasoning"), None, None),
        ] {
            row.update_reasoning_label(label.map(str::to_owned));
            row.update_inline_message(activity.map(str::to_owned));
            row.update_hook_status_message(hook.map(str::to_owned));
            let buffer = render(&row, &timer, width);
            let visible = buffer
                .content
                .chunks(usize::from(width))
                .map(|cells| {
                    cells
                        .iter()
                        .map(ratatui::buffer::Cell::symbol)
                        .collect::<String>()
                        .trim_end()
                        .to_owned()
                })
                .collect::<Vec<_>>()
                .join("\n");
            snapshots.push(format!("{width} columns:\n{visible}"));
        }
        insta::assert_snapshot!(snapshots.join("\n\n"), @"
        80 columns:
        Working (1m 34s • esc to interrupt)

        80 columns:
        Working (1m 34s • esc to interrupt) · xHigh Reasoning

        80 columns:
        Working (1m 34s • esc to interrupt) · Max Reasoning · 3 background terminals

        60 columns:
        Working (1m 34s • esc to interrupt) · Max Reasoning · 3 bac…

        60 columns:
        Working (1m 34s • esc to interrupt) · Max Reasoning
          └ Running SessionStart hook

        40 columns:
        Working (1m 34s • esc to interrupt)
        ");
    }
}
