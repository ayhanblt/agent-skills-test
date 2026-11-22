import AppKit
import Vision
let image = NSImage(contentsOfFile: CommandLine.arguments[1])!
var rect = CGRect(origin: .zero, size: image.size)
let cg = image.cgImage(forProposedRect: &rect, context: nil, hints: nil)!
let request = VNRecognizeTextRequest()
try VNImageRequestHandler(cgImage: cg).perform([request])
for result in request.results ?? [] {
    if let value = result.topCandidates(1).first { print(value.string) }
}
