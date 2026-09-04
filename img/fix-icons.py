from PIL import Image

# Define the exact sizes Windows looks for
icon_sizes = [(8, 8), (12, 12), (16, 16), (24, 24), (26, 26), (32, 32), (48, 48), (64, 64), (96, 96), (128, 128), (256, 256), (512, 512), (1024, 1024), (2048, 2048), (4096, 4096)]

# Convert Black Icon
try:
    img_black = Image.open("img/icon_black.ico") # Your original high-res image
    img_black.save("img/icon_black.ico", format="ICO", sizes=icon_sizes)
    print("Multi-res icon_black.ico created successfully!")
except Exception as e:
    print(f"Error with black icon: {e}")

# Convert White Icon
try:
    img_white = Image.open("img/icon_white.ico") # Your original high-res image
    img_white.save("img/icon_white.ico", format="ICO", sizes=icon_sizes)
    print("Multi-res icon_white.ico created successfully!")
except Exception as e:
    print(f"Error with white icon: {e}")

try:
    img_white = Image.open("img/iconApp.ico") # Your original high-res image
    img_white.save("img/iconApp.ico", format="ICO", sizes=icon_sizes)
    print("Multi-res icon_white.ico created successfully!")
except Exception as e:
    print(f"Error with white icon: {e}")