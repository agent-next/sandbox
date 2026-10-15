use std::io::{self, Read};

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let parts: Vec<&str> = input.split_whitespace().collect();
    let lo: usize = parts[0].parse().unwrap();
    let hi: usize = parts[1].parse().unwrap();
    if hi < 2 {
        println!("0");
        return;
    }
    let mut sieve = vec![false; hi + 1];
    let mut i = 2;
    while i * i <= hi {
        if !sieve[i] {
            let mut j = i * i;
            while j <= hi {
                sieve[j] = true;
                j += i;
            }
        }
        i += 1;
    }
    let mut count = 0;
    for i in lo..=hi {
        if i >= 2 && !sieve[i] {
            count += 1;
        }
    }
    println!("{}", count);
}
