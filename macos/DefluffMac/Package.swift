// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "Defluff",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "Defluff", targets: ["Defluff"])
    ],
    targets: [
        .executableTarget(name: "Defluff")
    ]
)
