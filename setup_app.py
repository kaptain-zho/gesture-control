"""Install the app's isolated environment and official recognition model."""
import hashlib
from pathlib import Path
import subprocess
import sys
import urllib.request
import venv

ROOT = Path(__file__).resolve().parent
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task'
MODEL_SHA256 = '97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482'


def ensure_model():
    model = ROOT / 'gesture_recognizer.task'
    if model.exists() and hashlib.sha256(model.read_bytes()).hexdigest() == MODEL_SHA256:
        return
    print('Downloading the official MediaPipe gesture model...')
    with urllib.request.urlopen(MODEL_URL, timeout=60) as response:
        data = response.read(20 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
        raise RuntimeError('Model download did not match the expected checksum. Please run setup again.')
    temporary = model.with_suffix('.download')
    temporary.write_bytes(data)
    temporary.replace(model)


def main():
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12):
        raise RuntimeError('Setup requires Windows and Python 3.12 (64-bit).')
    environment = ROOT / '.venv'
    if not (environment / 'Scripts' / 'python.exe').exists():
        print('Creating the app environment...')
        venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / 'Scripts' / 'python.exe'
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')], check=True)
    ensure_model()
    print('Ready. Double-click Start Gesture Control.cmd.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Setup failed: {error}', file=sys.stderr)
        sys.exit(1)
