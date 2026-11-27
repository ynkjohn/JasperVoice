# JasperVoice demo

The GitHub README uses **ReadmeDemo**, a 19-second Remotion composition with the actual v1.2 Windows overlay, Mic Check, and AI Polish preview. The editor scene illustrates insertion and uses text produced by the app's local Whisper pipeline from the included synthetic voice sample.

```powershell
npm ci
npm run lint
npx remotion render ReadmeDemo ../docs/media/JasperVoice-1.2-demo.mp4 --codec=h264 --crf=20
```

Source media is in `public/showcase`. To refresh the overlay and AI Polish captures, run `scripts/capture-showcase.py` from the repository root with JasperVoice installed in the Python environment and the tiny Whisper model available. Set `JASPER_SHOWCASE_ENDPOINT` to a local OpenAI-compatible `/v1` endpoint to include a real Polish preview result. The Mic Check clip is captured from the Windows app responding to a speech sample.

`PillDemo` and `AppTour` are the earlier compositions.
