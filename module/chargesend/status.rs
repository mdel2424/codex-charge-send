// Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
//! Reserve one fixed-width dock for reasoning without moving working controls.
use crate::line_truncation::line_width;
use crate::line_truncation::truncate_line_with_ellipsis_if_overflow;
use ratatui::style::Stylize;
use ratatui::text::Line;

const LABEL_WIDTH: usize = 20;
const SEPARATOR: &str = " · ";
const DOCK_WIDTH: usize = LABEL_WIDTH + 3;

pub(crate) fn content_width(width: u16, core_width: usize, label: Option<&str>) -> u16 {
    if label.is_some() && usize::from(width) >= core_width + DOCK_WIDTH {
        width - DOCK_WIDTH as u16
    } else {
        width
    }
}

pub(crate) fn dock_reasoning(
    header: Line<'static>,
    label: Option<&str>,
    width: u16,
    content_width: u16,
) -> Line<'static> {
    let mut header = truncate_line_with_ellipsis_if_overflow(header, usize::from(content_width));
    if let Some(label) = label.filter(|_| content_width < width) {
        header.spans.push(
            " ".repeat(usize::from(content_width) - line_width(&header))
                .into(),
        );
        header.spans.push(SEPARATOR.dim());
        let label =
            truncate_line_with_ellipsis_if_overflow(Line::from(label.to_owned()), LABEL_WIDTH);
        let padding = LABEL_WIDTH - line_width(&label);
        header
            .spans
            .extend(label.spans.into_iter().map(|span| span.dim()));
        header.spans.push(" ".repeat(padding).into());
    }
    header
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn chargesend_working_label_dock_stays_fixed_across_efforts_and_timers() {
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
                let content = content_width(width, line_width(&Line::from(header)), Some(label));
                let line = dock_reasoning(Line::from(header), Some(label), width, content);
                assert_eq!(line_width(&line), usize::from(width));
                let text = line.to_string();
                assert!(text.starts_with(header));
                assert_eq!(
                    line_width(&Line::from(text.split(label).next().unwrap().to_owned())),
                    usize::from(width) - LABEL_WIDTH
                );
            }
        }
    }
    #[test]
    fn chargesend_working_dock_hides_without_wrapping_on_narrow_rows() {
        let header = "Working (0s • esc to interrupt)";
        for width in [8, 24, 40] {
            let content = content_width(
                width,
                line_width(&Line::from(header)),
                Some("Max Reasoning"),
            );
            assert_eq!(content, width);
            let line = dock_reasoning(Line::from(header), Some("Max Reasoning"), width, content);
            assert!(!line.to_string().contains("Reasoning"));
            assert!(line_width(&line) <= usize::from(width));
        }
    }
    #[test]
    fn chargesend_working_dock_clips_unicode_labels_and_long_inline_activity() {
        let label = "推論能力が非常に高い Reasoning";
        let content = content_width(80, 30, Some(label));
        let line = dock_reasoning(
            Line::from("Working (0s • esc to interrupt) · ".to_owned() + &"background ".repeat(20)),
            Some(label),
            80,
            content,
        );
        assert_eq!(line_width(&line), 80);
        assert!(line.to_string().contains('…'));
        assert!(line.to_string().contains("推論"));
    }
}

#[cfg(test)]
mod widget_tests {
    use crate::app_event_sender::AppEventSender;
    use crate::render::renderable::Renderable;
    use crate::status_indicator_widget::{StatusIndicatorWidget, StatusTimer};
    use crate::tui::FrameRequester;
    use ratatui::buffer::Buffer;
    use ratatui::layout::Rect;
    use tokio::sync::mpsc::unbounded_channel;

    #[test]
    fn chargesend_working_widget_dock_does_not_move_controls_or_change_height() {
        let (tx, _rx) = unbounded_channel();
        let mut row = StatusIndicatorWidget::new(
            AppEventSender::new(tx),
            FrameRequester::test_dummy(),
            false,
            Default::default(),
        );
        let mut timer = StatusTimer::default();
        timer.pause_at(std::time::Instant::now());
        timer.reset(std::time::Duration::ZERO);
        let mut control_cells = None;
        for label in [
            "Low Reasoning",
            "Medium Reasoning",
            "xHigh Reasoning",
            "Max Reasoning",
        ] {
            row.update_reasoning_label(Some(label.to_owned()));
            let indicator = row.with_timer(&timer);
            assert_eq!(indicator.desired_height(80), 1);
            let area = Rect::new(0, 0, 80, 1);
            let mut buffer = Buffer::empty(area);
            indicator.render(area, &mut buffer);
            let controls = buffer.content[..30].to_vec();
            if let Some(expected) = &control_cells {
                assert_eq!(&controls, expected);
            }
            control_cells = Some(controls);
            assert_eq!(buffer[(60, 0)].symbol(), &label[..1]);
            let text: String = buffer
                .content
                .iter()
                .map(ratatui::buffer::Cell::symbol)
                .collect();
            assert!(text.contains(label));
        }
        for width in [8, 24, 40] {
            let indicator = row.with_timer(&timer);
            assert_eq!(indicator.desired_height(width), 1);
            let area = Rect::new(0, 0, width, 1);
            let mut buffer = Buffer::empty(area);
            indicator.render(area, &mut buffer);
            let text: String = buffer
                .content
                .iter()
                .map(ratatui::buffer::Cell::symbol)
                .collect();
            assert!(!text.contains("Reasoning"));
        }
    }
}
