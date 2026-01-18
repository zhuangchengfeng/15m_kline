import winsound
import threading


class PlaySound():
    def __init__(self):
        pass

    def play_sound_for_SHORT(self):
        winsound.Beep(3300, 666)  # A的声音

    def play_sound_for_LONG(self):
        winsound.Beep(200, 666)   # B的声音
        winsound.Beep(200, 666)   # B的声音

if __name__ == '__main__':

    s = PlaySound()
    for i in range(10):
        s.play_sound_for_SHORT()
        s.play_sound_for_LONG()