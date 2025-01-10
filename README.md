# RTMP Stream Scheduler

A web-based application for scheduling and managing RTMP video streams. This application allows you to schedule pre-recorded videos to be streamed to various RTMP destinations (like Vimeo) using FFmpeg.

## Features

- Schedule video streams with a user-friendly web interface
- Support for multiple RTMP destinations
- Automatic video streaming using FFmpeg
- Stream status tracking
- Easy management of scheduled streams

## Requirements

- Python 3.7+
- FFmpeg installed on the system
- Required Python packages (see requirements.txt)

## Installation

1. Install FFmpeg if not already installed:
   ```bash
   # For macOS using Homebrew
   brew install ffmpeg
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Initialize the database:
   ```bash
   python app.py
   ```

## Usage

1. Start the application:
   ```bash
   python app.py
   ```

2. Open your web browser and navigate to `http://localhost:5000`

3. Use the web interface to:
   - Add new stream schedules
   - Monitor stream status
   - Delete scheduled streams

## Stream Configuration

When adding a new stream, you'll need to provide:
- Stream Name: A descriptive name for the stream
- Input Path: Path to the pre-recorded video file
- Output RTMP URL: The destination RTMP URL (e.g., Vimeo RTMP URL)
- Scheduled Time: When the stream should start

## Notes

- Make sure you have proper permissions for the input video files
- Verify that your RTMP destinations are correctly configured and accessible
- The application uses a SQLite database to store stream information
- Streams are scheduled using APScheduler and processed using FFmpeg
