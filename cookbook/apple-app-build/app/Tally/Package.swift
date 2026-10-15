// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Tally",
    platforms: [.iOS(.v17)],
    products: [.library(name: "Tally", targets: ["Tally"])],
    targets: [.target(name: "Tally")]
)
