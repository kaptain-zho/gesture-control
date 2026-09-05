import ctypes
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path

import cv2
import mediapipe as mp
from PIL import Image, ImageTk
from gate import GestureGate
from thumb_direction import resolve_gesture

ROOT = Path(__file__).resolve().parent
MAPPING = {
    'Open_Palm': ('Open palm', 'Play / pause', 0xB3),
    'Closed_Fist': ('Fist', 'Play / pause', 0xB3),
    'Thumb_Right': ('Thumb right', 'Next track', 0xB0),
    'Thumb_Left': ('Thumb left', 'Previous track', 0xB1),
    'Victory': ('Two fingers', 'Next track', 0xB0),
    'Thumb_Up': ('Thumbs up', 'Volume up', 0xAF),
    'Thumb_Down': ('Thumbs down', 'Volume down', 0xAE),
}
EDGES = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
         (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),
         (13,17),(0,17),(17,18),(18,19),(19,20)]

def send_media(key):
    # Fixed media keys only; the app accepts no arbitrary shell commands.
    if key not in {item[2] for item in MAPPING.values()}:
        raise ValueError('Unsupported media key')
    from ctypes import wintypes
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [('wVk',wintypes.WORD),('wScan',wintypes.WORD),
                    ('dwFlags',wintypes.DWORD),('time',wintypes.DWORD),
                    ('dwExtraInfo',ctypes.c_size_t)]
    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [('dx',wintypes.LONG),('dy',wintypes.LONG),
                    ('mouseData',wintypes.DWORD),('dwFlags',wintypes.DWORD),
                    ('time',wintypes.DWORD),('dwExtraInfo',ctypes.c_size_t)]
    class UNION(ctypes.Union):
        _fields_ = [('ki',KEYBDINPUT),('mi',MOUSEINPUT)]
    class INPUT(ctypes.Structure):
        _anonymous_ = ('u',)
        _fields_ = [('type',wintypes.DWORD),('u',UNION)]
    inputs = (INPUT * 2)()
    inputs[0].type = inputs[1].type = 1
    inputs[0].ki.wVk = inputs[1].ki.wVk = key
    inputs[1].ki.dwFlags = 2
    fn = ctypes.windll.user32.SendInput
    fn.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    fn.restype = wintypes.UINT
    if fn(2, inputs, ctypes.sizeof(INPUT)) != 2:
        raise RuntimeError('Windows could not send the media key. Try running the media app without administrator privileges.')

def recognizer():
    options = mp.tasks.vision.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(ROOT / 'gesture_recognizer.task')),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=1, min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.6, min_tracking_confidence=0.6)
    return mp.tasks.vision.GestureRecognizer.create_from_options(options)

