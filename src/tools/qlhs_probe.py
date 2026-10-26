"""Probes a headset's lhsyncd from the PC, without SteamVR: UDP discovery, then a short TCP session (the hello, the
camera calibration, and the frames lhsight sends). What the driver would see, for bringing up a headset's module.

  python qlhs_probe.py [headset ip or broadcast] [seconds]

  python qlhs_probe.py 192.168.1.50 8
  python qlhs_probe.py                  # broadcast discovery, 8 s

A headset answers discovery as "QLHS 1 <serial> <tcp port> <model> <idle|capturing>"; on a Quest 2 (hollywood) the
module should report model Quest_2, a calibration with CameraCalibration in it, and then lhsight's lines:
  I lhsyncd: lhsight started in vendor.oculus.hardware.sensors@1.0-service (pid N); tracking cameras (id:width:height:scan) ...
  I cameras 0:10 1:10 2:10 3:10        one ring of ten buffers per camera
  F ... / T ...                        frames (nblobs -1: a long frame, only its mean) and per-second heartbeats
"No camera buffers found; dmabuf sizes here: ..." means lhsight attached but the HAL's rings aren't the sizes the
calibration asks for: the sizes it found are what to compare with /proc/<HAL pid>/maps.
"""
import socket
import sys
import time

host = sys.argv[1] if len(sys.argv) > 1 else "255.255.255.255"
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0

u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
u.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
u.settimeout(2.0)
u.sendto(b"QLHS?", (host, 47281))
try:
    data, addr = u.recvfrom(2048)
except socket.timeout:
    sys.exit(f"no answer on UDP 47281 from {host}: is the module installed and lhsyncd running?")
print(f"discovery {addr[0]}: {data.decode(errors='replace')}")

s = socket.create_connection((addr[0], 47280), timeout=5)
s.settimeout(1.0)
buf, frames, beats, others, pinged = b"", 0, 0, 0, 0
end = time.time() + secs
while time.time() < end:
    try:
        chunk = s.recv(65536)
        if not chunk:
            print("the headset closed the connection")
            break
        buf += chunk
    except socket.timeout:
        pass
    if not pinged and time.time() > end - secs / 2:  # one clock round trip mid-session
        pinged = time.time_ns()
        s.sendall(f"P 1 {pinged}\n".encode())
    while b"\n" in buf:
        line, buf = buf.split(b"\n", 1)
        text = line.decode(errors="replace")
        if text.startswith("F "):
            frames += 1
            if frames <= 4:
                print("frame:", text[:96])
            continue
        if text.startswith("T "):
            beats += 1
        elif text.startswith("C "):  # the calibration: "C <len> <name>", then that many bytes
            n = int(text.split()[1])
            while len(buf) < n:
                buf += s.recv(65536)
            cal, buf = buf[:n], buf[n:]
            print(f"calibration {text[2:]} ({len(cal)} bytes, CameraCalibration: {b'CameraCalibration' in cal})")
            continue
        else:
            others += 1
        print("line:", text[:220])

print(f"\n{frames} frames, {beats} heartbeats, {others} other lines in {secs:.0f} s")
s.close()
