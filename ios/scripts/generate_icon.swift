// Generates the 1024×1024 app icon using CoreGraphics. Run via:
//   swift ios/scripts/generate_icon.swift
// Output lands at ios/InverterMonitor/InverterMonitor/Resources/Assets.xcassets/AppIcon.appiconset/icon-1024.png

import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

let size: CGFloat = 1024
let bounds = CGRect(x: 0, y: 0, width: size, height: size)

let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!
guard let ctx = CGContext(
    data: nil,
    width: Int(size),
    height: Int(size),
    bitsPerComponent: 8,
    bytesPerRow: 0,
    space: colorSpace,
    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
) else {
    FileHandle.standardError.write("Failed to create bitmap context\n".data(using: .utf8)!)
    exit(1)
}

// ---- Background: deep-navy → indigo gradient matching the app's immersiveBackground
let bgColors = [
    CGColor(srgbRed: 0.06, green: 0.09, blue: 0.16, alpha: 1.0),   // #0F172A
    CGColor(srgbRed: 0.05, green: 0.12, blue: 0.24, alpha: 1.0),
    CGColor(srgbRed: 0.10, green: 0.10, blue: 0.30, alpha: 1.0)    // indigo
]
let bgGradient = CGGradient(colorsSpace: colorSpace,
                            colors: bgColors as CFArray,
                            locations: [0, 0.5, 1])!
ctx.drawLinearGradient(bgGradient,
                       start: CGPoint(x: 0, y: size),
                       end: CGPoint(x: size, y: 0),
                       options: [])

// ---- Radial glow behind the main mark
let glowColors = [
    CGColor(srgbRed: 0.988, green: 0.827, blue: 0.302, alpha: 0.35), // solar amber
    CGColor(srgbRed: 0.988, green: 0.827, blue: 0.302, alpha: 0.0)
]
let glowGradient = CGGradient(colorsSpace: colorSpace,
                              colors: glowColors as CFArray,
                              locations: [0, 1])!
ctx.drawRadialGradient(glowGradient,
                       startCenter: CGPoint(x: size / 2, y: size / 2 + 40),
                       startRadius: 0,
                       endCenter: CGPoint(x: size / 2, y: size / 2 + 40),
                       endRadius: size * 0.55,
                       options: [])

// ---- Sun: stylized circle with 8 rays, top half of the icon
let sunCenter = CGPoint(x: size / 2, y: size * 0.62)
let sunRadius: CGFloat = size * 0.14
let rayInner = sunRadius + 24
let rayOuter = sunRadius + 92
let solarColor = CGColor(srgbRed: 0.988, green: 0.827, blue: 0.302, alpha: 1.0)
let solarBright = CGColor(srgbRed: 1.0, green: 0.93, blue: 0.55, alpha: 1.0)

// Sun body with soft radial fill
let sunGrad = CGGradient(colorsSpace: colorSpace,
                         colors: [solarBright, solarColor] as CFArray,
                         locations: [0, 1])!
ctx.saveGState()
ctx.addEllipse(in: CGRect(x: sunCenter.x - sunRadius,
                          y: sunCenter.y - sunRadius,
                          width: sunRadius * 2, height: sunRadius * 2))
ctx.clip()
ctx.drawRadialGradient(sunGrad,
                       startCenter: CGPoint(x: sunCenter.x - 10, y: sunCenter.y + 20),
                       startRadius: 2,
                       endCenter: sunCenter,
                       endRadius: sunRadius,
                       options: [])
ctx.restoreGState()

// Rays — tapered capsules at 8 directions
ctx.setFillColor(solarColor)
for i in 0..<8 {
    let angle = CGFloat(i) * .pi / 4
    ctx.saveGState()
    ctx.translateBy(x: sunCenter.x, y: sunCenter.y)
    ctx.rotate(by: angle)
    let rayWidth: CGFloat = 22
    let path = CGMutablePath()
    path.move(to: CGPoint(x: -rayWidth / 2, y: rayInner))
    path.addLine(to: CGPoint(x: rayWidth / 2, y: rayInner))
    path.addLine(to: CGPoint(x: rayWidth / 3, y: rayOuter))
    path.addLine(to: CGPoint(x: -rayWidth / 3, y: rayOuter))
    path.closeSubpath()
    ctx.addPath(path)
    ctx.fillPath()
    ctx.restoreGState()
}

