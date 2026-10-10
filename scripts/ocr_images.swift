// macOS: swift scripts/ocr_images.swift image.png [image2.png ...]
// Searchable OCR derivative only; original images remain the authoritative source.
import Foundation
import Vision
import ImageIO

for file in CommandLine.arguments.dropFirst() {
    let url = URL(fileURLWithPath: file)
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    do {
        try VNImageRequestHandler(url: url, options: [:]).perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        let output = URL(fileURLWithPath: "archive/extracted/" + url.lastPathComponent + ".ocr.txt")
        try lines.joined(separator: "\n").write(to: output, atomically: true, encoding: .utf8)
        print("\(url.lastPathComponent): \(lines.count) lines")
    } catch {
        fputs("OCR failed for \(file): \(error)\n", stderr)
        exit(1)
    }
}
