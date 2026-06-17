"""A small always-on-top floating widget — visible and clickable regardless of menu-bar crowding/notch.

A colored dot that shows Claudia's state and floats above everything:
    green = on · red = muted · orange = speaking · gray = silenced (on a call) · yellow = needs Accessibility
Click it to MUTE/unmute. Right-click for a menu (conversation, open panel, quit). Drag to reposition.
"""
import subprocess

import objc
from Foundation import NSObject, NSAttributedString, NSMakeRect, NSPoint
from AppKit import (
    NSPanel, NSButton, NSColor, NSFont, NSScreen, NSMenu, NSMenuItem,
    NSWindowStyleMaskBorderless, NSStatusWindowLevel, NSBackingStoreBuffered,
    NSForegroundColorAttributeName, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
)

_COLORS = {
    "on": lambda: NSColor.systemGreenColor(),
    "muted": lambda: NSColor.systemRedColor(),
    "speaking": lambda: NSColor.systemOrangeColor(),
    "call": lambda: NSColor.systemGrayColor(),
    "off": lambda: NSColor.darkGrayColor(),
    "nokey": lambda: NSColor.systemYellowColor(),
}


class _Handler(NSObject):
    def initWithApp_(self, app):
        self = objc.super(_Handler, self).init()
        if self is None:
            return None
        self.app = app
        return self

    def clicked_(self, sender):
        self.app.toggle_mute(None)

    def conv_(self, sender):
        self.app.toggle_conv(None)

    def panel_(self, sender):
        subprocess.run(["open", "http://127.0.0.1:4242"])

    def quit_(self, sender):
        import rumps
        rumps.quit_application()


class FloatingWidget:
    def __init__(self, app):
        self.handler = _Handler.alloc().initWithApp_(app)
        rect = NSMakeRect(0, 0, 52, 52)
        self.win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
        self.win.setLevel_(NSStatusWindowLevel)
        self.win.setOpaque_(False)
        self.win.setBackgroundColor_(NSColor.clearColor())
        self.win.setMovableByWindowBackground_(True)
        self.win.setHidesOnDeactivate_(False)
        self.win.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary)
        try:
            # visibleFrame accounts for the menu bar/dock AND the screen's real origin (multi-display).
            vf = NSScreen.mainScreen().visibleFrame()
            x = vf.origin.x + vf.size.width - 70
            y = vf.origin.y + vf.size.height - 64
            self.win.setFrameOrigin_(NSPoint(x, y))
        except Exception:
            pass

        self.btn = NSButton.alloc().initWithFrame_(rect)
        self.btn.setBordered_(False)
        self.btn.setFont_(NSFont.systemFontOfSize_(42))
        self.btn.setTarget_(self.handler)
        self.btn.setAction_("clicked:")
        self.btn.setToolTip_("Click to mute · right-click for more")

        menu = NSMenu.alloc().init()
        for title, action in (("Conversation mode", "conv:"),
                              ("Open control panel", "panel:"),
                              ("Quit Claudia", "quit:")):
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            it.setTarget_(self.handler)
            menu.addItem_(it)
        self.btn.setMenu_(menu)

        self.win.setContentView_(self.btn)
        self.win.orderFrontRegardless()
        self.set_state("on")

    def set_state(self, state):
        color = _COLORS.get(state, _COLORS["on"])()
        attr = NSAttributedString.alloc().initWithString_attributes_(
            "●", {NSForegroundColorAttributeName: color})
        self.btn.setAttributedTitle_(attr)
