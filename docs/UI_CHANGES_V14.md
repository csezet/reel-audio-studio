# UI changes v14

- Added **Убрать файл** to detach selected media without deleting it from disk.
- Clearing media resets player source with a null `QUrl`, waveform, timeline, comparison state, export state and preview reference.
- Replaced the main Auto Enhance `QPushButton` with a custom-painted `AnimatedPrimaryButton`.
- Main action now animates on hover even before a media file is selected (when FFmpeg is available).
- Clicking Auto Enhance without media gives a short attention pulse and a status hint instead of silently doing nothing.
- Added hover styling and vector X icon for the remove-file action.
