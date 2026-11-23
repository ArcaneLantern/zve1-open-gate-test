# ZV-E1 open gate: test kit (firmware 2.02)

<p><b>Not run on a ZV-E1 yet.</b> This is the A7S III open-gate kit, which works on an A7S III, rebuilt for the ZV-E1 from the ZV-E1's own firmware and tested only in emulation. The first person to run it is the first test. Everything it writes goes to RAM only, and a battery pull removes it.</p>

The kit records a true 3840 × 2560 (3:2) file of the whole sensor area in XAVC HS 4K and XAVC S 4K at 23.98p. It also shows the live view at 3:2 on the rear screen and adds an anamorphic preview on the C2 key.

**Why it should carry over:** the ZV-E1 has the A7S III's sensor (IMX510) and the same list of sensor modes, less one. The 4K mode and the full-height mode the patch borrows have the same table values as on the A7S III, except for a few documented differences (see `PORT_NOTES.md`). The picture records were rebuilt with the same model, and the scaler numbers come out the same as the A7S III's working version. The USB service route uses the same commands and login.

**What is different from the A7S III kit:**

- **The screen.** The ZV-E1 has a 3:2 rear screen and no viewfinder; the A7S III has 4:3 panels. So the screen step is the A7 IV's: the whole 3:2 picture fills the screen, with the focus frames.
- **The key.** The preview cycle is on **C2**: 3:2 → 2:1 (1.33x) → 2.25:1 (1.5x) → 2.4:1 (1.6x) → 3:2. While it is applied, C2's own function (Step zoom by default) is gone in movie mode.
- **Switching modes.** The ZV-E1 has no mode dial. Where the A7S III instructions say "dial on stills / movie", use the **Still/Movie/S&Q** button.

**What the A7S III showed, which may or may not happen here:**

- The live view was glitchy (purple, lower part black) whenever movie mode was entered from stills. Starting and stopping a short recording fixed it until the next visit to stills. The recorded file was always right.
- 60p distorted the picture and crashed the camera while the patch was applied.
- The power switch removed the patch.

| Launcher (`windows/` `.cmd`, `macos/` `.command`) | What it does | Writes to the camera? |
|---|---|---|
| `check_readonly` | Confirms the camera runs the 2.02 software the port was made from, and reads what every patch site holds. Verdict READY / NOT READY | No |
| `dump_info` | The same, plus facts for the port: the camera's logs, sensor register state, internal tables, the display tables | No |
| `open_gate_apply` | Applies the state in five steps (open gate, the screen at 3:2, the C2 preview), then one read-only session | **Yes: memory only** |
| `open_gate_apply_no_screen` | Only the three open-gate steps | **Yes: memory only** |
| `open_gate_putback` | Puts the five steps back | Yes: memory only |
| `screen_putback` | Puts the two screen steps back | Yes: memory only |

Nothing in this kit writes to the camera's firmware or to its settings.

## Before you start

1. The camera's menu must show **Ver. 2.02** (Setup, Setup Option, Version). On any other version, stop and tell us the version.
2. **USB Connection Mode: Mass Storage.** If asked on connection, choose **Image Transfer (MSC)**.
3. A charged battery. Do not record or play back while a step runs.
4. **Run `check_readonly` first.** The apply refuses to start until a check on your camera has said READY.

## Windows, once