// ---- Lightning bolt in the center of the sun — the "inverter" accent
let boltPath = CGMutablePath()
let bx = sunCenter.x
let by = sunCenter.y
let boltScale: CGFloat = 1.0
// Build a stylized bolt as a polygon.
let boltPoints: [CGPoint] = [
    CGPoint(x: bx - 18 * boltScale, y: by + 68 * boltScale),   // top-left
    CGPoint(x: bx + 26 * boltScale, y: by + 68 * boltScale),   // top-right
    CGPoint(x: bx + 4 * boltScale,  y: by + 6  * boltScale),   // mid-right
    CGPoint(x: bx + 30 * boltScale, y: by + 6  * boltScale),   // step
    CGPoint(x: bx - 8  * boltScale, y: by - 72 * boltScale),   // bottom
    CGPoint(x: bx + 10 * boltScale, y: by - 8  * boltScale),   // mid-left step
    CGPoint(x: bx - 18 * boltScale, y: by - 8  * boltScale)    // inner left
]
boltPath.addLines(between: boltPoints)
boltPath.closeSubpath()
ctx.setFillColor(CGColor(srgbRed: 0.06, green: 0.09, blue: 0.16, alpha: 1.0))
ctx.addPath(boltPath)
ctx.fillPath()

// ---- "Solar panel" slab at the bottom — 3x2 cell grid, tilted
ctx.saveGState()
let panelCenter = CGPoint(x: size / 2, y: size * 0.24)
ctx.translateBy(x: panelCenter.x, y: panelCenter.y)
ctx.rotate(by: -0.18) // slight tilt

let panelW: CGFloat = size * 0.56
let panelH: CGFloat = size * 0.22
let panelRect = CGRect(x: -panelW / 2, y: -panelH / 2, width: panelW, height: panelH)

// Panel body with glass-blue gradient
let panelColors = [
    CGColor(srgbRed: 0.22, green: 0.42, blue: 0.72, alpha: 1.0),
    CGColor(srgbRed: 0.12, green: 0.22, blue: 0.40, alpha: 1.0)
]
let panelGradient = CGGradient(colorsSpace: colorSpace,
                               colors: panelColors as CFArray,
                               locations: [0, 1])!
ctx.saveGState()
let panelClip = CGPath(roundedRect: panelRect, cornerWidth: 22, cornerHeight: 22, transform: nil)
ctx.addPath(panelClip)
ctx.clip()
ctx.drawLinearGradient(panelGradient,
                       start: CGPoint(x: 0, y: -panelH / 2),
                       end: CGPoint(x: 0, y: panelH / 2),
                       options: [])
// Cell grid
ctx.setStrokeColor(CGColor(srgbRed: 0.05, green: 0.08, blue: 0.16, alpha: 0.9))
ctx.setLineWidth(6)
let cellCols = 4
let cellRows = 2
let cellW = panelW / CGFloat(cellCols)
let cellH = panelH / CGFloat(cellRows)
for c in 1..<cellCols {
    let x = -panelW / 2 + CGFloat(c) * cellW
    ctx.move(to: CGPoint(x: x, y: -panelH / 2))
    ctx.addLine(to: CGPoint(x: x, y: panelH / 2))
}
for r in 1..<cellRows {
    let y = -panelH / 2 + CGFloat(r) * cellH
    ctx.move(to: CGPoint(x: -panelW / 2, y: y))
    ctx.addLine(to: CGPoint(x: panelW / 2, y: y))
}
ctx.strokePath()
ctx.restoreGState()

// Panel outer border
ctx.setStrokeColor(CGColor(srgbRed: 0.988, green: 0.827, blue: 0.302, alpha: 0.85))
ctx.setLineWidth(10)
ctx.addPath(panelClip)
ctx.strokePath()

ctx.restoreGState()

// ---- Write PNG
guard let image = ctx.makeImage() else {
    FileHandle.standardError.write("Failed to create image\n".data(using: .utf8)!)
    exit(1)
}

let outPath = (ProcessInfo.processInfo.environment["OUT_PATH"] ??
    "ios/InverterMonitor/InverterMonitor/Resources/Assets.xcassets/AppIcon.appiconset/icon-1024.png")
let url = URL(fileURLWithPath: outPath, isDirectory: false)
try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                         withIntermediateDirectories: true)

guard let dest = CGImageDestinationCreateWithURL(url as CFURL,
                                                  UTType.png.identifier as CFString,
                                                  1, nil) else {
    FileHandle.standardError.write("Failed to create image destination\n".data(using: .utf8)!)
    exit(1)
}
CGImageDestinationAddImage(dest, image, nil)
if !CGImageDestinationFinalize(dest) {
    FileHandle.standardError.write("Failed to write PNG\n".data(using: .utf8)!)
    exit(1)
}

FileHandle.standardOutput.write("Wrote \(url.path)\n".data(using: .utf8)!)
