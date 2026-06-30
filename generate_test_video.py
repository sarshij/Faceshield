import cv2
import numpy as np

# Create a 2-second video at 30 fps
fps = 30
duration = 2
frames = fps * duration

fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter('test_video.mp4', fourcc, fps, (640, 480))

for i in range(frames):
    # Create a simple frame with a moving circle
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Moving circle
    x = int(320 + 200 * np.sin(i / 10.0))
    y = int(240 + 100 * np.cos(i / 10.0))
    
    cv2.circle(frame, (x, y), 50, (255, 255, 255), -1)
    
    out.write(frame)

out.release()
print("Generated test_video.mp4")