1. Install Python 3.10 or later from python.org (with the "py launcher").
2. Run `windows/setup.cmd`.
3. Install the libusb-win32 driver for the camera with [Zadig](https://zadig.akeo.ie): Options, List All Devices, pick the camera, choose libusb-win32, Replace Driver. The first run switches the camera to service mode, where it shows up as a new device (054C:0336): install the driver for that one too, then run the step again.

## macOS, once

1. Python 3.9 or later: the one macOS offers with the Xcode Command Line Tools (run `xcode-select --install` in Terminal) works, or install it from python.org.
2. Double-click `macos/setup.command`. No Homebrew and no driver are needed.
3. Use the `.command` launchers in `macos/`, which match the Windows ones.

Each live run asks for your Mac password. macOS keeps its own driver on the camera's USB connection, and only an administrator can hand the camera over to the script. The script unmounts the camera's memory card first and does not erase anything on it.

If macOS refuses to open a .command file, open System Settings > Privacy & Security and click "Open Anyway". Or, in Terminal, type `bash` and a space, drag the file in, and press Return.

## Android

`android/ZVE1-OpenGate.apk` runs the same files from a phone connected by USB-C (or an OTG adapter). Only the USB access, the dialogs and the folder for the results are the phone's.

1. Install the APK (allow installing from unknown sources). Set the camera's **USB Power Supply to Off**, or it charges from the phone.
2. Press **1. Read-only check**, then **2. Apply to camera**. The "Screen steps" box chooses between five steps (ticked) and three.
3. When Android asks to open *ZV-E1 Open Gate* for the camera, tick **Always**. It asks twice: once for Mass Storage, once for service mode.
4. When the log says **unplug and plug in again**, do that with the phone cable. Never switch the camera off.
5. Afterwards, press **Export logs**. It writes a zip to `Download/ZVE1-OpenGate/`: send that zip back.

**Self-test** and **Dry run** need no camera.

## Running it

1. In the menu, set File Format XAVC S 4K (or XAVC HS 4K) and 24p. APS-C/Super 35 off, S&Q off.
2. Pull the battery for 10 seconds, put it back, and switch on, in **stills** mode. Do not go into movie mode yet.
3. Connect USB and run `check_readonly`. Send the folder back if it does not say READY.
4. Run `open_gate_apply`. It asks for the firmware version and a typed YES. It runs five steps.
5. Between steps it asks you to **unplug and replug the USB cable. Do not switch the camera off and do not pull the battery** until it says it is finished.
6. At the end, it asks for one more session, which only reads. Switch to **movie** mode with the Still/Movie/S&Q button, unplug, then plug in again. The script runs the read-only dump itself.
7. When it says so, unplug. Record 20 to 30 seconds, stop, and play the clip back.
8. To return to stock, pull the battery for 10 seconds, or run `open_gate_putback` with the preview at 3:2.

**While it is applied:** use only XAVC HS 4K or XAVC S 4K at 24p. Other formats, frame rates, S&Q and APS-C/Super 35 are likely to fail or hang.

## Please send back

- The zipped `windows/camera_private` folder, or the phone's export zip.
- What the screen showed between the unplug and the replug of step 6, and after it.
- The clip's size and frame rate (3840 × 2560, 23.976?), and whether the picture shows the whole sensor height (compare with a photo).
- What each C2 press shows, and whether the focus frames sit on the picture.
- Whether the live view is glitchy when you go from stills to movie, and whether a short recording fixes it.
- **One check after a power-off:** switch off and on with the power switch (no battery pull), stills mode, run `check_readonly`, and include that folder. It tells us whether the power switch removes the patch on this camera.

**If the camera misbehaves** (grey lines, flicker, restart, freeze, recording that stops by itself), and it still responds: don't pull the battery yet. Switch to stills, connect USB, run `dump_info`, send the folder, and then pull the battery. If it does not respond, just pull the battery.

## If something stops

Every stop prints a reason, and says either "Nothing was sent" or what was sent. Please send that text.

- *the camera is in service mode but that device has no libusb driver yet*: this is expected on the first Windows run. Do the Zadig step for the new device and run again.
- *DeviceInfo.xml is not the file of the 2.02 update*: the camera has other firmware. Nothing further is sent.
- *VERDICT NOT READY*: something on the camera is not as the 2.02 files predict. Send the folder; the apply will not start.

## What is in here

- `windows/`: the launchers, `setup.cmd`, and `tools/` (the scripts, the pinned program files and their source, the five patch designs, and in `tools/modding/zve1` the builders and the C2 routine's source).
- `macos/`: `setup.command` and the `.command` launchers; they run `windows/tools`.
- `android/ZVE1-OpenGate.apk`: the phone app, carrying `windows/tools` as published here.
- `PORT_NOTES.md`: how the A7S III kit maps onto the ZV-E1, what is the same, what differs, and what is guessed.

Built on [Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) (vendored under `windows/tools/third_party`, MIT licence).
