"""Offline checks. Never opens a camera or sends an actual media command."""
import time
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace

import numpy as np
import app
from gate import GestureGate
from thumb_direction import resolve_gesture


def thumb_landmarks(direction='right'):
    points = [(320,350), (335,330), (335,300), (370,300), (405,300),
              (310,280), (300,255), (300,280), (310,305),
              (290,280), (280,250), (280,280), (290,305),
              (270,290), (260,260), (260,285), (270,310),
              (250,300), (240,275), (240,300), (250,320)]
    rotated=[]
    for x,y in points:
        x,y=x-320,y-300
        if direction=='left': x=-x
        elif direction=='up': x,y=y,-x
        elif direction=='down': x,y=-y,x
        elif direction=='diagonal': x,y=(x-y)*.7071,(x+y)*.7071
        rotated.append(SimpleNamespace(x=(x+320)/640,y=(y+300)/480))
    return rotated


class DirectionTests(unittest.TestCase):
    def test_right_left_and_upright_are_separate(self):
        for direction,label in [('right','Thumb_Right'),('left','Thumb_Left'),('up','Thumb_Up'),('down','Thumb_Down')]:
            with self.subTest(direction=direction):
                name,score=resolve_gesture('None',0,thumb_landmarks(direction))
                self.assertEqual(name,label)
                self.assertGreaterEqual(score,.7)

    def test_model_thumb_orientation_and_diagonal_dead_zone(self):
        self.assertEqual(resolve_gesture('Thumb_Up',.8,thumb_landmarks('left')),('Thumb_Left',.8))
        self.assertEqual(resolve_gesture('Thumb_Up',.8,thumb_landmarks('diagonal')),(None,0))

    def test_open_fingers_and_tucked_thumb_do_not_skip(self):
        hand=thumb_landmarks()
        hand[8]=SimpleNamespace(x=300/640,y=200/480)
        self.assertEqual(resolve_gesture('Open_Palm',.9,hand),('Open_Palm',.9))
        hand=thumb_landmarks()
        hand[4]=SimpleNamespace(x=330/640,y=305/480)
        self.assertEqual(resolve_gesture('Closed_Fist',.9,hand),('Closed_Fist',.9))

    def test_fist_next_previous_key_mapping(self):
        self.assertEqual(app.MAPPING['Closed_Fist'][2],0xB3)
        self.assertEqual(app.MAPPING['Thumb_Right'][2],0xB0)
        self.assertEqual(app.MAPPING['Thumb_Left'][2],0xB1)


class GateTests(unittest.TestCase):
    def test_brief_confidence_dip_pauses_hold(self):
        gate = GestureGate(threshold=.8)
        for tick in [0, .1, .2, .3]: gate.update('Open_Palm', .95, tick)
        progress = gate.progress
        self.assertIsNone(gate.update('Open_Palm', .79, .4))
        self.assertEqual(gate.progress, progress)
        self.assertIsNone(gate.update('Open_Palm', .95, .5))
        self.assertEqual(gate.progress, progress)
        events = [gate.update('Open_Palm', .95, t) for t in [.6, .7, .8, .9]]
        self.assertEqual(events.count('Open_Palm'), 1)
        gate.update('Open_Palm', .95, 1)
        self.assertEqual(gate.progress, 1)

    def test_long_confidence_loss_restarts_hold(self):
        gate = GestureGate()
        for tick in [0, .1, .2, .3]: gate.update('Open_Palm', .95, tick)
        for tick in [.4, .5, .6]: gate.update('Open_Palm', .4, tick)
        self.assertEqual(gate.progress, 0)
        self.assertIsNone(gate.update('Open_Palm', .95, .7))
        self.assertEqual(gate.progress, 0)

    def test_hold_release_and_no_repeat(self):
        gate = GestureGate()
        events = [gate.update('Open_Palm', .95, i / 10) for i in range(20)]
        self.assertEqual(events.count('Open_Palm'), 1)
        self.assertTrue(all(gate.update('Victory', .95, 2 + i / 10) is None for i in range(10)))
        for i in range(6):
            gate.update(None, 0, 3 + i / 10)
        events = [gate.update('Victory', .95, 4 + i / 10) for i in range(10)]
        self.assertEqual(events.count('Victory'), 1)

    def test_low_confidence_short_holds_and_frame_gaps(self):
        gate = GestureGate()
        self.assertTrue(all(gate.update('Open_Palm', .4, i / 10) is None for i in range(20)))
        gate.reset()
        for tick in [0, .1, .2, 1, 1.1, 1.2]:
            self.assertIsNone(gate.update('Open_Palm', .99, tick))
        self.assertIsNone(gate.update('Victory', .99, 1.3))
        self.assertEqual(gate.progress, 0)


