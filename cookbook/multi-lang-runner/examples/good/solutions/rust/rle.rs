use std::io::{self, Read, Write};

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let s = input.trim_end_matches('\n');
    if s.is_empty() {
        return;
    }
    let mut out = String::new();
    let chars: Vec<char> = s.chars().collect();
    let mut prev = chars[0];
    let mut count = 1usize;
    for &ch in &chars[1..] {
        if ch == prev {
            count += 1;
        } else {
            out.push_str(&count.to_string());
            out.push(prev);
            prev = ch;
            count = 1;
        }
    }
    out.push_str(&count.to_string());
    out.push(prev);
    out.push('\n');
    io::stdout().write_all(out.as_bytes()).unwrap();
}
