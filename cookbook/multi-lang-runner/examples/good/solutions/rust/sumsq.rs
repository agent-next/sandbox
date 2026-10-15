use std::io::{self, Read};

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let mut parts = input.split_whitespace();
    let n: usize = parts.next().unwrap().parse().unwrap();
    let mut total: i64 = 0;
    for _ in 0..n {
        let x: i64 = parts.next().unwrap().parse().unwrap();
        total += x * x;
        if total > 1_000_000_000_000_000_000 {
            total = 1_000_000_000_000_000_000;
            break;
        }
    }
    println!("{}", total);
}