class AppTests(unittest.TestCase):
    def setUp(self):
        self.root = app.tk.Tk()
        self.root.withdraw()
        self.ui = app.App(self.root)
        self.root.update_idletasks()
        self.frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.clock = 100.0
        self.sender = patch.object(app, 'send_media').start()

    def tearDown(self):
        for timer in self.root.tk.call('after', 'info'):
            self.root.after_cancel(timer)
        self.root.destroy()
        patch.stopall()

    def feed(self, name, score=.99, count=1):
        for _ in range(count):
            self.clock += .1
            self.ui.frames.put((self.frame, name, score, 12, self.clock))
            with patch.object(app.time, 'monotonic', return_value=self.clock):
                self.ui.poll()

    def test_all_gestures_in_test_mode(self):
        self.assertFalse(self.ui.live.get())
        for gesture in app.MAPPING:
            self.feed(gesture, count=10)
            self.feed(None, 0, count=6)
        lines = self.ui.log.get(0, 'end')
        self.assertEqual(sum('TEST  ' in line for line in lines), len(app.MAPPING))
        self.sender.assert_not_called()

    def test_directional_holds_and_fist_send_correct_commands(self):
        self.ui.live.set(True)
        for direction in ['right','left']:
            name,score=resolve_gesture('None',0,thumb_landmarks(direction))
            self.feed(name,score,count=10)
            self.feed(None,0,count=6)
        self.feed('Closed_Fist',.9,count=10)
        self.assertEqual([call.args[0] for call in self.sender.call_args_list],[0xB0,0xB1,0xB3])

    def test_low_confidence_explains_empty_bar(self):
        self.feed('Open_Palm', .65, count=10)
        self.assertIn('Confidence too low: 65%; needs 70%', self.ui.detail.get())
        self.assertEqual(float(self.ui.progress['value']), 0)
        self.sender.assert_not_called()

    def test_reported_palm_confidence_fills_bar(self):
        for score in [.72, .75, .71, .78, .74, .70, .77, .73, .79, .72]:
            self.feed('Open_Palm', score)
        self.assertEqual(float(self.ui.progress['value']), 1)
        self.assertIn('Hold complete', self.ui.detail.get())
        self.assertEqual(sum('TEST  Open palm' in line for line in self.ui.log.get(0, 'end')), 1)
        self.sender.assert_not_called()

    def test_live_enable_requires_release_and_sends_one_pair(self):
        self.ui.live.set(True)
        self.ui.mode_change()
        self.feed('Open_Palm', count=10)
        self.sender.assert_not_called()
        self.feed(None, 0, count=6)
        self.feed('Open_Palm', count=20)
        self.sender.assert_called_once_with(0xB3)

    def test_send_failure_disables_controls(self):
        self.sender.side_effect = RuntimeError('Synthetic failure')
        self.ui.live.set(True)
        self.feed('Open_Palm', count=10)
        self.assertFalse(self.ui.live.get())
        self.assertIn('FAILED', self.ui.log.get(0))

    def test_stale_frame_and_stall_never_send(self):
        self.ui.live.set(True)
        self.ui.last_frame = 95
        self.ui.frames.put((self.frame, 'Open_Palm', .99, 12, 95))
        with patch.object(app.time, 'monotonic', return_value=100):
            self.ui.poll()
        self.assertFalse(self.ui.live.get())
        self.assertTrue(self.ui.stalled)
        self.sender.assert_not_called()

    def test_stop_ignores_frames_and_invalid_camera(self):
        self.ui.live.set(True)
        self.ui.stop()
        self.feed('Open_Palm', count=10)
        self.sender.assert_not_called()
        self.ui.camera.set(99)
        self.ui.start()
        self.assertIsNone(self.ui.worker)

    def test_worker_releases_camera(self):
        cap = Mock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, self.frame)
        model = Mock()
        result = SimpleNamespace(gestures=[[SimpleNamespace(category_name='Open_Palm', score=.99)]], hand_landmarks=[])
        def recognize(*args):
            self.ui.stop_event.set()
            return result
        model.recognize_for_video.side_effect = recognize
        context = Mock()
        context.__enter__ = Mock(return_value=model)
        context.__exit__ = Mock(return_value=False)
        with patch.object(app, 'recognizer', return_value=context), patch.object(app.cv2, 'VideoCapture', return_value=cap):
            self.ui.capture(0)
        cap.release.assert_called_once()
        self.assertEqual(self.ui.frames.get_nowait()[1], 'Open_Palm')
        self.sender.assert_not_called()

    def test_camera_error_is_visible_and_released(self):
        cap = Mock()
        cap.isOpened.return_value = False
        context = Mock()
        context.__enter__ = Mock(return_value=Mock())
        context.__exit__ = Mock(return_value=False)
        with patch.object(app, 'recognizer', return_value=context), patch.object(app.cv2, 'VideoCapture', return_value=cap):
            self.ui.capture(0)
        self.ui.poll()
        self.assertIn('Camera unavailable', self.ui.status.get())
        cap.release.assert_called_once()
        self.assertFalse(self.ui.live.get())


if __name__ == '__main__':
    unittest.main(verbosity=2)
