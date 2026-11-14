import AppKit
import Foundation

// Disposable native acceptance fixture. No network, clipboard, accounts or
// user document access. A bounded lifetime prevents an orphaned UI process.
final class Probe: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var label: NSTextField!
    var count = 0
    let receipt: URL
    let nonce: String
    init(receipt: URL, nonce: String) {
        self.receipt = receipt
        self.nonce = nonce
    }
    func record(_ stage: String) {
        let value: [String: Any] = [
            "schema": "mastermind.native_app_use_probe.v1",
            "nonce": nonce, "pid": ProcessInfo.processInfo.processIdentifier,
            "count": count, "stage": stage
        ]
        if let bytes = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) {
            try? bytes.write(to: receipt, options: .atomic)
        }
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 420, height: 200),
            styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Mastermind native app use proof"
        window.setAccessibilityIdentifier("mastermind-native-proof-window")
        let button = NSButton(title: "Increment proof", target: self, action: #selector(increment))
        button.frame = NSRect(x: 30, y: 95, width: 180, height: 36)
        button.setAccessibilityIdentifier("mastermind-native-proof-increment")
        label = NSTextField(labelWithString: "Proof count: 0")
        label.frame = NSRect(x: 30, y: 45, width: 330, height: 28)
        label.setAccessibilityIdentifier("mastermind-native-proof-count")
        window.contentView?.addSubview(button)
        window.contentView?.addSubview(label)
        window.orderBack(nil)
        record("ready")
        Timer.scheduledTimer(withTimeInterval: 180, repeats: false) { _ in
            NSApplication.shared.terminate(nil)
        }
    }
    @objc func increment() {
        count += 1
        label.stringValue = "Proof count: \(count)"
        record("clicked")
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let arguments = CommandLine.arguments
guard let index = arguments.firstIndex(of: "--receipt"), index + 1 < arguments.count,
      let nonceIndex = arguments.firstIndex(of: "--nonce"), nonceIndex + 1 < arguments.count else {
    exit(64)
}
let target = URL(fileURLWithPath: arguments[index + 1])
guard target.path.hasPrefix("/private/tmp/") || target.path.hasPrefix("/tmp/") else { exit(64) }
let app = NSApplication.shared
let delegate = Probe(receipt: target, nonce: arguments[nonceIndex + 1])
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
