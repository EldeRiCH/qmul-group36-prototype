"""
Run this once after placing the original qmul-crest.png in static/img/.
Uses flood-fill from image edges to remove only the background,
leaving the crown intact regardless of how similar the shades are.
"""
from PIL import Image
from collections import deque

path = 'static/img/qmul-crest.png'
img = Image.open(path).convert('RGBA')
pixels = img.load()
w, h = img.size

def is_background(r, g, b):
    # Light grey / white — same range the original background falls in
    return r > 185 and g > 185 and b > 185

# Flood fill from all four edges using a queue
visited = [[False] * h for _ in range(w)]
queue = deque()

for x in range(w):
    for y in [0, h - 1]:
        r, g, b, a = pixels[x, y]
        if not visited[x][y] and is_background(r, g, b):
            queue.append((x, y))
            visited[x][y] = True
for y in range(h):
    for x in [0, w - 1]:
        r, g, b, a = pixels[x, y]
        if not visited[x][y] and is_background(r, g, b):
            queue.append((x, y))
            visited[x][y] = True

while queue:
    cx, cy = queue.popleft()
    pixels[cx, cy] = (255, 255, 255, 0)  # transparent
    for nx, ny in [(cx-1,cy),(cx+1,cy),(cx,cy-1),(cx,cy+1)]:
        if 0 <= nx < w and 0 <= ny < h and not visited[nx][ny]:
            r, g, b, a = pixels[nx, ny]
            if is_background(r, g, b):
                visited[nx][ny] = True
                queue.append((nx, ny))

img.save(path)
print(f"Done — background removed from {w}x{h} image.")
