"""Offline checks of the macOS takeover: finding the camera and its card in the I/O Registry, and unmounting the card
before Apple's mass-storage driver is detached. No device is touched: ioreg, diskutil and the USB driver are stubbed.

    python -I -B test_macos_takeover.py        (with pyusb installed; macos/.venv has it)
"""
import plistlib
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ct1_common as c
import ct1_stage2_service as service
import usb.core


def entry(cls, children=(), **props):
    return dict(props, IOObjectClass=cls, IORegistryEntryChildren=list(children))


def camera(pid=0x0DA5):
    """The shape of a Sony camera in Mass Storage mode (an A7 IV, as the PR recorded it): interface, Apple's driver, the card as a whole disk and a partition."""
    card = entry("IOMedia", [entry("IOMedia", **{"BSD Name": "disk4s1", "Whole": False})], **{"BSD Name": "disk4", "Whole": True})
    driver = entry("IOUSBMassStorageInterfaceNub", [entry("IOUSBMassStorageDriver", [entry("IOBlockStorageDriver", [card])])])
    interface = entry("IOUSBHostInterface", [driver], idVendor=c.SONY_VID, idProduct=pid, bInterfaceClass=8)
    return entry("IOUSBHostDevice", [interface], idVendor=c.SONY_VID, idProduct=pid, locationID=0x01100000,
                 **{"USB Product Name": "ILCE-7M4"})


def hub(*children):
    port = entry("AppleUSB20HubPort", children)
    return entry("IOUSBHostDevice", [entry("AppleUSB20Hub", [port])], idVendor=0x05E3, idProduct=0x0610)


class FakeSession:
    def __init__(self):
        self.events = []

    def log(self, kind, **fields):
        self.events.append(kind)

    def say(self, text):
        pass


class FakeDriver:
    def __init__(self, session, refuse=False):
        self.session = session
        self.refuse = refuse

    def reset(self):
        if self.refuse:
            raise usb.core.USBError("Access denied (insufficient permissions)")
        self.session.events.append("detach")


def fake_run(tops, unmount_code=0):
    def run(cmd, **kwargs):
        if cmd[0] == "ioreg":
            if tops is None:
                raise OSError("ioreg not found")
            return subprocess.CompletedProcess(cmd, 0, stdout=plistlib.dumps(tops, fmt=plistlib.FMT_XML))
        if cmd[:2] == ["diskutil", "unmountDisk"]:
            return subprocess.CompletedProcess(cmd, unmount_code, stdout="done " + cmd[2], stderr="")
        raise AssertionError("unexpected command %r" % cmd)
    return run


class IoregListing(unittest.TestCase):
    def rows(self, tops):
        with mock.patch.object(c.subprocess, "run", fake_run(tops)):
            return c.ioreg_sony_devices()

    def test_direct_camera_lists_its_whole_disk(self):
        rows = self.rows([camera()])
        self.assertEqual([r["disks"] for r in rows], [["disk4"]])
        self.assertEqual(rows[0]["instance_id"], "USB 054C:0DA5 at 0x01100000")

    def test_camera_behind_a_hub_is_found(self):
        self.assertEqual([r["disks"] for r in self.rows([hub(camera())])], [["disk4"]])

    def test_other_vendors_are_left_out(self):
        self.assertEqual(self.rows([hub()]), [])


class Takeover(unittest.TestCase):
    def take_over(self, tops, euid=0, unmount_code=0, refuse=False):
        self.session = FakeSession()
        with mock.patch.object(c.subprocess, "run", fake_run(tops, unmount_code)), \
                mock.patch("os.geteuid", return_value=euid, create=True):     # Windows has no os.geteuid
            service.take_over_from_macos(self.session, FakeDriver(self.session, refuse))
        return self.session.events

    def test_unmounts_before_detaching(self):
        events = self.take_over([hub(camera())])
        self.assertLess(events.index("unmount"), events.index("detach"))

    def test_stops_without_root(self):
        with self.assertRaisesRegex(c.StopTest, "admin rights"):
            self.take_over([camera()], euid=501)

    def test_stops_before_detaching_when_the_camera_is_not_listed(self):
        with self.assertRaisesRegex(c.StopTest, "not found in the macOS I/O Registry"):
            self.take_over([hub()])

    def test_stops_before_detaching_when_the_unmount_fails(self):
        with self.assertRaisesRegex(c.StopTest, "could not unmount"):
            self.take_over([camera()], unmount_code=1)
        self.assertNotIn("detach", self.session.events)

    def test_stops_before_detaching_when_the_listing_fails(self):
        with self.assertRaisesRegex(c.StopTest, "not found in the macOS I/O Registry.*ioreg not found"):
            self.take_over(None)
        self.assertNotIn("detach", self.session.events)

    def test_stops_when_macos_keeps_its_driver(self):
        with self.assertRaisesRegex(c.StopTest, "did not let go"):
            self.take_over([camera()], refuse=True)


if __name__ == "__main__":
    unittest.main()
