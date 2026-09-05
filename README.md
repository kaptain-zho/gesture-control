# Gesture Control

A local Windows webcam app that turns hand gestures into media controls. Includes a mirrored preview, adjustable hold time and confidence threshold, and a test mode.

## Setup

1. Install 64-bit Python 3.12 on Windows.
2. Download or clone this repository and extract it to a folder.
3. Double-click **Setup Gesture Control.cmd**. Setup installs dependencies into `.venv` and downloads the official MediaPipe model, verifying its SHA-256 checksum.
4. Double-click **Start Gesture Control.cmd**, then click **Start camera**.

An internet connection is needed for setup. Gesture recognition runs locally afterward. A webcam is required.

## Controls

| Gesture | Command |
|---|---|
| Fist | Play / pause |
| Sideways thumb pointing to your right | Next track |
| Sideways thumb pointing to your left | Previous track |
| Open palm | Play / pause |
| Two fingers (V) | Next track |
| Upright thumbs up | Volume up one step |
| Thumbs down | Volume down one step |

For track changes, make a thumbs-up shape and rotate it until your thumb points sideways. Right and left follow your perspective in the mirrored preview, with either hand. Keep your other fingers curled. Diagonal thumb directions are ignored while you turn your hand.

Start in test mode and check the command log. Hold a gesture for 0.6 seconds of confident recognition. The default confidence threshold is 70%. A confidence dip up to 0.15 seconds pauses progress; longer dips restart the hold. The bar stays full after a command. Lower your hand for about 0.4 seconds between commands.

Check **Enable real media controls** when recognition is consistent. Lower your hand once after enabling it before making your first command. Press **Escape** while the app has focus to stop the camera. Closing the window exits the app.

## Behavior and privacy

- Camera images stay in memory on your PC. The app does not record or upload them.
- Restarting the camera always starts in test mode. A feed stall longer than one second disables real controls.
- The app does not start with Windows.
- Media commands go to Windows. Your player must support media keys; previous track may restart the current song first. The app reports sending a key, not proof that a player acted on it.
- The displayed gesture score is a model confidence or thumb-shape geometry score, not measured accuracy. Lighting, camera angle and hand visibility affect results. Sideways thumb recognition may need tuning for your hand.

If the camera cannot open, close other camera apps, check Windows camera permissions, or try another camera number. Keep your whole hand visible and use good lighting.

## Tests

After setup, run:

```powershell
.\.venv\Scripts\python.exe test_app.py
```

18 automated tests cover gesture mappings, thumb directions, hold/release timing, confidence dips, stale frames, camera cleanup and command failures. Tests use synthetic frames and landmarks, and replace media delivery with a test substitute. They do not open your camera or send media commands. Live recognition accuracy requires testing with a real hand.

## Model

Uses Google's [MediaPipe Gesture Recognizer](https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer). The model and Python environment are downloaded during setup and excluded from version control. Third-party dependencies and model assets retain their respective licenses and terms.
