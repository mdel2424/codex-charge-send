// Copyright 2026 ChargeSend contributors. Licensed under Apache-2.0.
//! Styled footer: charge position and advertised effort share a green-red scale.
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};

fn color(position: u16) -> Color {
    let position = position.min(1000);
    let (from, to, offset) = if position <= 500 {
        ((70i32, 200i32, 95i32), (240i32, 205i32, 70i32), position)
    } else {
        ((240, 205, 70), (235, 70, 65), position - 500)
    };
    let channel = |a: i32, b: i32| (a + (b - a) * i32::from(offset) / 500) as u8;
    Color::Rgb(
        channel(from.0, to.0),
        channel(from.1, to.1),
        channel(from.2, to.2),
    )
}

pub(crate) fn status_line(label: &str, permille: u16, descending: bool) -> Line<'static> {
    let filled = usize::from(permille.min(1000)) * 12 / 1000;
    let current = Style::default().fg(color(permille));
    let mut spans = vec![Span::styled(format!("{label} ["), current)];
    for index in 0..12 {
        spans.push(if index < filled {
            Span::styled("=", Style::default().fg(color((index * 1000 / 11) as u16)))
        } else {
            Span::styled("-", Style::default().fg(Color::DarkGray))
        });
    }
    spans.push(Span::styled("]", current));
    let direction = if descending { "v" } else { "^" };
    spans.push(Span::raw(format!(
        " {direction} · release Enter to send · Esc cancels"
    )));
    Line::from(spans)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn chargesend_gradient_endpoints_and_intermediate_colors() {
        let low = status_line("Low", 0, false);
        let max = status_line("Max", 1000, true);
        assert_eq!(low.spans[0].style.fg, Some(Color::Rgb(70, 200, 95)));
        assert_eq!(max.spans[0].style.fg, Some(Color::Rgb(235, 70, 65)));
        assert_eq!(max.spans[1].style.fg, low.spans[0].style.fg);
        assert_eq!(max.spans[12].style.fg, max.spans[0].style.fg);
        assert_ne!(max.spans[6].style.fg, max.spans[1].style.fg);
        assert_eq!(color(500), Color::Rgb(240, 205, 70));
    }
}
