from pynput import keyboard  # For key press detection
import subprocess
import time
import os
import base64
import logging
import threading
import json
from picamera2 import Picamera2
from audiobooker.scrappers.librivox import Librivox
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()  # Take environment variables from .env.

# Initialize the camera
picam2 = Picamera2()
config = picam2.create_still_configuration({"size": (1920, 1080)})
picam2.configure(config)
picam2.start()
success = picam2.autofocus_cycle()

client = OpenAI()

# Define the path for storing playback progress
PROGRESS_FILE = "playback_progress.json"

# Load previous playback progress from the file (if it exists)
playback_data = {}
if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, "r") as f:
        playback_data = json.load(f)

def getBookName():
    picam2.capture_file("book.png")
    
    # Use OpenAI API to analyze the image and get the book's name
    with open("book.png", "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is the name of the book in this picture - Please respond in the form Book title ~ author"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                            }
                        },
                    ],
                }
            ],
        )
        finalResponse = response.choices[0].message.content
        print(finalResponse)
        return finalResponse

    except Exception as e:
        logging.exception("Something broke at OPENAI")
        return None

def findBook(bookName):
    book_title = bookName.split("~")[0].strip()
    print(f"Searching for: {book_title}")

    books_folder = "books"
    
    local_file_path = None
    for file_name in os.listdir(books_folder):
        if book_title in file_name and file_name.endswith(".mp3"):
            local_file_path = os.path.join(books_folder, file_name)
            break

    if local_file_path:
        print(f"Playing local file for {book_title} found as '{file_name}'.")
        play_audio_with_progress_tracking(local_file_path, book_title)
        return
    
    try:
        book = Librivox.search_audiobooks(title=book_title)[0]
        print(f"Playing {book_title} from Librivox.")
        book.play()
    except Exception as e:
        print(f"Error finding or playing book '{book_title}': {e}")

def play_audio_with_progress_tracking(audio_file, book_title):
    # Retrieve the start time from playback_data, default to 0 if not found
    start_time = playback_data.get(book_title, 0)
    
    # Use ffplay to play the audio from the start time
    command = ["ffplay", "-nodisp", "-autoexit", "-ss", str(start_time), audio_file]
    process = subprocess.Popen(command)
    
    # Track the progress in a separate thread
    def track_progress():
        elapsed_time = start_time
        while process.poll() is None:  # While the audio is playing
            elapsed_time += 1
            playback_data[book_title] = elapsed_time  # Save the progress
            save_progress()  # Save the progress to file every second
            time.sleep(1)  # Update progress every second

    # Start a background thread to track the playback progress
    progress_thread = threading.Thread(target=track_progress)
    progress_thread.daemon = True  # Allow thread to exit when main program exits
    progress_thread.start()

def save_progress():
    """Save the current playback progress to the file."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(playback_data, f)
    print("Playback progress saved.")

def main():
    book_name = getBookName()
    if book_name:
        findBook(book_name)

# Set up a listener for key press events using pynput
def on_press(key):
    try:
        if key.char == 'b':
            print("Starting process...")  # Print confirmation that 'b' was pressed
            main()  # Trigger the main function when 'b' is pressed
    except AttributeError:
        pass  # Ignore special keys

def on_release(key):
    if key == keyboard.Key.esc:
        save_progress()  # Save playback progress when 'esc' is pressed
        return False  # Stop listener

print("Press 'b' to capture an image and process the book name. Press 'esc' to exit.")

# Start the listener
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()