class App:
    def __init__(self, root):
        self.root = root
        root.title('Gesture Control')
        root.geometry('1040x750')
        root.minsize(920,700)
        root.configure(bg='#101722')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI',11), background='#101722', foreground='#e9eef7')
        style.configure('TButton', padding=9, background='#26374c', foreground='white')
        style.map('TButton', background=[('active','#38506b')])
        style.configure('TCheckbutton', background='#101722', foreground='#e9eef7')
        style.map('TCheckbutton', background=[('active','#101722')])
        style.configure('Horizontal.TProgressbar', background='#72ddc3', troughcolor='#26374c')
        self.stop_event = threading.Event()
        self.frames = queue.Queue(maxsize=1)
        self.messages = queue.Queue()
        self.worker = None
        self.last_frame = None
        self.stalled = False
        self.gate = GestureGate()
        self.live = tk.BooleanVar(value=False)
        self.camera = tk.IntVar(value=0)
        self.hold = tk.DoubleVar(value=0.6)
        self.threshold = tk.DoubleVar(value=0.7)
        self.status = tk.StringVar(value='Camera off · Test mode')
        self.detected = tk.StringVar(value='Ready when you are')
        self.detail = tk.StringVar(value='Start the camera, then hold one gesture.')
        self.metrics = tk.StringVar(value='No camera frames saved or uploaded')
        outer = ttk.Frame(root, padding=22)
        outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='Gesture Control',font=('Segoe UI',25,'bold')).pack(anchor='w')
        ttk.Label(outer,text='Your hand. Your media. On this PC.',foreground='#9aacbf').pack(anchor='w',pady=(2,16))
        bar = ttk.Frame(outer)
        bar.pack(fill='x',pady=(0,14))
        self.start_btn=ttk.Button(bar,text='Start camera',command=self.start)
        self.start_btn.pack(side='left')
        ttk.Button(bar,text='Stop camera',command=self.stop).pack(side='left',padx=8)
        ttk.Label(bar,text='Camera').pack(side='left',padx=(12,5))
        self.camera_picker=ttk.Spinbox(bar,from_=0,to=5,width=3,textvariable=self.camera)
        self.camera_picker.pack(side='left')
        ttk.Checkbutton(bar,text='Enable real media controls',variable=self.live,command=self.mode_change).pack(side='right')
        body=ttk.Frame(outer)
        body.pack(fill='both',expand=True)
        left=ttk.Frame(body)
        left.pack(side='left',fill='both',expand=True)
        preview_frame=tk.Frame(left,width=640,height=480,bg='#192433')
        preview_frame.pack(fill='both',expand=True)
        preview_frame.pack_propagate(False)
        self.preview=tk.Label(preview_frame,text='CAMERA OFF\n\nClick Start camera to begin',bg='#192433',fg='#9aacbf',font=('Segoe UI',15))
        self.preview.pack(fill='both',expand=True)
        ttk.Label(left,textvariable=self.status,foreground='#72ddc3').pack(anchor='w',pady=(9,4))
        ttk.Label(left,textvariable=self.metrics,foreground='#9aacbf',font=('Segoe UI',9)).pack(anchor='w')
        right=ttk.Frame(body,padding=(22,0,0,0),width=300)
        right.pack(side='right',fill='y')
        ttk.Label(right,text='DETECTED',foreground='#9aacbf').pack(anchor='w')
        ttk.Label(right,textvariable=self.detected,font=('Segoe UI',19,'bold'),wraplength=265).pack(anchor='w',pady=(5,7))
        self.progress=ttk.Progressbar(right,maximum=1,length=260)
        self.progress.pack(fill='x')
        ttk.Label(right,textvariable=self.detail,wraplength=265).pack(anchor='w',pady=9)
        ttk.Label(right,text='GESTURES',foreground='#9aacbf').pack(anchor='w',pady=(12,6))
        for label,action,_ in MAPPING.values():
            ttk.Label(right,text=f'{label}  →  {action}').pack(anchor='w',pady=2)
        ttk.Label(right,text='Hold time (seconds)').pack(anchor='w',pady=(18,0))
        ttk.Spinbox(right,from_=0.3,to=2.0,increment=0.1,textvariable=self.hold,width=8).pack(anchor='w',pady=5)
        ttk.Label(right,text='Confidence threshold (0–1)').pack(anchor='w',pady=(8,0))
        ttk.Spinbox(right,from_=0.5,to=0.99,increment=0.05,textvariable=self.threshold,width=8).pack(anchor='w',pady=5)
        ttk.Label(right,text='Left/right = your direction in the mirror.\nLower your hand between commands.\nEscape stops the camera.',wraplength=265,foreground='#9aacbf').pack(anchor='w',pady=12)
        ttk.Label(outer,text='RECENT COMMANDS',foreground='#9aacbf').pack(anchor='w',pady=(16,5))
        self.log=tk.Listbox(outer,height=4,bg='#192433',fg='#e9eef7',borderwidth=0,highlightthickness=0,font=('Segoe UI',10))
        self.log.pack(fill='x')
        self.log.insert(0,'Test mode: gestures appear here without changing your media.')
        root.bind('<Escape>',lambda event:self.stop())
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(40,self.poll)

    def mode_change(self):
        self.gate.reset()
        self.gate.latched=True
        self.detail.set('Lower your hand, then show a gesture.')
        self.status.set('Real controls enabled' if self.live.get() else 'Test mode · No media commands sent')

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            camera=int(self.camera.get())
            if not 0 <= camera <= 5:
                raise ValueError('Camera index out of range')
        except (ValueError,tk.TclError):
            self.status.set('Choose a camera number from 0 to 5.')
            return
        self.stop_event.clear()
        for channel in (self.frames, self.messages):
            while not channel.empty():
                try: channel.get_nowait()
                except queue.Empty: break
        self.last_frame = None
        self.stalled = False
        self.gate.reset()
        self.live.set(False)
        self.start_btn.configure(state='disabled')
        self.camera_picker.configure(state='disabled')
        self.status.set('Opening camera · Test mode')
        self.worker=threading.Thread(target=self.capture,args=(camera,),daemon=True)
        self.worker.start()

    def capture(self,index):
        cap=None
        try:
            with recognizer() as model:
                if self.stop_event.is_set(): return
                cap=cv2.VideoCapture(index,cv2.CAP_DSHOW)
                if not cap.isOpened():
                    raise RuntimeError('Camera unavailable. Close other camera apps or try another camera number. Check Windows camera privacy settings.')
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
                failures=0
                while not self.stop_event.is_set():
                    began=time.monotonic()
                    ok,frame=cap.read()
                    if not ok:
                        failures+=1
                        if failures>=8: raise RuntimeError('Camera stopped returning frames. Stop and restart the camera.')
                        self.stop_event.wait(0.1)
                        continue
                    failures=0
                    frame=cv2.flip(cv2.resize(frame,(640,480)),1)
                    rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                    image=mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb)
                    t0=time.monotonic()
                    result=model.recognize_for_video(image,int(t0*1000))
                    latency=(time.monotonic()-t0)*1000
                    name,score=None,0.0
                    if result.gestures and result.gestures[0]:
                        category=result.gestures[0][0]
                        name,score=category.category_name,category.score
                    hand=result.hand_landmarks[0] if result.hand_landmarks else []
                    name,score=resolve_gesture(name,score,hand)
                    for hand in result.hand_landmarks:
                        points=[(int(p.x*640),int(p.y*480)) for p in hand]
                        for a,b in EDGES: cv2.line(rgb,points[a],points[b],(114,221,195),2)
                        for p in points: cv2.circle(rgb,p,4,(245,245,245),-1)
                    packet=(rgb,name,score,latency,t0)
                    try: self.frames.get_nowait()
                    except queue.Empty: pass
                    self.frames.put_nowait(packet)
                    self.stop_event.wait(max(0,1/15-(time.monotonic()-began)))
        except Exception as exc:
            self.messages.put(str(exc))
        finally:
            if cap is not None: cap.release()

    def stop(self):
        self.stop_event.set()
        self.live.set(False)
        self.gate.reset()
        self.detected.set('Camera off')
        self.detail.set('No commands active.')
        self.status.set('Stopping camera…' if self.worker and self.worker.is_alive() else 'Camera off · Test mode')
        self.preview.configure(image='',text='CAMERA OFF\n\nClick Start camera to begin')
        self.preview.image=None
        self.metrics.set('No camera frames saved or uploaded')
        self.progress['value']=0

    def poll(self):
        try:
            error=self.messages.get_nowait()
            self.stop()
            self.status.set(error)
            self.log.insert(0,error)
        except queue.Empty: pass
        if not self.worker or not self.worker.is_alive():
            self.start_btn.configure(state='normal')
            self.camera_picker.configure(state='normal')
            if self.status.get()=='Stopping camera…': self.status.set('Camera off · Test mode')
        if (self.last_frame is not None and not self.stop_event.is_set()
                and time.monotonic()-self.last_frame>1 and not self.stalled):
            self.live.set(False)
            self.gate.reset()
            self.stalled=True
            self.status.set('Camera feed paused · Returned to test mode')
            self.detected.set('Waiting for camera')
            self.progress['value']=0
        try:
            rgb,name,score,latency,stamp=self.frames.get_nowait()
            if not self.stop_event.is_set() and time.monotonic()-stamp<0.3:
                self.last_frame=stamp
                self.stalled=False
                preview=Image.fromarray(rgb)
                preview.thumbnail((max(1,self.preview.winfo_width()),max(1,self.preview.winfo_height())))
                photo=ImageTk.PhotoImage(preview)
                self.preview.configure(image=photo,text='')
                self.preview.image=photo
                try:
                    self.gate.hold=max(0.3,min(2.0,self.hold.get()))
                    self.gate.threshold=max(0.5,min(0.99,self.threshold.get()))
                except (ValueError,tk.TclError): pass
                gesture=name if name in MAPPING else None
                self.detected.set(MAPPING[name][0] if gesture else 'No command gesture')
                self.metrics.set(f'Gesture score: {score:.0%} / required {self.gate.threshold:.0%}  ·  Recognition: {latency:.0f} ms')
                event=self.gate.update(gesture,score,stamp)
                self.progress['value']=self.gate.progress
                if self.gate.latched:
                    self.detail.set('Hold complete. Lower your hand to reset.' if self.gate.progress >= 1 else 'Lower your hand first to enable a new command.')
                elif gesture and score < self.gate.threshold:
                    self.detail.set(f'Confidence too low: {score:.0%}; needs {self.gate.threshold:.0%}. Keep your whole hand visible, improve lighting, or lower the confidence threshold.')
                elif gesture:
                    self.detail.set(f'Keep holding · {self.gate.progress:.0%} complete')
                else:
                    self.detail.set('Show a gesture and hold it steady.')
                self.status.set('Camera on · Real media controls' if self.live.get() else 'Camera on · Test mode')
                if event:
                    label,action,key=MAPPING[event]
                    prefix='TEST'
                    if self.live.get():
                        try:
                            send_media(key)
                            prefix='SENT'
                        except Exception as exc:
                            self.live.set(False)
                            prefix='FAILED'
                            action=str(exc)
                    self.log.insert(0,f'{time.strftime("%H:%M:%S")}  {prefix}  {label} → {action}')
                    if self.log.size()>50: self.log.delete(50,tk.END)
        except queue.Empty: pass
        self.root.after(40,self.poll)

    def close(self):
        self.stop_event.set()
        self.root.destroy()

if __name__=='__main__':
    root=tk.Tk()
    App(root)
    root.mainloop()
